import frappe
from frappe import _
from frappe.model.document import Document


class ChannelConversation(Document):
    """One chat (gateway + contact handle). Messages stay in the existing log, keyed back by link."""

    def validate(self):
        self.contact_handle = (self.contact_handle or "").strip()
        if not self.contact_handle:
            frappe.throw(_("Contact handle is required."))
        if self.status != "closed" and frappe.db.exists(
            "Channel Conversation",
            {
                "gateway": self.gateway,
                "contact_handle": self.contact_handle,
                "status": ("!=", "closed"),
                "name": ("!=", self.name),
            },
        ):
            frappe.throw(
                _("An open conversation already exists for this contact on this gateway."),
                exc=frappe.UniqueValidationError,
            )


def on_doctype_update():
    frappe.db.add_index("Channel Conversation", ["gateway", "contact_handle"])
