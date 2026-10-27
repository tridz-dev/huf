import frappe
from frappe import _
from frappe.model.document import Document


class TemplateUsage(Document):
    """Records that a solution owns or uses a WhatsApp template.

    ``whatsapp_account`` is plain Data on purpose: it must never link to a
    doctype from another app.
    """

    def validate(self):
        if frappe.db.exists(
            "Template Usage",
            {
                "whatsapp_account": self.whatsapp_account,
                "template": self.template,
                "language": self.language,
                "solution": self.solution,
                "name": ("!=", self.name),
            },
        ):
            frappe.throw(_("This template usage is already recorded."), exc=frappe.UniqueValidationError)


def on_doctype_update():
    frappe.db.add_index("Template Usage", ["whatsapp_account", "template", "language"])
