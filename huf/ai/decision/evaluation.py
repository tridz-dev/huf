"""Evaluation service: policy metrics, shadow agreement, followed-advice, replay (PLAN.md §3.13, IP §19).

T10.01 (PR 10). Backs four whitelisted ``huf.ai.decision.api`` endpoints
(``get_policy_metrics``, ``get_shadow_agreement``, ``get_followed_advice``, ``replay_policy``).
Every read here goes through ``frappe.get_list``/``frappe.get_doc``, so D5 row-level visibility
(``huf.huf.doctype.decision_call.decision_call.get_permission_query_conditions`` /
``has_permission``) applies exactly as it does to ``api.list_decision_calls`` -- this module
does not re-implement or bypass it. Capability gating (``decision.run``) is the API layer's job
(``api._require``), not this module's -- these functions are plain, capability-agnostic, and
therefore directly unit-testable.

IMPORTANT -- what "agreement" and "followed-advice" can and cannot measure today
==================================================================================

PLAN.md §3.13 describes "Shadow agreement ... per binding, Shadow answer vs what actually
happened (tool loaded, model used, branch taken)" and, for Advise, "how often the LLM chose the
top suggested candidate." Two things make an exact version of that unavailable today, and both
are read-only facts about the surrounding code, not something this task's file scope (this
module, ``api.py``, its own tests) can fix:

1. **``Decision Call.shadow_of`` is never populated.** It exists on the DocType ("Reference to
   the production outcome this shadow call was comparing against") and ``DecisionOrigin`` carries
   a ``shadow_of`` field end to end (``service.py`` -> ``persistence.py``), but no caller
   anywhere in the tree -- ``agent_surfaces.py``, ``model_routing.py``,
   ``huf/ai/tools/lazy_discovery.py`` -- ever constructs a ``DecisionOrigin`` with it set. This
   also follows from how bindings work: one ``Agent Decision Binding`` row has exactly one mode
   (Off/Shadow/Advise/Enforce), so a Shadow-mode binding never *also* produces a same-turn
   Enforce decision on the same surface to link against -- there is no "production outcome"
   *decision* to point ``shadow_of`` at, only the caller's own non-decision default behavior.
   Verified by grep (`rg -n 'shadow_of=' huf/ai huf/huf`, excluding pure pass-throughs): the only
   non-``None`` write path is ``service._capturing_sink`` copying ``origin.shadow_of`` straight
   through, and every origin constructed by a real surface leaves it unset.

2. **The two other fields the plan's parenthetical names ("tool loaded", "model used") are not
   on ``Decision Call`` either.** They live on separate doctypes that a Decision Call links to
   only via its own ``agent_run`` -- ``Agent Run.model`` (the model actually used for that run)
   and ``Agent Tool Call`` (one row per tool actually invoked, with its own ``agent_run`` link
   and ``tool`` field). "Branch taken" (Flow routing) has no equivalent recorded field found
   anywhere in this tree as of T10.01 -- Flow Run does not persist which branch a Flow Decision
   Router node actually took as a queryable field, so Flow-surface agreement is not computed.

Given that, this module computes agreement/followed-advice **by correlation through
``agent_run``**, only for the two surfaces where a same-run "actual outcome" is queryable, and
returns an explicit ``measurable`` / ``not_measurable`` split rather than one blended number for
every surface (this mirrors the IP §19.3 instruction: "Do not ship one generic 'Decision
accuracy' number for heterogeneous surfaces."):

- **Model Routing** (Shadow only -- it is not in ``binding.ADVISE_SURFACES``): the Shadow
  Decision Call's top-scored candidate id is a ``Decision`` ``AI Model`` docname (see
  ``model_routing.route_agent_model``: ``Option(item.model, ...)`` where ``item.model`` is the
  same docname ``Agent Run.model`` stores for the run that actually executed). Matched when they
  are equal.
- **Tool Selection** (Shadow and Advise): the Shadow/Advise Decision Call's top-scored candidate
  id is compared against the set of ``Agent Tool Call.tool`` values for the same ``agent_run``.
  **Caveat, documented rather than hidden**: ``huf/ai/tools/lazy_discovery.py`` runs Tool
  Selection at two different granularities under the same surface name -- group-level
  (``handle_list_tool_groups``, candidate id = a tool group/service name) and tool-level
  (``handle_search_tools``, candidate id = an individual ``tool_name``, the same value
  ``Agent Tool Call.tool`` records). A ``Decision Call`` row does not record which of the two
  produced it, so this module can only equality-match against ``Agent Tool Call.tool``, which is
  correct for tool-level calls and will under-count (report "no match") for group-level calls
  whose candidate id is a group name, not a tool name. This is a known, accepted imprecision;
  the alternative (attempting to resolve a group id to its member tools and match "is the actual
  tool a member of this group") is not implemented here to keep the correlation you can actually
  audit through one field.

Every other Advise-eligible surface (``Skill Selection``, ``Procedure Selection``,
``Agent Routing``, ``RAG Filter``) and every Shadow-eligible surface outside the two above
(``Context Relevance``, ``Input Guardrail``, ``Output Guardrail``, ``Output Verification``, the
``decide`` tool's ``Agent Tool`` surface) have **no** actual-outcome doctype/field this module
found to correlate against, so calls on those surfaces are always reported under
``not_measurable`` with a ``reason`` string, never silently dropped or guessed at. A later task
(T2B.11/T2B.10 or the UI built on top of this in T10.03) should treat ``measurable_surfaces``
below as the authoritative, current list -- not assume every surface row has a number.

Replay's own limitations (``replay_policy`` docstring below) are documented at the point of use.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import timedelta
from typing import Any

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

from huf.ai.decision import service
from huf.ai.decision.types import CandidateSource, DecisionOrigin, Option

# -- Surfaces this module can correlate a Shadow/Advise answer against a real outcome for -----
#
# See the module docstring's numbered limitation list for exactly why only these two, and what
# each one's correlation actually checks. Keys are `Decision Call.surface` values; values are a
# short machine/human-readable description surfaced in every response so a caller never has to
# read this source file to know what "measurable" means for a given surface.
MEASURABLE_SURFACES: dict[str, str] = {
	"Model Routing": "Top Shadow candidate (an AI Model docname) vs Agent Run.model for the same agent_run.",
	"Tool Selection": (
		"Top Shadow/Advise candidate vs the set of Agent Tool Call.tool values for the same "
		"agent_run. Only exact-matches tool-level candidates (huf.ai.tools.lazy_discovery."
		"handle_search_tools); group-level candidates (handle_list_tool_groups) will not match "
		"a tool name and are reported as no-match, not excluded -- see module docstring."
	),
}

#: DecisionStatus values (types.py) that represent the backend/provider itself failing, as
#: opposed to a policy-level fallback/no-match outcome. RATE_LIMITED is counted here rather than
#: as a timeout since it is a provider signal, not a deadline miss (IP §19.3 keeps
#: "backend_error_rate" and "timeout_rate" as separate rows).
_BACKEND_ERROR_STATUSES = frozenset({"unavailable", "authentication_failed", "invalid_response", "failed", "rate_limited"})
_TIMEOUT_STATUSES = frozenset({"timeout"})

#: Fields pulled per Decision Call row for get_policy_metrics. Kept to the non-admin-gated
#: summary columns (api._DECISION_CALL_LIST_FIELDS is the equivalent for list_decision_calls) --
#: answer_json is included because IP §19.3's "distribution by selected option" and
#: "no_match_rate" both need each row's answers, not just the summary status.
_METRICS_FIELDS = (
	"name", "status", "policy_version", "surface", "mode", "latency_ms", "input_tokens",
	"cost", "gate_result", "fallback_action", "answer_json", "started_at",
)

#: Fields pulled per Decision Call row for shadow-agreement / followed-advice correlation.
_CORRELATION_FIELDS = ("name", "surface", "mode", "agent_run", "answer_json", "fallback_action", "started_at")

#: Cap on rows fetched per call -- these are read-time aggregations over frappe.get_list, not
#: pre-aggregated SQL, so an unbounded window over a busy site would be an unbounded query. The
#: response reports `sample_capped` so a caller knows to narrow from_date/to_date rather than
#: silently trusting a partial window.
_DEFAULT_ROW_LIMIT = 5000


# -- Shared helpers -----------------------------------------------------------------------


def _resolve_date_range(from_date: Any, to_date: Any) -> tuple[Any, Any]:
	"""Default ``to_date`` to now and ``from_date`` to 7 days before it, like ``get_binding_stats``."""
	to_dt = get_datetime(to_date) if to_date else now_datetime()
	from_dt = get_datetime(from_date) if from_date else to_dt - timedelta(days=7)
	return from_dt, to_dt


def _parse_answers(answer_json: str | None) -> dict[str, dict]:
	"""Best-effort decode of a persisted ``Decision Call.answer_json`` blob.

	Never raises -- a malformed/missing blob (should not happen, but this module must not crash
	an evaluation read over one bad historical row) degrades to "no answers for this row".
	"""
	if not answer_json:
		return {}
	try:
		data = json.loads(answer_json)
	except (TypeError, ValueError):
		return {}
	return data if isinstance(data, dict) else {}


def _top_candidate_id(answer: dict) -> str | None:
	"""The highest-scored candidate id in one normalized answer dict, or ``None``.

	Mirrors ``agent_surfaces._narrow_to_subset``'s own reading of an answer: prefer
	``probabilities`` (score/select-with-scores), else a plain ``select`` answer's ``value``
	(skipping the explicit ``"none"`` sentinel, which is a real, meaningful answer -- "matched
	none of the candidates" -- not a candidate id to compare against an outcome).
	"""
	if not answer:
		return None
	probabilities = answer.get("probabilities")
	if isinstance(probabilities, dict) and probabilities:
		try:
			return max(probabilities, key=lambda candidate_id: probabilities[candidate_id])
		except (TypeError, ValueError):
			pass
	value = answer.get("value")
	if isinstance(value, str) and value and value != "none":
		return value
	return None


def _row_top_candidate(answer_json: str | None) -> str | None:
	"""The first answer's top candidate id for a Decision Call row (most policies ask one
	select/score question per surface; this reads whichever answer comes first if there is more
	than one)."""
	for answer in _parse_answers(answer_json).values():
		top = _top_candidate_id(answer)
		if top is not None:
			return top
	return None


def _percentile(sorted_values: list[float], pct: float) -> float | None:
	"""Nearest-rank percentile, same method as ``api.get_binding_stats``'s p95 calculation."""
	if not sorted_values:
		return None
	index = min(len(sorted_values) - 1, math.ceil(pct * len(sorted_values)) - 1)
	return sorted_values[index]


