import frappe
from frappe.model.document import Document

COUNTED = ("queued", "sending", "sent", "delivered", "read", "failed", "deferred", "unknown", "skipped")

GUARDED_FIELDS = (
	"consent_attested", "consent_attested_by", "consent_attested_at", "consent_source",
	"gateway", "template", "whatsapp_account",
)


class WhatsAppBroadcast(Document):
	"""A one-template-to-many send. Per-recipient state lives in WhatsApp Broadcast Recipient."""

	def validate(self):
		"""Reject consent/gateway/template writes that bypass the management API (generic REST, set_value).

		The management layer sets ``frappe.flags.in_broadcast_api`` after proving Gateway write authority.
		Status and counters are deliberately not guarded here: the runner owns them.
		"""
		if getattr(frappe.flags, "in_broadcast_api", False):
			return
		if self.is_new():
			if self.consent_attested or self.consent_attested_by or self.consent_attested_at:
				frappe.throw("Consent can only be attested through the broadcast API.", frappe.PermissionError)
			return
		for field in GUARDED_FIELDS:
			if self.has_value_changed(field):
				frappe.throw(f"{field} can only be changed through the broadcast API.", frappe.PermissionError)

	def recount(self, commit: bool = False) -> dict[str, int]:
		"""Recompute the counter fields from recipient rows (source of truth) and save them."""
		rows = frappe.db.sql(
			"select status, count(*) from `tabWhatsApp Broadcast Recipient` where broadcast=%s group by status",
			self.name,
		)
		counts = {k: 0 for k in COUNTED}
		for status, n in rows:
			counts[status] = int(n)
		counts["total"] = sum(counts[k] for k in COUNTED)
		for k, v in counts.items():
			frappe.db.set_value(self.doctype, self.name, k, v, update_modified=False)
		if commit:
			frappe.db.commit()
		return counts
