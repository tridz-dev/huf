"""Optional Frappe persistence for normalized Decision Call telemetry."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from typing import Any

from huf.ai.decision.telemetry import DecisionCall

#: Decision Call.origin_type (huf/huf/doctype/decision_call/decision_call.json) is a Select
#: whose options are exactly these eight values. Callers across the codebase (agent runs, flow
#: nodes, automations, hub triage, knowledge ingestion, ...) construct DecisionOrigin with looser
#: strings ("Agent Run", "Hub Triage", "knowledge_ingestion", ...); an unrecognized Select value
#: makes the Decision Call insert fail outright, and DecisionRuntime._emit swallows sink failures
#: by design (a telemetry problem must never rewrite the decision result), so the call would be
#: silently dropped. Normalizing here, centrally, means no caller needs to know the exact enum.
_VALID_ORIGIN_TYPES = frozenset({"Playground", "API", "Agent", "Flow", "Automation", "Hub", "Gateway", "Knowledge"})

_ORIGIN_TYPE_ALIASES: dict[str, str] = {
    "playground": "Playground",
    "api": "API",
    "agent": "Agent",
    "agent run": "Agent",
    "agent_run": "Agent",
    "agent tool": "Agent",
    "flow": "Flow",
    "flow run": "Flow",
    "flow_run": "Flow",
    "flow decision router": "Flow",
    "automation": "Automation",
    "hub": "Hub",
    "hub triage": "Hub",
    "hub routing": "Hub",
    "gateway": "Gateway",
    "knowledge": "Knowledge",
    "knowledge_ingestion": "Knowledge",
    "knowledge ingestion": "Knowledge",
    "rag": "Knowledge",
}

#: Throttle window (seconds) for the "unmapped origin_type" and "persistence failed" log_error
#: entries below -- a persistently misconfigured/unrecognized caller must not write one Error Log
#: row per Decision Call.
_LOG_THROTTLE_SECONDS = 600
_last_logged_at: dict[str, float] = {}


def normalize_origin_type(value: str | None) -> str | None:
    """Map a caller-supplied origin label onto the ``Decision Call.origin_type`` Select options.

    Case-insensitive; underscores/hyphens are treated as spaces. Returns ``None`` (never raises)
    for a value with no known mapping, logging once per throttle window so an uncovered caller
    string is discoverable without spamming the Error Log. Exported so callers other than
    ``make_frappe_telemetry_sink`` (e.g. ``service.py``, ``telemetry.py``) can pre-normalize or
    validate an ``origin_type`` before it reaches persistence, if useful.
    """
    if not value or not isinstance(value, str):
        return None
    if value in _VALID_ORIGIN_TYPES:
        return value
    key = " ".join(value.strip().lower().replace("_", " ").replace("-", " ").split())
    mapped = _ORIGIN_TYPE_ALIASES.get(key)
    if mapped is not None:
        return mapped
    _log_throttled(
        f"origin_type:{key}",
        title="Decision Call origin_type unmapped",
        message=f"No normalize_origin_type mapping for origin_type={value!r}; Decision Call.origin_type left blank.",
    )
    return None


def _log_throttled(signature: str, *, title: str, message: str, frappe_module: Any | None = None) -> None:
    """Best-effort, throttled ``frappe.log_error``. Never raises; no-ops outside a Frappe site.

    ``frappe_module`` lets a caller that already resolved (or was injected with, e.g. in tests)
    a frappe module reuse it rather than importing the real package fresh -- ``persist`` below
    passes its own resolved ``frappe`` so the sink's ``frappe_module=`` override applies here too.
    """
    now = time.monotonic()
    cache_key = hashlib.sha256(signature.encode()).hexdigest()[:16]
    if now - _last_logged_at.get(cache_key, 0.0) < _LOG_THROTTLE_SECONDS:
        return
    _last_logged_at[cache_key] = now
    try:
        module = frappe_module
        if module is None:
            import frappe as module
        module.log_error(title=title[:140], message=message[:2000])
    except Exception:  # noqa: BLE001 - logging must never raise, and must not require a site
        pass


def make_frappe_telemetry_sink(*, frappe_module: Any | None = None, ignore_permissions: bool = True) -> Callable[[DecisionCall], str]:
    """Return a sink that persists only normalized, redacted Decision Call fields.

    Frappe is resolved lazily so the provider-neutral runtime remains usable in unit tests
    and non-Frappe workers. Sink failures are intentionally left to the runtime boundary.

    Returns the inserted ``Decision Call`` docname (its ``call_id``) so a caller wrapping
    this sink (e.g. ``huf.ai.decision.service.run_policy``, T2A.10) can report which row
    corresponds to a given ``ServiceResult`` -- ``DecisionRuntime._emit`` itself discards
    the return value, so this is opt-in for callers that invoke the sink directly.
    """
    frappe = frappe_module

    def persist(call: DecisionCall) -> str:
        nonlocal frappe
        if frappe is None:
            import frappe as frappe_runtime
            frappe = frappe_runtime
        identity = call.resolved_identity
        call_id = _call_id(call)
        values = {
            "doctype": "Decision Call",
            "call_id": call_id,
            "status": call.status,
            "surface": call.surface,
            "policy": call.policy_id,
            "policy_version": call.policy_version,
            "policy_fingerprint": call.policy_fingerprint,
            "resolved_provider": call.resolved_provider or identity.provider,
            "resolved_deployment": call.resolved_deployment,
            "requested_model": call.requested_model,
            "resolved_provider_model_id": identity.provider_model_id,
            "decision_model": identity.canonical_model,
            "resolved_model": call.resolved_model,
            "resolved_model_version": call.resolved_model_version,
            "backend_adapter": call.backend_adapter,
            "mode": call.mode,
            "origin_type": normalize_origin_type(call.origin_type),
            "agent": call.agent,
            "agent_run": call.agent_run,
            "conversation": call.conversation,
            "flow_run": call.flow_run,
            "flow_node_id": call.flow_node_id,
            "automation": call.automation,
            "owner_user": call.owner_user,
            "shadow_of": call.shadow_of,
            "latency_ms": call.latency_ms,
            "candidate_count": len(call.candidate_ids),
            "candidate_ids_json": _json(call.candidate_ids),
            "answer_json": _json(call.answers),
            "state_hash": call.state_hash,
            "state_snapshot": _json(call.state_snapshot) if call.state_snapshot is not None else None,
            "input_tokens": call.usage.input_tokens,
            "output_tokens": call.usage.output_tokens,
            "cost": call.usage.measured_cost,
            "cost_source": call.usage.cost_source,
            "gate_result": call.gate_result,
            "fallback_action": call.policy_fallback_action,
            "deployment_selection_source": call.deployment_selection_source,
            "deployment_fallback_chain": _json(call.deployment_fallback_chain),
            "deployment_fallback_count": call.deployment_fallback_count,
            "error_code": call.error_code,
        }
        doc = frappe.get_doc(values)
        try:
            doc.insert(ignore_permissions=ignore_permissions)
        except Exception as exc:
            # DecisionRuntime._emit swallows this sink's exceptions by design (a telemetry
            # problem must never rewrite the decision result) -- log it here, throttled, so a
            # persistently failing sink (bad Select value, missing link, ...) is discoverable
            # instead of silently never persisting, then re-raise so _emit's swallow is unchanged.
            _log_throttled(
                f"persist_failed:{type(exc).__name__}:{exc}",
                title="Decision Call persistence failed",
                message=f"call_id={call_id} status={call.status} policy={call.policy_id}\n{type(exc).__name__}: {exc}",
                frappe_module=frappe,
            )
            raise
        # autoname is `field:call_id` (decision_call.json), so the docname is always exactly
        # this -- returning it directly rather than reading `doc.name` also keeps this
        # working against the fake `frappe.get_doc` stub the existing tests in this module
        # use (SimpleNamespace(insert=...), no `.name`).
        return call_id

    return persist


def _call_id(call: DecisionCall) -> str:
    # autoname is `field:call_id` and the field is `unique=1` (decision_call.json), so the
    # id must be unique per row, not just per (policy, status) -- two Decision Runtime calls
    # for the same policy with the same outcome (the common case: repeated Enforce success)
    # would otherwise collide on insert. The fingerprint/status prefix stays for readability;
    # frappe.generate_hash makes each row's name unique.
    fingerprint = call.policy_fingerprint[:12] or "unknown"
    import frappe

    return f"decision-{fingerprint}-{call.status}-{frappe.generate_hash(length=8)}"


def _json(value: Any) -> str:
    return json.dumps(value, default=_json_default, separators=(",", ":"), sort_keys=True)


def _json_default(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "__dict__"):
        return value.__dict__
    return str(value)
