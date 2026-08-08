import frappe
from frappe import _
from frappe.model.document import Document


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

        expected_service = {"VK": "vk", "WeCom": "wecom", "WhatsApp": "whatsapp", "Telegram": "telegram"}.get(self.provider)
        if expected_service and self.is_enabled:
            if not self.integration_settings:
                frappe.throw(_("Enabled {0} gateways need a connected integration.").format(self.provider))
            integration = frappe.get_doc("Integration Settings", self.integration_settings)
            if integration.service != expected_service:
                frappe.throw(
                    _("The connected integration must use the {0} service.").format(expected_service)
                )
