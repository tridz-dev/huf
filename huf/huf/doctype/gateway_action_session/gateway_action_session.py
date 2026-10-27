from frappe.model.document import Document


class GatewayActionSession(Document):
	"""Opaque server-side state behind one interactive message (buttons, confirms).

	Slack only ever sees this document's name. Business data lives in ``payload``; the first
	valid click consumes the session atomically (see ``slack_interactivity``).
	"""
