from frappe.model.document import Document


class WhatsAppFlowCache(Document):
	"""Cache of a Flow listed from the WABA on Meta (synced by huf.ai.channels.wa_flows)."""
