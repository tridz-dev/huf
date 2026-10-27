import frappe
from frappe.model.document import Document

from huf.ai.gateways.teams_refs import reference_name


class TeamsConversationReference(Document):
	"""Where the bot can talk to someone: one row per Teams conversation (personal chat,
	group chat or channel) for a Gateway and tenant. The deterministic name makes the
	(gateway, tenant_id, conversation_id) key unique at the database level.
	"""

	def autoname(self):
		self.name = reference_name(self.gateway, self.tenant_id, self.conversation_id)


def on_doctype_update():
	frappe.db.add_index(
		"Teams Conversation Reference",
		["gateway", "tenant_id", "user_aad_id"],
		"teams_ref_user_idx",
	)
