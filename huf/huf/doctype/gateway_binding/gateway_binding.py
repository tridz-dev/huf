import frappe
from frappe import _
from frappe.model.document import Document


class GatewayBinding(Document):
    """A deterministic route from a provider conversation scope to Huf work."""

    def validate(self):
        if self.match_type != "Any conversation" and not self.match_value:
            frappe.throw(_("Provider value is required for this match type."))
        if self.target_type == "Agent" and not self.agent:
            frappe.throw(_("Choose an agent for an Agent route."))
        if self.target_type == "Flow" and not self.flow:
            frappe.throw(_("Choose a flow for a Flow route."))
