from frappe.model.document import Document


class ChannelOutbox(Document):
	"""One queued flow send (H-W2-15). Token names and references only, never bound values or a phone (G4)."""