# -- get_policy_metrics ---------------------------------------------------------------------


def get_policy_metrics(
	policy: str,
	*,
	policy_version: str | None = None,
	surface: str | None = None,
	from_date: Any = None,
	to_date: Any = None,
	limit: int = _DEFAULT_ROW_LIMIT,
) -> dict:
	"""Per-policy/version metrics for the window, per IP §19.3.

	Args:
		policy: ``Decision Policy`` docname. Required -- this endpoint answers "how is this
			policy doing", not a site-wide rollup (``huf.ai.decision.analytics`` from T10.02
			already covers cross-policy spend aggregation).
		policy_version: Narrow to one ``Decision Policy Version``. When omitted, the window's
			calls are grouped by whichever version they actually ran under (``by_version``),
			plus an ``overall`` aggregate across all of them -- a policy that republished
			mid-window should not have its old and new version's numbers silently blended.
		surface: Narrow to one ``Decision Call.surface`` (a policy can be reused across more
			than one binding/surface).
		from_date / to_date: Window bounds (anything ``frappe.utils.get_datetime`` accepts).
			Defaults to the last 7 days, matching ``api.get_binding_stats``.
		limit: Row fetch cap (see ``_DEFAULT_ROW_LIMIT``); response reports ``sample_capped``.

	Returns:
		``{policy, policy_version, surface, from_date, to_date, sample_size, sample_capped,
		overall: <metrics>, by_version: {<version>: <metrics>, ...}}`` where ``<metrics>`` is
		the IP §19.3 list: ``decision_calls, success_rate, backend_error_rate, timeout_rate,
		average_latency_ms, p95_latency_ms, input_tokens, cost, low_confidence_rate,
		fallback_rate, no_match_rate, distribution_by_selected_option``. Rate fields are
		``None`` (not ``0.0``) when their denominator is zero, so a caller can distinguish
		"no calls" from "zero rate".
	"""
	from_dt, to_dt = _resolve_date_range(from_date, to_date)

	filters: dict[str, Any] = {"policy": policy, "started_at": ["between", [from_dt, to_dt]]}
	if policy_version:
		filters["policy_version"] = policy_version
	if surface:
		filters["surface"] = surface

	rows = frappe.get_list(
		"Decision Call",
		filters=filters,
		fields=list(_METRICS_FIELDS),
		order_by="started_at asc",
		limit_page_length=limit,
	)

	by_version: dict[str, list[dict]] = {}
	for row in rows:
		by_version.setdefault(row.get("policy_version") or "unversioned", []).append(row)

	return {
		"policy": policy,
		"policy_version": policy_version,
		"surface": surface,
		"from_date": str(from_dt),
		"to_date": str(to_dt),
		"sample_size": len(rows),
		"sample_capped": len(rows) >= limit,
		"overall": _aggregate_metric_rows(rows),
		"by_version": {version: _aggregate_metric_rows(group) for version, group in by_version.items()},
	}


