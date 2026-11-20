import frappe
from frappe.model.document import Document


class ChannelConsent(Document):
	"""Append-only SMS/Email consent change per channel + recipient. The latest row wins; rows are never edited."""

	def before_save(self):
		if not self.is_new():
			frappe.throw("Consent records are append-only.")
