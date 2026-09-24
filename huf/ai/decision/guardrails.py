"""Opt-in semantic guardrail decisions layered after hard validation.

PLAN.md §3.6 ("Runtime behavior per surface" table, row "Input/Output Guardrail, Output
Verification") and §3.19 ("Failure modes"). These three surfaces are judge questions --
"is this text safe/verified?" -- not narrow-a-candidate-list surfaces, so they do not go
through :func:`huf.ai.decision.agent_surfaces.decide_for_surface` (built for
Option/subset shapes). This module is their purpose-built equivalent: resolve the
Agent's bound binding for the surface, run it through
:func:`huf.ai.decision.service.run_policy` with no candidates, and turn the normalized
judge answer into a pass/block verdict the caller applies.

Hard security invariant (I-DR1, P3): a "safe"/pass verdict from here must NEVER be used
to skip or widen any HUF permission/capability check that already runs elsewhere in the
request path. This module only ever narrows what may proceed (it can turn an otherwise-
allowed request into a blocked one); it never grants access, never bypasses
``resolve_run_identity_and_authorize``/``assert_agent_access``/``has_capability``/model
override checks, and is not even consulted by them. See
``huf/ai/decision/tests/test_guardrails_decision.py::GuardrailNeverWidensPermissionsTest``
for the regression test proving this.

Per-mode contract (D6, D9, D14, §3.19), mirroring ``agent_surfaces.decide_for_surface``:

- **Off / no binding** -- :func:`huf.ai.decision.binding.resolve_agent_decision_binding`
  returns ``None``; the caller proceeds exactly as today. No network, no ``run_policy``
  call.
- **Shadow** (D6) -- ``run_policy(..., mode="Shadow")`` enqueues the job and returns
  immediately; the caller proceeds exactly as if the binding were Off. Log only, never
  applied to the run.
- **Advise** -- not offered for these surfaces (D18: "Not offered for ... Input/Output
  Guardrail, Output Verification ... the UI hides it and the server rejects it").
  ``resolve_agent_decision_binding`` already downgrades a stray ``Advise`` row on these
  surfaces to Off (``huf.ai.decision.binding.ADVISE_SURFACES`` excludes them), so this
  module never receives it; it is not re-checked here.
- **Enforce** -- runs inline under budget. A successful judge answer is turned into
  allow/reject by :func:`evaluate_guardrail`. ``allow`` proceeds; ``reject`` blocks with a
  safe, user-facing message (the guardrail actively judged the content unsafe -- this is
  not a failure path, so the binding's ``failure_action`` does not apply).
- **Disabled (kill switch off, D12), timeout, error, budget-exceeded, throughput-exhausted,
  or any other non-``SUCCESS`` service result, and an ``uncertain`` judge verdict (missing/
  low-confidence answer)** -- all treated as "the guardrail could not render a verdict".
  Defense-in-depth (this module's ADR): a broken guardrail must not silently open the gate,
  so these degrade to the resolved policy's own ``fallback_action`` (PLAN.md §3.19: "policy
  `failure_action` (default `fail_closed`)"), read via :func:`_policy_failure_action`.
  ``fail_closed`` (the default, and anything unrecognized) blocks; an explicit
  ``fail_open`` proceeds. The one exception is the kill switch itself (``DISABLED``) and
  "no binding" -- both mean the guardrail was never configured/enabled at all, so they
  proceed exactly as today, same as Off.

Callers (``huf.ai.agent_integration.run_agent_sync``/``_execute_agent_run`` and
``run_agent_stream``, T8.03) are expected to:

1. Call :func:`check_input_guardrail` before the run starts, with the raw user prompt.
2. Call :func:`check_output_guardrail` and :func:`check_output_verification` after the
   final output is produced, before it is persisted or returned.
3. On ``GuardrailResult.action == "block"``: do not persist/return the real content --
   substitute ``GuardrailResult.message`` (a safe, generic string; never raw policy/backend
   text) and stop, exactly as if the request had been refused for any other reason.
4. On ``"proceed"``: continue exactly as if no guardrail existed. Never skip or loosen any
   other check because of this result (I-DR1, P3 above).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import frappe

from huf.ai.decision import service
from huf.ai.decision.binding import resolve_agent_decision_binding
from huf.ai.decision.types import DecisionOrigin, DecisionResponse, DecisionStatus, QuestionKind


@dataclass(frozen=True, slots=True)
class GuardrailDecision:
	status: str
	action: str
	reason: str


def evaluate_guardrail(response: DecisionResponse, *, reject_threshold: float = 0.5, uncertain_action: str = "review") -> GuardrailDecision:
	"""Map a normalized judge response to allow/reject/uncertain without mutating input."""
	if not 0 <= reject_threshold <= 1:
		raise ValueError("reject_threshold must be in [0, 1]")
	if response.status != DecisionStatus.SUCCESS:
		return GuardrailDecision("uncertain", uncertain_action, response.error_code or "decision_failed")
	answer = next(iter(response.answers.values()), None)
	if answer is None or answer.kind != QuestionKind.JUDGE or not isinstance(answer.value, (int, float)):
		return GuardrailDecision("uncertain", uncertain_action, "guardrail_missing_judge")
	if answer.confidence is None:
		return GuardrailDecision("uncertain", uncertain_action, "guardrail_missing_confidence")
	if answer.confidence < reject_threshold:
		return GuardrailDecision("uncertain", uncertain_action, "guardrail_low_confidence")
	return GuardrailDecision("reject" if answer.value >= reject_threshold else "allow", "reject" if answer.value >= reject_threshold else "allow", "guardrail_decision")


# -- run_agent_sync / run_agent_stream integration (T8.03) --------------------------------


@dataclass(frozen=True, slots=True)
class GuardrailResult:
	"""What a caller (``run_agent_sync`` / ``run_agent_stream``) does with a guardrail check.

	``action`` is always ``"proceed"`` or ``"block"`` -- callers only need this one field to
	decide what to do; the rest is diagnostic/telemetry context.
	"""

	action: str  # "proceed" | "block"
	status: str  # "off" | "disabled" | "shadow" | "allow" | "reject" | "uncertain" | "error"
	reason: str
	message: str | None
	decision_call: str | None


#: Fixed, generic, data-only messages -- never raw policy criteria, backend text, or state
#: content (I-DR1: nothing from the judged text or the provider's reasoning is echoed back).
_SAFE_BLOCK_MESSAGE = {
	"Input Guardrail": "Your message could not be processed by this assistant. Please rephrase and try again.",
	"Output Guardrail": "The response was withheld by a safety check.",
	"Output Verification": "The response could not be verified and was withheld.",
}

_PROCEED = "proceed"
_BLOCK = "block"

#: ``state["text"]`` truncation length -- matches the request-text truncation convention
#: already used by ``huf.ai.decision.agent_surfaces.build_surface_state``.
_TEXT_MAX_CHARS = 4000

#: Throttle for unexpected-exception logging, same cadence/reasoning as
#: ``huf.ai.decision.agent_surfaces._log_unexpected`` (one Error Log per surface per hour,
#: not one per agent turn).
_LOG_THROTTLE_SECONDS = 3600
_last_logged_at: dict[str, float] = {}


def check_input_guardrail(
	agent_doc: Any,
	input_text: str,
	origin: DecisionOrigin,
	*,
	conversation_id: str | None = None,
	agent_run_id: str | None = None,
) -> GuardrailResult:
	"""Judge ``input_text`` (the user's prompt) against the Agent's Input Guardrail binding.

	Called before the run starts. See module docstring for the full per-mode contract.
	"""
	return _check_guardrail_surface(
		"Input Guardrail", agent_doc, input_text, origin,
		conversation_id=conversation_id, agent_run_id=agent_run_id,
	)


def check_output_guardrail(
	agent_doc: Any,
	output_text: str,
	origin: DecisionOrigin,
	*,
	conversation_id: str | None = None,
	agent_run_id: str | None = None,
) -> GuardrailResult:
	"""Judge ``output_text`` (the model's final output) against the Output Guardrail binding.

	Called after the final output is produced, before it is persisted or returned.
	"""
	return _check_guardrail_surface(
		"Output Guardrail", agent_doc, output_text, origin,
		conversation_id=conversation_id, agent_run_id=agent_run_id,
	)


def check_output_verification(
	agent_doc: Any,
	output_text: str,
	origin: DecisionOrigin,
	*,
	conversation_id: str | None = None,
	agent_run_id: str | None = None,
) -> GuardrailResult:
	"""Judge ``output_text`` against the Output Verification binding (e.g. factuality/policy
	compliance, as distinct from the safety judgment of Output Guardrail).

	Called after the final output is produced, alongside :func:`check_output_guardrail`.
	"""
	return _check_guardrail_surface(
		"Output Verification", agent_doc, output_text, origin,
		conversation_id=conversation_id, agent_run_id=agent_run_id,
	)


def _check_guardrail_surface(
	surface: str,
	agent_doc: Any,
	text: str,
	origin: DecisionOrigin,
	*,
	conversation_id: str | None,
	agent_run_id: str | None,
) -> GuardrailResult:
	"""Shared core for the three ``check_*`` entry points above. Never raises."""
	try:
		resolved = resolve_agent_decision_binding(agent_doc, surface)
	except Exception as exc:  # noqa: BLE001 - must never raise into the agent run path
		_log_unexpected(surface, exc)
		return GuardrailResult(action=_PROCEED, status="error", reason="binding_resolution_failed", message=None, decision_call=None)

	if resolved is None:
		# Off, missing, or disabled binding: proceed exactly as today (D14).
		return GuardrailResult(action=_PROCEED, status="off", reason="no_binding", message=None, decision_call=None)

	state = _build_state(text, conversation_id=conversation_id, agent_run_id=agent_run_id)

	try:
		result = service.run_policy(
			resolved.policy,
			state=state,
			mode=resolved.mode,
			surface=surface,
			origin=origin,
		)
	except Exception as exc:  # noqa: BLE001 - must never raise into the agent run path
		_log_unexpected(surface, exc)
		return _apply_failure_action(surface, resolved.policy, reason="exception")

	if result.status == service.DISABLED:
		# Kill switch off (D12): the whole runtime is off, not just this binding -- proceed
		# exactly as today, same as Off/no binding.
		return GuardrailResult(action=_PROCEED, status="disabled", reason="kill_switch_off", message=None, decision_call=None)

	if result.status == service.SHADOW_ENQUEUED:
		# Shadow (D6): log only, never applied. The job records its own answer; the run
		# proceeds normally regardless of what it eventually finds.
		return GuardrailResult(action=_PROCEED, status="shadow", reason="shadow_logged", message=None, decision_call=None)

	if result.response is None or result.status != DecisionStatus.SUCCESS:
		# BUDGET_EXCEEDED, TIMEOUT, FAILED, UNAVAILABLE, THROUGHPUT_BUDGET_EXHAUSTED, ...:
		# the guardrail could not render a verdict. Defense-in-depth -- degrade to the
		# policy's own failure_action rather than silently opening the gate.
		return _apply_failure_action(
			surface, resolved.policy, reason=str(result.status), decision_call=result.decision_call,
		)

	decision = evaluate_guardrail(result.response)
	if decision.status == "allow":
		return GuardrailResult(action=_PROCEED, status="allow", reason=decision.reason, message=None, decision_call=result.decision_call)
	if decision.status == "reject":
		return GuardrailResult(
			action=_BLOCK, status="reject", reason=decision.reason,
			message=_SAFE_BLOCK_MESSAGE.get(surface, "The request could not be completed."),
			decision_call=result.decision_call,
		)
	# "uncertain" (missing judge answer, missing/low confidence): treat like any other
	# failure to render a verdict.
	return _apply_failure_action(surface, resolved.policy, reason=decision.reason, decision_call=result.decision_call)


def _apply_failure_action(
	surface: str, policy_name: str, *, reason: str, decision_call: str | None = None,
) -> GuardrailResult:
	"""Turn "the guardrail could not render a verdict" into proceed/block per the resolved
	policy's own ``fallback_action`` (PLAN.md §3.19: "policy `failure_action` (default
	`fail_closed`)"). ``fail_open`` (case-insensitive) is the only recognized opt-out;
	anything else -- ``fail_closed``, unset, or any other value -- blocks. Never raises.
	"""
	failure_action = _policy_failure_action(policy_name)
	if failure_action == "fail_open":
		return GuardrailResult(action=_PROCEED, status="uncertain", reason=reason, message=None, decision_call=decision_call)
	return GuardrailResult(
		action=_BLOCK, status="uncertain", reason=reason,
		message=_SAFE_BLOCK_MESSAGE.get(surface, "The request could not be completed."),
		decision_call=decision_call,
	)


def _policy_failure_action(policy_name: str) -> str:
	"""Best-effort read of the resolved ``Decision Policy``'s ``fallback_action``, defaulting
	to ``"fail_closed"`` on any missing/unpublished/malformed policy or lookup error -- this
	must never raise, and must never default to the open side.
	"""
	try:
		import json as _json

		policy_doc = frappe.get_cached_doc("Decision Policy", policy_name)
		version_name = policy_doc.current_version
		if not version_name:
			return "fail_closed"
		version_doc = frappe.get_cached_doc("Decision Policy Version", version_name)
		definition = _json.loads(version_doc.definition_json or "{}")
		action = definition.get("fallback_action")
		if isinstance(action, str) and action.strip().lower() == "fail_open":
			return "fail_open"
		return "fail_closed"
	except Exception:  # noqa: BLE001 - best-effort only; default stays fail_closed
		return "fail_closed"


def _build_state(text: str, *, conversation_id: str | None, agent_run_id: str | None) -> dict:
	state: dict[str, Any] = {"text": (text or "")[:_TEXT_MAX_CHARS]}
	if conversation_id:
		state["conversation_id"] = conversation_id
	if agent_run_id:
		state["agent_run_id"] = agent_run_id
	return state


def _log_unexpected(surface: str, exc: Exception) -> None:
	"""Best-effort, throttled ``frappe.log_error``, same cadence as
	``huf.ai.decision.agent_surfaces._log_unexpected``.
	"""
	now = time.monotonic()
	if now - _last_logged_at.get(surface, 0.0) < _LOG_THROTTLE_SECONDS:
		return
	_last_logged_at[surface] = now
	try:
		frappe.log_error(title=f"decision.guardrails:{surface}"[:140], message=str(exc)[:2000])
	except Exception:  # noqa: BLE001 - logging must never raise
		pass
