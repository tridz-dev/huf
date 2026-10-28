import frappe
from frappe.model.document import Document

COUNTED = ("queued", "sending", "sent", "delivered", "read", "failed", "deferred", "unknown", "skipped")

GUARDED_FIELDS = (
	"consent_attested", "consent_attested_by", "consent_attested_at", "consent_source",
	"gateway", "template", "whatsapp_account",
	"status", "started_by", "started_at", "finished_at", "pause_reason",
	"max_recipients", "send_via", "mps",
	*COUNTED, "total",
)
# Values a brand-new row may carry without the broadcast API (the doctype defaults).
# max_recipients / mps have no doctype default: blank means "use WhatsApp Broadcast Settings".
NEW_ROW_DEFAULTS = {"status": "Draft", "send_via": "messages"}


class WhatsAppBroadcast(Document):
	"""A one-template-to-many send. Per-recipient state lives in WhatsApp Broadcast Recipient."""

	def validate(self):
		"""Reject writes to gated fields that bypass the management API (generic REST, doc.save).

		The management layer sets ``frappe.flags.in_broadcast_api`` after proving Gateway write authority.
		The runner/status code writes status and counters through raw SQL or ``frappe.db.set_value``,
		which skip ``validate``, so this guard does not interfere with them.
		"""
		if getattr(frappe.flags, "in_broadcast_api", False):
			return
		if self.is_new():
			for field in GUARDED_FIELDS:
				value = self.get(field)
				if field in NEW_ROW_DEFAULTS:
					bad = value not in (None, "") and str(value) != str(NEW_ROW_DEFAULTS[field])
				else:
					bad = bool(value) and field not in ("gateway", "template", "whatsapp_account")
				if bad:
					frappe.throw(f"{field} can only be set through the broadcast API.", frappe.PermissionError)
			return
		for field in GUARDED_FIELDS:
			if self.has_value_changed(field):
				frappe.throw(f"{field} can only be changed through the broadcast API.", frappe.PermissionError)

	def on_trash(self):
		"""Only a Draft with no started rows can be deleted; its queued rows go with it."""
		if self.status != "Draft":
			frappe.throw("Only a Draft broadcast can be deleted.", frappe.PermissionError)
		started = frappe.db.count(
			"WhatsApp Broadcast Recipient",
			{"broadcast": self.name, "status": ["not in", ["queued", "deferred", "skipped"]]},
		)
		if started:
			frappe.throw("This broadcast has sent rows and cannot be deleted.", frappe.PermissionError)
		prev = frappe.flags.get("in_broadcast_api")
		frappe.flags.in_broadcast_api = True
		try:
			for name in frappe.get_all("WhatsApp Broadcast Recipient", filters={"broadcast": self.name}, pluck="name"):
				frappe.delete_doc("WhatsApp Broadcast Recipient", name, force=True, ignore_permissions=True)
		finally:
			frappe.flags.in_broadcast_api = prev

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
		from huf.ai.whatsapp.broadcast import progress

		progress.publish(self.name)
		return counts
