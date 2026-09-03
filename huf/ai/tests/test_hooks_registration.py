"""Test that has_permission and permission_query_conditions hooks are registered.

This test verifies that the five has_permission hooks (ST-01.2a-e) and the
permission_query_conditions hooks for list scoping are correctly registered
in the app's hook map, so any future edit that drops a hook registration
will be caught immediately.
"""

import frappe
from frappe.tests import IntegrationTestCase


class TestHooksRegistration(IntegrationTestCase):
	def test_has_permission_hooks_registered(self):
		"""Verify that all five runtime doctype has_permission hooks are registered."""
		hooks = frappe.get_hooks("has_permission")

		expected_doctypes = [
			"Agent Run",
			"Agent Message",
			"Agent Conversation",
			"Agent Tool Call",
			"Agent Context Artifact",
		]

		for doctype in expected_doctypes:
			assert hooks.get(doctype), f"no has_permission hook registered for {doctype}"

	def test_pqc_hooks_registered_for_list_scoped_doctypes(self):
		"""Verify that permission_query_conditions hooks are registered for list-scoped doctypes.

		ST-02 adds PQC hooks for four doctypes: Agent Tool Call, Agent Run Prompt Snapshot,
		Huf API Key, and Agent Procedure Run. This test ensures all four are registered.
		"""
		hooks = frappe.get_hooks("permission_query_conditions")

		expected_doctypes = [
			"Agent Tool Call",
			"Agent Run Prompt Snapshot",
			"Huf API Key",
			"Agent Procedure Run",
		]

		for doctype in expected_doctypes:
			assert hooks.get(doctype), f"no permission_query_conditions hook registered for {doctype}"
