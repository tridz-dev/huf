from frappe.model.document import Document


class WhatsAppSendKey(Document):
	"""Durable idempotency claim of one agent/tool WhatsApp send (see huf.ai.whatsapp.send_keys)."""
