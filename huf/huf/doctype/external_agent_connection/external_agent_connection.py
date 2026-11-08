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
		if not check_agent_access(agent_doc, self.user):
			frappe.throw(_("This user cannot run the selected agent."))

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
