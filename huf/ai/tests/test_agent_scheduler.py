"""
Tests for agent scheduler, specifically idempotency of Batch Job submissions.

Covers:
- ST-R4.5: Idempotency guard prevents duplicate Batch Job submissions.

Note: run_scheduled_agents() was refactored (alongside this track's own
changes, merged from a sibling security-hardening track) to pre-claim each
due trigger via a conditional UPDATE (atomic dequeue -- only the tick that
observes the expected next_execution value wins the claim) and then
`frappe.enqueue` the actual execution as `execute_scheduled_agent`, rather
than running the agent inline. The scheduler-tick-level duplicate-enqueue
race is now closed by the pre-claim itself; ST-R4.5's Batch Job idempotency
check moved into `execute_scheduled_agent` (where `_submit_batch_job_for_trigger`
is now actually called) as defense-in-depth against an RQ worker retrying
the same job after a crash mid-execution.

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_agent_scheduler
"""
import unittest
from unittest.mock import MagicMock, patch
from frappe.utils import now_datetime

from huf.ai.agent_scheduler import execute_scheduled_agent, run_scheduled_agents


class TestAgentSchedulerPreClaim(unittest.TestCase):
	"""Test the pre-claim dequeue mechanism in run_scheduled_agents()."""

	def setUp(self):
		self.now = now_datetime().replace(microsecond=0)
		self.trigger = {
			"name": "trigger-batch-001",
			"agent": "test-agent",
			"scheduled_interval": "daily",
			"interval_count": 1,
			"next_execution": self.now,
			"last_execution": None,
			"execution_mode": "Batch",
		}

	@patch("huf.ai.agent_scheduler.frappe")
	@patch("huf.ai.agent_scheduler.automation_runtime_is_new")
	def test_enqueues_when_pre_claim_wins(self, mock_automation_runtime_is_new, mock_frappe):
		"""A tick that wins the conditional-UPDATE claim (rowcount == 1) enqueues execute_scheduled_agent."""
		mock_automation_runtime_is_new.return_value = False
		mock_frappe.session.user = "Administrator"
		mock_frappe.has_permission.return_value = True
		mock_frappe.db.exists.return_value = True
		mock_frappe.get_all.return_value = [self.trigger]
		# UPDATE call, then SELECT ROW_COUNT() -> [[1]] (claim won)
		mock_frappe.db.sql.side_effect = [None, [[1]]]

		run_scheduled_agents()

		mock_frappe.enqueue.assert_called_once()
		call_kwargs = mock_frappe.enqueue.call_args
		self.assertEqual(call_kwargs[0][0], "huf.ai.agent_scheduler.execute_scheduled_agent")
		self.assertEqual(call_kwargs[1]["agent_trigger"], "trigger-batch-001")

	@patch("huf.ai.agent_scheduler.frappe")
	@patch("huf.ai.agent_scheduler.automation_runtime_is_new")
	def test_skips_enqueue_when_pre_claim_lost(self, mock_automation_runtime_is_new, mock_frappe):
		"""A tick that loses the conditional-UPDATE claim (rowcount == 0, another tick already
		claimed this trigger) must not enqueue a second execute_scheduled_agent job -- this is
		the actual duplicate-enqueue race fix now that submission is deferred to the queue."""
		mock_automation_runtime_is_new.return_value = False
		mock_frappe.session.user = "Administrator"
		mock_frappe.has_permission.return_value = True
		mock_frappe.db.exists.return_value = True
		mock_frappe.get_all.return_value = [self.trigger]
		# UPDATE call, then SELECT ROW_COUNT() -> [[0]] (claim lost)
		mock_frappe.db.sql.side_effect = [None, [[0]]]

		run_scheduled_agents()

		mock_frappe.enqueue.assert_not_called()


class TestExecuteScheduledAgentIdempotency(unittest.TestCase):
	"""Test the Batch Job idempotency guard inside execute_scheduled_agent()."""

	def setUp(self):
		self.trigger_doc = MagicMock()
		self.trigger_doc.name = "trigger-batch-001"
		self.trigger_doc.execution_mode = "Batch"
		self.trigger_doc.get = lambda key, default=None: {"agent": "test-agent", "name": "trigger-batch-001"}.get(
			key, default
		)
		self.trigger_doc.__getitem__ = lambda self_, key: {"agent": "test-agent", "name": "trigger-batch-001"}[key]

		self.agent_doc = MagicMock()
		self.agent_doc.agent_name = "test-agent"
		self.agent_doc.provider = "test-provider"
		self.agent_doc.model = "test-model"

	@patch("huf.ai.agent_scheduler.frappe")
	@patch("huf.ai.agent_scheduler._submit_batch_job_for_trigger")
	@patch("huf.ai.prompt_resolver.resolve_prompt")
	def test_batch_job_submitted_when_no_existing_job(
		self, mock_resolve_prompt, mock_submit_batch, mock_frappe
	):
		"""execute_scheduled_agent submits a Batch Job when none is Pending/Submitted for this trigger."""
		mock_frappe.get_doc.side_effect = [self.trigger_doc, self.agent_doc]
		mock_frappe.db.get_value.return_value = None  # No existing job
		mock_resolve_prompt.return_value = "Test prompt"

		execute_scheduled_agent(agent_trigger="trigger-batch-001", agent="test-agent")

		mock_submit_batch.assert_called_once()
		call_args = mock_submit_batch.call_args
		self.assertEqual(call_args[0][0], self.trigger_doc)
		self.assertEqual(call_args[0][1], self.agent_doc)
		self.assertEqual(call_args[0][2], "Test prompt")

	@patch("huf.ai.agent_scheduler.frappe")
	@patch("huf.ai.agent_scheduler._submit_batch_job_for_trigger")
	@patch("huf.ai.prompt_resolver.resolve_prompt")
	def test_batch_job_skipped_when_pending_job_exists(
		self, mock_resolve_prompt, mock_submit_batch, mock_frappe
	):
		"""execute_scheduled_agent skips submission when a Batch Job already exists Pending/Submitted
		for this trigger -- the defense-in-depth guard against an RQ retry re-running this job."""
		mock_frappe.get_doc.side_effect = [self.trigger_doc, self.agent_doc]
		mock_frappe.db.get_value.return_value = "BJ-existing-pending"
		mock_resolve_prompt.return_value = "Test prompt"

		execute_scheduled_agent(agent_trigger="trigger-batch-001", agent="test-agent")

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
