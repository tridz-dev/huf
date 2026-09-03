"""Test record-level authorization for Agent Run doctype.

Tests the has_permission hook for Agent Run, verifying that only
the run owner, System Manager, or users with agent.view_all can
access a run.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase


class TestAgentRunRecordAuth(IntegrationTestCase):
	def setUp(self):
		if not frappe.db.exists("Agent", "Test Agent"):
			frappe.get_doc({
				"doctype": "Agent",
				"agent_name": "Test Agent",
				"agent_modality": "Both",
				"instructions": "Test agent fixture for automated tests.",
			}).insert(ignore_permissions=True)

	def test_agent_run_owner_can_read(self):
		"""Owner of a run can read it."""
		# Create a test run owned by alice
		run_doc = frappe.new_doc("Agent Run")
		run_doc.agent = "Test Agent"
		run_doc.status = "Success"
		run_doc.owner = "alice@example.com"
		run_doc.insert()

		try:
			# Verify alice can read it
			from huf.ai.record_access import user_can_read_run
			assert user_can_read_run(run_doc, user="alice@example.com") is True
		finally:
			run_doc.delete()

	def test_agent_run_non_owner_cannot_read(self):
		"""Non-owner cannot read a run."""
		# Create a test run owned by alice
		run_doc = frappe.new_doc("Agent Run")
		run_doc.agent = "Test Agent"
		run_doc.status = "Success"
		run_doc.owner = "alice@example.com"
		run_doc.insert()

		try:
			# Verify bob cannot read it
			from huf.ai.record_access import user_can_read_run
			assert user_can_read_run(run_doc, user="bob@example.com") is False
		finally:
			run_doc.delete()

	def test_agent_run_system_manager_can_read(self):
		"""System Manager can read any run."""
		# Create a test run owned by alice
		run_doc = frappe.new_doc("Agent Run")
		run_doc.agent = "Test Agent"
		run_doc.status = "Success"
		run_doc.owner = "alice@example.com"
		run_doc.insert()

		try:
			# Verify System Manager can read it
			from huf.ai.record_access import user_can_read_run
			assert user_can_read_run(run_doc, user="Administrator") is True
		finally:
			run_doc.delete()

	def test_agent_run_view_all_capability_can_read(self):
		"""A non-owner with the agent.view_all capability can read any run."""
		run_doc = frappe.new_doc("Agent Run")
		run_doc.agent = "Test Agent"
		run_doc.status = "Success"
		run_doc.owner = "alice@example.com"
		run_doc.insert()

		try:
			from huf.ai.record_access import user_can_read_run

			with patch("huf.permissions.has_capability", return_value=True):
				assert user_can_read_run(run_doc, user="carol@example.com") is True
		finally:
			run_doc.delete()
