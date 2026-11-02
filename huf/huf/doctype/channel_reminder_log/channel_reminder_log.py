from frappe.model.document import Document


class ChannelReminderLog(Document):
	"""One row per proactive reminder sent (DB-backed throttle shared by reminder jobs)."""
