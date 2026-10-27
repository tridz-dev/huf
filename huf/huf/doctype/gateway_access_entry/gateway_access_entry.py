import frappe
from frappe import _
from frappe.model.document import Document


class GatewayAccessEntry(Document):
    """Canonical, auditable sender or room admission entry."""

    def validate(self):
        # A10: WhatsApp sender ids are digits-only wa_ids. Meta's wa_id is
        # canonical (Brazil/Mexico numbers can differ from what a human types);
        # we only strip +, spaces, dashes and a leading 00, never add digits.
        if self.provider == "WhatsApp" and self.entry_type == "Sender" and self.external_id:
            from huf.ai.gateway_adapters.whatsapp_bridge import normalize_phone

            self.external_id = normalize_phone(self.external_id) or self.external_id

        # Pairing codes are unique per gateway among Pending entries.
        if self.state == "Pending" and self.pairing_code:
            clash = frappe.get_all(
                "Gateway Access Entry",
                filters={
                    "gateway": self.gateway,
                    "state": "Pending",
                    "pairing_code": self.pairing_code,
                    "name": ["!=", self.name or ""],
                },
                pluck="name",
                limit_page_length=1,
            )
            if clash:
                frappe.throw(_("Pairing code {0} is already in use on this gateway.").format(self.pairing_code))
