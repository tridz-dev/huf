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

	def tearDown(self):
		"""Restore user after test."""
		frappe.set_user(self.current_user)

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

		# Create or use a test user with only Huf User role
		frappe.set_user("test_huf_user@example.com")
		with self.assertRaises(frappe.PermissionError):
			fetch_tool_parameters_from_code("frappe.throw")

		# Create or use a test user with Huf Manager role
		frappe.set_user("test_huf_manager@example.com")
		result = fetch_tool_parameters_from_code("frappe.throw")
		self.assertIsNotNone(result)
