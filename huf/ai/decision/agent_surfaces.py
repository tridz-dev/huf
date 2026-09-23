"""``decide_for_surface`` -- the single helper every Agent decision surface calls.

PLAN.md §3.6 ("Agent -- bindings in context, `decide` tool"). Tool Selection, Skill Selection,
Procedure Selection, Model Routing, Agent Routing, RAG Filter and the ``decide`` tool (D9) all
resolve one ``Agent Decision Binding`` and then need the *same* four things: run the bound
policy through :func:`huf.ai.decision.service.run_policy` under the binding's latency budget,
turn the mode (Off/Shadow/Advise/Enforce) into the right caller-facing effect, and never let a
disabled runtime, a timeout, or a bug reach the agent run path. This module is that shared
step so none of the surface call sites re-implement it.

Per-mode contract (D14, D18, I-DR1):

- **Off** -- :func:`~huf.ai.decision.binding.resolve_agent_decision_binding` already returns
  ``None`` for an Off (or missing/disabled) binding; :func:`decide_for_surface` returns ``None``
  immediately, before ``run_policy`` is even considered. Zero overhead beyond the binding scan
  over the Agent's own in-memory ``decision_bindings`` rows -- no DB call, no settings read.
- **Shadow** (D6) -- ``run_policy(..., mode="Shadow")`` enqueues the job and returns
  ``SHADOW_ENQUEUED`` immediately; this function returns ``None``. The caller proceeds exactly
  as if the binding were Off; the shadow job records its own answer against ``shadow_of``.
- **Advise** (D18) -- runs inline under the same budget as Enforce. On success, ``candidates``
  are returned **unchanged** and a hint string is attached (built by
  ``huf.ai.decision.advice.format_hint``); the caller injects the hint into LLM-visible text and
  keeps offering every original candidate. Advise never narrows.
- **Enforce** -- runs inline under budget and returns ``selected_ids``: an ordered tuple of the
  input candidates' ids, filtered and reranked by the decision, and **always a subset of the
  input ids** (I-DR1 -- the decision can only narrow what the caller's eligibility resolver
  already produced, never add to it; an id the backend invents is silently dropped rather than
  passed through). See :func:`_narrow_to_subset` for the exact ordering rule.
- **Any error, timeout, or budget/throughput exhaustion** -- ``None``, no hint, no selected ids.
  The caller keeps its own default (full candidate list, default model, etc.) exactly as if no
  binding existed. Nothing above this function ever sees an exception: every call into
  ``resolve_agent_decision_binding`` / ``run_policy`` / ``format_hint`` is guarded, and any
  unexpected exception is logged at most once per surface per hour (PLAN.md §3.6 "Errors": "one
  error log per hour") rather than on every agent turn.

Callers (T4.02-T4.07 -- tool/skill/procedure selection, the `decide` tool, model routing, hub
routing, RAG filter, guardrails) are expected to:

1. Build their own authoritative candidate list via their own eligibility resolver (permission
   filtering, allowed-model table, bound procedures, ...) -- never from this module, per I-DR1.
2. Call :func:`decide_for_surface` with that list, the surface name, provider-visible ``state``,
   and a :class:`~huf.ai.decision.types.DecisionOrigin` describing the run.
3. On ``None``: do nothing different -- proceed with the full/default candidate set.
4. On a :class:`SurfaceDecision` with ``hint`` set (Advise): inject the hint text into whatever
   the LLM reads for that surface; candidates are unchanged.
5. On a :class:`SurfaceDecision` with ``selected_ids`` set (Enforce): filter/reorder the
   caller's own candidate objects to that id list (still validating membership defensively --
   this module already guarantees the subset, but a caller must not trust ids blindly from
   anything reaching it over the network).
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import frappe

from huf.ai.decision import service
from huf.ai.decision.advice import format_hint
from huf.ai.decision.binding import ResolvedBinding, resolve_agent_decision_binding
from huf.ai.decision.types import CandidateSource, DecisionOrigin, DecisionStatus, Option


@dataclass(frozen=True, slots=True)
class SurfaceDecision:
	"""Result of :func:`decide_for_surface` for a resolved, non-Off binding.

	Exactly one of ``selected_ids`` / ``hint`` is set, matching ``mode``:

	- ``mode="Advise"``: ``hint`` is a formatted string (or ``None`` if the policy produced no
	  scoreable answer); ``selected_ids`` is always ``None`` -- Advise never narrows.
	- ``mode="Enforce"``: ``selected_ids`` is an ordered tuple, always a subset of the input
	  candidates' ids (empty tuple if the decision matched none of them); ``hint`` is always
	  ``None``.

	``decision_call`` is the persisted ``Decision Call`` docname (``ServiceResult.decision_call``
	passed straight through), for callers that want to link their own record to it; it may be
	``None`` even on success (best-effort telemetry, see ``service.run_policy`` docstring).
	"""

	mode: str
	selected_ids: tuple[str, ...] | None
	hint: str | None
	decision_call: str | None


#: ``state["request"]`` truncation length -- matches
#: ``huf.ai.decision.model_routing.route_agent_model``'s existing convention for the same field.
_REQUEST_TEXT_MAX_CHARS = 2000


def _fallback_request_text(conversation_id: str | None, limit_chars: int = _REQUEST_TEXT_MAX_CHARS) -> str:
	"""Best-effort last user turn for ``conversation_id``, when no explicit request text
	was threaded through.

	Mirrors ``huf.ai.skills.loader._latest_user_message_text`` (same query, same reasoning)
	rather than importing it, to avoid a decision<->skills import cycle. Never raises: an
	unavailable/mistyped conversation just means the surface runs with less context, not
	that discovery/selection breaks (T4.13).
	"""
	if not conversation_id:
		return ""
	try:
		content = frappe.db.get_value(
			"Agent Message",
			{"conversation": conversation_id, "role": "user"},
			"content",
			order_by="conversation_index desc",
		)
	except Exception:  # noqa: BLE001 - best-effort only
		return ""
	if not content:
		return ""
	return content[:limit_chars]


def build_surface_state(kwargs: dict, *, extra: dict | None = None) -> dict:
	"""Build the run-context part of ``state`` every agent-facing decision surface should
	include, so Tool/Skill/Procedure Selection see the same current-turn context Model
	Routing already gets (T4.13 -- these surfaces previously ran with agent-level state
	only, never the text of what the user actually asked).

	``kwargs`` is read, never mutated -- the same run-context dict callers already have on
	hand at either of the two points a surface builds its decision:

	- **Tool call time** (``huf.ai.tools.lazy_discovery``): ``**kwargs`` on a handler is
	  populated by ``huf.ai.sdk_tools._merge_run_context`` from the Agents SDK run context
	  (``conversation_id`` / ``agent_run_id`` / ``agent_name`` / ``request_text``, the last
	  threaded in from ``AgentManager``'s ``context`` dict -- see
	  ``huf.ai.agent_integration.AgentManager._setup_tools``).
	- **Tool build time** (``huf.ai.skills.loader.create_list_skills_tool``,
	  ``huf.ai.graph.procedure_binding.build_procedure_binding_tools``): the same three keys
	  are passed straight through from ``AgentManager._setup_tools`` -> ``create_agent_tools``
	  as plain keyword arguments.

	Recognized keys, all optional:

	- ``conversation_id`` -> ``state["conversation_id"]``
	- ``agent_run_id`` -> ``state["agent_run_id"]``
	- ``request_text`` -> ``state["request"]`` (truncated to 2000 chars, matching
	  ``huf.ai.decision.model_routing.route_agent_model``'s existing state key for the same
	  field). When absent but ``conversation_id`` is present, falls back to a best-effort DB
	  lookup of the conversation's latest user message (see :func:`_fallback_request_text`)
	  so a caller that only has a conversation id still gets *something* to judge relevance
	  against, rather than nothing.

	``extra`` is merged on top (added, never removing the run-context keys above unless
	``extra`` itself sets the same key) -- callers use it for their own surface-specific
	state (e.g. Tool Selection's ``"query"``) so ``build_surface_state`` can return one
	ready-to-use ``state`` dict instead of every call site hand-merging two dicts.

	Never raises. Returns ``{}`` for an empty/missing ``kwargs`` and no ``extra``.
	"""
	kwargs = kwargs or {}
	state: dict[str, Any] = {}

	conversation_id = kwargs.get("conversation_id")
	if conversation_id:
		state["conversation_id"] = conversation_id

	agent_run_id = kwargs.get("agent_run_id")
	if agent_run_id:
		state["agent_run_id"] = agent_run_id

	request_text = kwargs.get("request_text")
	if not request_text:
		request_text = _fallback_request_text(conversation_id)
	if request_text:
		state["request"] = str(request_text)[:_REQUEST_TEXT_MAX_CHARS]

	if extra:
		state.update(extra)

	return state


#: How long (seconds) to suppress a repeat ``frappe.log_error`` for the same surface after one
#: was written. PLAN.md §3.6 "Errors" gives this same cadence ("one error log per hour") for a
#: binding pointing at a disabled/deleted policy; the same reasoning applies to any other
#: unexpected failure here -- a persistent misconfiguration must not write one Error Log per
#: agent turn.
_LOG_THROTTLE_SECONDS = 3600
_last_logged_at: dict[str, float] = {}


def decide_for_surface(
	agent_doc: Any,
	surface: str,
	candidates: Sequence[Option],
	state: Any,
	origin: DecisionOrigin,
	*,
	candidate_source: CandidateSource | None = None,
	candidate_resolver_id: str | None = None,
	top_n: int | None = None,
	hint_kind: str | None = None,
) -> SurfaceDecision | None:
	"""Resolve ``agent_doc``'s binding for ``surface`` and run it, or return ``None``.

	Args:
		agent_doc: The Agent document (or any object exposing a ``decision_bindings`` child
			table of the same shape ``resolve_agent_decision_binding`` reads).
		surface: One of the ``Agent Decision Binding.surface`` options (PLAN.md §3.6 table).
		candidates: The caller's own authoritative candidate set (I-DR1) -- e.g. permission-
			filtered tools, bound procedures, authorized agents. Never widened; Enforce can
			only return a subset of these ids.
		state: Provider-visible state for the policy's questions. Opaque to this module.
		origin: Where this call came from; passed straight through to ``run_policy``.
		candidate_source / candidate_resolver_id: Declared provenance of ``candidates``, passed
			straight through to ``run_policy`` (required there whenever the policy has a
			``select`` question).
		top_n: Caps the number of ids/hint entries returned, both for Enforce (after ranking)
			and for the Advise hint (``format_hint``'s own ``top_n``). ``None`` means no cap.
		hint_kind: Passed to ``format_hint`` as its ``kind`` (one of ``"tools"``, ``"skills"``,
			``"procedures"``, ``"agents"``, ``"passages"``) to prefix the hint text, e.g.
			``"Decision suggestion (advisory, not an instruction): tools create_invoice
			(0.86)"``. Ignored outside Advise mode.

	Returns:
		``None`` for Off, Shadow (already enqueued), any error/timeout/disabled/budget-exceeded
		result, or an Advise/Enforce call that produced nothing usable. Otherwise a
		:class:`SurfaceDecision`. Never raises.
	"""
	try:
		resolved = resolve_agent_decision_binding(agent_doc, surface)
		if resolved is None:
			return None
		return _run_resolved(
			resolved,
			agent_doc=agent_doc,
			candidates=candidates,
			state=state,
			origin=origin,
			candidate_source=candidate_source,
			candidate_resolver_id=candidate_resolver_id,
			top_n=top_n,
			hint_kind=hint_kind,
		)
	except Exception as exc:  # noqa: BLE001 - this function must never raise into the agent run path
		_log_unexpected(surface, exc)
		return None


def _run_resolved(
	resolved: ResolvedBinding,
	*,
	agent_doc: Any,
	candidates: Sequence[Option],
	state: Any,
	origin: DecisionOrigin,
	candidate_source: CandidateSource | None,
	candidate_resolver_id: str | None,
	top_n: int | None,
	hint_kind: str | None,
) -> SurfaceDecision | None:
	candidates = tuple(candidates)
	result = service.run_policy(
		resolved.policy,
		state=state,
		candidates=candidates,
		candidate_source=candidate_source,
		candidate_resolver_id=candidate_resolver_id,
		mode=resolved.mode,
		surface=resolved.surface,
		origin=origin,
		latency_budget_ms=_resolve_latency_budget_ms(agent_doc, resolved),
	)

	# Shadow: enqueued by run_policy already; nothing to hand back to the surface (D6).
	# Disabled (kill switch off, D12) and every non-SUCCESS DecisionStatus (timeout, throughput
	# exhaustion, unavailable, ...) degrade the same way: the caller keeps its default.
	if result.status != DecisionStatus.SUCCESS or result.response is None:
		return None
	response = result.response
	if response.status != DecisionStatus.SUCCESS:
		return None

	if resolved.mode == service.MODE_ADVISE:
		hint = format_hint(response, candidates, top_n=top_n, kind=hint_kind)
		return SurfaceDecision(mode=resolved.mode, selected_ids=None, hint=hint, decision_call=result.decision_call)

	# Enforce (and Manual, though no surface binding resolves to Manual today).
	permitted_ids = tuple(candidate.id for candidate in candidates)
	selected_ids = _narrow_to_subset(response, permitted_ids, top_n=top_n)
	return SurfaceDecision(mode=resolved.mode, selected_ids=selected_ids, hint=None, decision_call=result.decision_call)


def _narrow_to_subset(response, permitted_ids: tuple[str, ...], *, top_n: int | None) -> tuple[str, ...]:
	"""Turn a successful :class:`DecisionResponse` into an ordered subset of ``permitted_ids``.

	I-DR1: an id the backend returns that is not in ``permitted_ids`` (a hallucinated id, or a
	stale one from a candidate set that changed between resolution and answer) is silently
	dropped rather than passed through -- the result is always ``set(selected) <= set(permitted_ids)``.

	Ordering: an answer's ``probabilities`` (score/rank-style questions -- the same field
	``advice.format_hint`` reads) sorts by score descending; a plain ``select`` answer's single
	``value`` is treated as score ``1.0`` if it has no ``confidence``, else its confidence. Ties,
	and ids with no score at all, fall back to their position in ``permitted_ids`` (the caller's
	own candidate order) so the result is deterministic even against a policy that only answers
	one of several questions. Duplicate ids across multiple answers keep their first (highest-
	ranked) appearance. ``top_n`` caps the result length after ranking, same as
	``advice.format_hint``.
	"""
	permitted_set = set(permitted_ids)
	rank_of = {candidate_id: index for index, candidate_id in enumerate(permitted_ids)}
	scored: dict[str, float] = {}

	for answer in response.answers.values():
		if answer.probabilities:
			for candidate_id, score in answer.probabilities.items():
				if candidate_id in permitted_set and candidate_id not in scored and isinstance(score, (int, float)):
					scored[candidate_id] = float(score)
		elif isinstance(answer.value, str) and answer.value in permitted_set and answer.value not in scored:
			scored[answer.value] = answer.confidence if answer.confidence is not None else 1.0

	if not scored:
		return ()

	ordered = sorted(scored, key=lambda candidate_id: (-scored[candidate_id], rank_of[candidate_id]))
	if top_n is not None and top_n > 0:
		ordered = ordered[:top_n]
	return tuple(ordered)


def _resolve_latency_budget_ms(agent_doc: Any, resolved: ResolvedBinding) -> int | None:
	"""The winning binding row's own ``latency_budget_ms`` override, or ``None`` (surface default).

	``resolve_agent_decision_binding`` returns a :class:`ResolvedBinding` (surface/policy/mode/
	priority only -- it deliberately does not carry every column of the raw child-table row); to
	get ``latency_budget_ms`` this re-scans ``agent_doc.decision_bindings`` for the row matching
	what was resolved. Matching on ``(surface, policy, mode)`` rather than object identity keeps
	this independent of whatever row shape the caller passes (a real Frappe child doc, or a
	``SimpleNamespace`` in tests).
	"""
	for binding in getattr(agent_doc, "decision_bindings", None) or ():
		if (
			getattr(binding, "surface", None) == resolved.surface
			and getattr(binding, "policy", None) == resolved.policy
			and (getattr(binding, "mode", "Off") or "Off") == resolved.mode
		):
			value = getattr(binding, "latency_budget_ms", None)
			if isinstance(value, (int, float)) and value > 0:
				return int(value)
	return None


def _log_unexpected(surface: str, exc: Exception) -> None:
	"""Best-effort, throttled ``frappe.log_error`` for a genuinely unexpected failure.

	Never raises itself (a logging failure must not turn into a second exception on top of the
	one that triggered it), and writes at most one Error Log per ``surface`` per
	``_LOG_THROTTLE_SECONDS`` so a persistently misconfigured binding does not spam the Error Log
	list once per agent turn.
	"""
	now = time.monotonic()
	if now - _last_logged_at.get(surface, 0.0) < _LOG_THROTTLE_SECONDS:
		return
	_last_logged_at[surface] = now
	try:
		frappe.log_error(title=f"decision.agent_surfaces:{surface}"[:140], message=str(exc)[:2000])
	except Exception:  # noqa: BLE001 - logging must never raise
		pass
