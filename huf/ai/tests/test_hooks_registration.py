"""Test that has_permission hooks are registered for all runtime doctypes.

This test verifies that the five has_permission hooks (ST-01.2a-e) are
correctly registered in the app's hook map, so any future edit that drops
a hook registration will be caught immediately.
"""

import frappe


def test_has_permission_hooks_registered():
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
