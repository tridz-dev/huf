from frappe.model.document import Document


class GatewayConsent(Document):
	"""Append-only consent change per gateway + sender + category. The latest row wins; rows are never edited."""

	def before_save(self):
		if not self.is_new():
			import frappe

			frappe.throw("Consent records are append-only.")
