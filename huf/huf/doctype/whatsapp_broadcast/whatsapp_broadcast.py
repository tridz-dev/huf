import frappe
from frappe.model.document import Document

COUNTED = ("queued", "sending", "sent", "delivered", "read", "failed", "deferred", "unknown", "skipped")


class WhatsAppBroadcast(Document):
	"""A one-template-to-many send. Per-recipient state lives in WhatsApp Broadcast Recipient."""

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
