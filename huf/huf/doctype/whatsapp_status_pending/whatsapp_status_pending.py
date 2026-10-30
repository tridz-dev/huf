from frappe.model.document import Document


class WhatsAppStatusPending(Document):
	"""A Meta delivery status that arrived before its broadcast recipient row had a committed wamid.

	Parked by ``huf.ai.whatsapp.broadcast.status.apply_from_webhook`` and re-applied by the sender right after it
	commits the wamid and by the */5 sweep; expires after 24h."""
