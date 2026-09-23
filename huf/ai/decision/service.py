"""``run_policy`` -- the single entry point every HUF surface uses for one decision.

PLAN.md §4.7 (Service, PR 2A). Every consumer (Agent bindings, the Hub Orchestrator, the
Flow Decision Router, Automation Decide, the `decide` tool, the Playground and the public
`run_decision` API) calls :func:`run_policy`; nothing constructs a :class:`DecisionRuntime`
or calls :func:`~huf.ai.decision.deployment_loader.load_chain` directly. That means the
contract here -- the exact status values, when a ``Decision Call`` is persisted, and how a
kill switch / a missing key / a slow provider degrade -- is load-bearing for the whole
programme; see PLAN.md §3.19 ("Failure modes") for the table this module implements.

Dispatch, in order:

1. Kill switch (``Agent Settings.decision_runtime_enabled``, D12) -> :data:`DISABLED`. Zero
   network, no chain construction, nothing persisted.
2. Resolve the policy: a published ``Decision Policy Version`` (optionally pinned by name,
   D10 -- a Flow Run pins the version it started with so a later republish cannot change a
   running Flow's behavior), or a validated ad-hoc definition (no ``Decision Policy`` row).
3. ``mode="Shadow"``: enqueue and return :data:`SHADOW_ENQUEUED` immediately (D6 -- Shadow
   must never add latency to the surface that triggered it). The job itself
   (``huf.ai.decision.service.run_shadow_job``, throughput/rate-cap dropping, T2A.11) is a
   separate task; this module only wires the dispatch and the reusable core
   (:func:`_execute_inline`) that job will call with ``deadline=None``.
4. ``mode in {"Enforce", "Advise", "Manual"}``: same inline path. ``Advise`` is rejected
   (surface not in :data:`~huf.ai.decision.binding.ADVISE_SURFACES`) before anything else
   runs; it is otherwise identical to Enforce -- it never narrows ``candidates``, that is the
   calling surface's job when it turns the answer into a hint instead of a filter (D18).
   ``Manual`` is the label the Playground/API path (T2A.8, `run_decision`) uses for a call
   with no Agent Decision Binding behind it; it takes the same inline path as Enforce.
5. Deadline = ``latency_budget_ms`` or the surface default (PLAN.md §3.6 latency table).
   :func:`~huf.ai.decision.deployment_loader.load_chain` builds live backends eagerly and
   turns a missing-key / unhealthy deployment into simply not being a candidate (it never
   raises for that); an empty chain flows into
   :meth:`~huf.ai.decision.runtime.DecisionRuntime.evaluate_deployment_chain`, which already
   turns "no candidates" into a normal ``FAILED`` :class:`DecisionResponse` -- so a provider
   with no configured key degrades to the policy fallback exactly like a down provider,
   without this module needing a separate branch for it.
6. :meth:`DecisionRuntime.evaluate_deployment_chain` runs against a telemetry sink built on
   :func:`~huf.ai.decision.persistence.make_frappe_telemetry_sink`, wrapped here
   (:func:`_capturing_sink`) so ``mode`` and ``origin`` -- both of which
   :meth:`DecisionRuntime._emit` does not know about -- land on the persisted row, and so the
   inserted docname is available for :attr:`ServiceResult.decision_call` (see NOTES in the
   task report for why this wrapping was needed instead of a ``DecisionRuntime`` edit).
7. On any non-``SUCCESS`` result, :meth:`DecisionRuntime.apply_policy_fallback` records the
   policy's ``fallback_action`` and persists a second row for it (existing, tested runtime
   behavior -- one row per deployment attempt plus one for the fallback wrap).
8. Spend accounting (D15, T2A.17) is **not implemented here**. The hook point is the comment
   in :func:`_execute_inline` marked ``NOTE(T2A.17 hook)``: a pre-check
   (``RunBudget.check_spend``) belongs immediately after step 2 (policy resolved, before
   ``load_chain``) for an Enforce/Manual call whose ``origin.agent_run`` is set, returning
   :data:`BUDGET_EXCEEDED` with zero network when it would exceed the cap; an after-persist
   hook (``accounting.record_call``) belongs right after step 7, for every completed call
   (Enforce, Manual or Shadow, success or billed failure).
9. Returns :class:`~huf.ai.decision.types.ServiceResult`.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, replace
from typing import Any

import frappe

from huf.ai.decision.binding import ADVISE_SURFACES
from huf.ai.decision.deployment_loader import load_chain
from huf.ai.decision.persistence import make_frappe_telemetry_sink
from huf.ai.decision.policy import validate_policy_data
from huf.ai.decision.runtime import DecisionRuntime
from huf.ai.decision.telemetry import DecisionCall
from huf.ai.decision.types import (
	CandidateSource,
	DecisionOrigin,
	DecisionPolicy,
	DecisionRequest,
	DecisionStatus,
	Option,
	ServiceResult,
)

# -- Service-level statuses ------------------------------------------------------------
#
# DecisionStatus (types.py) enumerates the outcome of one *executed* decision -- it is
# exactly the Select options on the `Decision Call` DocType (decision_call.json `status`),
# because every DecisionStatus value gets persisted as one. The three outcomes below never
# reach a Decision Call the same way, so they are deliberately kept outside that enum
# rather than added to it (types.py is not in this task's file scope; extending an enum
# additively there would be a trivial change but these three are conceptually a different
# axis -- "did the call run at all" vs. "how did it end" -- so plain string sentinels here
# both avoid the out-of-scope edit and keep that distinction visible at the call site):
#   - DISABLED: kill switch is off (D12). Zero network, nothing built, nothing persisted.
#   - SHADOW_ENQUEUED: the job (T2A.11) has not run yet; its own success/failure is recorded
#     against `shadow_of` by that job, not by this ServiceResult.
#   - BUDGET_EXCEEDED: reserved for T2A.17 (RunBudget spend-cap pre-check). Not returned by
#     this module yet; see the NOTE(T2A.17 hook) comment in `_execute_inline`.
DISABLED = "disabled"
SHADOW_ENQUEUED = "shadow_enqueued"
BUDGET_EXCEEDED = "budget_exceeded"

# Mode values, matching `Agent Decision Binding.mode` (Off/Shadow/Advise/Enforce) plus
# `Decision Call.mode` (Manual/Shadow/Advise/Enforce -- PLAN.md §4.1: "mode Select gains
# Manual for Playground/API calls"). "Off" is never passed to run_policy: a binding resolved
# as Off means the surface does not call this function at all (see
# huf.ai.decision.binding.resolve_agent_decision_binding).
MODE_SHADOW = "Shadow"
MODE_ADVISE = "Advise"
MODE_ENFORCE = "Enforce"
MODE_MANUAL = "Manual"
_INLINE_MODES = frozenset({MODE_ENFORCE, MODE_ADVISE, MODE_MANUAL})
_VALID_MODES = _INLINE_MODES | {MODE_SHADOW}

#: PLAN.md §3.6 "Latency (D6)": per-surface default enforce/advise budgets in milliseconds,
#: overridable per call by `latency_budget_ms` (and per Agent Decision Binding row by its own
#: `latency_budget_ms`, resolved by the caller before it reaches here). Surfaces the plan does
#: not give a default for (Agent Routing, Flow Decision Router, Automation Decide, and any
#: Manual/Playground/API call with no surface convention) fall back to
#: `_DEFAULT_LATENCY_BUDGET_MS`, chosen as the same conservative budget as the guardrail
#: surfaces since those, like an ungoverned surface, gate a whole run rather than one tool
#: pick.
_SURFACE_LATENCY_BUDGET_MS = {
	"Tool Selection": 1500,
	"Skill Selection": 1500,
	"Procedure Selection": 1500,
	"Model Routing": 1500,
	"RAG Filter": 2000,
	"Context Relevance": 2000,
	"Input Guardrail": 3000,
	"Output Guardrail": 3000,
	"Output Verification": 3000,
	"Agent Tool": 5000,  # the `decide` tool (D9)
}
_DEFAULT_LATENCY_BUDGET_MS = 3000


def run_policy(
	policy: str | None = None,
	*,
	definition: Mapping[str, Any] | None = None,
	decision_model: str | None = None,
	state: Any = None,
	candidates: Sequence[Option] = (),
	candidate_source: CandidateSource | None = None,
	candidate_resolver_id: str | None = None,
	mode: str = MODE_ENFORCE,
	surface: str,
	origin: DecisionOrigin,
	policy_version: str | None = None,
	pinned_deployment: str | None = None,
	latency_budget_ms: int | None = None,
) -> ServiceResult:
	"""Run one decision for one surface call. The only entry point (PLAN.md §4.7).

	Args:
		policy: ``Decision Policy`` docname. Mutually exclusive with ``definition``.
		definition: Ad-hoc policy JSON in the shape
			:func:`~huf.ai.decision.policy.validate_policy_data` accepts (no ``Decision
			Policy`` row is read or created). Mutually exclusive with ``policy``; requires
			``decision_model`` since there is no policy row to read a default model from.
		decision_model: ``Decision Model`` docname (its ``model_key``). Required for an
			ad-hoc ``definition``. Optional override when ``policy`` is given -- normally the
			resolved ``Decision Policy Version.default_model`` (or ``Decision
			Policy.default_model`` when the version has none) is used.
		state: Provider-visible state for the questions being asked. Opaque to this module;
			:class:`DecisionRuntime` hashes/redacts/snapshots it per the policy's
			``store_state`` flag.
		candidates: Closed candidate/option set for ``select``/``score`` questions. Passed
			through unchanged; validated by :class:`DecisionRuntime` (candidate provenance,
			uniqueness, coverage of any ``select`` question's options).
		candidate_source / candidate_resolver_id: Declared provenance for ``candidates``
			(:class:`~huf.ai.decision.types.CandidateSource`); required by
			:class:`DecisionRuntime` whenever a ``select`` question is present.
		mode: One of ``"Enforce"``, ``"Advise"``, ``"Manual"`` (same inline path; see module
			docstring) or ``"Shadow"`` (enqueues and returns immediately). ``"Off"`` is never
			passed here -- the caller does not invoke this function for an Off binding.
		surface: One of the ``Agent Decision Binding`` / ``Decision Policy.purpose`` surface
			names (PLAN.md §3.6 table), used for the default latency budget, the Advise
			surface check, and telemetry (`Decision Call.surface`).
		origin: Where this call came from (:class:`DecisionOrigin`); persisted on the
			``Decision Call`` and read back on the Agent Run / Flow Run / Automation views.
			Required -- a Playground/API call still supplies one with
			``origin_type="Playground"`` or ``"API"`` and no other fields.
		policy_version: Explicit ``Decision Policy Version`` docname (D10 -- a Flow Run
			pinning the version it started with). Requires ``policy``; overrides
			``Decision Policy.current_version``. The pinned version may be ``Retired`` (a
			newer one has since published) but must exist and belong to ``policy``.
		pinned_deployment: Passed straight through to
			:func:`~huf.ai.decision.deployment_loader.load_chain` -- narrows the chain to one
			``Decision Deployment`` regardless of priority/default.
		latency_budget_ms: Overrides the surface default deadline.

	Returns:
		:class:`ServiceResult`. ``status`` is either :data:`DISABLED`,
		:data:`SHADOW_ENQUEUED`, or a :class:`DecisionStatus` value (as its plain string,
		e.g. ``"success"``, ``"timeout"``). ``decision_call`` is the persisted ``Decision
		Call`` docname when one was written (never for :data:`DISABLED` or
		:data:`SHADOW_ENQUEUED`; best-effort -- ``None`` if the telemetry sink itself failed,
		since a sink failure must never change the decision result, PLAN.md §4.7 step 6 /
		``DecisionRuntime._emit``).

	Raises:
		ValueError: Bad call shape -- both or neither of ``policy``/``definition``, an
			ad-hoc call with no ``decision_model``, ``policy_version`` without ``policy``, an
			unresolvable policy/version/model, or an unknown ``mode``.
		frappe.ValidationError: ``mode="Advise"`` on a ``surface`` outside
			``ADVISE_SURFACES`` (PLAN.md §3.19: "Save rejected with a message naming the
			supported modes"; ``Agent.validate``, T1.22, is the save-time half of this same
			rule -- this is the runtime half, for any caller that reaches here directly).
	"""
	if mode not in _VALID_MODES:
		raise ValueError(f"mode must be one of {sorted(_VALID_MODES)}, got {mode!r}")
	if mode == MODE_ADVISE and surface not in ADVISE_SURFACES:
		raise frappe.ValidationError(
			f"Advise mode is not supported on surface {surface!r}. "
			f"Supported surfaces: {', '.join(sorted(ADVISE_SURFACES))}."
		)
	if not isinstance(origin, DecisionOrigin):
		raise ValueError("origin is required and must be a DecisionOrigin")

	# 1. Kill switch (D12). A single scalar read -- no doc load, no chain, no network.
	if not frappe.db.get_single_value("Agent Settings", "decision_runtime_enabled"):
		return ServiceResult(status=DISABLED)

	# 2. Resolve policy: published version, pinned version (D10), or validated ad-hoc.
	resolved = _resolve_policy(
		policy=policy,
		definition=definition,
		decision_model=decision_model,
		policy_version=policy_version,
	)

	deadline = _deadline(surface, latency_budget_ms)

	# 3. Shadow never touches the hot path (D6): enqueue and return immediately.
	if mode == MODE_SHADOW:
		return _enqueue_shadow(
			resolved=resolved,
			state=state,
			candidates=candidates,
			candidate_source=candidate_source,
			candidate_resolver_id=candidate_resolver_id,
			surface=surface,
			origin=origin,
			pinned_deployment=pinned_deployment,
		)

	# 4-9. Enforce / Advise / Manual: same inline path (D18).
	return _execute_inline(
		resolved=resolved,
		state=state,
		candidates=candidates,
		candidate_source=candidate_source,
		candidate_resolver_id=candidate_resolver_id,
		surface=surface,
		mode=mode,
		origin=origin,
		pinned_deployment=pinned_deployment,
		deadline=deadline,
	)


# -- Policy resolution -------------------------------------------------------------------


class _ResolvedPolicy:
	"""Internal: a normalized policy plus the docnames/model needed to run and persist it."""

	__slots__ = ("policy", "policy_name", "policy_version_name", "decision_model")

	def __init__(
		self,
		*,
		policy: DecisionPolicy,
		policy_name: str | None,
		policy_version_name: str | None,
		decision_model: str,
	) -> None:
		self.policy = policy
		self.policy_name = policy_name
		self.policy_version_name = policy_version_name
		self.decision_model = decision_model


def _resolve_policy(
	*,
	policy: str | None,
	definition: Mapping[str, Any] | None,
	decision_model: str | None,
	policy_version: str | None,
) -> _ResolvedPolicy:
	if policy and definition:
		raise ValueError("Pass either policy or definition, not both")
	if not policy and not definition:
		raise ValueError("Either policy (a Decision Policy name) or definition (ad-hoc) is required")

	if policy is None:
		if policy_version is not None:
			raise ValueError("policy_version requires a named policy")
		if not decision_model:
			raise ValueError("decision_model is required for an ad-hoc policy definition")
		decision_policy = validate_policy_data(definition)
		return _ResolvedPolicy(
			policy=decision_policy,
			policy_name=None,
			policy_version_name=None,
			decision_model=decision_model,
		)

	policy_doc = frappe.get_doc("Decision Policy", policy)
	if not policy_doc.enabled:
		raise ValueError(f"Decision Policy {policy!r} is disabled")

	version_name = policy_version or policy_doc.current_version
	if not version_name:
		raise ValueError(f"Decision Policy {policy!r} has no published version and none was pinned")

	version_doc = frappe.get_doc("Decision Policy Version", version_name)
	if version_doc.policy != policy_doc.name:
		raise ValueError(f"Decision Policy Version {version_name!r} does not belong to policy {policy!r}")
	if version_doc.status not in ("Published", "Retired"):
		# A pinned version may since have been retired by a newer publish (D10: that is
		# exactly what pinning protects a running Flow against); Draft is not runnable.
		raise ValueError(f"Decision Policy Version {version_name!r} is not published")

	decision_policy = validate_policy_data(json.loads(version_doc.definition_json))
	decision_policy = replace(decision_policy, version=version_doc.name)

	resolved_model = decision_model or version_doc.default_model or policy_doc.default_model
	if not resolved_model:
		raise ValueError(f"Decision Policy {policy!r} has no default_model and none was given")

	return _ResolvedPolicy(
		policy=decision_policy,
		policy_name=policy_doc.name,
		policy_version_name=version_doc.name,
		decision_model=resolved_model,
	)


def _deadline(surface: str, latency_budget_ms: int | None) -> float:
	budget_ms = latency_budget_ms or _SURFACE_LATENCY_BUDGET_MS.get(surface, _DEFAULT_LATENCY_BUDGET_MS)
	if budget_ms <= 0:
		raise ValueError("latency_budget_ms must be positive")
	return time.monotonic() + budget_ms / 1000.0


# -- Inline execution (Enforce / Advise / Manual) ----------------------------------------


def _execute_inline(
	*,
	resolved: _ResolvedPolicy,
	state: Any,
	candidates: Sequence[Option],
	candidate_source: CandidateSource | None,
	candidate_resolver_id: str | None,
	surface: str,
	mode: str,
	origin: DecisionOrigin,
	pinned_deployment: str | None,
	deadline: float | None,
) -> ServiceResult:
	"""Steps 4-8 of PLAN.md §4.7. Shared core for the inline path here and, by design, for
	T2A.11's ``run_shadow_job`` (same function, ``mode="Shadow"``, ``deadline=None`` -- a
	Shadow job has no wall-clock budget beyond each provider's own timeout, per the module
	docstring's point 3 / PLAN.md §4.7 step 3's "no deadline beyond provider timeout").
	"""
	chain = load_chain(
		decision_model=resolved.decision_model,
		pinned_deployment=pinned_deployment,
		deadline=deadline,
	)

	request = DecisionRequest(
		policy=resolved.policy,
		state=state,
		identity=chain.requested_identity,
		surface=surface,
		candidates=tuple(candidates),
		candidate_source=candidate_source,
		candidate_resolver_id=candidate_resolver_id,
	)

	# NOTE(T2A.17 hook): the spend-cap pre-check belongs here, before load_chain/evaluate --
	# `RunBudget.check_spend(estimate)` for an Enforce/Manual call whose `origin.agent_run`
	# is set, returning ServiceResult(status=BUDGET_EXCEEDED) with zero network when it would
	# exceed `Agent Settings.spend_cap_usd`. Not implemented here (T2A.10/T2A.11 scope).

	persisted: list[str | None] = [None]
	runtime = DecisionRuntime(
		telemetry_sink=_capturing_sink(origin=origin, mode=mode, policy_name=resolved.policy_name, box=persisted)
	)
	response = runtime.evaluate_deployment_chain(request, chain, deadline=deadline)

	if response.status != DecisionStatus.SUCCESS:
		response = runtime.apply_policy_fallback(request, response, deployments_exhausted=True)

	# NOTE(T2A.17 hook): `accounting.record_call(origin, response.usage, ...)` belongs here,
	# after every completed call (Enforce/Manual or Shadow, success or billed failure) --
	# atomically incrementing decision totals on the origin's Agent Run / Flow Run /
	# Automation and `RunBudget.spend_so_far_usd`. Not implemented here.

	return ServiceResult(
		status=response.status,
		response=response,
		decision_call=persisted[0],
		fallback_action=response.policy_fallback_action,
	)


def _capturing_sink(
	*, origin: DecisionOrigin, mode: str, policy_name: str | None, box: list[str | None]
) -> Callable[[DecisionCall], None]:
	"""Wrap ``make_frappe_telemetry_sink()`` to fill in ``mode``/``origin``/``policy``, and
	capture the inserted docname.

	Two things ``DecisionRuntime._emit`` cannot fill in on its own, because it only sees the
	provider-neutral ``DecisionRequest``/``DecisionResponse``, not this module's caller-facing
	arguments:

	- ``mode`` / ``origin``: service-level concepts; changing ``DecisionRuntime``'s
	  constructor to know about them is out of this task's file scope, so the sink is wrapped
	  here instead.
	- ``policy_id`` -> ``Decision Call.policy``: ``make_decision_call`` sets
	  ``DecisionCall.policy_id`` from ``request.policy.policy_id``, the *semantic* id inside
	  a policy's ``definition_json`` (author-chosen, e.g. ``"support_urgency"``) -- not the
	  ``Decision Policy`` docname (autoname is ``field:policy_name``, e.g. ``"Escalate to
	  human_a1b2c3d4"``). ``persistence.py`` writes that value straight into ``policy``, a
	  Link to ``Decision Policy``; unless the two happen to coincide, ``doc.insert()`` fails
	  Frappe's Link-target validation on the very first named-policy call. This overrides
	  ``policy_id`` with the resolved policy's real docname (``None`` for an ad-hoc
	  definition, which has no ``Decision Policy`` row -- the Link stays blank, which is
	  valid; the semantic id and the fingerprint are still on ``policy_fingerprint``).

	Every ``DecisionCall`` the runtime emits (one per deployment attempt, plus one more if
	``apply_policy_fallback`` runs) is replaced with a copy carrying these overrides before it
	reaches the real Frappe sink. ``box[0]`` ends up holding the *last* row written, which is
	exactly the one ``ServiceResult.decision_call`` should point to (the fallback-wrapped row
	on failure, or the successful attempt's row).
	"""
	base_persist = make_frappe_telemetry_sink()

	def sink(call: DecisionCall) -> None:
		enriched = replace(
			call,
			policy_id=policy_name,
			mode=mode,
			origin_type=origin.origin_type,
			agent=origin.agent,
			agent_run=origin.agent_run,
			conversation=origin.conversation,
			flow_run=origin.flow_run,
			flow_node_id=origin.flow_node_id,
			automation=origin.automation,
			owner_user=origin.owner_user,
			shadow_of=origin.shadow_of,
			resolved_deployment=call.resolved_identity.deployment,
			resolved_provider=call.resolved_identity.provider,
		)
		box[0] = base_persist(enriched)

	return sink


# -- Shadow dispatch (T2A.10 wiring; T2A.11 implements run_shadow_job) --------------------


def _enqueue_shadow(
	*,
	resolved: _ResolvedPolicy,
	state: Any,
	candidates: Sequence[Option],
	candidate_source: CandidateSource | None,
	candidate_resolver_id: str | None,
	surface: str,
	origin: DecisionOrigin,
	pinned_deployment: str | None,
) -> ServiceResult:
	"""PLAN.md §4.7 step 3: serialize the request and enqueue, returning immediately.

	``huf.ai.decision.service.run_shadow_job`` (the target below) is T2A.11's function, not
	defined in this module -- ``frappe.enqueue`` resolves the string only when a worker
	dequeues the job, so referencing it ahead of that task landing is safe (nothing here
	calls or imports it). T2A.11 also owns the Shadow rate cap
	(``Agent Settings.decision_shadow_rate_per_minute``) and the per-deployment enforce
	throughput bucket (``throughput.py``); this function only does the unconditional
	dispatch PLAN.md §4.7 step 3 describes as part of ``run_policy`` itself. When T2A.11
	adds the rate cap, it drops/counts *before* this enqueue (or wraps this function) rather
	than after -- enqueuing and then dropping would already have paid the enqueue cost this
	step exists to avoid.
	"""
	payload: dict[str, Any] = {
		"policy": resolved.policy_name,
		"policy_version": resolved.policy_version_name,
		"definition": None if resolved.policy_name else _policy_definition(resolved.policy),
		"decision_model": resolved.decision_model,
		"state": state,
		"candidates": [{"id": item.id, "description": item.description} for item in candidates],
		"candidate_source": candidate_source.value if candidate_source is not None else None,
		"candidate_resolver_id": candidate_resolver_id,
		"surface": surface,
		"origin": asdict(origin),
		"pinned_deployment": pinned_deployment,
	}
	frappe.enqueue(
		"huf.ai.decision.service.run_shadow_job",
		queue="short",
		enqueue_after_commit=True,
		is_async=True,
		**payload,
	)
	return ServiceResult(status=SHADOW_ENQUEUED)


def _policy_definition(policy: DecisionPolicy) -> dict[str, Any]:
	"""Re-serialize a resolved ad-hoc :class:`DecisionPolicy` back to the JSON shape
	:func:`~huf.ai.decision.policy.validate_policy_data` accepts, so an ad-hoc Shadow call
	can be reconstructed from the enqueued payload without re-sending raw Option objects.
	"""
	return {
		"policy_id": policy.policy_id,
		"version": policy.version,
		"minimum_confidence": policy.minimum_confidence,
		"fallback_action": policy.fallback_action,
		"store_state": policy.store_state,
		"max_state_bytes": policy.max_state_bytes,
		"required_modalities": sorted(policy.required_modalities),
		"state_bindings": [{"name": item.name, "path": item.path} for item in policy.state_bindings],
		"questions": [
			{
				"id": question.id,
				"kind": question.kind.value,
				"instructions": question.instructions,
				"options": [{"id": option.id, "description": option.description} for option in question.options],
				"allow_none": question.allow_none,
				"positive_criteria": question.positive_criteria,
				"negative_criteria": question.negative_criteria,
			}
			for question in policy.questions
		],
	}
