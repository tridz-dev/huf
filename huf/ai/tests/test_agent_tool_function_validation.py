"""
Unit tests for Agent Tool Function validation, specifically:
- ST-05.1: App Provided tool path validation against hook allow-set
- ST-05.6: Regression tests for F-07 RCE scenario

These tests patch get_hook_declared_function_paths to avoid real hook
reads and follow the pure-mock convention per PR #597.

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_agent_tool_function_validation
"""
import unittest
from unittest import mock

import frappe


class TestAppProvidedToolValidation(unittest.TestCase):
	"""Test ST-05.1: App Provided tool paths validated against hook allow-set."""

	def test_app_provided_in_allow_set_passes(self):
		"""
		App Provided tool whose function_path is in the hook allow-set
		should pass validation.
		"""
		with mock.patch(
			"huf.huf.doctype.agent_tool_function.agent_tool_function.get_hook_declared_function_paths",
			return_value={"huf.ai.tools.recipient.handle_get_recipient"},
		):
			tool = frappe.new_doc("Agent Tool Function")
			tool.tool_name = "test_valid_app_provided"
			tool.types = "App Provided"
			tool.function_path = "huf.ai.tools.recipient.handle_get_recipient"

			# Should not raise
			tool.validate()

	def test_app_provided_outside_allow_set_blocked(self):
		"""
		Regression test for F-07: an App Provided tool whose function_path is
		not declared by any installed app's huf_tools hook is rejected at
		validation time. This is a frappe.throw() with no explicit exception
		class, i.e. frappe.ValidationError -- NOT frappe.PermissionError,
		which is what is_whitelisted() raises for the (separate) Custom
		Function branch. See ST-05.1.
		"""
		with mock.patch(
			"huf.huf.doctype.agent_tool_function.agent_tool_function.get_hook_declared_function_paths",
			return_value={"huf.ai.tools.recipient.handle_get_recipient"},
		):
			tool = frappe.new_doc("Agent Tool Function")
			tool.tool_name = "test_rce"
			tool.types = "App Provided"
			tool.function_path = "subprocess.getoutput"

			with self.assertRaises(frappe.ValidationError):
				tool.save()

	def test_custom_function_non_whitelisted_blocked(self):
		"""
		Pre-existing behaviour, confirm unchanged: Custom Function still
		goes through is_whitelisted(), which raises frappe.PermissionError
		(frappe/__init__.py:878-892), not frappe.ValidationError.
		"""
		tool = frappe.new_doc("Agent Tool Function")
		tool.tool_name = "test_custom_rce"
		tool.types = "Custom Function"
		tool.function_path = "subprocess.getoutput"

		with self.assertRaises(frappe.PermissionError):
			tool.save()
