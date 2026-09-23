"""Fail-closed context relevance and compaction helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import frappe


def retain_relevant_context(
	items: Iterable[Any],
	selected_ids: Iterable[str] | None,
	*,
	required_ids: Iterable[str] = (),
	decision_succeeded: bool = False,
) -> tuple[Any, ...]:
	"""Narrow optional context while always retaining required items.

	Uncertain or failed semantic decisions retain the complete authorized input, so
	context compaction cannot silently discard mandatory context.
	"""
	items = tuple(items)
	required = set(required_ids)
	if not decision_succeeded or selected_ids is None:
		return items
	selected = required | set(selected_ids)
	return tuple(item for item in items if _identifier(item) in selected)


def _identifier(item: Any) -> str | None:
	return getattr(item, "id", None) or getattr(item, "name", None)


# --------------------------------------------------------------------------------------------
# T8.04 -- Context Relevance decision surface (PLAN.md §3.6 "Context Relevance" row, D6, D9,
# D14, D18, I-DR1).
#
# ``compact_context`` is the Context Relevance analogue of ``huf.ai.decision.agent_surfaces
# .decide_for_surface`` (SURFACE_API.md), built directly on ``huf.ai.decision.service.run_policy``
# instead: that helper's Enforce semantics ("selected_ids = subset to KEEP") are the wrong shape
# here -- this surface must default to keeping everything and only ever remove entries the policy
# is *confidently* sure are irrelevant, never the reverse. ``huf.ai.conversation_manager
# .get_tool_exchange_candidates`` builds the raw exchange list this module reads; that function
# never decides eligibility, only describes what each completed/failed/pending exchange is.
#
# Hard constraints (I-DR1: the decision can never be handed something it might wrongly drop),
# enforced by ``_is_eligible`` *before* any candidate is ever built or any decision call is made:
#   - only a tool exchange whose backing ``Agent Tool Call.status == "Completed"`` is eligible
#     (unresolved/unknown status -- a message with no linked Agent Tool Call -- is never eligible
#     either, since "unknown" is not "Completed");
#   - an exchange with an error (``Agent Tool Call.error_message`` or ``status == "Failed"``) is
#     never eligible;
#   - an exchange tied to a pending/required approval is never eligible;
#   - an exchange inside the "recent" window (the last few tool exchanges -- see
#     ``get_tool_exchange_candidates``'s ``_RECENT_TOOL_EXCHANGES``) is never eligible;
#   - an exchange sharing its assistant turn with another tool call (``shared_turn``) is never
#     eligible -- dropping only one of several tool calls declared in the same assistant message
#     would corrupt the OpenAI-format tool_call/tool-result pairing invariant
#     ``conversation_manager.safe_history_slice``/``safe_history_split`` otherwise protect.
#
# Everything that fails any of the above is "protected": always retained, regardless of what a
# decision backend says (and it is never even shown to one). Only the remaining "eligible" set is
# ever offered to ``run_policy`` as candidates.
#
# Modes: Off / no binding -- ``resolve_agent_decision_binding`` returns ``None``, retain
# everything. Shadow (D6) -- runs and is logged for measurement only; never compacts (D14: "Shadow
# ... never show or apply it"). Advise is not offered for this surface (D18; already enforced by
# ``resolve_agent_decision_binding`` downgrading an Advise binding here to Off) -- defended again
# below regardless. Enforce -- drops only the ids the policy confidently marks irrelevant, gated
# both by the policy's own ``minimum_confidence`` (via ``DecisionResponse.gate_result``) and a
# local minimum floor (``_MIN_DROP_CONFIDENCE``) so a policy with no configured threshold still
# cannot silently drop history on a weak signal. Any error, timeout, budget-exceeded, or otherwise
# non-``SUCCESS`` result retains everything unchanged -- the same safe default as Off.
# --------------------------------------------------------------------------------------------

_SURFACE = "Context Relevance"

#: Per-candidate irrelevance score floor below which a candidate is never dropped, even when the
#: policy's own ``minimum_confidence`` gate (``DecisionResponse.gate_result``) accepts the call as
#: a whole (that gate is evaluated over the answer's own ``confidence``, not per-candidate
#: ``probabilities`` scores -- see ``_confidently_irrelevant_ids``). Conservative by design: this
#: surface only ever narrows conversation history, so a marginal score keeps the exchange.
_MIN_DROP_CONFIDENCE = 0.85


def _get(exchange: Any, key: str, default: Any = None) -> Any:
	"""Duck-typed accessor: ``exchange`` may be a dict (as built by
	``get_tool_exchange_candidates``) or any object exposing the same attributes."""
	if isinstance(exchange, Mapping):
		return exchange.get(key, default)
	return getattr(exchange, key, default)


def _is_eligible(exchange: Any) -> bool:
	"""Hard constraints (I-DR1) -- see module docstring. Never raises: a malformed exchange
	dict/object degrades to ineligible (protected) rather than crashing the history build."""
	try:
		if _get(exchange, "status") != "Completed":
			return False
		if _get(exchange, "has_error", False):
			return False
		if _get(exchange, "pending_approval", False):
			return False
		if _get(exchange, "is_recent", False):
			return False
		if _get(exchange, "shared_turn", False):
			return False
		return bool(_get(exchange, "id"))
	except Exception:  # noqa: BLE001 - a bad candidate must never become eligible
		return False


def _confidently_irrelevant_ids(response: Any, eligible_ids: frozenset) -> set:
	"""Ids the decision marked irrelevant with at least ``_MIN_DROP_CONFIDENCE``.

	Reads the same two answer shapes ``huf.ai.decision.agent_surfaces._narrow_to_subset`` reads
	(a per-candidate ``probabilities`` map, or a single ``value``/``confidence`` pair), but with
	inverted polarity: a *high* score here means "confidently irrelevant, drop it" rather than
	"most relevant, keep it". Any id the backend names that is not in ``eligible_ids`` (a
	hallucinated or stale id) is silently ignored, never acted on (I-DR1).
	"""
	drop: set = set()
	for answer in (response.answers or {}).values():
		if answer.probabilities:
			for candidate_id, score in answer.probabilities.items():
				if (
					candidate_id in eligible_ids
					and isinstance(score, (int, float))
					and score >= _MIN_DROP_CONFIDENCE
				):
					drop.add(candidate_id)
		elif isinstance(answer.value, str) and answer.value in eligible_ids:
			confidence = answer.confidence if answer.confidence is not None else 0.0
			if confidence >= _MIN_DROP_CONFIDENCE:
				drop.add(answer.value)
	return drop


def compact_context(
	agent_doc: Any,
	exchanges: Sequence[Any],
	origin: Any,
	*,
	latency_budget_ms: int | None = None,
) -> tuple[tuple[str, ...], str | None]:
	"""Drop confidently-irrelevant, already-completed tool exchanges (T8.04).

	Args:
		agent_doc: The Agent document (or any object exposing ``decision_bindings``, same
			contract as ``huf.ai.decision.binding.resolve_agent_decision_binding``).
		exchanges: One entry per tool exchange in the current history, as built by
			``huf.ai.conversation_manager.get_tool_exchange_candidates`` (dicts) or any object
			exposing the same fields (``id``, ``status``, ``has_error``, ``pending_approval``,
			``is_recent``, ``shared_turn``). Read-only -- never mutated.
		origin: :class:`huf.ai.decision.types.DecisionOrigin` for this call.
		latency_budget_ms: Optional override; ``None`` uses the surface default (2000ms,
			PLAN.md §3.6 "Latency (D6)").

	Returns:
		``(kept_ids, decision_call)``: ``kept_ids`` is every input exchange's ``id`` that survives
		compaction, in original order -- always a subset of the input ids (I-DR1), and equal to
		all input ids whenever nothing was dropped (Off, no binding, Shadow, any non-success
		result, or an Enforce result with nothing confidently irrelevant). ``decision_call`` is
		the persisted ``Decision Call`` docname when one exists (best-effort, may be ``None``).
		Never raises.
	"""
	exchanges = list(exchanges)
	all_ids = tuple(_get(exchange, "id") for exchange in exchanges)

	eligible = [exchange for exchange in exchanges if _is_eligible(exchange)]
	if not eligible:
		return all_ids, None
	eligible_ids = frozenset(_get(exchange, "id") for exchange in eligible)

	try:
		from huf.ai.decision import service
		from huf.ai.decision.binding import resolve_agent_decision_binding
		from huf.ai.decision.types import CandidateSource, DecisionStatus, Option

		resolved = resolve_agent_decision_binding(agent_doc, _SURFACE)
		if resolved is None:
			return all_ids, None
		# D18 defense-in-depth: resolve_agent_decision_binding already downgrades an Advise
		# binding on this surface to Off (it is not in ADVISE_SURFACES), so this should be
		# unreachable -- kept as a fail-safe rather than trusting that invariant blindly here.
		if resolved.mode not in (service.MODE_SHADOW, service.MODE_ENFORCE):
			return all_ids, None

		candidates = tuple(
			Option(id=_get(exchange, "id"), description=str(_get(exchange, "summary", "") or "")[:500])
			for exchange in eligible
		)
		state = {
			"exchanges": [
				{
					"id": _get(exchange, "id"),
					"tool_name": _get(exchange, "tool_name", ""),
					"summary": _get(exchange, "summary", ""),
				}
				for exchange in eligible
			],
		}

		result = service.run_policy(
			resolved.policy,
			state=state,
			candidates=candidates,
			candidate_source=CandidateSource.COMPLETED_TOOL_EXCHANGES,
			candidate_resolver_id="huf.ai.decision.context_relevance.compact_context",
			mode=resolved.mode,
			surface=_SURFACE,
			origin=origin,
			latency_budget_ms=latency_budget_ms,
		)
	except Exception:  # noqa: BLE001 - this function must never raise into the history build path
		try:
			frappe.log_error(title="context_relevance.compact_context", message=frappe.get_traceback())
		except Exception:  # noqa: BLE001 - logging must never raise either
			pass
		return all_ids, None

	# Shadow (D6, D14): already enqueued by run_policy; measurement only, never compacts.
	if resolved.mode == service.MODE_SHADOW:
		return all_ids, result.decision_call

	if result.status != DecisionStatus.SUCCESS or result.response is None:
		return all_ids, result.decision_call
	response = result.response
	if response.status != DecisionStatus.SUCCESS:
		return all_ids, result.decision_call
	if response.gate_result not in (None, "accepted"):
		# Policy-configured minimum_confidence not met (huf.ai.decision.gating.evaluate_gate) --
		# same safe default as any other non-success result.
		return all_ids, result.decision_call

	drop_ids = _confidently_irrelevant_ids(response, eligible_ids)
	if not drop_ids:
		return all_ids, result.decision_call

	kept_ids = tuple(exchange_id for exchange_id in all_ids if exchange_id not in drop_ids)
	return kept_ids, result.decision_call
