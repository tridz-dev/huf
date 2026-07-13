"""
Tests for queue-first execution of run_agent_sync.

Covers:
- Default behavior: only the Agent Run is persisted up front; the user
  message is deferred to the worker and the run is handed to the queue.
- `now` override and the `run_immediately` agent flag: synchronous
  execution with the user message persisted immediately (legacy behavior).
- Queued worker: acquires the conversation lock, adds exactly one user
  message under it, executes the precreated run, and releases the lock.
- Lock contention: the worker re-enqueues itself instead of dropping work,
  and never creates a duplicate user message.

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_queue_first_runs
"""
import unittest
from unittest.mock import MagicMock, patch

from huf.ai.agent_integration import (
    _execute_agent_run,
    _run_queued_agent,
    run_agent_sync,
)
from huf.ai import agent_chat
from huf.ai import agent_scheduler
from huf.ai.orchestration.planning import run_planning
from huf.ai.flow_engine import _exec_agent_run


def _make_agent_doc(**overrides):
    doc = MagicMock()
    doc.agent_name = "Test Agent"
    doc.provider = "Test Provider"
    doc.model = "test-model"
    doc.allow_guest = 1
    doc.allowed_users = []
    doc.allowed_roles = []
    doc.persist_conversation = 1
    doc.prompt_mode = "Local"
    doc.history_limit = 20
    doc.context_strategy = "FIFO"
    doc.enable_conversation_data = 0
    doc.enable_multi_run = 0
    doc.run_immediately = 0
    doc.max_knowledge_tokens = 4000
    doc.autonaming_of_conversation_title = 0
    doc.temperature = 0.7
    doc.top_p = 1.0
    doc.max_turns = 20
    for key, value in overrides.items():
        setattr(doc, key, value)
    return doc


