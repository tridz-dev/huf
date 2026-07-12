# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestAgentUser(HufTestSuite):
	"""`Agent User` is a child table (istable=1) of the `allowed_users`
	Table MultiSelect field on `Agent` — used by
	Agent.get_permission_query_conditions() to restrict list-view
	visibility to specific users. Tested as rows on a parent Agent."""

	def _make_agent_with_users(self, users):
		return frappe.get_doc({
			"doctype": "Agent",
			"agent_name": "_Test Agent User Scoped",
			"provider": self.bootstrap.provider.name,
			"model": self.bootstrap.model.name,
			"instructions": "You are a test assistant.",
			"allowed_users": [{"doctype": "Agent User", "user": u} for u in users],
		}).insert(ignore_permissions=True)

	def test_user_row_saved_on_agent(self):
		agent = self._make_agent_with_users(["Administrator"])

		self.assertEqual(len(agent.allowed_users), 1)
		self.assertEqual(agent.allowed_users[0].user, "Administrator")
		self.assertEqual(agent.allowed_users[0].parenttype, "Agent")

	def test_multiple_user_rows_kept(self):
		agent = self._make_agent_with_users(["Administrator", "Guest"])

		self.assertEqual({r.user for r in agent.allowed_users}, {"Administrator", "Guest"})

	def test_invalid_user_link_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_agent_with_users(["_nonexistent@example.com"])
