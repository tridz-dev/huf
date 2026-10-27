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
		result.append(RouteableModel(model=model, provider=getattr(item, "provider", None), canonical_model=getattr(item, "canonical_model", None), canonical_version=getattr(item, "canonical_version", None)))
	return tuple(result)


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
