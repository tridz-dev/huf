"""
Tests for agent scheduler, specifically idempotency of Batch Job submissions.

Covers:
- ST-R4.5: Idempotency guard prevents duplicate Batch Job submissions
  when a trigger is due and the scheduler runs multiple times in sequence.

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_agent_scheduler
"""
import unittest
from unittest.mock import MagicMock, patch, call
from frappe.utils import now_datetime

from huf.ai.agent_scheduler import run_scheduled_agents


class TestAgentSchedulerIdempotency(unittest.TestCase):
	"""Test idempotency guards in the scheduled agent scheduler."""

	def setUp(self):
		"""Set up mock objects for testing."""
		self.now = now_datetime().replace(microsecond=0)

		# Create a mock trigger with Batch execution mode
		self.trigger = {
			"name": "trigger-batch-001",
			"agent": "test-agent",
			"scheduled_interval": "daily",
			"interval_count": 1,
			"next_execution": self.now,
			"last_execution": None,
			"execution_mode": "Batch",
		}

		# Create a mock agent document
		self.agent_doc = MagicMock()
		self.agent_doc.agent_name = "test-agent"
		self.agent_doc.provider = "test-provider"
		self.agent_doc.model = "test-model"

	@patch("huf.ai.agent_scheduler.frappe")
	@patch("huf.ai.agent_scheduler.automation_runtime_is_new")
	@patch("huf.ai.agent_scheduler._submit_batch_job_for_trigger")
	@patch("huf.ai.agent_scheduler.resolve_prompt")
	def test_batch_job_idempotency_prevents_duplicate_submissions(
		self,
		mock_resolve_prompt,
		mock_submit_batch,
		mock_automation_runtime_is_new,
		mock_frappe,
	):
		"""
		Test that calling run_scheduled_agents() twice with the same due
		Batch trigger results in exactly one _submit_batch_job_for_trigger call.

		This verifies ST-R4.5: the idempotency guard queries for an existing
		Batch Job with the trigger name and status Pending/Submitted, and
		skips submission if one is found.
		"""
		# Mock automation_runtime_is_new to return False (legacy path is active)
		mock_automation_runtime_is_new.return_value = False

		# Set up frappe mock
		mock_frappe.session.user = "Administrator"
		mock_frappe.has_permission.return_value = True
		mock_frappe.db.exists.return_value = True  # Agent Trigger DocType exists
		mock_frappe.get_doc.return_value = self.agent_doc
		mock_frappe.logger.return_value = MagicMock()

		# Mock resolve_prompt to return a test prompt
		mock_resolve_prompt.return_value = "Test scheduled prompt"

		# First call: no existing Batch Job, should submit
		mock_frappe.get_all.return_value = [self.trigger]
		mock_frappe.db.get_value.return_value = None  # No existing job

		run_scheduled_agents()

		# Assert _submit_batch_job_for_trigger was called once
		self.assertEqual(mock_submit_batch.call_count, 1)

		# Second call: simulating an existing Batch Job with Pending status
		# Reset the mock to track the second call
		mock_frappe.db.get_value.return_value = "BJ-00001"  # Existing job name

		run_scheduled_agents()

		# Assert _submit_batch_job_for_trigger was NOT called a second time
		# (still 1, not 2)
		self.assertEqual(mock_submit_batch.call_count, 1)

	@patch("huf.ai.agent_scheduler.frappe")
	@patch("huf.ai.agent_scheduler.automation_runtime_is_new")
	@patch("huf.ai.agent_scheduler._submit_batch_job_for_trigger")
	@patch("huf.ai.agent_scheduler.resolve_prompt")
	def test_batch_job_submitted_when_no_existing_job(
		self,
		mock_resolve_prompt,
		mock_submit_batch,
		mock_automation_runtime_is_new,
		mock_frappe,
	):
		"""
		Test that _submit_batch_job_for_trigger is called when there is
		no existing Batch Job for the trigger.
		"""
		mock_automation_runtime_is_new.return_value = False
		mock_frappe.session.user = "Administrator"
		mock_frappe.has_permission.return_value = True
		mock_frappe.db.exists.return_value = True
		mock_frappe.get_doc.return_value = self.agent_doc
		mock_frappe.logger.return_value = MagicMock()
		mock_resolve_prompt.return_value = "Test prompt"

		mock_frappe.get_all.return_value = [self.trigger]
		mock_frappe.db.get_value.return_value = None  # No existing job

		run_scheduled_agents()

		# Verify _submit_batch_job_for_trigger was called with correct arguments
		mock_submit_batch.assert_called_once()
		call_args = mock_submit_batch.call_args
		self.assertEqual(call_args[0][0], self.trigger)  # trigger
		self.assertEqual(call_args[0][1], self.agent_doc)  # agent
		self.assertEqual(call_args[0][2], "Test prompt")  # prompt

	@patch("huf.ai.agent_scheduler.frappe")
	@patch("huf.ai.agent_scheduler.automation_runtime_is_new")
	@patch("huf.ai.agent_scheduler._submit_batch_job_for_trigger")
	@patch("huf.ai.agent_scheduler.resolve_prompt")
	def test_batch_job_skipped_when_pending_job_exists(
		self,
		mock_resolve_prompt,
		mock_submit_batch,
		mock_automation_runtime_is_new,
		mock_frappe,
	):
		"""
		Test that _submit_batch_job_for_trigger is skipped when a Batch Job
		already exists with status "Pending".
		"""
		mock_automation_runtime_is_new.return_value = False
		mock_frappe.session.user = "Administrator"
		mock_frappe.has_permission.return_value = True
		mock_frappe.db.exists.return_value = True
		mock_frappe.get_doc.return_value = self.agent_doc
		mock_frappe.logger.return_value = MagicMock()
		mock_resolve_prompt.return_value = "Test prompt"

		mock_frappe.get_all.return_value = [self.trigger]
		mock_frappe.db.get_value.return_value = "BJ-existing-pending"

		run_scheduled_agents()

		# Verify _submit_batch_job_for_trigger was NOT called
		mock_submit_batch.assert_not_called()

	@patch("huf.ai.agent_scheduler.frappe")
	@patch("huf.ai.agent_scheduler.automation_runtime_is_new")
	def test_legacy_scheduler_logs_when_new_runtime_active(
		self,
		mock_automation_runtime_is_new,
		mock_frappe,
	):
		"""
		Test that run_scheduled_agents logs a message when returning early
		due to automation_runtime_is_new() being True (ST-R4.6).
		"""
		mock_automation_runtime_is_new.return_value = True
		mock_logger = MagicMock()
		mock_frappe.logger.return_value = mock_logger

		run_scheduled_agents()

		# Verify the logger was called with the deprecation message
		mock_logger.info.assert_called_once()
		call_args = mock_logger.info.call_args[0][0]
		self.assertIn("legacy scheduler is disabled", call_args)
		self.assertIn("new automation_runtime is active", call_args)