def _aggregate_metric_rows(rows: list[dict]) -> dict:
	total = len(rows)
	if total == 0:
		return {
			"decision_calls": 0,
			"success_rate": None,
			"backend_error_rate": None,
			"timeout_rate": None,
			"average_latency_ms": None,
			"p95_latency_ms": None,
			"input_tokens": 0,
			"cost": 0.0,
			"low_confidence_rate": None,
			"fallback_rate": None,
			"no_match_rate": None,
			"distribution_by_selected_option": {},
		}

	status_counts = Counter(row.get("status") for row in rows)
	backend_errors = sum(status_counts.get(status, 0) for status in _BACKEND_ERROR_STATUSES)
	timeouts = sum(status_counts.get(status, 0) for status in _TIMEOUT_STATUSES)

	latencies = sorted(row["latency_ms"] for row in rows if isinstance(row.get("latency_ms"), (int, float)))
	input_tokens = sum(row.get("input_tokens") or 0 for row in rows)
	cost = sum(row.get("cost") or 0.0 for row in rows)
	fallback_count = sum(1 for row in rows if row.get("fallback_action"))

	gated_rows = [row for row in rows if row.get("gate_result")]
	low_confidence_count = sum(1 for row in gated_rows if row["gate_result"] == "uncertain")

	distribution: Counter[str] = Counter()
	no_match_count = 0
	for row in rows:
		row_has_no_match = False
		for answer in _parse_answers(row.get("answer_json")).values():
			value = answer.get("value")
			if not isinstance(value, str):
				continue
			if value == "none":
				row_has_no_match = True
			elif answer.get("kind") in ("select", "score"):
				distribution[value] += 1
		if row_has_no_match:
			no_match_count += 1

	return {
		"decision_calls": total,
		"success_rate": status_counts.get("success", 0) / total,
		"backend_error_rate": backend_errors / total,
		"timeout_rate": timeouts / total,
		"average_latency_ms": (sum(latencies) / len(latencies)) if latencies else None,
		"p95_latency_ms": _percentile(latencies, 0.95),
		"input_tokens": input_tokens,
		"cost": cost,
		"low_confidence_rate": (low_confidence_count / len(gated_rows)) if gated_rows else None,
		"fallback_rate": fallback_count / total,
		"no_match_rate": no_match_count / total,
		"distribution_by_selected_option": dict(distribution),
	}


