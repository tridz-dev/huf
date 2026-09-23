"""Optional Frappe persistence for normalized Decision Call telemetry."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from huf.ai.decision.telemetry import DecisionCall


def make_frappe_telemetry_sink(*, frappe_module: Any | None = None, ignore_permissions: bool = True) -> Callable[[DecisionCall], None]:
    """Return a sink that persists only normalized, redacted Decision Call fields.

    Frappe is resolved lazily so the provider-neutral runtime remains usable in unit tests
    and non-Frappe workers. Sink failures are intentionally left to the runtime boundary.
    """
    frappe = frappe_module

    def persist(call: DecisionCall) -> None:
        nonlocal frappe
        if frappe is None:
            import frappe as frappe_runtime
            frappe = frappe_runtime
        identity = call.resolved_identity
        doc = frappe.get_doc({
            "doctype": "Decision Call",
            "call_id": _call_id(call),
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
            "origin_type": call.origin_type,
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
        })
        doc.insert(ignore_permissions=ignore_permissions)

    return persist


def _call_id(call: DecisionCall) -> str:
    fingerprint = call.policy_fingerprint[:12] or "unknown"
    return f"decision-{fingerprint}-{call.status}"


def _json(value: Any) -> str:
    return json.dumps(value, default=_json_default, separators=(",", ":"), sort_keys=True)


def _json_default(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "__dict__"):
        return value.__dict__
    return str(value)
