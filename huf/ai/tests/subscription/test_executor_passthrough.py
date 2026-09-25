# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (no bench / no live Frappe site) unit tests for the Subscription CLI
passthrough execution branch (Track-Item: T-06-C):

- huf/ai/subscription/executor.py (SubscriptionPassthroughExecutor)
- the dispatch branches added to huf/ai/agent_integration.py
  (_execute_agent_run, run_agent_stream, generate_conversation_title,
  run_background_summarization)
- the fail-closed guard added to huf/ai/run.py (RunProvider._assert_not_subscription_cli)

Relies on the repo-root ``conftest.py`` (sibling of this worktree's
``pyproject.toml``) to stub ``frappe``/``litellm``/``agents`` before anything
under the ``huf`` package is imported, exactly as
``huf/ai/tests/subscription/test_runtime_doctype_tenancy.py`` already does
for a narrower case. See that root conftest's docstring for why the stubbing
cannot live in ``huf/ai/tests/conftest.py`` alone.
"""

from __future__ import annotations

import types
import unittest
from unittest import mock

import frappe

import huf.ai.agent_integration as agent_integration
import huf.ai.run as run_module
from huf.ai.subscription import executor as executor_module
from huf.ai.subscription.executor import SubscriptionPassthroughExecutor
from huf.ai.subscription.types import SubscriptionTurnResult


def _fake_runtime(**overrides):
	defaults = dict(
		name="RUNTIME-1",
		provider_family="Claude",
		transport_type="Local",
		executable="claude",
		working_directory=None,
		docker_container=None,
		ssh_connection=None,
		timeout_seconds=None,
		auth_status="ready",
	)
	defaults.update(overrides)
	runtime = types.SimpleNamespace(**defaults)
	runtime.check_tenancy = mock.MagicMock(return_value=True)
	return runtime


def _fake_provider_doc(**overrides):
	defaults = dict(name="PROVIDER-1", subscription_runtime="RUNTIME-1")
	defaults.update(overrides)
	return types.SimpleNamespace(**defaults)


def _fake_agent_doc(**overrides):
	defaults = dict(name="AGENT-1", model="MODEL-1")
	defaults.update(overrides)
	return types.SimpleNamespace(**defaults)


def _fake_conversation(**overrides):
	defaults = dict(
		name="CONV-1",
		subscription_provider_session_id=None,
		subscription_provider_session_status="Uninitialized",
		subscription_runtime=None,
	)
	defaults.update(overrides)
	return types.SimpleNamespace(**defaults)


def _fake_run_doc(**overrides):
	defaults = dict(name="RUN-1")
	defaults.update(overrides)
	return types.SimpleNamespace(**defaults)


class TestTenancyBeforeAnyCLIInvocation(unittest.TestCase):
	"""Step 2 of the design: tenancy is checked BEFORE any login/inference attempt."""

	def test_tenancy_refusal_happens_before_adapter_is_built(self):
		runtime = _fake_runtime()
		runtime.check_tenancy.return_value = False

		with mock.patch.object(frappe, "get_doc", return_value=runtime), \
			mock.patch.object(frappe, "session", types.SimpleNamespace(user="bob@example.com")), \
			mock.patch.object(executor_module, "_build_adapter") as mock_build_adapter, \
			mock.patch.object(frappe, "db", mock.MagicMock()):

			result = SubscriptionPassthroughExecutor.execute(
				agent_doc=_fake_agent_doc(),
				run_doc=_fake_run_doc(),
				conversation=_fake_conversation(),
				provider_doc=_fake_provider_doc(),
				prompt="hello",
			)

		runtime.check_tenancy.assert_called_once_with("bob@example.com")
		mock_build_adapter.assert_not_called()
		self.assertFalse(result["success"])
		self.assertEqual(result["status"], "Failed")
		self.assertIn("not authorized", result["response"])


class TestAuthRequiredParksNotFails(unittest.TestCase):
	"""Step 3/8: an auth-required condition must park the run, never fail it,
	and must never invoke the CLI when the runtime is already known not-ready."""

	def test_not_ready_runtime_never_builds_adapter_and_parks(self):
		runtime = _fake_runtime(auth_status="required")

		with mock.patch.object(frappe, "get_doc", return_value=runtime), \
			mock.patch.object(frappe, "session", types.SimpleNamespace(user="alice@example.com")), \
			mock.patch.object(executor_module, "_build_adapter") as mock_build_adapter, \
			mock.patch.object(executor_module.auth_service, "get_or_create_active_challenge",
				return_value={"name": "CHALLENGE-1"}) as mock_challenge, \
			mock.patch.object(executor_module.auth_service, "park_run") as mock_park, \
			mock.patch.object(frappe, "db", mock.MagicMock()), \
			mock.patch.object(frappe, "cache", mock.MagicMock()):

			result = SubscriptionPassthroughExecutor.execute(
				agent_doc=_fake_agent_doc(),
				run_doc=_fake_run_doc(),
				conversation=_fake_conversation(),
				provider_doc=_fake_provider_doc(),
				prompt="hello",
			)

		mock_build_adapter.assert_not_called()
		mock_challenge.assert_called_once()
		mock_park.assert_called_once_with("RUN-1", "CHALLENGE-1")
		self.assertFalse(result["success"])
		self.assertEqual(result["status"], "Waiting Authentication")

	def test_adapter_auth_required_result_parks_not_fails(self):
		runtime = _fake_runtime(auth_status="ready")
		adapter = mock.MagicMock()

		async def fake_run_turn(_runtime, _request):
			return SubscriptionTurnResult(
				status="auth_required",
				final_text=None,
				provider_session_id=None,
				auth_reason="Session expired",
			)

		adapter.run_turn = fake_run_turn

		with mock.patch.object(frappe, "get_doc", return_value=runtime), \
			mock.patch.object(frappe, "session", types.SimpleNamespace(user="alice@example.com")), \
			mock.patch.object(executor_module, "_build_adapter", return_value=adapter), \
			mock.patch.object(executor_module.auth_service, "get_or_create_active_challenge",
				return_value={"name": "CHALLENGE-2"}) as mock_challenge, \
			mock.patch.object(executor_module.auth_service, "park_run") as mock_park, \
			mock.patch.object(executor_module.auth_service, "mark_runtime_auth_state") as mock_mark, \
			mock.patch.object(frappe, "db", mock.MagicMock()), \
			mock.patch.object(frappe, "cache", mock.MagicMock()):

			result = SubscriptionPassthroughExecutor.execute(
				agent_doc=_fake_agent_doc(),
				run_doc=_fake_run_doc(),
				conversation=_fake_conversation(),
				provider_doc=_fake_provider_doc(),
				prompt="hello",
			)

		mock_mark.assert_called_once()
		mock_challenge.assert_called_once()
		mock_park.assert_called_once_with("RUN-1", "CHALLENGE-2")
		self.assertFalse(result["success"])
		self.assertEqual(result["status"], "Waiting Authentication")


class TestStatelessRunDoesNotPersistBinding(unittest.TestCase):
	def test_stateless_run_never_calls_session_binding_resolve(self):
		runtime = _fake_runtime()
		adapter = mock.MagicMock()

		async def fake_run_turn(_runtime, _request):
			return SubscriptionTurnResult(
				status="success", final_text="hi there", provider_session_id="sess-xyz"
			)

		adapter.run_turn = fake_run_turn
		adapter.delete_session = mock.AsyncMock(
			return_value=types.SimpleNamespace(cleanup_status="deleted")
		)

		with mock.patch.object(frappe, "get_doc", return_value=runtime), \
			mock.patch.object(frappe, "session", types.SimpleNamespace(user="alice@example.com")), \
			mock.patch.object(executor_module, "_build_adapter", return_value=adapter), \
			mock.patch.object(executor_module.session_binding, "resolve_binding_for_turn") as mock_resolve, \
			mock.patch.object(frappe, "db", mock.MagicMock()), \
			mock.patch.object(frappe, "publish_realtime", mock.MagicMock()):

			result = SubscriptionPassthroughExecutor.execute(
				agent_doc=_fake_agent_doc(),
				run_doc=_fake_run_doc(),
				conversation=None,  # stateless: no Agent Conversation
				provider_doc=_fake_provider_doc(),
				prompt="hello",
			)

		mock_resolve.assert_not_called()
		adapter.delete_session.assert_called_once()
		self.assertTrue(result["success"])
		self.assertEqual(result["status"], "Success")


class TestBindingMismatchRefusesCleanly(unittest.TestCase):
	def test_refuse_mismatch_fails_run_with_exact_reason(self):
		runtime = _fake_runtime()

		with mock.patch.object(frappe, "get_doc", return_value=runtime), \
			mock.patch.object(frappe, "session", types.SimpleNamespace(user="alice@example.com")), \
			mock.patch.object(executor_module, "_build_adapter") as mock_build_adapter, \
			mock.patch.object(frappe, "db", mock.MagicMock()), \
			mock.patch.object(frappe, "publish_realtime", mock.MagicMock()):

			conversation = _fake_conversation(
				subscription_provider_session_status="Active",
				subscription_runtime="OTHER-RUNTIME",
			)
			result = SubscriptionPassthroughExecutor.execute(
				agent_doc=_fake_agent_doc(),
				run_doc=_fake_run_doc(),
				conversation=conversation,
				provider_doc=_fake_provider_doc(),
				prompt="hello",
			)

		mock_build_adapter.assert_not_called()
		self.assertFalse(result["success"])
		self.assertEqual(result["status"], "Failed")
		self.assertIn("different subscription", result["response"])


class TestFailClosedGuardInRunProvider(unittest.TestCase):
	"""Step 11: RunProvider must refuse a Subscription CLI provider outright."""

	def test_assert_not_subscription_cli_raises_for_subscription_provider(self):
		with mock.patch.object(executor_module, "is_subscription_cli_provider", return_value=True):
			with self.assertRaises(RuntimeError):
				run_module.RunProvider._assert_not_subscription_cli("SUBSCRIPTION-PROVIDER")

	def test_assert_not_subscription_cli_noop_for_normal_provider(self):
		with mock.patch.object(executor_module, "is_subscription_cli_provider", return_value=False):
			run_module.RunProvider._assert_not_subscription_cli("OPENAI-PROVIDER")  # must not raise


class TestGenerateConversationTitleSkipsLiteLLM(unittest.TestCase):
	def test_passthrough_conversation_uses_truncated_heuristic_not_litellm(self):
		history = [{"role": "user", "content": "x" * 100}]

		with mock.patch.object(frappe, "db", mock.MagicMock()) as mock_db, \
			mock.patch.object(executor_module, "is_subscription_passthrough_conversation", return_value=True), \
			mock.patch.object(agent_integration, "ConversationManager") as mock_conv_mgr_cls, \
			mock.patch.object(agent_integration, "_emit_conversation_title_updated") as mock_emit, \
			mock.patch("huf.ai.providers.litellm.get_simple_completion") as mock_completion:

			mock_db.get_value.return_value = "Chat with Agent-1"
			mock_conv_mgr_cls.return_value.get_conversation_history.return_value = history

			agent_integration.generate_conversation_title("CONV-1", "AGENT-1")

		mock_completion.assert_not_called()
		mock_emit.assert_called_once()
		title_arg = mock_db.set_value.call_args[0][3]
		self.assertLessEqual(len(title_arg), 61)  # 60 chars + ellipsis
		self.assertTrue(title_arg.startswith("x"))

	def test_non_passthrough_conversation_still_uses_litellm(self):
		history = [{"role": "user", "content": "hi"}]

		with mock.patch.object(frappe, "db", mock.MagicMock()) as mock_db, \
			mock.patch.object(executor_module, "is_subscription_passthrough_conversation", return_value=False), \
			mock.patch.object(agent_integration, "ConversationManager") as mock_conv_mgr_cls, \
			mock.patch.object(agent_integration, "frappe") as mock_frappe_in_module, \
			mock.patch.object(agent_integration, "_run_async_safely", return_value="A title") as mock_run_async, \
			mock.patch.object(agent_integration, "_emit_conversation_title_updated") as mock_emit:

			mock_db.get_value.return_value = "Chat with Agent-1"
			mock_conv_mgr_cls.return_value.get_conversation_history.return_value = history
			mock_frappe_in_module.get_doc.return_value = _fake_agent_doc(provider="P", model="M")
			mock_frappe_in_module.db = mock_db

			agent_integration.generate_conversation_title("CONV-1", "AGENT-1")

		mock_run_async.assert_called_once()
		mock_emit.assert_called_once()


class TestRunBackgroundSummarizationSkipped(unittest.TestCase):
	def test_passthrough_conversation_returns_immediately(self):
		with mock.patch.object(executor_module, "is_subscription_passthrough_conversation", return_value=True), \
			mock.patch.object(agent_integration, "ConversationManager") as mock_conv_mgr_cls:

			agent_integration.run_background_summarization("CONV-1", "AGENT-1")

		mock_conv_mgr_cls.assert_not_called()


class TestSyncPathNeverBuildsAgentManagerForPassthrough(unittest.TestCase):
	"""A passthrough run must never reach the normal history-fetch / AgentManager
	/ RunProvider code path in `_execute_agent_run`."""

	def test_execute_agent_run_dispatches_to_executor_and_skips_normal_path(self):
		provider_doc = _fake_provider_doc()
		agent_doc = _fake_agent_doc()
		conversation = _fake_conversation()
		run_doc = _fake_run_doc()

		docs_by_type = {
			("Agent", "AGENT-1"): agent_doc,
			("AI Provider", "PROVIDER-1"): provider_doc,
			("Agent Conversation", "CONV-1"): conversation,
			("Agent Run", "RUN-1"): run_doc,
		}

		def fake_get_doc(doctype, name):
			return docs_by_type[(doctype, name)]

		with mock.patch.object(agent_integration, "_resolve_effective_model",
				return_value=("PROVIDER-1", "MODEL-1", "model-name")), \
			mock.patch.object(executor_module, "is_subscription_cli_provider", return_value=True), \
			mock.patch.object(agent_integration.frappe, "get_doc", side_effect=fake_get_doc), \
			mock.patch.object(agent_integration.frappe, "db", mock.MagicMock()), \
			mock.patch.object(agent_integration, "RunBudget") as mock_budget_cls, \
			mock.patch.object(agent_integration, "set_current_budget"), \
			mock.patch.object(agent_integration, "safe_commit"), \
			mock.patch.object(agent_integration, "_emit_run_lifecycle_event"), \
			mock.patch.object(agent_integration, "AgentManager") as mock_agent_manager_cls, \
			mock.patch.object(agent_integration, "ConversationManager") as mock_conv_mgr_cls, \
			mock.patch.object(agent_integration.RunProvider, "run") as mock_run_provider, \
			mock.patch.object(
				executor_module.SubscriptionPassthroughExecutor, "execute",
				return_value={"success": True, "response": "ok", "agent_run_id": "RUN-1", "status": "Success"},
			) as mock_execute:

			mock_budget_cls.from_run_doc.return_value = mock.MagicMock()

			result = agent_integration._execute_agent_run(
				agent_name="AGENT-1",
				run_id="RUN-1",
				conversation_id="CONV-1",
				prompt="hello",
			)

		mock_execute.assert_called_once()
		mock_agent_manager_cls.assert_not_called()
		mock_run_provider.assert_not_called()
		mock_conv_mgr_cls.assert_not_called()
		self.assertTrue(result["success"])


class TestStreamingPathNeverBuildsAgentManagerForPassthrough(unittest.TestCase):
	"""`run_agent_stream` must intercept before its own history-fetch/AgentManager
	construction and never call AgentManager/RunProvider directly for a
	passthrough run; it queues + drains under the sync path's lock instead
	(see `_run_subscription_stream_interim`)."""

	def test_stream_defers_to_queued_drain_and_polls_for_terminal_status(self):
		import asyncio

		conversation = _fake_conversation()

		statuses = iter([("Started", None, None), ("Success", "final text", None)])

		def fake_get_value(doctype, name, fields):
			if doctype == "Agent Run" and fields == ["status", "response", "error_message"]:
				return next(statuses)
			return None

		with mock.patch.object(executor_module, "is_subscription_cli_provider", return_value=True), \
			mock.patch.object(agent_integration, "_resolve_effective_model",
				return_value=("PROVIDER-1", "MODEL-1", "model-name")), \
			mock.patch.object(agent_integration.frappe, "has_permission", return_value=True), \
			mock.patch.object(agent_integration.frappe, "get_doc", return_value=conversation), \
			mock.patch.object(agent_integration.frappe, "db", mock.MagicMock()) as mock_db, \
			mock.patch.object(agent_integration.frappe, "as_json", side_effect=lambda v: v), \
			mock.patch.object(agent_integration, "safe_commit"), \
			mock.patch.object(agent_integration, "_next_run_sequence", return_value=1), \
			mock.patch.object(agent_integration, "_enqueue_drain") as mock_enqueue_drain, \
			mock.patch.object(agent_integration, "_emit_run_lifecycle_event"), \
			mock.patch.object(agent_integration, "AgentManager") as mock_agent_manager_cls, \
			mock.patch.object(agent_integration.RunProvider, "run_stream") as mock_run_stream, \
			mock.patch("asyncio.sleep", new=mock.AsyncMock()):

			mock_db.get_value.side_effect = fake_get_value
			fake_run_doc = mock.MagicMock(name="RUN-STREAM-1")
			fake_run_doc.name = "RUN-STREAM-1"
			with mock.patch.object(agent_integration.frappe, "get_doc") as mock_get_doc:
				mock_get_doc.return_value = fake_run_doc

				async def collect():
					chunks = []
					async for chunk in agent_integration._run_subscription_stream_interim(
						agent_name="AGENT-1",
						agent_doc=_fake_agent_doc(),
						conversation=conversation,
						conv_manager=mock.MagicMock(session_id="sess-1"),
						prompt="hello",
						resolved_provider="PROVIDER-1",
						resolved_model="MODEL-1",
						resolved_prompt_template=None,
						prompt_template=None,
						prompt_version=None,
						parent_conversation_id=None,
						invoked_by_agent=None,
						prompt_cache_options=None,
						files=None,
						skip_user_message=False,
						channel_id="api",
						external_id=None,
						response_format=None,
						client_idempotency_key=None,
					):
						chunks.append(chunk)
					return chunks

				chunks = asyncio.run(collect())

		mock_agent_manager_cls.assert_not_called()
		mock_run_stream.assert_not_called()
		mock_enqueue_drain.assert_called_once()
		self.assertEqual(chunks[-1]["type"], "complete")
		self.assertEqual(chunks[-1]["response"], "final text")


if __name__ == "__main__":
	unittest.main()