# -- get_shadow_agreement / get_followed_advice ----------------------------------------------


def _actual_model_for_agent_run(agent_run: str | None) -> str | None:
	if not agent_run:
		return None
	return frappe.db.get_value("Agent Run", agent_run, "model")


def _actual_tools_for_agent_run(agent_run: str | None) -> set[str]:
	if not agent_run:
		return set()
	tools = frappe.get_list("Agent Tool Call", filters={"agent_run": agent_run}, pluck="tool")
	return {tool for tool in tools if tool}


def _correlate_row(row: dict) -> tuple[bool, bool | None]:
	"""Return ``(measurable, matched)`` for one Decision Call row.

	``matched`` is only meaningful when ``measurable`` is True. See ``MEASURABLE_SURFACES`` /
	module docstring for exactly what each surface compares.
	"""
	surface = row.get("surface")
	if surface not in MEASURABLE_SURFACES:
		return False, None

	top_candidate = _row_top_candidate(row.get("answer_json"))
	if top_candidate is None:
		# The call produced no scoreable answer (fallback/no-match) -- there is nothing to
		# compare, so this row is not measurable rather than counted as a mismatch.
		return False, None

	if surface == "Model Routing":
		actual_model = _actual_model_for_agent_run(row.get("agent_run"))
		if not actual_model:
			return False, None
		return True, top_candidate == actual_model

	if surface == "Tool Selection":
		actual_tools = _actual_tools_for_agent_run(row.get("agent_run"))
		if not actual_tools:
			return False, None
		return True, top_candidate in actual_tools

	return False, None  # pragma: no cover - MEASURABLE_SURFACES guards this


