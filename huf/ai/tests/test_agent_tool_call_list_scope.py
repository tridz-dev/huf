"""Test list-scoping for Agent Tool Call via permission_query_conditions.

Tests that Agent Tool Call list is scoped via the agent_run link field's owner,
preventing users from enumerating tool calls from other users' runs.
"""

import frappe
from frappe.tests import IntegrationTestCase
from huf.ai.agent_integration import get_tool_call_permission_conditions


class TestAgentToolCallListScope(IntegrationTestCase):
	"""Test permission_query_conditions for Agent Tool Call."""

	def setUp(self):
		if not frappe.db.exists("Agent", "Test Agent"):
			frappe.get_doc({
				"doctype": "Agent",
				"agent_name": "Test Agent",
				"agent_modality": "Both",
				"instructions": "Test agent fixture for automated tests.",
			}).insert(ignore_permissions=True)

		# frappe.get_list's read check goes through the full role-based
		# permission stack; alice/bob need a real User with a role that has
		# base read access on Agent Tool Call (Huf User) before the
		# permission_query_conditions scoping is ever reached.
		for email in ("alice@example.com", "bob@example.com"):
			if not frappe.db.exists("User", email):
				frappe.get_doc({
					"doctype": "User",
					"email": email,
					"first_name": email.split("@")[0],
					"send_welcome_email": 0,
					"roles": [{"role": "Huf User"}],
				}).insert(ignore_permissions=True)

	def test_system_manager_gets_no_filter(self):
		"""System Manager should see no filter (returns None)."""
		frappe.set_user("Administrator")
		result = get_tool_call_permission_conditions("Administrator")
		assert result is None

	def test_huf_user_gets_where_clause(self):
		"""Regular Huf User should get a WHERE clause filtering by agent_run owner."""
		frappe.set_user("alice@example.com")
		result = get_tool_call_permission_conditions("alice@example.com")
		assert result is not None
		assert "Agent Run" in result
		assert "owner" in result
		assert "alice@example.com" in result or "alice@example.com" in result

	def test_huf_user_list_sees_only_own_tool_calls(self):
		"""Huf User listing tool calls should only see those from own runs."""
		# Setup: Create two users' runs
		alice_run = frappe.new_doc("Agent Run")
		alice_run.agent = "Test Agent"
		alice_run.status = "Started"
		alice_run.owner = "alice@example.com"
		alice_run.insert()
		alice_run.db_set("owner", "alice@example.com", update_modified=False)

		bob_run = frappe.new_doc("Agent Run")
		bob_run.agent = "Test Agent"
		bob_run.status = "Started"
		bob_run.owner = "bob@example.com"
		bob_run.insert()
		bob_run.db_set("owner", "bob@example.com", update_modified=False)

		# Create tool calls for each run
		alice_tool = frappe.new_doc("Agent Tool Call")
		alice_tool.agent_run = alice_run.name
		alice_tool.tool_name = "test_tool"
		alice_tool.status = "Completed"
		alice_tool.insert()

		bob_tool = frappe.new_doc("Agent Tool Call")
		bob_tool.agent_run = bob_run.name
		bob_tool.tool_name = "test_tool"
		bob_tool.status = "Completed"
		bob_tool.insert()

		try:
			# Alice lists tool calls as alice
			frappe.set_user("alice@example.com")
			alice_list = frappe.get_list(
				"Agent Tool Call",
				filters=[],
				pluck="name",
			)

			# Alice should only see her own tool call
			assert alice_tool.name in alice_list
			assert bob_tool.name not in alice_list
		finally:
			frappe.set_user("Administrator")
			alice_tool.delete()
			bob_tool.delete()
			alice_run.delete()
			bob_run.delete()

	def test_huf_user_list_excludes_foreign_tool_calls(self):
		"""Huf User should not appear in list results for others' tool calls."""
		# Setup: Create a run owned by bob
		bob_run = frappe.new_doc("Agent Run")
		bob_run.agent = "Test Agent"
		bob_run.status = "Started"
		bob_run.owner = "bob@example.com"
		bob_run.insert()
		bob_run.db_set("owner", "bob@example.com", update_modified=False)

		# Create a tool call for bob's run
		bob_tool = frappe.new_doc("Agent Tool Call")
		bob_tool.agent_run = bob_run.name
		bob_tool.tool_name = "test_tool"
		bob_tool.status = "Completed"
		bob_tool.insert()

		try:
			# Alice lists tool calls as alice
			frappe.set_user("alice@example.com")
			alice_list = frappe.get_list(
				"Agent Tool Call",
				filters=[],
				pluck="name",
			)

			# Alice should NOT see bob's tool call
			assert bob_tool.name not in alice_list
		finally:
			frappe.set_user("Administrator")
			bob_tool.delete()
			bob_run.delete()

	def test_system_manager_list_sees_all_tool_calls(self):
		"""System Manager should see all tool calls from all users."""
		# Setup: Create runs for two users
		alice_run = frappe.new_doc("Agent Run")
		alice_run.agent = "Test Agent"
		alice_run.status = "Started"
		alice_run.owner = "alice@example.com"
		alice_run.insert()
		alice_run.db_set("owner", "alice@example.com", update_modified=False)

		bob_run = frappe.new_doc("Agent Run")
		bob_run.agent = "Test Agent"
		bob_run.status = "Started"
		bob_run.owner = "bob@example.com"
		bob_run.insert()
		bob_run.db_set("owner", "bob@example.com", update_modified=False)

		# Create tool calls for each run
		alice_tool = frappe.new_doc("Agent Tool Call")
		alice_tool.agent_run = alice_run.name
		alice_tool.tool_name = "test_tool"
		alice_tool.status = "Completed"
		alice_tool.insert()

		bob_tool = frappe.new_doc("Agent Tool Call")
		bob_tool.agent_run = bob_run.name
		bob_tool.tool_name = "test_tool"
		bob_tool.status = "Completed"
		bob_tool.insert()

		try:
			# System Manager lists tool calls
			frappe.set_user("Administrator")
			admin_list = frappe.get_list(
				"Agent Tool Call",
				filters=[],
				pluck="name",
			)

			# Admin should see both tool calls
			assert alice_tool.name in admin_list
			assert bob_tool.name in admin_list
		finally:
			alice_tool.delete()
			bob_tool.delete()
			alice_run.delete()
			bob_run.delete()
