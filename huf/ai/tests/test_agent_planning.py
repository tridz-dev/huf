"""
Unit tests for Agent planning and scheduling (WP-08).

Tests cover:
1. ST-08.1: run_immediately default is 0
2. ST-08.2: on_update enqueues planning
3. ST-08.3: provider errors don't block Agent save
4. ST-08.6: scheduler pre-claims next_execution and enqueues

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_agent_planning
"""
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, call
import frappe
from frappe.utils import now_datetime, add_to_date


class TestAgentRunImmediatelyDefault(unittest.TestCase):
    """ST-08.1: run_immediately defaults to 0 for new agents."""

    def test_new_agent_has_run_immediately_zero_by_default(self):
        """Verify that a freshly created Agent has run_immediately=0."""
        # Create a minimal Agent doc without saving
        agent = frappe.get_doc({
            "doctype": "Agent",
            "agent_name": "test_agent_default_" + frappe.utils.generate_hash(length=8),
            "provider": "OpenAI",
            "model": "gpt-4",
        })
        # Check the default value from the doctype schema
        self.assertEqual(agent.run_immediately, 0)

    def test_explicit_run_immediately_one_is_respected(self):
        """Verify that explicit run_immediately=1 is still respected."""
        agent = frappe.get_doc({
            "doctype": "Agent",
            "agent_name": "test_agent_explicit_" + frappe.utils.generate_hash(length=8),
            "provider": "OpenAI",
            "model": "gpt-4",
            "run_immediately": 1,
        })
        self.assertEqual(agent.run_immediately, 1)


class TestAgentPlanningEnqueue(unittest.TestCase):
    """ST-08.2: on_update enqueues planning instead of calling directly."""

    @patch("huf.huf.doctype.agent.agent.frappe.enqueue")
    @patch("huf.huf.doctype.agent.agent.clear_doc_event_agents_cache")
    def test_on_update_enqueues_planning_when_prompt_changes(self, mock_cache_clear, mock_enqueue):
        """Verify that on_update enqueues generate_default_plan_job when prompt changes."""
        # Create an agent with enable_multi_run=1
        agent = frappe.get_doc({
            "doctype": "Agent",
            "agent_name": "test_planning_enqueue_" + frappe.utils.generate_hash(length=8),
            "provider": "OpenAI",
            "model": "gpt-4",
            "enable_multi_run": 1,
            "instructions": "Initial instructions",
        })
        agent.insert(ignore_permissions=True)

        # Modify instructions to trigger on_update
        agent.instructions = "Modified instructions"

        # Mock out the actual enqueue to prevent job submission
        mock_enqueue.reset_mock()

        # Save to trigger on_update
        agent.save(ignore_permissions=True)

        # Verify enqueue was called with the correct parameters
        mock_enqueue.assert_called_once()
        call_args = mock_enqueue.call_args
        self.assertEqual(
            call_args[0][0],
            "huf.huf.doctype.agent.agent.generate_default_plan_job"
        )
        self.assertEqual(call_args[1]["agent"], agent.name)
        self.assertEqual(call_args[1]["enqueue_after_commit"], True)
        self.assertEqual(call_args[1]["queue"], "long")

    @patch("huf.huf.doctype.agent.agent.frappe.get_doc")
    @patch("huf.huf.doctype.agent.agent.frappe.log_error")
    def test_generate_default_plan_job_catches_all_exceptions(self, mock_log_error, mock_get_doc):
        """Verify that generate_default_plan_job catches all exceptions and logs them."""
        from huf.huf.doctype.agent.agent import generate_default_plan_job

        # Mock the agent doc to raise a provider error
        mock_agent = MagicMock()
        mock_agent.generate_default_plan.side_effect = Exception("Provider timeout")
        mock_get_doc.return_value = mock_agent

        # Call the job function - should not raise
        generate_default_plan_job("test_agent")

        # Verify the error was logged
        mock_log_error.assert_called_once()
        call_args = mock_log_error.call_args
        self.assertIn("Planning Job Failed", str(call_args))

    @patch("huf.huf.doctype.agent.agent.frappe.enqueue")
    @patch("huf.huf.doctype.agent.agent.clear_doc_event_agents_cache")
    def test_on_update_does_not_enqueue_when_multi_run_disabled(self, mock_cache_clear, mock_enqueue):
        """Verify that on_update does not enqueue when enable_multi_run is 0."""
        agent = frappe.get_doc({
            "doctype": "Agent",
            "agent_name": "test_no_enqueue_" + frappe.utils.generate_hash(length=8),
            "provider": "OpenAI",
            "model": "gpt-4",
            "enable_multi_run": 0,
            "instructions": "Initial instructions",
        })
        agent.insert(ignore_permissions=True)

        mock_enqueue.reset_mock()

        # Modify instructions
        agent.instructions = "Modified"
        agent.save(ignore_permissions=True)

        # Verify enqueue was NOT called
        mock_enqueue.assert_not_called()


