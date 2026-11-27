from frappe.model.document import Document


class HufVoiceSession(Document):
	"""Server-side record of a minted voice session (nonce hash, owner, redelivery key)."""