def _evaluate_binding_calls(
	*,
	mode: str,
	policy: str | None,
	agent: str | None,
	agent_run: str | None,
	surface: str | None,
	from_date: Any,
	to_date: Any,
	limit: int,
) -> dict:
	"""Shared core for ``get_shadow_agreement`` (``mode="Shadow"``) and ``get_followed_advice``
	(``mode="Advise"``): fetch matching Decision Calls, correlate each to an actual outcome
	where a measurable surface allows it, and report per-surface breakdowns.
	"""
	from_dt, to_dt = _resolve_date_range(from_date, to_date)

	filters: dict[str, Any] = {"mode": mode, "status": "success", "started_at": ["between", [from_dt, to_dt]]}
	if policy:
		filters["policy"] = policy
	if agent:
		filters["agent"] = agent
	if agent_run:
		filters["agent_run"] = agent_run
	if surface:
		filters["surface"] = surface

	rows = frappe.get_list(
		"Decision Call",
		filters=filters,
		fields=list(_CORRELATION_FIELDS),
		order_by="started_at asc",
		limit_page_length=limit,
	)

	by_surface: dict[str, dict] = {}
	unmeasured_surfaces: Counter[str] = Counter()

	for row in rows:
		row_surface = row.get("surface") or "unknown"
		measurable, matched = _correlate_row(row)
		bucket = by_surface.setdefault(
			row_surface,
			{
				"sampled": 0,
				"measurable": 0,
				"matched": 0,
				"would_have_fallback": 0,
			},
		)
		bucket["sampled"] += 1
		if row.get("fallback_action"):
			bucket["would_have_fallback"] += 1
		if measurable:
			bucket["measurable"] += 1
			if matched:
				bucket["matched"] += 1
		elif row_surface not in MEASURABLE_SURFACES:
			unmeasured_surfaces[row_surface] += 1

	by_surface_response = {}
	for surface_name, bucket in by_surface.items():
		rate = (bucket["matched"] / bucket["measurable"]) if bucket["measurable"] else None
		fallback_rate = (bucket["would_have_fallback"] / bucket["sampled"]) if bucket["sampled"] else None
		by_surface_response[surface_name] = {
			"sampled": bucket["sampled"],
			"measurable": bucket["measurable"],
			"rate": rate,
			"would_have_fallback_rate": fallback_rate,
			"method": MEASURABLE_SURFACES.get(surface_name),
		}

	return {
		"mode": mode,
		"policy": policy,
		"agent": agent,
		"agent_run": agent_run,
		"surface": surface,
		"from_date": str(from_dt),
		"to_date": str(to_dt),
		"sample_size": len(rows),
		"sample_capped": len(rows) >= limit,
		"measurable_surfaces": dict(MEASURABLE_SURFACES),
		"by_surface": by_surface_response,
		"not_measurable": {
			name: {
				"sampled": count,
				"reason": (
					"No actual-outcome field/doctype is correlated for this surface yet -- see "
					"huf.ai.decision.evaluation module docstring."
				),
			}
			for name, count in unmeasured_surfaces.items()
		},
	}


