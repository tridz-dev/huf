# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class ExternalAgentConnection(Document):
	def validate(self):
		from huf.ai.agent.access import check_agent_access

		agent_doc = frappe.get_doc("Agent", self.agent)
		if not agent_doc.get("execution_mode") or agent_doc.get("execution_mode") == "Native":
			frappe.throw(_("Choose an agent whose execution mode is external."))

		if not check_agent_access(agent_doc, self.user):
			frappe.throw(_("This user cannot run the selected agent."))

		if self.enabled:
			filters = {"user": self.user, "agent": self.agent, "enabled": 1}
			if self.name:
				filters["name"] = ["!=", self.name]
			if frappe.db.exists("External Agent Connection", filters):
				frappe.throw(_("An enabled connection already exists for this user and agent."))

	def has_permission(self, permission_type=None, verbose=False):
		user = frappe.session.user

		if "System Manager" in frappe.get_roles(user):
			return True

		return self.user == user and permission_type in ("read", None)


def get_active_connection(user: str, agent: str) -> str | None:
	"""Return the name of the enabled connection for this user and agent, or None."""
	return frappe.db.get_value(
		"External Agent Connection",
		{"user": user, "agent": agent, "enabled": 1},
		"name",
	)
