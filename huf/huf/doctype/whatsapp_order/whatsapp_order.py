from frappe.model.document import Document


class WhatsAppOrder(Document):
	def validate(self):
		self.total = sum((r.qty or 0) * (r.price or 0) for r in self.items or [])