def get_shadow_agreement(
	*,
	policy: str | None = None,
	agent: str | None = None,
	agent_run: str | None = None,
	surface: str | None = None,
	from_date: Any = None,
	to_date: Any = None,
	limit: int = _DEFAULT_ROW_LIMIT,
) -> dict:
	"""Shadow agreement per surface: Shadow Decision Call top candidate vs actual outcome.

	"Per binding" from the acceptance clause is expressed here as filtering by
	``policy``/``agent``/``agent_run``/``surface`` (a binding is exactly the tuple
	(agent, surface, policy) -- there is no separate binding docname to key off of, child table
	rows are unnamed beyond their own hash). Pass ``agent`` (+ optionally ``surface``) to scope
	to one Agent's bindings, or ``policy`` to scope across every agent/surface using that policy.

	See the module docstring for exactly what "agreement" can and cannot measure today
	(``shadow_of`` is never populated by any caller; only Model Routing and Tool Selection have
	a correlatable actual-outcome field).
	"""
	return _evaluate_binding_calls(
		mode=service.MODE_SHADOW,
		policy=policy,
		agent=agent,
		agent_run=agent_run,
		surface=surface,
		from_date=from_date,
		to_date=to_date,
		limit=limit,
	)


def get_followed_advice(
	*,
	policy: str | None = None,
	agent: str | None = None,
	agent_run: str | None = None,
	surface: str | None = None,
	from_date: Any = None,
	to_date: Any = None,
	limit: int = _DEFAULT_ROW_LIMIT,
) -> dict:
	"""Followed-advice rate per surface: Advise Decision Call top-suggested candidate vs what the
	LLM/agent actually used afterward, for the same surfaces ``get_shadow_agreement`` can
	correlate (only Tool Selection is both Advise-eligible, ``binding.ADVISE_SURFACES``, and
	measurable, ``MEASURABLE_SURFACES`` -- Model Routing is Shadow/Enforce-only, so it never
	appears here; Skill Selection/Procedure Selection/Agent Routing/RAG Filter are Advise-eligible
	but have no actual-outcome field to correlate against, so they always land in
	``not_measurable``).
	"""
	return _evaluate_binding_calls(
		mode=service.MODE_ADVISE,
		policy=policy,
		agent=agent,
		agent_run=agent_run,
		surface=surface,
		from_date=from_date,
		to_date=to_date,
		limit=limit,
	)


# -- replay_policy --------------------------------------------------------------------------


