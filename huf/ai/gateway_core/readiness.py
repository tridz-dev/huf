"""Gateway readiness checklist (dry-run of Gateway.validate())."""

from __future__ import annotations

import frappe
from frappe import _

from huf.ai.gateway_adapters.provider_ids import provider_to_service_id


# GW-15: the frontend readiness checklist (gatewayReadiness.ts) only checked 3
# conditions (credentials connected, route target set, enabled) while
# Gateway.validate() enforces at least 5 more before an enabled gateway can
# actually save: execution_user set, the chosen route target concretely
# filled in, required provider credentials present, execution_user's role,
# and execution_user's access to the default agent. Rather than re-encode
# those rules a second time in TypeScript (and have them drift again), this
# endpoint runs the real Gateway.validate() checks in dry-run mode -- read
# only, no save, no side effects -- and returns each one as a pass/fail item
# the frontend can render directly.
GATEWAY_READINESS_CHECKS = (
    ("enabled", "Gateway enabled"),
    ("execution-user", "Run as user set"),
    ("route-target", "Route target set"),
    ("route-target-concrete", "Route target fully chosen"),
    ("credentials", "Credentials connected"),
    ("credential-values", "Required credential values set"),
    ("execution-user-role", "Run-as user has gateway role"),
    ("agent-access", "Run-as user can access default agent"),
)


def preview_gateway_readiness(gateway_name: str) -> dict:
    """Report, per-check, whether a Gateway meets every precondition Gateway.validate()
    would enforce if it were enabled and saved right now -- without saving it.

    Reuses Gateway's own private validation methods (read-only) so this list can
    never silently drift from what actually blocks save/enable.
    """
    if not frappe.has_permission("Gateway", "read"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    gateway = frappe.get_doc("Gateway", gateway_name)
    results: dict[str, dict] = {}

    def record(check_id: str, label: str, ok: bool, hint: str | None = None):
        results[check_id] = {"id": check_id, "label": label, "done": bool(ok), "hint": None if ok else hint}

    def run_check(check_id: str, label: str, fn, default_hint: str):
        try:
            fn()
            record(check_id, label, True)
        except frappe.exceptions.ValidationError as e:
            record(check_id, label, False, str(e) or default_hint)
        except Exception as e:  # defensive: never let a lookup error break the preview
            record(check_id, label, False, str(e) or default_hint)

    record("enabled", "Gateway enabled", bool(gateway.is_enabled), "Turn the gateway on")

    def _execution_user_set():
        if not gateway.execution_user:
            frappe.throw(_("Set a Run as user."))

    run_check("execution-user", "Run as user set", _execution_user_set, "Set a least-privileged Run as user")

    record(
        "route-target",
        "Route target set",
        bool(gateway.default_target_type),
        "Choose an agent or flow to receive messages",
    )

    def _route_target_concrete():
        if gateway.default_target_type == "Agent" and not gateway.default_agent:
            frappe.throw(_("Choose a default agent or clear the default route."))
        if gateway.default_target_type == "Flow" and not gateway.default_flow:
            frappe.throw(_("Choose a default flow or clear the default route."))

    run_check(
        "route-target-concrete",
        "Route target fully chosen",
        _route_target_concrete,
        "Finish choosing the agent or flow for this route",
    )

    def _credentials_connected():
        expected_service = provider_to_service_id(gateway.provider) if gateway.provider else None
        if not expected_service:
            return
        if not gateway.integration_settings:
            frappe.throw(_("Connect credentials for this channel."))
        integration = frappe.get_doc("Integration Settings", gateway.integration_settings)
        if integration.service != expected_service:
            frappe.throw(
                _("The connected integration must use the {0} service.").format(expected_service)
            )

    run_check("credentials", "Credentials connected", _credentials_connected, "Connect credentials for this channel")

    run_check(
        "credential-values",
        "Required credential values set",
        gateway._validate_required_credentials,
        "Fill in the required credential fields for this provider",
    )

    def _execution_user_role():
        if gateway.execution_user:
            gateway._validate_execution_user_role()

    run_check(
        "execution-user-role",
        "Run-as user has gateway role",
        _execution_user_role,
        "Grant the Run as user the required gateway role",
    )

    def _agent_access():
        if gateway.execution_user and gateway.default_agent:
            gateway._validate_agent_access()

    run_check(
        "agent-access",
        "Run-as user can access default agent",
        _agent_access,
        "Grant the Run as user access to the default agent",
    )

    ordered = [results[check_id] for check_id, _label in GATEWAY_READINESS_CHECKS]
    blocking = [c for c in ordered if not c["done"]]
    return {"ready": len(blocking) == 0, "blocking_count": len(blocking), "checks": ordered}
