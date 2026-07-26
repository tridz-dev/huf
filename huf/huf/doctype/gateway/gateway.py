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