class TestQueueFirstRuns(unittest.TestCase):
    def setUp(self):
        self.agent_doc = _make_agent_doc()

        self.conversation = MagicMock()
        self.conversation.name = "CONV-TEST-0001"
        self.conversation.title = "Chat with Test Agent"
        self.conversation.conversation_data = None

        self.run_doc = MagicMock()
        self.run_doc.name = "AR-TEST-0001"
        self.run_doc.agent = "Test Agent"
        self.run_doc.conversation = self.conversation.name
        self.run_doc.status = "Queued"
        self.run_doc.provider = "Test Provider"
        self.run_doc.model = "test-model"

        self.conv_manager = MagicMock()
        self.conv_manager.session_id = "session-123"
        self.conv_manager.get_or_create_conversation.return_value = self.conversation
        self.conv_manager.create_new_conversation.return_value = self.conversation
        self.conv_manager.get_conversation_history.return_value = []
        self.conv_manager.get_stored_summary.return_value = None

    def _get_doc_side_effect(self, agent_doc=None):
        agent_doc = agent_doc or self.agent_doc

        def _get_doc(first, *args, **kwargs):
            if first == "Agent":
                return agent_doc
            if first == "Agent Conversation":
                return self.conversation
            if first == "Agent Run":
                return self.run_doc
            if isinstance(first, dict) and first.get("doctype") == "Agent Run":
                return self.run_doc
            return MagicMock()

        return _get_doc

    def _published_statuses(self, mock_frappe):
        return [
            call.kwargs["message"]["status"]
            for call in mock_frappe.publish_realtime.call_args_list
        ]

    @patch("huf.ai.agent_integration._execute_agent_run")
    @patch("huf.ai.agent_integration.ConversationManager")
    @patch("huf.ai.agent_integration.frappe")
    def test_default_run_is_queued(self, mock_frappe, mock_cm_cls, mock_execute):
        mock_frappe.session.user = "test@example.com"
        mock_frappe.get_doc.side_effect = self._get_doc_side_effect()
        mock_frappe.db.get_value.return_value = None
        mock_cm_cls.return_value = self.conv_manager

        result = run_agent_sync(agent_name="Test Agent", prompt="hello")

        self.assertTrue(result["success"])
        self.assertTrue(result["queued"])
        self.assertEqual(result["status"], "Queued")
        self.assertEqual(result["agent_run_id"], "AR-TEST-0001")
        self.assertEqual(result["conversation_id"], "CONV-TEST-0001")

        # Only the run document is persisted up front. The user message is
        # deferred to the worker (added immediately before execution).
        self.run_doc.insert.assert_called_once_with(ignore_permissions=True)
        self.conv_manager.add_message.assert_not_called()

        # Execution is handed to the worker entry point, never run inline.
        mock_execute.assert_not_called()
        mock_frappe.enqueue.assert_called_once()
        enqueue_args, enqueue_kwargs = mock_frappe.enqueue.call_args
        self.assertEqual(enqueue_args[0], "huf.ai.agent_integration._run_queued_agent")
        self.assertEqual(enqueue_kwargs["run_id"], "AR-TEST-0001")
        self.assertEqual(enqueue_kwargs["conversation_id"], "CONV-TEST-0001")
        self.assertTrue(enqueue_kwargs["is_async"])
        self.assertTrue(enqueue_kwargs["enqueue_after_commit"])

        # A "queued" lifecycle event is emitted.
        self.assertIn("queued", self._published_statuses(mock_frappe))

    @patch("huf.ai.agent_integration._execute_agent_run")
    @patch("huf.ai.agent_integration.ConversationManager")
    @patch("huf.ai.agent_integration.frappe")
    def test_now_override_executes_synchronously(self, mock_frappe, mock_cm_cls, mock_execute):
        mock_frappe.session.user = "test@example.com"
        mock_frappe.get_doc.side_effect = self._get_doc_side_effect()
        mock_frappe.db.get_value.return_value = None
        mock_cm_cls.return_value = self.conv_manager
        sentinel = {"success": True, "response": "done"}
        mock_execute.return_value = sentinel

        # String value exercises the boolean-ish coercion of the public override.
        result = run_agent_sync(agent_name="Test Agent", prompt="hello", now="true")

        self.assertIs(result, sentinel)
        mock_frappe.enqueue.assert_not_called()
        mock_execute.assert_called_once()
        self.assertEqual(mock_execute.call_args.kwargs["run_id"], "AR-TEST-0001")

        # Direct path keeps the immediate behavior: user message up front.
        self.conv_manager.add_message.assert_called_once()
        self.assertEqual(self.conv_manager.add_message.call_args.args[1], "user")

    @patch("huf.ai.agent_integration._execute_agent_run")
    @patch("huf.ai.agent_integration.ConversationManager")
    @patch("huf.ai.agent_integration.frappe")
    def test_run_immediately_agent_executes_synchronously(self, mock_frappe, mock_cm_cls, mock_execute):
        mock_frappe.session.user = "test@example.com"
        agent_doc = _make_agent_doc(run_immediately=1)
        mock_frappe.get_doc.side_effect = self._get_doc_side_effect(agent_doc)
        mock_frappe.db.get_value.return_value = None
        mock_cm_cls.return_value = self.conv_manager
        sentinel = {"success": True, "response": "done"}
        mock_execute.return_value = sentinel

        result = run_agent_sync(agent_name="Test Agent", prompt="hello")

        self.assertIs(result, sentinel)
        mock_frappe.enqueue.assert_not_called()
        mock_execute.assert_called_once()
        self.conv_manager.add_message.assert_called_once()
        self.assertEqual(self.conv_manager.add_message.call_args.args[1], "user")

    @patch("huf.ai.agent_integration._execute_agent_run")
    @patch("huf.ai.agent_integration.ConversationManager")
    @patch("huf.ai.agent_integration.frappe")
    def test_queued_worker_adds_one_user_message_before_executing(self, mock_frappe, mock_cm_cls, mock_execute):
        mock_frappe.session.user = "worker@example.com"
        mock_frappe.get_doc.side_effect = self._get_doc_side_effect()
        mock_frappe.cache.return_value.set.return_value = True  # lock acquired
        mock_frappe.db.exists.return_value = False  # no user message yet
        mock_cm_cls.return_value = self.conv_manager
        mock_execute.return_value = {"success": True}

        result = _run_queued_agent(
            agent_name="Test Agent",
            run_id="AR-TEST-0001",
            conversation_id="CONV-TEST-0001",
            prompt="hello",
            provider="Test Provider",
            model="test-model",
            channel_id="api",
        )

        self.assertEqual(result, {"success": True})

        # Lock uses the nx/ex cache convention, scoped to the conversation.
        mock_frappe.cache.return_value.set.assert_called_once_with(
            "agent_run_conv_CONV-TEST-0001", 1, ex=600, nx=True
        )

        # Exactly one user message is created, for this run, under the lock.
        self.conv_manager.add_message.assert_called_once()
        msg_args = self.conv_manager.add_message.call_args.args
        self.assertEqual(msg_args[1], "user")
        self.assertEqual(msg_args[2], "hello")
        self.assertEqual(msg_args[-1], "AR-TEST-0001")

        # The precreated run is executed, never re-created.
        mock_execute.assert_called_once()
        self.assertEqual(mock_execute.call_args.kwargs["run_id"], "AR-TEST-0001")
        self.run_doc.insert.assert_not_called()

        # Lock is always released.
        mock_frappe.cache.return_value.delete.assert_called_once_with(
            "agent_run_conv_CONV-TEST-0001"
        )

    @patch("huf.ai.agent_integration.time.sleep")
    @patch("huf.ai.agent_integration._execute_agent_run")
    @patch("huf.ai.agent_integration.ConversationManager")
    @patch("huf.ai.agent_integration.frappe")
    def test_queued_worker_reenqueues_when_lock_busy(self, mock_frappe, mock_cm_cls, mock_execute, mock_sleep):
        mock_frappe.session.user = "worker@example.com"
        mock_frappe.get_doc.side_effect = self._get_doc_side_effect()
        mock_frappe.cache.return_value.set.return_value = False  # lock busy
        mock_cm_cls.return_value = self.conv_manager

        result = _run_queued_agent(
            agent_name="Test Agent",
            run_id="AR-TEST-0001",
            conversation_id="CONV-TEST-0001",
            prompt="hello",
            channel_id="api",
        )

        # Work is not lost: the job re-enqueues itself with a bumped attempt.
        self.assertIsNone(result)
        mock_frappe.enqueue.assert_called_once()
        enqueue_args, enqueue_kwargs = mock_frappe.enqueue.call_args
        self.assertEqual(enqueue_args[0], "huf.ai.agent_integration._run_queued_agent")
        self.assertEqual(enqueue_kwargs["lock_attempt"], 1)
        self.assertEqual(enqueue_kwargs["run_id"], "AR-TEST-0001")
        mock_sleep.assert_called_once()

        # Nothing executed, nothing persisted, no lock to release.
        mock_execute.assert_not_called()
        self.conv_manager.add_message.assert_not_called()
        mock_frappe.cache.return_value.delete.assert_not_called()

    @patch("huf.ai.agent_integration._execute_agent_run")
    @patch("huf.ai.agent_integration.ConversationManager")
    @patch("huf.ai.agent_integration.frappe")
    def test_queued_worker_never_duplicates_user_message(self, mock_frappe, mock_cm_cls, mock_execute):
        mock_frappe.session.user = "worker@example.com"
        mock_frappe.get_doc.side_effect = self._get_doc_side_effect()
        mock_frappe.cache.return_value.set.return_value = True
        mock_frappe.db.exists.return_value = True  # user message already exists
        mock_cm_cls.return_value = self.conv_manager
        mock_execute.return_value = {"success": True}

        _run_queued_agent(
            agent_name="Test Agent",
            run_id="AR-TEST-0001",
            conversation_id="CONV-TEST-0001",
            prompt="hello",
            channel_id="api",
        )

        self.conv_manager.add_message.assert_not_called()
        mock_execute.assert_called_once()

    @patch("huf.ai.agent_integration._execute_agent_run")
    @patch("huf.ai.agent_integration.ConversationManager")
    @patch("huf.ai.agent_integration.frappe")
    def test_queued_worker_skips_run_that_left_queued_state(self, mock_frappe, mock_cm_cls, mock_execute):
        mock_frappe.session.user = "worker@example.com"
        self.run_doc.status = "Success"  # picked up/cancelled elsewhere
        mock_frappe.get_doc.side_effect = self._get_doc_side_effect()
        mock_frappe.cache.return_value.set.return_value = True
        mock_cm_cls.return_value = self.conv_manager

        result = _run_queued_agent(
            agent_name="Test Agent",
            run_id="AR-TEST-0001",
            conversation_id="CONV-TEST-0001",
            prompt="hello",
            channel_id="api",
        )

        self.assertIsNone(result)
        mock_execute.assert_not_called()
        self.conv_manager.add_message.assert_not_called()
        mock_frappe.cache.return_value.delete.assert_called_once()

    @patch("huf.ai.agent_integration._execute_agent_run")
    @patch("huf.ai.agent_integration.ConversationManager")
    @patch("huf.ai.agent_integration.frappe")
    def test_queued_worker_skips_user_message_for_silent_trigger(self, mock_frappe, mock_cm_cls, mock_execute):
        mock_frappe.session.user = "worker@example.com"
        mock_frappe.get_doc.side_effect = self._get_doc_side_effect()
        mock_frappe.cache.return_value.set.return_value = True
        mock_cm_cls.return_value = self.conv_manager
        mock_execute.return_value = {"success": True}

        _run_queued_agent(
            agent_name="Test Agent",
            run_id="AR-TEST-0001",
            conversation_id="CONV-TEST-0001",
            prompt="[SILENT_TRIGGER] background task done",
            channel_id="api",
        )

        self.conv_manager.add_message.assert_not_called()
        mock_execute.assert_called_once()

    @patch("huf.ai.knowledge.context_builder.build_knowledge_context", return_value=None)
    @patch("huf.ai.agent_integration._run_async_safely")
    @patch("huf.ai.agent_integration.RunProvider")
    @patch("huf.ai.agent_integration.AgentManager")
    @patch("huf.ai.agent_integration.ConversationManager")
    @patch("huf.ai.agent_integration.frappe")
    def test_execute_run_reuses_precreated_run(
        self,
        mock_frappe,
        mock_cm_cls,
        mock_manager_cls,
        mock_run_provider,
        mock_run_async,
        _mock_knowledge,
    ):
        mock_frappe.session.user = "worker@example.com"
        mock_frappe.get_doc.side_effect = self._get_doc_side_effect()
        mock_frappe.db.get_value.return_value = None
        mock_frappe.db.count.return_value = 1
        mock_cm_cls.return_value = self.conv_manager

        result_obj = MagicMock()
        result_obj.new_items = []
        result_obj.final_output = "mocked response"
        result_obj.usage = None
        result_obj.cost = 0
        mock_run_async.return_value = result_obj

        result = _execute_agent_run(
            agent_name="Test Agent",
            run_id="AR-TEST-0001",
            conversation_id="CONV-TEST-0001",
            prompt="hello",
            provider="Test Provider",
            model="test-model",
            channel_id="api",
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["response"], "mocked response")
        self.assertEqual(result["agent_run_id"], "AR-TEST-0001")
        self.assertEqual(result["conversation_id"], "CONV-TEST-0001")

        # The precreated run is loaded, never re-inserted (no duplicates).
        mock_frappe.get_doc.assert_any_call("Agent Run", "AR-TEST-0001")
        self.run_doc.insert.assert_not_called()

        # Only the final agent response is persisted — no duplicate user message.
        self.conv_manager.add_message.assert_called_once()
        self.assertEqual(self.conv_manager.add_message.call_args.args[1], "agent")

        # The provider is actually invoked.
        mock_run_provider.run.assert_called_once()

        # started + success lifecycle events are emitted.
        statuses = self._published_statuses(mock_frappe)
        self.assertIn("started", statuses)
        self.assertIn("success", statuses)

    # ------------------------------------------------------------------
    # Caller compatibility (QFR-06)
    # ------------------------------------------------------------------

    @patch("huf.ai.orchestration.planning.run_agent_sync")
    def test_planning_caller_passes_now_true(self, mock_run):
        """A representative synchronous consumer must force direct execution."""
        mock_run.return_value = {"success": True, "response": "1. do the thing"}

        result = run_planning(
            agent_name="Planner",
            user_prompt="plan something",
            provider="Test Provider",
            model="test-model",
        )

        self.assertEqual(result, "1. do the thing")
        mock_run.assert_called_once()
        self.assertTrue(mock_run.call_args.kwargs.get("now"))

    @patch("huf.ai.agent_chat.frappe")
    @patch("huf.ai.agent_chat.ConversationManager")
    @patch("huf.ai.agent_chat.run_agent_sync")
    def test_new_conversation_returns_queued_ack(self, mock_run, mock_cm_cls, mock_frappe):
        """Web-facing chat endpoints queue by default and surface the queued ack."""
        conversation = MagicMock()
        conversation.name = "CONV-CHAT-001"
        cm = MagicMock()
        cm.create_new_conversation.return_value = conversation
        mock_cm_cls.return_value = cm

        mock_frappe.db.get_value.side_effect = lambda dt, name, field, **kw: {
            "provider": "Test Provider",
            "model": "test-model",
        }.get(field)
        mock_run.return_value = {
            "success": True,
            "queued": True,
            "status": "Queued",
            "agent_run_id": "AR-CHAT-001",
            "conversation_id": "CONV-CHAT-001",
        }

        result = agent_chat.new_conversation(agent="Test Agent", message="hello")

        self.assertTrue(result["success"])
        self.assertEqual(result["conversation_id"], "CONV-CHAT-001")
        self.assertTrue(result["run"]["queued"])
        self.assertEqual(result["run"]["status"], "Queued")
        mock_run.assert_called_once()
        self.assertNotIn("now", mock_run.call_args.kwargs)

    @patch("huf.ai.agent_chat.frappe")
    @patch("huf.ai.agent_chat.run_agent_sync")
    def test_send_message_to_conversation_returns_queued_ack(self, mock_run, mock_frappe):
        """Continuing a conversation also queues by default."""
        conv_doc = MagicMock()
        conv_doc.is_active = True
        conv_doc.agent = "Test Agent"
        conv_doc.channel = "Chat"
        conv_doc.name = "CONV-CHAT-001"
        mock_frappe.get_doc.return_value = conv_doc
        mock_frappe.db.get_value.side_effect = lambda dt, name, field, **kw: {
            "provider": "Test Provider",
            "model": "test-model",
        }.get(field)
        mock_run.return_value = {
            "success": True,
            "queued": True,
            "status": "Queued",
            "agent_run_id": "AR-CHAT-002",
            "conversation_id": "CONV-CHAT-001",
        }

        result = agent_chat.send_message_to_conversation(
            conversation="CONV-CHAT-001", message="hello again"
        )

        self.assertTrue(result["queued"])
        self.assertEqual(result["agent_run_id"], "AR-CHAT-002")
        mock_run.assert_called_once()
        self.assertNotIn("now", mock_run.call_args.kwargs)

    @patch("huf.ai.flow_engine.frappe")
    @patch("huf.ai.flow_engine.run_agent_sync")
    def test_flow_engine_agent_node_forces_now_true(self, mock_run, mock_frappe):
        """Flow engine agent nodes must keep direct execution inside the flow worker."""
        flow_run = MagicMock()
        flow_run.name = "FR-001"
        flow_run.conversation = "CONV-FLOW-001"
        flow_run.context_json = None
        flow_run.mode = None

        mock_run.return_value = {
            "success": True,
            "agent_run_id": "AR-FLOW-001",
            "response": "flow response",
        }

        result = _exec_agent_run(
            flow_run,
            node={"id": "node-1"},
            config={"agent_name": "Flow Agent", "input": {"prompt_template": "hello"}},
            settings={},
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["agent_run_id"], "AR-FLOW-001")
        mock_run.assert_called_once()
        self.assertTrue(mock_run.call_args.kwargs.get("now"))

    @patch("huf.ai.agent_scheduler.resolve_prompt")
    @patch("huf.ai.agent_scheduler.frappe")
    @patch("huf.ai.agent_scheduler.run_agent_sync")
    def test_scheduler_submits_queued_run(self, mock_run, mock_frappe, mock_resolve_prompt):
        """Scheduled triggers are background workers; they hand runs to the queue."""
        mock_frappe.session.user = "Administrator"
        mock_frappe.has_permission.return_value = True
        mock_frappe.db.exists.return_value = True

        trigger = {
            "name": "SCH-001",
            "agent": "Scheduled Agent",
            "scheduled_interval": "Hourly",
            "interval_count": 1,
            "next_execution": "2026-01-01 00:00:00",
            "last_execution": None,
        }

        agent_doc = _make_agent_doc()
        agent_doc.name = "Scheduled Agent"

        mock_frappe.get_all.return_value = [trigger]
        mock_frappe.get_doc.side_effect = lambda doctype, name: (
            agent_doc if doctype == "Agent" and name == "Scheduled Agent" else MagicMock()
        )
        mock_resolve_prompt.return_value = "scheduled prompt"
        mock_run.return_value = {
            "success": True,
            "queued": True,
            "status": "Queued",
            "agent_run_id": "AR-SCH-001",
        }

        agent_scheduler.run_scheduled_agents()

        mock_run.assert_called_once()
        self.assertNotIn("now", mock_run.call_args.kwargs)
        self.assertEqual(mock_run.call_args.args, ("Scheduled Agent", "scheduled prompt", "Test Provider", "test-model"))


if __name__ == "__main__":
    unittest.main()
