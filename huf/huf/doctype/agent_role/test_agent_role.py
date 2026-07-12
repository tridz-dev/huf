# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestAgentRole(HufTestSuite):
	"""`Agent Role` is a child table (istable=1) of the `allowed_roles`
	Table MultiSelect field on `Agent` — used by Agent.get_permission_query_conditions()
	to restrict list-view visibility by Frappe role. Tested as rows on a
	parent Agent."""

	def _make_agent_with_roles(self, roles):
		return frappe.get_doc({
			"doctype": "Agent",
			"agent_name": "_Test Agent Role Scoped",
			"provider": self.bootstrap.provider.name,
			"model": self.bootstrap.model.name,
			"instructions": "You are a test assistant.",
			"allowed_roles": [{"doctype": "Agent Role", "role": r} for r in roles],
		}).insert(ignore_permissions=True)

	def test_role_row_saved_on_agent(self):
		agent = self._make_agent_with_roles(["System Manager"])

		self.assertEqual(len(agent.allowed_roles), 1)
		self.assertEqual(agent.allowed_roles[0].role, "System Manager")
		self.assertEqual(agent.allowed_roles[0].parenttype, "Agent")

	def test_multiple_role_rows_kept(self):
		agent = self._make_agent_with_roles(["System Manager", "Huf User"])

		self.assertEqual({r.role for r in agent.allowed_roles}, {"System Manager", "Huf User"})

	def test_invalid_role_link_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_agent_with_roles(["_Nonexistent Role"])
