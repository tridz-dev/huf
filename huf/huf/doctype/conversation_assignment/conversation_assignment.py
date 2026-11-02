import frappe
from frappe import _
from frappe.model.document import Document


class ConversationAssignment(Document):
    """Which solution currently owns one chat (gateway + contact)."""

    def validate(self):
        self.contact = (self.contact or "").strip()
        if not self.contact:
            frappe.throw(_("Contact is required."))
        if frappe.db.exists(
            "Conversation Assignment",
            {"gateway": self.gateway, "contact": self.contact, "name": ("!=", self.name)},
        ):
            frappe.throw(
                _("This contact already has an assignment on this gateway."),
                exc=frappe.UniqueValidationError,
            )


def on_doctype_update():
    frappe.db.add_index("Conversation Assignment", ["gateway", "contact"])