class TestSchedulerPreClaim(unittest.TestCase):
    """ST-08.6: scheduler pre-claims next_execution with conditional UPDATE."""

    @patch("huf.ai.agent_scheduler.frappe.db.sql")
    @patch("huf.ai.agent_scheduler.frappe.db.commit")
    @patch("huf.ai.agent_scheduler.frappe.enqueue")
    @patch("huf.ai.agent_scheduler.frappe.get_all")
    def test_scheduler_issues_conditional_update_for_each_trigger(
        self, mock_get_all, mock_enqueue, mock_commit, mock_sql
    ):
        """Verify that run_scheduled_agents issues a conditional UPDATE for each trigger."""
        from huf.ai.agent_scheduler import run_scheduled_agents

        # Mock triggers list
        now = now_datetime().replace(microsecond=0)
        past = now - timedelta(seconds=1)
        mock_get_all.return_value = [
            {
                "name": "trigger_1",
                "agent": "test_agent",
                "scheduled_interval": "daily",
                "interval_count": 1,
                "next_execution": past,
                "last_execution": None,
                "execution_mode": "Sync",
            }
        ]

        # Mock SQL to return success (rowcount == 1)
        mock_sql.side_effect = [
            None,  # First call: the UPDATE statement
            [[1]],  # Second call: ROW_COUNT() returns 1
        ]

        # Mock frappe permissions/db checks
        with patch("huf.ai.agent_scheduler.frappe.session.user", "Administrator"):
            with patch("huf.ai.agent_scheduler.frappe.db.exists", return_value=True):
                with patch("huf.ai.agent_scheduler.frappe.has_permission", return_value=True):
                    with patch("huf.ai.agent_scheduler.automation_runtime_is_new", return_value=False):
                        with patch("huf.ai.agent_scheduler.frappe.get_doc") as mock_get_doc:
                            mock_agent = MagicMock()
                            mock_agent.provider = "OpenAI"
                            mock_agent.model = "gpt-4"
                            mock_get_doc.return_value = mock_agent

                            run_scheduled_agents()

        # Verify UPDATE was called with conditional WHERE clause
        update_call = mock_sql.call_args_list[0]
        self.assertIn("UPDATE `tabAgent Trigger`", update_call[0][0])
        self.assertIn("next_execution = %(observed_next)s", update_call[0][0])
        self.assertIn("WHERE name = %(name)s", update_call[0][0])

    @patch("huf.ai.agent_scheduler.frappe.db.sql")
    @patch("huf.ai.agent_scheduler.frappe.db.commit")
    @patch("huf.ai.agent_scheduler.frappe.enqueue")
    @patch("huf.ai.agent_scheduler.frappe.get_all")
    def test_scheduler_skips_trigger_if_rowcount_is_zero(
        self, mock_get_all, mock_enqueue, mock_commit, mock_sql
    ):
        """Verify that scheduler skips a trigger if another tick already claimed it (rowcount==0)."""
        from huf.ai.agent_scheduler import run_scheduled_agents

        now = now_datetime().replace(microsecond=0)
        past = now - timedelta(seconds=1)
        mock_get_all.return_value = [
            {
                "name": "trigger_1",
                "agent": "test_agent",
                "scheduled_interval": "daily",
                "interval_count": 1,
                "next_execution": past,
                "last_execution": None,
                "execution_mode": "Sync",
            }
        ]

        # Mock SQL to return failure (rowcount == 0)
        mock_sql.side_effect = [
            None,  # UPDATE statement
            [[0]],  # ROW_COUNT() returns 0 (another tick got there first)
        ]

        with patch("huf.ai.agent_scheduler.frappe.session.user", "Administrator"):
            with patch("huf.ai.agent_scheduler.frappe.db.exists", return_value=True):
                with patch("huf.ai.agent_scheduler.frappe.has_permission", return_value=True):
                    with patch("huf.ai.agent_scheduler.automation_runtime_is_new", return_value=False):
                        with patch("huf.ai.agent_scheduler.frappe.get_doc"):
                            run_scheduled_agents()

        # Verify enqueue was NOT called (we skipped due to rowcount==0)
        mock_enqueue.assert_not_called()

    @patch("huf.ai.agent_scheduler.frappe.db.sql")
    @patch("huf.ai.agent_scheduler.frappe.db.commit")
    @patch("huf.ai.agent_scheduler.frappe.enqueue")
    @patch("huf.ai.agent_scheduler.frappe.get_all")
    def test_scheduler_enqueues_execute_scheduled_agent(
        self, mock_get_all, mock_enqueue, mock_commit, mock_sql
    ):
        """Verify that scheduler enqueues execute_scheduled_agent when rowcount==1."""
        from huf.ai.agent_scheduler import run_scheduled_agents

        now = now_datetime().replace(microsecond=0)
        past = now - timedelta(seconds=1)
        mock_get_all.return_value = [
            {
                "name": "trigger_1",
                "agent": "test_agent",
                "scheduled_interval": "daily",
                "interval_count": 1,
                "next_execution": past,
                "last_execution": None,
                "execution_mode": "Sync",
            }
        ]

        # Mock SQL to return success
        mock_sql.side_effect = [
            None,  # UPDATE
            [[1]],  # ROW_COUNT()
        ]

        with patch("huf.ai.agent_scheduler.frappe.session.user", "Administrator"):
            with patch("huf.ai.agent_scheduler.frappe.db.exists", return_value=True):
                with patch("huf.ai.agent_scheduler.frappe.has_permission", return_value=True):
                    with patch("huf.ai.agent_scheduler.automation_runtime_is_new", return_value=False):
                        with patch("huf.ai.agent_scheduler.frappe.get_doc"):
                            run_scheduled_agents()

        # Verify enqueue was called with correct parameters
        mock_enqueue.assert_called_once()
        call_args = mock_enqueue.call_args
        self.assertEqual(
            call_args[0][0],
            "huf.ai.agent_scheduler.execute_scheduled_agent"
        )
        self.assertEqual(call_args[1]["agent_trigger"], "trigger_1")
        self.assertEqual(call_args[1]["agent"], "test_agent")
        self.assertEqual(call_args[1]["enqueue_after_commit"], True)
        self.assertEqual(call_args[1]["queue"], "long")
