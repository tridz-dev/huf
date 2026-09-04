"""Test list-scoping for Agent Run Prompt Snapshot via permission_query_conditions.

Tests that Agent Run Prompt Snapshot list is scoped via the agent_run link field's owner,
preventing managers from enumerating snapshots from other users' runs.
"""

import frappe
from frappe.tests import IntegrationTestCase
from huf.ai.agent_integration import get_prompt_snapshot_permission_conditions


class TestAgentRunPromptSnapshotListScope(IntegrationTestCase):
	"""Test permission_query_conditions for Agent Run Prompt Snapshot."""

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
		# base read access on Agent Run Prompt Snapshot (Huf User) before
		# the permission_query_conditions scoping is ever reached.
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
		result = get_prompt_snapshot_permission_conditions("Administrator")
		assert result is None

	def test_huf_manager_gets_where_clause(self):
		"""Huf User should get a WHERE clause filtering by agent_run owner."""
		result = get_prompt_snapshot_permission_conditions("alice@example.com")
		assert result is not None
		assert "Agent Run" in result
		assert "owner" in result
		assert "alice@example.com" in result

	def test_huf_manager_list_sees_only_own_snapshots(self):
		"""Huf User listing snapshots should only see those from own runs."""
		# Setup: Create two users' runs with snapshots
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

		# Create snapshots for each run
		alice_snapshot = frappe.new_doc("Agent Run Prompt Snapshot")
		alice_snapshot.agent_run = alice_run.name
		alice_snapshot.system_prompt = "test prompt"
		alice_snapshot.captured_at = frappe.utils.now_datetime()
		alice_snapshot.insert()

		bob_snapshot = frappe.new_doc("Agent Run Prompt Snapshot")
		bob_snapshot.agent_run = bob_run.name
		bob_snapshot.system_prompt = "test prompt"
		bob_snapshot.captured_at = frappe.utils.now_datetime()
		bob_snapshot.insert()

		try:
			# Alice lists snapshots as alice
			frappe.set_user("alice@example.com")
			alice_list = frappe.get_list(
				"Agent Run Prompt Snapshot",
				filters=[],
				pluck="name",
			)

			# Alice should only see her own snapshot
			assert alice_snapshot.name in alice_list
			assert bob_snapshot.name not in alice_list
		finally:
			frappe.set_user("Administrator")
			alice_snapshot.delete()
			bob_snapshot.delete()
			alice_run.delete()
			bob_run.delete()

	def test_huf_manager_list_excludes_foreign_snapshots(self):
		"""Huf User should not see snapshots from other users' runs."""
		# Setup: Create a run owned by bob
		bob_run = frappe.new_doc("Agent Run")
		bob_run.agent = "Test Agent"
		bob_run.status = "Started"
		bob_run.owner = "bob@example.com"
		bob_run.insert()
		bob_run.db_set("owner", "bob@example.com", update_modified=False)

		# Create a snapshot for bob's run
		bob_snapshot = frappe.new_doc("Agent Run Prompt Snapshot")
		bob_snapshot.agent_run = bob_run.name
		bob_snapshot.system_prompt = "test prompt"
		bob_snapshot.captured_at = frappe.utils.now_datetime()
		bob_snapshot.insert()

		try:
			# Alice lists snapshots as alice
			frappe.set_user("alice@example.com")
			alice_list = frappe.get_list(
				"Agent Run Prompt Snapshot",
				filters=[],
				pluck="name",
			)

			# Alice should NOT see bob's snapshot
			assert bob_snapshot.name not in alice_list
		finally:
			frappe.set_user("Administrator")
			bob_snapshot.delete()
			bob_run.delete()

	def test_system_manager_list_sees_all_snapshots(self):
		"""System Manager should see all snapshots from all users."""
		# Setup: Create runs for two users with snapshots
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

		# Create snapshots for each run
		alice_snapshot = frappe.new_doc("Agent Run Prompt Snapshot")
		alice_snapshot.agent_run = alice_run.name
		alice_snapshot.system_prompt = "test prompt"
		alice_snapshot.captured_at = frappe.utils.now_datetime()
		alice_snapshot.insert()

		bob_snapshot = frappe.new_doc("Agent Run Prompt Snapshot")
		bob_snapshot.agent_run = bob_run.name
		bob_snapshot.system_prompt = "test prompt"
		bob_snapshot.captured_at = frappe.utils.now_datetime()
		bob_snapshot.insert()

		try:
			# System Manager lists snapshots
			frappe.set_user("Administrator")
			admin_list = frappe.get_list(
				"Agent Run Prompt Snapshot",
				filters=[],
				pluck="name",
			)

			# Admin should see both snapshots
			assert alice_snapshot.name in admin_list
			assert bob_snapshot.name in admin_list
		finally:
			alice_snapshot.delete()
			bob_snapshot.delete()
			alice_run.delete()
			bob_run.delete()
