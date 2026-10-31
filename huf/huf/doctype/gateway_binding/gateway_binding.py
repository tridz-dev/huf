import frappe
from frappe import _
from frappe.model.document import Document

from huf.ai.solutions.ceiling import ceiling_for_gateway

_SCOPE_OVERRIDE = {"Only approved contacts": "Approved contacts", "Allow list": "Allow-list"}


def _gateway_scope(gateway):
    from huf.ai.whatsapp import send_scope

    value = frappe.db.get_value("Gateway", gateway, "agent_recipient_scope") if gateway else None
    return value if value in send_scope.SCOPES else send_scope.DEFAULT_SCOPE


class GatewayBinding(Document):
    """A deterministic route from a provider conversation scope to Huf work."""

    def _validate_policy_overrides(self):
        """Overrides may only tighten the gateway: cap within the ceiling, scope no wider than the gateway's."""
        cap = self.get("cap_per_day")
        if cap:
            if int(cap) < 0:
                frappe.throw("cap_exceeds_ceiling: " + _("Cap per day must be 0 or more."))
            ceiling, _source = ceiling_for_gateway(self.gateway)
            if ceiling is not None and int(cap) > ceiling:
                frappe.throw("cap_exceeds_ceiling: " + _("Cap per day {0} is above this number's limit of {1}.").format(cap, ceiling))
        override = _SCOPE_OVERRIDE.get(self.get("scope_override") or "")
        if override:
            from huf.ai.whatsapp import send_scope

            if send_scope.SCOPES.index(override) > send_scope.SCOPES.index(_gateway_scope(self.gateway)):
                frappe.throw("scope_loosening: " + _("The recipient scope can only be narrower than the gateway's ({0}).").format(_gateway_scope(self.gateway)))

    def validate(self):
        self._validate_policy_overrides()
        if self.match_type == "Catch-all":
            pass
        elif self.match_type in ("Keyword", "Ad or link tag"):
            values = [v.strip() for v in (self.match_value or "").split(",") if v.strip()]
            if not values:
                frappe.throw(_("Provider value is required for this match type."))
            # Keywords are stored comma-separated and normalised.
            self.match_value = ", ".join(values)
        elif self.match_type != "Any conversation" and not self.match_value:
            frappe.throw(_("Provider value is required for this match type."))
        if self.target_type == "Triage":
            return
        if self.solution and frappe.db.get_value("Solution", self.solution, "status") != "Live":
            # A purpose never creates an agent, so a not-yet-live solution may have no target yet.
            return
        if self.target_type == "Agent" and not self.agent:
            frappe.throw(_("Choose an agent for an Agent route."))
        if self.target_type == "Flow" and not self.flow:
            frappe.throw(_("Choose a flow for a Flow route."))
        if self.target_type == "Flow":
            from huf.ai.flow.gateways.route_warning import warn_if_flow_not_live

            warn_if_flow_not_live(self.flow)  # Q11: warn, never refuse
