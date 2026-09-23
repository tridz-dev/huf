"""Authoritative automatic model candidate resolution."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RouteableModel:
	"""A model already admitted by Agent configuration and availability checks."""

	model: str
	provider: str | None = None
	canonical_model: str | None = None
	canonical_version: str | None = None
	routing_description: str | None = None


def get_routeable_models(
	agent_doc: Any,
	user: str | None = None,
	run_context: Any | None = None,
	*,
	availability: Callable[[Any, str | None, Any | None], Iterable[Any]] | None = None,
) -> tuple[RouteableModel, ...]:
	"""Return only authoritative automatic candidates for an Agent run.

	The function reads the Agent's explicit allowed-model table and optionally applies
	a deployment/availability resolver. It deliberately has no manual override argument;
	manual caller selection must remain a separate path.
	"""
	allowed = list(getattr(agent_doc, "allowed_models", None) or ())
	if availability is not None:
		allowed = list(availability(agent_doc, user, run_context))
	elif not allowed:
		current_model = getattr(agent_doc, "model", None)
		if current_model:
			allowed = [agent_doc]
	result = []
	seen = set()
	for item in allowed:
		model = getattr(item, "model", None) or getattr(item, "name", None) or getattr(item, "model_name", None)
		if not isinstance(model, str) or not model.strip() or model in seen:
			continue
		seen.add(model)
		result.append(
			RouteableModel(
				model=model,
				provider=getattr(item, "provider", None),
				canonical_model=getattr(item, "canonical_model", None),
				canonical_version=getattr(item, "canonical_version", None),
				routing_description=getattr(item, "routing_description", None),
			)
		)
	return tuple(result)


def get_agent_model_candidates(agent_doc: Any) -> tuple[RouteableModel, ...]:
	"""Frappe-facing wrapper: candidates = the Agent's default model plus its enabled
	``Agent Allowed Model`` rows (T5.01: ``enable_auto_routing``), minus any Decision-only
	AI Model (IP §12.5/agent_integration.py's own guard is defense in depth, not the only
	filter -- a Decision-only model must never even be offered as a routing candidate).

	This is the single source of truth ``huf.ai.agent_integration._resolve_effective_model``
	uses when no caller/automation override was given (IP §12.2); it is deliberately the only
	caller of :func:`get_routeable_models` for agent runs, via that function's own
	``availability`` extension point, so the "candidates come only from get_routeable_models"
	acceptance clause stays true even though this function does the Frappe-specific (modality,
	auto-routing flag) filtering that :func:`get_routeable_models` itself is deliberately kept
	agnostic of (it is unit-tested against plain ``SimpleNamespace`` objects with no Frappe
	dependency).
	"""

	def _availability(agent: Any, _user: str | None, _run_context: Any | None) -> list[Any]:
		from types import SimpleNamespace

		from huf.huf.doctype.ai_model.ai_model import is_decision_only_model

		items: list[Any] = []
		seen_models: set[str] = set()

		default_model = getattr(agent, "model", None)
		if isinstance(default_model, str) and default_model.strip() and not is_decision_only_model(default_model):
			items.append(SimpleNamespace(model=default_model, provider=getattr(agent, "provider", None)))
			seen_models.add(default_model)

		for row in getattr(agent, "allowed_models", None) or ():
			model = getattr(row, "model", None)
			if not isinstance(model, str) or not model.strip() or model in seen_models:
				continue
			if not getattr(row, "enable_auto_routing", 0):
				continue
			if is_decision_only_model(model):
				continue
			seen_models.add(model)
			items.append(row)

		return items

	return get_routeable_models(agent_doc, availability=_availability)


def route_agent_model(
	agent_doc: Any,
	*,
	user: str | None = None,
	conversation: str | None = None,
	agent_run: str | None = None,
	request_text: str | None = None,
	run_context: Any | None = None,
) -> tuple[RouteableModel | None, str | None]:
	"""Run the Model Routing decision surface for ``agent_doc``, or fall back to ``(None, None)``.

	Called from ``agent_integration._resolve_effective_model`` only when the caller passed no
	model/provider override (D14, IP §12.1). Zero extra DB/work when there is no enabled Model
	Routing binding: ``resolve_agent_decision_binding`` is an in-memory scan over the Agent's own
	``decision_bindings`` rows (no DB call, no settings read) and is checked *before* any
	candidate is built, so an agent with no binding pays nothing beyond that scan.

	Advise is never offered for Model Routing (D18): ``resolve_agent_decision_binding`` already
	downgrades an "Advise" binding on this surface to Off (``binding.ADVISE_SURFACES`` excludes
	"Model Routing"), so only Off/Shadow/Enforce ever reach ``decide_for_surface`` here.

	Returns ``(None, None)`` on Off, Shadow (enqueued -- caller proceeds on the default, D6), any
	error/timeout/budget-exhaustion, or an Enforce result that selected nothing from the
	candidate set; otherwise ``(selected_model, decision_call_docname_or_None)``.
	"""
	from huf.ai.decision.agent_surfaces import decide_for_surface
	from huf.ai.decision.binding import resolve_agent_decision_binding
	from huf.ai.decision.types import CandidateSource, DecisionOrigin, Option

	if resolve_agent_decision_binding(agent_doc, "Model Routing") is None:
		return None, None

	candidates = get_agent_model_candidates(agent_doc)
	if not candidates:
		return None, None

	options = tuple(
		Option(item.model, item.routing_description or item.canonical_model or item.model) for item in candidates
	)
	origin = DecisionOrigin(
		origin_type="Agent Run",
		agent=getattr(agent_doc, "name", None),
		agent_run=agent_run,
		conversation=conversation,
		owner_user=user,
	)
	state = {"request": (request_text or "")[:2000]}

	decision = decide_for_surface(
		agent_doc,
		"Model Routing",
		options,
		state,
		origin,
		candidate_source=CandidateSource.ROUTEABLE_MODELS,
		candidate_resolver_id="get_routeable_models",
		top_n=1,
	)
	if decision is None or not decision.selected_ids:
		return None, None

	selected_id = decision.selected_ids[0]
	selected = next((item for item in candidates if item.model == selected_id), None)
	if selected is None:
		return None, None
	return selected, decision.decision_call


def select_routeable_model(runtime, request, backend, models: Iterable[RouteableModel]):
	"""Run a bounded model-selection policy over authoritative candidates."""
	from dataclasses import replace
	from huf.ai.decision.types import CandidateSource, DecisionStatus, Option, QuestionKind

	candidates = tuple(models)
	if not candidates:
		return None, runtime.evaluate(request, backend)
	request = replace(request, candidates=tuple(Option(item.model, item.model) for item in candidates), candidate_source=CandidateSource.ROUTEABLE_MODELS, candidate_resolver_id="get_routeable_models")
	response = runtime.evaluate(request, backend)
	if response.status != DecisionStatus.SUCCESS:
		return None, response
	answer = next((item for item in response.answers.values() if item.kind == QuestionKind.SELECT), None)
	selected = answer.value if answer and isinstance(answer.value, str) else None
	return next((item for item in candidates if item.model == selected), None), response
