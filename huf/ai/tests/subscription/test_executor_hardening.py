# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (no bench / no live Frappe site) unit tests covering the adversarial-
review hardening fixes to `huf/ai/subscription/executor.py`
(Track-Item: fix-executor-critical-c2-c3-h8):

- C2: a successful turn persists the Agent Message with role="agent" (the
  DocType's actual valid Select value), not the nonexistent "assistant".
- C3: a parked run publishes a `subscription_auth_required` realtime event
  carrying `runtime_name` and the challenge's public info.
- H8 (defensive minimum): the dead `is_stateless` branch stores its cleanup
  status inside the real `usage_snapshot` JSON field rather than a
  nonexistent `subscription_cleanup_status` column.
- Medium: any exception raised anywhere in the turn (including before the
  existing `except SubscriptionError` handling) still resolves the run to
  Failed/parked rather than leaving it stuck in Started.
- Medium: tenancy is checked against the Agent Run's owner, not the
  current session user, so a resumed run is checked against its initiator.
- Medium: `runtime_mode="subscription_passthrough"` is set on the
  conversation once a new provider session is created.

Relies on the repo-root ``conftest.py`` to stub ``frappe``/``litellm``/
``agents`` before anything under the ``huf`` package is imported, exactly as
``test_executor_passthrough.py`` (sibling file) already does.
"""

from __future__ import annotations

import types
import unittest
from unittest import mock

import frappe

from huf.ai.subscription import executor as executor_module
from huf.ai.subscription import session_binding
from huf.ai.subscription.executor import (
	SubscriptionPassthroughExecutor,
	SubscriptionPassthroughRefusal,
)
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
		owner_user=None,
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
	defaults = dict(name="RUN-1", owner="alice@example.com")
	defaults.update(overrides)
	return types.SimpleNamespace(**defaults)


class TestSuccessfulTurnUsesAgentRole(unittest.TestCase):
	"""C2: Agent Message.role only allows user/tool/agent/system — never
	"assistant". A successful turn must persist with role="agent" and must
	not raise (which a wrong role value would, via ValidationError on save)."""

	def test_success_persists_with_role_agent(self):
		runtime = _fake_runtime()
		adapter = mock.MagicMock()

		async def fake_run_turn(_runtime, _request):
			return SubscriptionTurnResult(
				status="success", final_text="hello back", provider_session_id="sess-1"
			)

		adapter.run_turn = fake_run_turn
		conv_manager = mock.MagicMock()

		with mock.patch.object(frappe, "get_doc", return_value=runtime), \
			mock.patch.object(frappe, "session", types.SimpleNamespace(user="alice@example.com")), \
			mock.patch.object(executor_module, "_build_adapter", return_value=adapter), \
			mock.patch.object(frappe, "db", mock.MagicMock()), \
			mock.patch.object(frappe, "publish_realtime", mock.MagicMock()), \
			mock.patch("huf.ai.conversation_manager.ConversationManager", return_value=conv_manager):

			result = SubscriptionPassthroughExecutor.execute(
				agent_doc=_fake_agent_doc(),
				run_doc=_fake_run_doc(),
				conversation=_fake_conversation(),
				provider_doc=_fake_provider_doc(),
				prompt="hello",
			)

		self.assertTrue(result["success"])
		conv_manager.add_message.assert_called_once()
		_, kwargs = conv_manager.add_message.call_args
		self.assertEqual(kwargs["role"], "agent")
		self.assertNotEqual(kwargs["role"], "assistant")


class TestParkEmitsRealtimeEventWithRuntimeName(unittest.TestCase):
	"""C3: parking for auth must publish a realtime event so the frontend
	does not appear frozen, and that event must carry `runtime_name` (needed
	to call the auth-challenge APIs) plus the challenge's public info."""

	def test_park_for_auth_publishes_event_with_runtime_name_and_challenge_info(self):
		runtime = _fake_runtime(auth_status="required")
		conversation = _fake_conversation()

		challenge = {
			"name": "CHALLENGE-1",
			"verification_url": "https://example.com/verify",
			"user_code": "ABCD-1234",
			"mode": "device_code",
		}

		with mock.patch.object(frappe, "get_doc", return_value=runtime), \
			mock.patch.object(frappe, "session", types.SimpleNamespace(user="alice@example.com")), \
			mock.patch.object(executor_module, "_build_adapter") as mock_build_adapter, \
			mock.patch.object(executor_module.auth_service, "get_or_create_active_challenge",
				return_value=challenge), \
			mock.patch.object(executor_module.auth_service, "park_run"), \
			mock.patch.object(frappe, "db", mock.MagicMock()), \
			mock.patch.object(frappe, "publish_realtime", mock.MagicMock()) as mock_publish:

			result = SubscriptionPassthroughExecutor.execute(
				agent_doc=_fake_agent_doc(),
				run_doc=_fake_run_doc(),
				conversation=conversation,
				provider_doc=_fake_provider_doc(),
				prompt="hello",
			)

		mock_build_adapter.assert_not_called()
		self.assertEqual(result["status"], "Waiting Authentication")

		mock_publish.assert_called_once()
		_, kwargs = mock_publish.call_args
		self.assertEqual(kwargs["event"], "conversation:CONV-1")
		message = kwargs["message"]
		self.assertEqual(message["type"], "subscription_auth_required")
		self.assertEqual(message["agent_run_id"], "RUN-1")
		self.assertEqual(message["conversation_id"], "CONV-1")
		self.assertEqual(message["runtime_name"], "RUNTIME-1")
		self.assertEqual(message["verification_url"], "https://example.com/verify")
		self.assertEqual(message["user_code"], "ABCD-1234")
		self.assertEqual(message["mode"], "device_code")

	def test_park_for_auth_does_not_delete_conversation_lock_directly(self):
		"""The redundant/racy direct lock deletion in `_park_for_auth` was
		removed: callers already release the lock in their own `finally`
		blocks. `frappe.cache()` must not be touched by `_park_for_auth`."""
		runtime = _fake_runtime(auth_status="required")
		conversation = _fake_conversation()

		with mock.patch.object(frappe, "get_doc", return_value=runtime), \
			mock.patch.object(frappe, "session", types.SimpleNamespace(user="alice@example.com")), \
			mock.patch.object(executor_module.auth_service, "get_or_create_active_challenge",
				return_value={"name": "CHALLENGE-1"}), \
			mock.patch.object(executor_module.auth_service, "park_run"), \
			mock.patch.object(frappe, "db", mock.MagicMock()), \
			mock.patch.object(frappe, "publish_realtime", mock.MagicMock()), \
			mock.patch.object(frappe, "cache", mock.MagicMock()) as mock_cache:

			SubscriptionPassthroughExecutor.execute(
				agent_doc=_fake_agent_doc(),
				run_doc=_fake_run_doc(),
				conversation=conversation,
				provider_doc=_fake_provider_doc(),
				prompt="hello",
			)

		mock_cache.assert_not_called()


class TestUnhandledExceptionsNeverLeaveRunStuck(unittest.TestCase):
	"""Medium fix: no exception raised anywhere in the turn (including before
	the existing `except SubscriptionError` handling) may leave the run
	stuck in Started — it must resolve to Failed (sanitized) or a legitimate
	park."""

	def test_adapter_build_refusal_fails_run_cleanly(self):
		runtime = _fake_runtime(provider_family="UnknownFamily")

		with mock.patch.object(frappe, "get_doc", return_value=runtime), \
			mock.patch.object(frappe, "session", types.SimpleNamespace(user="alice@example.com")), \
			mock.patch.object(frappe, "db", mock.MagicMock()) as mock_db, \
			mock.patch.object(frappe, "publish_realtime", mock.MagicMock()):

			result = SubscriptionPassthroughExecutor.execute(
				agent_doc=_fake_agent_doc(),
				run_doc=_fake_run_doc(),
				conversation=_fake_conversation(),
				provider_doc=_fake_provider_doc(),
				prompt="hello",
			)

		self.assertFalse(result["success"])
		self.assertEqual(result["status"], "Failed")
		self.assertIn("Unsupported subscription runtime provider family", result["response"])
		mock_db.set_value.assert_called_once()
		call_kwargs = mock_db.set_value.call_args[0]
		self.assertEqual(call_kwargs[2]["status"], "Failed")

	def test_arbitrary_exception_before_subscription_error_handling_fails_run(self):
		"""Simulates a staging/vision-style error raised outside the existing
		`except SubscriptionError` block — must still fail cleanly, sanitized,
		rather than propagating out of `execute()`."""
		runtime = _fake_runtime()

		with mock.patch.object(frappe, "get_doc", return_value=runtime), \
			mock.patch.object(frappe, "session", types.SimpleNamespace(user="alice@example.com")), \
			mock.patch.object(executor_module, "_build_adapter", side_effect=RuntimeError("boom: secret_key=abc123")), \
			mock.patch.object(frappe, "db", mock.MagicMock()) as mock_db, \
			mock.patch.object(frappe, "publish_realtime", mock.MagicMock()):

			result = SubscriptionPassthroughExecutor.execute(
				agent_doc=_fake_agent_doc(),
				run_doc=_fake_run_doc(),
				conversation=_fake_conversation(),
				provider_doc=_fake_provider_doc(),
				prompt="hello",
			)

		self.assertFalse(result["success"])
		self.assertEqual(result["status"], "Failed")
		# Sanitized: must not leak the raw secret-looking text.
		self.assertNotIn("secret_key=abc123", result["response"])
		mock_db.set_value.assert_called_once()

	def test_subscription_passthrough_refusal_uses_exact_reason(self):
		runtime = _fake_runtime()

		with mock.patch.object(frappe, "get_doc", return_value=runtime), \
			mock.patch.object(frappe, "session", types.SimpleNamespace(user="alice@example.com")), \
			mock.patch.object(
				executor_module, "_build_adapter",
				side_effect=SubscriptionPassthroughRefusal("Unsupported transport"),
			), \
			mock.patch.object(frappe, "db", mock.MagicMock()), \
			mock.patch.object(frappe, "publish_realtime", mock.MagicMock()):

			result = SubscriptionPassthroughExecutor.execute(
				agent_doc=_fake_agent_doc(),
				run_doc=_fake_run_doc(),
				conversation=_fake_conversation(),
				provider_doc=_fake_provider_doc(),
				prompt="hello",
			)

		self.assertFalse(result["success"])
		self.assertEqual(result["status"], "Failed")
		self.assertEqual(result["response"], "Unsupported transport")


class TestTenancyCheckedAgainstRunOwner(unittest.TestCase):
	"""Medium fix: tenancy must be checked against the Agent Run's own owner,
	not `frappe.session.user` — important for a resumed run re-dispatched by
	a different user's session (recovery sweep, resume_after_auth_success)."""

	def test_uses_run_doc_owner_not_session_user(self):
		runtime = _fake_runtime()
		run_doc = _fake_run_doc(owner="original_owner@example.com")

		with mock.patch.object(frappe, "get_doc", return_value=runtime), \
			mock.patch.object(frappe, "session", types.SimpleNamespace(user="different_resumer@example.com")), \
			mock.patch.object(executor_module, "_build_adapter") as mock_build_adapter, \
			mock.patch.object(frappe, "db", mock.MagicMock()), \
			mock.patch.object(frappe, "publish_realtime", mock.MagicMock()):

			runtime.check_tenancy.return_value = False
			SubscriptionPassthroughExecutor.execute(
				agent_doc=_fake_agent_doc(),
				run_doc=run_doc,
				conversation=_fake_conversation(),
				provider_doc=_fake_provider_doc(),
				prompt="hello",
			)

		runtime.check_tenancy.assert_called_once_with("original_owner@example.com")
		mock_build_adapter.assert_not_called()

	def test_falls_back_to_session_user_when_run_doc_has_no_owner(self):
		runtime = _fake_runtime()
		run_doc = types.SimpleNamespace(name="RUN-1")  # no `owner` attribute at all

		with mock.patch.object(frappe, "get_doc", return_value=runtime), \
			mock.patch.object(frappe, "session", types.SimpleNamespace(user="fallback@example.com")), \
			mock.patch.object(executor_module, "_build_adapter") as mock_build_adapter, \
			mock.patch.object(frappe, "db", mock.MagicMock()), \
			mock.patch.object(frappe, "publish_realtime", mock.MagicMock()):

			runtime.check_tenancy.return_value = False
			SubscriptionPassthroughExecutor.execute(
				agent_doc=_fake_agent_doc(),
				run_doc=run_doc,
				conversation=_fake_conversation(),
				provider_doc=_fake_provider_doc(),
				prompt="hello",
			)

		runtime.check_tenancy.assert_called_once_with("fallback@example.com")
		mock_build_adapter.assert_not_called()


class TestRuntimeModeSetOnNewSession(unittest.TestCase):
	"""Medium fix: `runtime_mode="subscription_passthrough"` must actually be
	written onto the conversation once a new provider session is created, so
	`is_subscription_passthrough_conversation` can later return True."""

	def test_binding_for_new_session_includes_runtime_mode(self):
		updates = session_binding.binding_for_new_session("sess-123", "RUNTIME-1")
		self.assertEqual(updates["runtime_mode"], "subscription_passthrough")

	def test_new_session_success_writes_runtime_mode_onto_conversation(self):
		runtime = _fake_runtime()
		adapter = mock.MagicMock()

		async def fake_run_turn(_runtime, _request):
			return SubscriptionTurnResult(
				status="success", final_text="hi", provider_session_id="sess-new"
			)

		adapter.run_turn = fake_run_turn
		conversation = _fake_conversation()  # Uninitialized -> ACTION_CREATE_NEW

		with mock.patch.object(frappe, "get_doc", return_value=runtime), \
			mock.patch.object(frappe, "session", types.SimpleNamespace(user="alice@example.com")), \
			mock.patch.object(executor_module, "_build_adapter", return_value=adapter), \
			mock.patch.object(frappe, "db", mock.MagicMock()) as mock_db, \
			mock.patch.object(frappe, "publish_realtime", mock.MagicMock()), \
			mock.patch("huf.ai.conversation_manager.ConversationManager"):

			SubscriptionPassthroughExecutor.execute(
				agent_doc=_fake_agent_doc(),
				run_doc=_fake_run_doc(),
				conversation=conversation,
				provider_doc=_fake_provider_doc(),
				prompt="hello",
			)

		# First set_value call binds the conversation; assert runtime_mode is there.
		conv_call = next(
			c for c in mock_db.set_value.call_args_list if c.args[0] == "Agent Conversation"
		)
		binding_updates = conv_call.args[2]
		self.assertEqual(binding_updates["runtime_mode"], "subscription_passthrough")


class TestStatelessCleanupStatusUsesRealField(unittest.TestCase):
	"""H8 (defensive minimum): `subscription_cleanup_status` is not a real
	Agent Run column; the stateless cleanup path must not write to it
	directly (which would raise), storing it inside `usage_snapshot` instead.

	`is_stateless` is only reachable with `conversation=None` today; this
	test exercises that path directly to lock in the safe field choice."""

	def test_cleanup_status_stored_inside_usage_snapshot(self):
		runtime = _fake_runtime()
		adapter = mock.MagicMock()

		async def fake_run_turn(_runtime, _request):
			return SubscriptionTurnResult(
				status="success", final_text="hi", provider_session_id="sess-xyz"
			)

		adapter.run_turn = fake_run_turn
		adapter.delete_session = mock.AsyncMock(
			return_value=types.SimpleNamespace(cleanup_status="deleted")
		)

		with mock.patch.object(frappe, "get_doc", return_value=runtime), \
			mock.patch.object(frappe, "session", types.SimpleNamespace(user="alice@example.com")), \
			mock.patch.object(executor_module, "_build_adapter", return_value=adapter), \
			mock.patch.object(frappe, "db", mock.MagicMock()) as mock_db, \
			mock.patch.object(frappe, "publish_realtime", mock.MagicMock()):

			result = SubscriptionPassthroughExecutor.execute(
				agent_doc=_fake_agent_doc(),
				run_doc=_fake_run_doc(),
				conversation=None,  # stateless
				provider_doc=_fake_provider_doc(),
				prompt="hello",
			)

		self.assertTrue(result["success"])
		run_call = next(
			c for c in mock_db.set_value.call_args_list if c.args[0] == "Agent Run"
		)
		run_fields = run_call.args[2]
		self.assertNotIn("subscription_cleanup_status", run_fields)
		self.assertEqual(
			run_fields["usage_snapshot"]["subscription_cleanup_status"], "deleted"
		)


if __name__ == "__main__":
	unittest.main()
