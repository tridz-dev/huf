import frappe
from frappe import _
from frappe.model.document import Document

from huf.ai.gateway_adapters.provider_ids import provider_to_service_id


class Gateway(Document):
    """A configured inbound/outbound messaging account.

    Credentials remain in the provider integration. A Gateway owns the
    inbound trust boundary, routing policy, and execution principal.
    """

    def validate(self):
        if self.is_enabled and not self.execution_user:
            frappe.throw(_("Enabled gateways need a Run as user. Use a least-privileged service user."))

        if self.default_target_type == "Agent" and not self.default_agent:
            frappe.throw(_("Choose a default agent or clear the default route."))
        if self.default_target_type == "Flow" and not self.default_flow:
            frappe.throw(_("Choose a default flow or clear the default route."))
        if self.direct_policy == "Open":
            frappe.throw(_("Public direct-message gateways are not available in this release."))

        # Every provider gets the same "linked Integration Settings must match
        # this provider's service" check now, via the one canonical
        # provider -> service_name transform (see provider_to_service_id).
        # This used to only cover 4 of 12 providers (VK, WeCom, WhatsApp,
        # Telegram); the other 8 previously had no such validation at all.
        # Gated on is_enabled, same as before, so a disabled gateway with a
        # stale/mismatched linked integration still saves.
        expected_service = provider_to_service_id(self.provider) if self.provider else None
        if expected_service and self.is_enabled:
            if not self.integration_settings:
                frappe.throw(_("Enabled {0} gateways need a connected integration.").format(self.provider))
            integration = frappe.get_doc("Integration Settings", self.integration_settings)
            if integration.service != expected_service:
                frappe.throw(
                    _("The connected integration must use the {0} service.").format(expected_service)
                )