def replay_policy(
	decision_call: str,
	target_policy_version: str,
	*,
	candidate_source: str | None = None,
	candidate_resolver_id: str | None = None,
	candidates: Any = None,
) -> dict:
	"""Rerun a stored Decision Call's request against a different (newer) published policy
	version, using ``service.run_policy`` -- the same entry point every production caller uses,
	so a replay is a real, gated run (kill switch, spend cap, throughput) against the exact
	machinery that would be used in production, not a separate simulation path.

	Not persisted as a normal production call: the replay's ``surface`` is set to
	``"Replay:<original surface>"`` and its ``origin_type`` to ``"Playground"`` with
	``owner_user`` set to the calling user (D17: no new auth scheme -- this is the same
	Playground-shaped Manual call ``api.run_decision`` already makes). This is the "persist with
	a clearly marked purpose" option from this task's brief rather than a silent no-persist mode:
	``service.run_policy`` (out of this task's file scope) has no flag to skip its telemetry
	sink, and skipping it here would mean a replay leaves no audit trail at all, including on
	failure. The marked ``surface`` value keeps a replay out of ``get_policy_metrics``/
	``get_shadow_agreement`` results for the real surface (those filter by the original surface
	name) and out of ``api.get_binding_stats`` (which filters by ``(agent, surface, policy)`` of
	a real binding) without needing a schema change.

	What a replay can and cannot reconstruct from the stored call:

	- **State**: ``Decision Call.state_snapshot`` is only populated when the original policy had
	  ``store_state=True`` (``persistence.py``). Without it there is nothing to replay against,
	  so this raises rather than silently running with ``state=None`` (a policy's questions are
	  answered *from* the state; running with none is not "the same request against a newer
	  version", it is a different request).
	- **Candidates**: ``Decision Call.candidate_ids_json`` stores ids only -- no descriptions
	  (``telemetry.make_decision_call`` never persists ``Option.description``). Reconstructed
	  candidates therefore have an empty ``description``, which can change a backend's answer for
	  policies whose questions read the description text. Pass ``candidates`` (a list of
	  ``{"id", "description"}``) to override with better data when available (e.g. a caller that
	  still has the original request in hand); otherwise this is a known, accepted precision
	  loss, not a bug.
	- **candidate_source**: not persisted on ``Decision Call`` at all (see ``types.DecisionRequest``
	  vs ``telemetry.DecisionCall`` -- the field exists on the request, not the stored call), so
	  it cannot be recovered from history. Required by the runtime only when the target version
	  has a ``select`` question (``runtime.py``: "if select_questions and candidate_source is
	  None"); pass it explicitly when replaying such a policy, else this raises whatever
	  ``run_policy``/the runtime raises for a missing provenance declaration -- this function
	  does not guess one.
	- **question_snapshot**: the DocType field exists but ``persistence.persist`` never writes
	  it, so there is nothing to compare the target version's questions against; a replay simply
	  runs the target version's own current question set, exactly as a fresh call to that version
	  would.

	Args:
		decision_call: The stored ``Decision Call`` docname to replay. Read access is enforced
			by ``doc.check_permission("read")`` -- the same D5 rule ``api.get_decision_call``
			uses.
		target_policy_version: ``Decision Policy Version`` docname to run against. Must belong
			to the same ``Decision Policy`` as the original call and be Published or Retired
			(the same rule ``service._resolve_policy`` applies to a pinned version).
		candidate_source: Override for the request's declared candidate provenance (a
			``CandidateSource`` value). See "candidate_source" above.
		candidate_resolver_id: Passed straight through to ``service.run_policy`` alongside
			``candidate_source`` -- required by the runtime whenever ``candidate_source`` is
			given and is not ``"policy_options"`` (``runtime._validate_request_candidates``).
		candidates: Override for the candidate/option list (JSON-decoded list of
			``{"id", "description"}`` mappings, or already-decoded). Defaults to the original
			call's ``candidate_ids_json`` with empty descriptions.

	Returns:
		``{original_decision_call, original_policy_version, target_policy_version,
		service_result, limitations}`` where ``service_result`` is the raw, un-serialized
		``huf.ai.decision.types.ServiceResult`` (``api.replay_policy`` pops and serializes it
		through the same ``_serialize_service_result`` helper ``run_decision`` uses, so raw
		backend metadata stays admin-gated in one place, and ``ServiceResult.decision_call`` is
		the replay's own persisted docname) and ``limitations`` restates the bullets above as
		short machine-readable strings for a UI to surface next to the result.

	Raises:
		frappe.DoesNotExistError: unknown ``decision_call`` or ``target_policy_version``.
		frappe.PermissionError: caller cannot read the original ``Decision Call`` (D5).
		frappe.ValidationError: no ``state_snapshot`` to replay, or ``target_policy_version``
			does not belong to the same policy as the original call, or is not
			Published/Retired.
		ValueError: propagated from ``service.run_policy`` for any other bad call shape (e.g. a
			missing ``candidate_source`` the target version's questions require).
	"""
	original = frappe.get_doc("Decision Call", decision_call)
	original.check_permission("read")

	if not original.policy:
		frappe.throw(
			_("Decision Call {0} has no Decision Policy (it was an ad-hoc/definition call) and cannot be replayed against a policy version.").format(decision_call),
			frappe.ValidationError,
		)

	version_doc = frappe.get_doc("Decision Policy Version", target_policy_version)
	if version_doc.policy != original.policy:
		frappe.throw(
			_("target_policy_version {0} belongs to policy {1}, not {2} (the original call's policy).").format(
				target_policy_version, version_doc.policy, original.policy
			),
			frappe.ValidationError,
		)
	if version_doc.status not in ("Published", "Retired"):
		frappe.throw(
			_("target_policy_version {0} must be Published or Retired to replay against.").format(target_policy_version),
			frappe.ValidationError,
		)

	if not original.state_snapshot:
		frappe.throw(
			_(
				"Decision Call {0} has no stored state_snapshot to replay -- its policy ran with "
				"store_state disabled at the time."
			).format(decision_call),
			frappe.ValidationError,
		)
	try:
		state = json.loads(original.state_snapshot)
	except (TypeError, ValueError):
		state = original.state_snapshot  # stored as plain text, not JSON -- pass through as-is

	limitations = [
		"state: replayed from state_snapshot (only available because store_state was enabled on the original run).",
	]

	if candidates is not None:
		decoded_candidates = json.loads(candidates) if isinstance(candidates, str) else candidates
		parsed_candidates = tuple(
			item if isinstance(item, Option) else Option(id=str(item["id"]), description=str(item.get("description", "")))
			for item in decoded_candidates
		)
		limitations.append("candidates: caller-supplied override (not reconstructed from history).")
	else:
		candidate_ids = json.loads(original.candidate_ids_json) if original.candidate_ids_json else []
		parsed_candidates = tuple(Option(id=candidate_id, description="") for candidate_id in candidate_ids)
		limitations.append(
			"candidates: reconstructed from candidate_ids_json (ids only -- original descriptions were never "
			"persisted and are empty here)."
		)

	candidate_source_enum = CandidateSource(candidate_source) if candidate_source else None
	if candidate_source_enum is None:
		limitations.append(
			"candidate_source: not persisted on Decision Call and not supplied here; will raise if the "
			"target policy version has a select question requiring it."
		)

	origin = DecisionOrigin(origin_type="Playground", owner_user=frappe.session.user)

	result = service.run_policy(
		policy=original.policy,
		state=state,
		candidates=parsed_candidates,
		candidate_source=candidate_source_enum,
		candidate_resolver_id=candidate_resolver_id,
		mode=service.MODE_MANUAL,
		surface=f"Replay:{original.surface or 'unknown'}"[:128],
		origin=origin,
		policy_version=target_policy_version,
	)

	return {
		"original_decision_call": original.name,
		"original_policy_version": original.policy_version,
		"target_policy_version": target_policy_version,
		"service_result": result,
		"limitations": limitations,
	}
