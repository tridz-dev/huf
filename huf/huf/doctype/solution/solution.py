import frappe
from frappe import _
from frappe.model.document import Document


class Solution(Document):
    """A named job on a gateway (answer, orders, support, ...) with one primary target."""

    def validate(self):
        self.title = (self.title or "").strip()
        if not self.title:
            frappe.throw(_("Title is required."))
        if frappe.db.exists("Solution", {"title": self.title, "name": ("!=", self.name)}):
            frappe.throw(_("A solution titled {0} already exists.").format(self.title), exc=frappe.UniqueValidationError)

        if self.test_mode:
            self.status = "Paused"

        if self.primary_target_type == "Agent":
            if not self.primary_agent:
                frappe.throw(_("Choose an agent for an Agent target."))
            self.primary_flow = None
        elif self.primary_target_type == "Flow":
            if not self.primary_flow:
                frappe.throw(_("Choose a flow for a Flow target."))
            self.primary_agent = None
        else:
            self.primary_target_type = None
            self.primary_agent = None
            self.primary_flow = None
