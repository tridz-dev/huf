from frappe.model.document import Document


class TeamsActionSession(Document):
	"""Opaque server-side state behind one Teams Adaptive Card (approval buttons).

	Teams only ever sees this document's name. The first valid invoke moves it Open -> Decided
	with one conditional UPDATE (see ``huf.ai.gateways.teams.actions``).
	"""
