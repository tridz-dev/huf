"""Test list-scoping for Agent Procedure Run via permission_query_conditions.

Tests that Agent Procedure Run list is scoped to the owner field,
preventing users from enumerating procedure runs created by other users.
"""

import frappe
import pytest
from huf.ai.agent_integration import get_procedure_run_permission_conditions


class TestProcedureRunListScope:
	"""Test permission_query_conditions for Agent Procedure Run."""

	def test_system_manager_gets_no_filter(self):
		"""System Manager should see no filter (returns None)."""
		frappe.set_user("Administrator")
		result = get_procedure_run_permission_conditions("Administrator")
		assert result is None

	def test_huf_user_gets_where_clause(self):
		"""Regular Huf User should get a WHERE clause filtering by owner."""
		result = get_procedure_run_permission_conditions("alice@example.com")
		assert result is not None
		assert "Agent Procedure Run" in result
		assert "owner" in result
		assert "alice@example.com" in result

	def test_huf_user_list_sees_only_own_procedure_runs(self):
		"""Huf User listing procedure runs should only see those they own."""
		# Setup: Create procedure runs for two users
		alice_run = frappe.new_doc("Agent Procedure Run")
		alice_run.procedure = "test_procedure"
		alice_run.pinned_fingerprint = "test-fingerprint"
		alice_run.pinned_definition_json = "{}"
		alice_run.status = "success"
		alice_run.owner = "alice@example.com"
		alice_run.insert()

		bob_run = frappe.new_doc("Agent Procedure Run")
		bob_run.procedure = "test_procedure"
		bob_run.pinned_fingerprint = "test-fingerprint"
		bob_run.pinned_definition_json = "{}"
		bob_run.status = "success"
		bob_run.owner = "bob@example.com"
		bob_run.insert()

		try:
			# Alice lists procedure runs as alice
			frappe.set_user("alice@example.com")
			alice_list = frappe.get_list(
				"Agent Procedure Run",
				filters=[],
				pluck="name",
			)

			# Alice should only see her own run
			assert alice_run.name in alice_list
			assert bob_run.name not in alice_list
		finally:
			alice_run.delete()
			bob_run.delete()

	def test_huf_user_list_excludes_foreign_procedure_runs(self):
		"""Huf User should not see procedure runs owned by others."""
		# Setup: Create a run owned by bob
		bob_run = frappe.new_doc("Agent Procedure Run")
		bob_run.procedure = "test_procedure"
		bob_run.pinned_fingerprint = "test-fingerprint"
		bob_run.pinned_definition_json = "{}"
		bob_run.status = "success"
		bob_run.owner = "bob@example.com"
		bob_run.insert()

		try:
			# Alice lists procedure runs as alice
			frappe.set_user("alice@example.com")
			alice_list = frappe.get_list(
				"Agent Procedure Run",
				filters=[],
				pluck="name",
			)

			# Alice should NOT see bob's run
			assert bob_run.name not in alice_list
		finally:
			bob_run.delete()

	def test_system_manager_list_sees_all_procedure_runs(self):
		"""System Manager should see all procedure runs from all users."""
		# Setup: Create runs for two users
		alice_run = frappe.new_doc("Agent Procedure Run")
		alice_run.procedure = "test_procedure"
		alice_run.pinned_fingerprint = "test-fingerprint"
		alice_run.pinned_definition_json = "{}"
		alice_run.status = "success"
		alice_run.owner = "alice@example.com"
		alice_run.insert()

		bob_run = frappe.new_doc("Agent Procedure Run")
		bob_run.procedure = "test_procedure"
		bob_run.pinned_fingerprint = "test-fingerprint"
		bob_run.pinned_definition_json = "{}"
		bob_run.status = "success"
		bob_run.owner = "bob@example.com"
		bob_run.insert()

		try:
			# System Manager lists procedure runs
			frappe.set_user("Administrator")
			admin_list = frappe.get_list(
				"Agent Procedure Run",
				filters=[],
				pluck="name",
			)

			# Admin should see both runs
			assert alice_run.name in admin_list
			assert bob_run.name in admin_list
		finally:
			alice_run.delete()
			bob_run.delete()
