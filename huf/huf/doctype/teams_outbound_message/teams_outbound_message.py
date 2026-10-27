from frappe.model.document import Document


class TeamsOutboundMessage(Document):
	"""Durable outbox row for one Teams delivery. Managed by huf.ai.gateways.teams_outbox."""
