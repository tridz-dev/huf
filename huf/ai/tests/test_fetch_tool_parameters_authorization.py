"""
Unit tests for fetch_tool_parameters_from_code authorization, specifically:
- ST-05.3: frappe.only_for("Huf Manager") gate
- ST-05.7: Regression test for F-19 endpoint authorization

The function is a module-level whitelisted endpoint, not an Agent Tool Function
document method. It requires the Huf Manager role.

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_fetch_tool_parameters_authorization
"""
import unittest

import frappe


class TestFetchToolParametersAuthorization(unittest.TestCase):
	"""Test ST-05.3/ST-05.7: fetch_tool_parameters_from_code authorization."""

	def setUp(self):
		"""Save current user to restore after test."""
		self.current_user = frappe.session.user

		# frappe.only_for() unconditionally no-ops when frappe.flags.in_test
		# is set (frappe/__init__.py:954), which bench run-tests sets for the
		# whole run -- so this gate can never actually be exercised without
		# temporarily clearing that flag around the calls under test.
		self.original_in_test = frappe.flags.in_test
		frappe.flags.in_test = False

		for email, roles in (
			("test_huf_user@example.com", ["Huf User"]),
			("test_huf_manager@example.com", ["Huf Manager"]),
		):
			if not frappe.db.exists("User", email):
				frappe.get_doc({
					"doctype": "User",
					"email": email,
					"first_name": email.split("@")[0],
					"send_welcome_email": 0,
					"roles": [{"role": r} for r in roles],
				}).insert(ignore_permissions=True)

	def tearDown(self):
		"""Restore user and in_test flag after test."""
		frappe.set_user(self.current_user)
		frappe.flags.in_test = self.original_in_test

	def test_fetch_tool_parameters_requires_huf_manager(self):
		"""
		Regression test for F-19 (the fetch_tool_parameters_from_code slice):
		the endpoint now requires the Huf Manager role. It is a module-level
		function taking function_path, not an AgentToolFunction method --
		huf/huf/doctype/agent_tool_function/agent_tool_function.py:124.
		"""
		from huf.huf.doctype.agent_tool_function.agent_tool_function import (
			fetch_tool_parameters_from_code,
		)

		# User with only Huf User role must be rejected
		frappe.set_user("test_huf_user@example.com")
		with self.assertRaises(frappe.PermissionError):
			fetch_tool_parameters_from_code("frappe.throw")

		# User with Huf Manager role must be allowed
		frappe.set_user("test_huf_manager@example.com")
		result = fetch_tool_parameters_from_code("frappe.throw")
		self.assertIsNotNone(result)
