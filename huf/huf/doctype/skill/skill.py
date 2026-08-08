# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class Skill(Document):
	def validate(self):
		if self.source_type == "App Provided" and not self.provider_app:
			frappe.throw(_("Provider App is required for App Provided skills."))

	def on_trash(self):
		attached_agents = frappe.get_all(
			"Agent Skill",
			filters={"skill": self.name},
			pluck="parent",
		)
		if attached_agents:
			frappe.throw(
				_("Cannot delete skill {0}: attached to {1} agent(s): {2}").format(
					frappe.bold(self.name),
					len(attached_agents),
					", ".join(attached_agents[:5]),
				)
			)

		# Skill Import Log is a historical audit trail, not a real dependency —
		# safe to unlink so it never blocks deleting the skill it logged.
		frappe.db.delete("Skill Import Log", {"skill": self.name})
