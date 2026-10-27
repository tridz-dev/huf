import frappe
from frappe import _
from frappe.model.document import Document


class GatewayIdentityLink(Document):
	"""Maps one external chat identity (team_id + external_id) to one Huf user.

	Keyed on (gateway, team_id, external_id), never on email. At most one row per key may be
	Linked at a time; Revoked rows are kept for audit.
	"""

	def validate(self):
		if self.user in ("Guest",):
			frappe.throw(_("A chat identity cannot be linked to Guest."), frappe.PermissionError)
		if self.state == "Linked":
			clash = frappe.db.get_value(
				"Gateway Identity Link",
				{
					"gateway": self.gateway,
					"team_id": self.team_id,
					"external_id": self.external_id,
					"state": "Linked",
					"name": ["!=", self.name or ""],
				},
				"name",
			)
			if clash:
				frappe.throw(_("This person is already linked ({0}).").format(clash))
