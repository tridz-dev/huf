"""Test record-level authorization for Agent Tool Call doctype.

Tests the has_permission hook for Agent Tool Call, verifying that only
users who own the tool call's run, System Manager, or users with
agent.view_all can access a tool call.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase


class TestAgentToolCallRecordAuth(IntegrationTestCase):
	def setUp(self):
		if not frappe.db.exists("Agent", "Test Agent"):
			frappe.get_doc({
				"doctype": "Agent",
				"agent_name": "Test Agent",
				"agent_modality": "Both",
				"instructions": "Test agent fixture for automated tests.",
			}).insert(ignore_permissions=True)

	def test_agent_tool_call_run_owner_can_read(self):
		"""Owner of the tool call's run can read it."""
		# Create a test run owned by alice
		run_doc = frappe.new_doc("Agent Run")
		run_doc.agent = "Test Agent"
		run_doc.status = "Started"
		run_doc.owner = "alice@example.com"
		run_doc.insert()
		run_doc.db_set("owner", "alice@example.com", update_modified=False)

		# Create a test tool call in that run
		tool_doc = frappe.new_doc("Agent Tool Call")
		tool_doc.agent_run = run_doc.name
		tool_doc.tool_name = "test_tool"
		tool_doc.status = "Completed"
		tool_doc.insert()

		try:
			# Verify alice can read it
			from huf.ai.record_access import user_can_read_tool_call
			assert user_can_read_tool_call(tool_doc, user="alice@example.com") is True
		finally:
			tool_doc.delete()
			run_doc.delete()

	def test_agent_tool_call_non_run_owner_cannot_read(self):
		"""Non-owner of the run cannot read its tool calls."""
		# Create a test run owned by alice
		run_doc = frappe.new_doc("Agent Run")
		run_doc.agent = "Test Agent"
		run_doc.status = "Started"
		run_doc.owner = "alice@example.com"
		run_doc.insert()
		run_doc.db_set("owner", "alice@example.com", update_modified=False)

		# Create a test tool call in that run
		tool_doc = frappe.new_doc("Agent Tool Call")
		tool_doc.agent_run = run_doc.name
		tool_doc.tool_name = "test_tool"
		tool_doc.status = "Completed"
		tool_doc.insert()

		try:
			# Verify bob cannot read it
			from huf.ai.record_access import user_can_read_tool_call
			assert user_can_read_tool_call(tool_doc, user="bob@example.com") is False
		finally:
			tool_doc.delete()
			run_doc.delete()

	def test_agent_tool_call_system_manager_can_read(self):
		"""System Manager can read any tool call."""
		# Create a test run owned by alice
		run_doc = frappe.new_doc("Agent Run")
		run_doc.agent = "Test Agent"
		run_doc.status = "Started"
		run_doc.owner = "alice@example.com"
		run_doc.insert()
		run_doc.db_set("owner", "alice@example.com", update_modified=False)

		# Create a test tool call in that run
		tool_doc = frappe.new_doc("Agent Tool Call")
		tool_doc.agent_run = run_doc.name
		tool_doc.tool_name = "test_tool"
		tool_doc.status = "Completed"
		tool_doc.insert()

		try:
			# Verify System Manager can read it
			from huf.ai.record_access import user_can_read_tool_call
			assert user_can_read_tool_call(tool_doc, user="Administrator") is True
		finally:
			tool_doc.delete()
			run_doc.delete()

	def test_agent_tool_call_view_all_capability_can_read(self):
		"""A non-owner with the agent.view_all capability can read any tool call."""
		run_doc = frappe.new_doc("Agent Run")
		run_doc.agent = "Test Agent"
		run_doc.status = "Started"
		run_doc.owner = "alice@example.com"
		run_doc.insert()
		run_doc.db_set("owner", "alice@example.com", update_modified=False)

		tool_doc = frappe.new_doc("Agent Tool Call")
		tool_doc.agent_run = run_doc.name
		tool_doc.tool_name = "test_tool"
		tool_doc.status = "Completed"
		tool_doc.insert()

		try:
			from huf.ai.record_access import user_can_read_tool_call

			with patch("huf.permissions.has_capability", return_value=True):
				assert user_can_read_tool_call(tool_doc, user="carol@example.com") is True
		finally:
			tool_doc.delete()
			run_doc.delete()
