"""Test record-level permissions for get_agent_run_status endpoint.

Tests that the get_agent_run_status endpoint enforces per-run owner checks
for both guest and logged-in callers.
"""

import frappe
from frappe.tests import IntegrationTestCase


class TestGetAgentRunStatusPerms(IntegrationTestCase):
	def setUp(self):
		if not frappe.db.exists("Agent", "Test Agent"):
			frappe.get_doc({
				"doctype": "Agent",
				"agent_name": "Test Agent",
				"agent_modality": "Both",
				"instructions": "Test agent fixture for automated tests.",
			}).insert(ignore_permissions=True)

	def test_get_agent_run_status_owner_can_access(self):
		"""Run owner can access the run status."""
		# Create test data
		conv_doc = frappe.new_doc("Agent Conversation")
		conv_doc.agent = "Test Agent"
		conv_doc.owner = "alice@example.com"
		conv_doc.insert()

		run_doc = frappe.new_doc("Agent Run")
		run_doc.agent = "Test Agent"
		run_doc.status = "Success"
		run_doc.response = "Test response"
		run_doc.conversation = conv_doc.name
		run_doc.owner = "alice@example.com"
		run_doc.insert()

		try:
			# Mock the call as alice
			import frappe.auth
			old_user = frappe.session.user
			try:
				frappe.session.user = "alice@example.com"
				frappe.set_user("alice@example.com")

				from huf.ai.agent_integration import get_agent_run_status
				result = get_agent_run_status(run_doc.name)

				assert result["success"] is True
				assert result["agent_run_id"] == run_doc.name
			finally:
				frappe.session.user = old_user
				frappe.set_user(old_user)
		finally:
			run_doc.delete()
			conv_doc.delete()

	def test_get_agent_run_status_non_owner_cannot_access(self):
		"""Non-owner cannot access the run status."""
		# Create test data
		conv_doc = frappe.new_doc("Agent Conversation")
		conv_doc.agent = "Test Agent"
		conv_doc.owner = "alice@example.com"
		conv_doc.insert()

		run_doc = frappe.new_doc("Agent Run")
		run_doc.agent = "Test Agent"
		run_doc.status = "Success"
		run_doc.response = "Test response"
		run_doc.conversation = conv_doc.name
		run_doc.owner = "alice@example.com"
		run_doc.insert()

		try:
			# Mock the call as bob
			old_user = frappe.session.user
			try:
				frappe.session.user = "bob@example.com"
				frappe.set_user("bob@example.com")

				from huf.ai.agent_integration import get_agent_run_status
				with self.assertRaises(frappe.PermissionError):
					get_agent_run_status(run_doc.name)
			finally:
				frappe.session.user = old_user
				frappe.set_user(old_user)
		finally:
			run_doc.delete()
			conv_doc.delete()
