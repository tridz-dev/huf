# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (no bench / no live Frappe site) unit tests for T-06-D (resume-side
subscription CLI passthrough work):

- claim-ordering fix in `huf.ai.agent_integration._next_queued_run`
- `huf.ai.subscription.resume.resume_after_auth_success`
- the SESSION_LOST vs AUTH_REQUIRED distinction in
  `huf.ai.subscription.executor.SubscriptionPassthroughExecutor.execute`

Relies on the repo-root ``conftest.py`` to stub ``frappe``/``litellm``/``agents``
before anything under the ``huf`` package is imported, exactly as
``test_executor_passthrough.py`` already does.
"""

from __future__ import annotations

import types
import unittest
from unittest import mock

import frappe

import huf.ai.agent_integration as agent_integration
from huf.ai.subscription import executor as executor_module
from huf.ai.subscription import resume as resume_module
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
		subscription_provider_session_id="sess-existing",
		subscription_provider_session_status="Active",
		subscription_runtime="RUNTIME-1",
	)
	defaults.update(overrides)
	return types.SimpleNamespace(**defaults)


def _fake_run_doc(**overrides):
	defaults = dict(name="RUN-1")
	defaults.update(overrides)
	return types.SimpleNamespace(**defaults)


class TestClaimOrderingBlocksOnParkedRun(unittest.TestCase):
	"""`_next_queued_run` must not let a later Queued run jump a parked one."""

	def test_queued_at_n_plus_1_not_selected_while_waiting_authentication_at_n_exists(self):
		call_log = []

		def fake_get_value(doctype, filters=None, fieldname=None, order_by=None):
			call_log.append((doctype, filters, fieldname, order_by))
			if filters.get("status") == "Waiting Authentication":
				# Parked run sits at sequence 5.
				return 5
			if filters.get("status") == "Queued":
				# Only a Queued run at sequence 6 (N+1) exists; the blocking
				# filter (sequence < 5) must exclude it.
				seq_filter = filters.get("sequence")
				if seq_filter and seq_filter[0] == "<" and seq_filter[1] == 5:
					return None
				return "RUN-QUEUED-6"
			return None

		with mock.patch.object(frappe.db, "get_value", side_effect=fake_get_value):
			result = agent_integration._next_queued_run("CONV-1")

		self.assertIsNone(result)
		# Confirm the blocking-sequence lookup happened before the Queued lookup.
		self.assertEqual(call_log[0][1]["status"], "Waiting Authentication")
		queued_call = call_log[1]
		self.assertEqual(queued_call[1]["status"], "Queued")
		self.assertEqual(queued_call[1]["sequence"], ("<", 5))

	def test_queued_run_selected_once_parked_run_resolved(self):
		def fake_get_value(doctype, filters=None, fieldname=None, order_by=None):
			if filters.get("status") == "Waiting Authentication":
				return None  # resolved: no parked run left
			if filters.get("status") == "Queued":
				self.assertNotIn("sequence", filters)  # no blocking filter applied
				return "RUN-QUEUED-6"
			return None

		with mock.patch.object(frappe.db, "get_value", side_effect=fake_get_value):
			result = agent_integration._next_queued_run("CONV-1")

		self.assertEqual(result, "RUN-QUEUED-6")

	def test_queued_run_with_lower_sequence_than_parked_run_still_selected(self):
		"""A Queued run that was already queued BEFORE the parked run's sequence
		is not blocked -- only runs at/after the parked run's sequence are."""

		def fake_get_value(doctype, filters=None, fieldname=None, order_by=None):
			if filters.get("status") == "Waiting Authentication":
				return 5
			if filters.get("status") == "Queued":
				self.assertEqual(filters.get("sequence"), ("<", 5))
				return "RUN-QUEUED-3"
			return None

		with mock.patch.object(frappe.db, "get_value", side_effect=fake_get_value):
			result = agent_integration._next_queued_run("CONV-1")

		self.assertEqual(result, "RUN-QUEUED-3")


class TestResumeAfterAuthSuccess(unittest.TestCase):
	"""`resume_after_auth_success` re-queues parked runs without disturbing
	sequence/idempotency_key and without creating a new Agent Message."""

	def test_resumes_parked_runs_preserving_sequence_and_idempotency_key(self):
		set_value_calls = []

		def fake_set_value(doctype, name, values, **kwargs):
			set_value_calls.append((doctype, name, values))

		def fake_get_value(doctype, name, fieldname):
			if doctype == "Agent Run" and fieldname == "conversation":
				return {"RUN-A": "CONV-1", "RUN-B": "CONV-2"}[name]
			return None

		with mock.patch.object(
			resume_module.auth_service,
			"resolve_parked_runs_for_runtime",
			return_value=["RUN-A", "RUN-B"],
		) as mock_resolve, \
			mock.patch.object(frappe.db, "set_value", side_effect=fake_set_value), \
			mock.patch.object(frappe.db, "get_value", side_effect=fake_get_value), \
			mock.patch.object(frappe.db, "commit"), \
			mock.patch.object(agent_integration, "_enqueue_drain") as mock_enqueue_drain, \
			mock.patch.dict("sys.modules", {"huf.ai.agent_integration": agent_integration}):

			resumed = resume_module.resume_after_auth_success("RUNTIME-1")

		mock_resolve.assert_called_once_with("RUNTIME-1")
		self.assertEqual(resumed, ["RUN-A", "RUN-B"])

		# Only `status` is touched -- sequence/idempotency_key are never
		# referenced or overwritten by this function.
		for _doctype, _name, values in set_value_calls:
			self.assertEqual(values, {"status": "Queued"})

		# Drain woken for each distinct conversation the resumed runs belong to.
		drained = {call.args[0] for call in mock_enqueue_drain.call_args_list}
		self.assertEqual(drained, {"CONV-1", "CONV-2"})

	def test_no_parked_runs_is_a_noop(self):
		with mock.patch.object(
			resume_module.auth_service, "resolve_parked_runs_for_runtime", return_value=[]
		), \
			mock.patch.object(frappe.db, "set_value") as mock_set_value, \
			mock.patch.object(agent_integration, "_enqueue_drain") as mock_enqueue_drain:

			resumed = resume_module.resume_after_auth_success("RUNTIME-1")

		self.assertEqual(resumed, [])
		mock_set_value.assert_not_called()
		mock_enqueue_drain.assert_not_called()

	def test_never_creates_a_new_agent_message(self):
		"""Resuming re-executes the CLI call; it must not touch Agent Message."""
		with mock.patch.object(
			resume_module.auth_service,
			"resolve_parked_runs_for_runtime",
			return_value=["RUN-A"],
		), \
			mock.patch.object(frappe.db, "set_value") as mock_set_value, \
			mock.patch.object(frappe.db, "get_value", return_value="CONV-1"), \
			mock.patch.object(frappe.db, "commit"), \
			mock.patch.object(agent_integration, "_enqueue_drain"):

			resume_module.resume_after_auth_success("RUNTIME-1")

		for call in mock_set_value.call_args_list:
			self.assertNotEqual(call.args[0], "Agent Message")


class TestSessionLostVsAuthRequired(unittest.TestCase):
	"""Step 8/8b: a lost provider-native session must be distinguished from a
	real auth failure -- different Agent Conversation status, different
	Agent Run failure path, and no park/auth-challenge for the session-lost
	case."""

	def _run_with_turn_result(self, turn_result, conversation=None):
		runtime = _fake_runtime(auth_status="ready")
		adapter = mock.MagicMock()

		async def fake_run_turn(_runtime, _request):
			return turn_result

		adapter.run_turn = fake_run_turn
		conversation = conversation or _fake_conversation()

		with mock.patch.object(frappe, "get_doc", return_value=runtime), \
			mock.patch.object(frappe, "session", types.SimpleNamespace(user="alice@example.com")), \
			mock.patch.object(executor_module, "_build_adapter", return_value=adapter), \
			mock.patch.object(
				executor_module.session_binding,
				"resolve_binding_for_turn",
				return_value=types.SimpleNamespace(
					action=executor_module.session_binding.ACTION_RESUME_EXISTING,
					provider_session_id="sess-existing",
					reason=None,
				),
			), \
			mock.patch.object(executor_module.auth_service, "get_or_create_active_challenge") as mock_challenge, \
			mock.patch.object(executor_module.auth_service, "park_run") as mock_park, \
			mock.patch.object(executor_module.auth_service, "mark_runtime_auth_state") as mock_mark, \
			mock.patch.object(frappe, "db", mock.MagicMock()) as mock_db, \
			mock.patch.object(frappe, "publish_realtime", mock.MagicMock()):

			result = SubscriptionPassthroughExecutor.execute(
				agent_doc=_fake_agent_doc(),
				run_doc=_fake_run_doc(),
				conversation=conversation,
				provider_doc=_fake_provider_doc(),
				prompt="hello",
			)

		return result, mock_db, mock_challenge, mock_park, mock_mark

	def test_session_not_found_marks_conversation_unavailable_and_fails_run_only(self):
		turn_result = SubscriptionTurnResult(
			status="error",
			final_text=None,
			provider_session_id=None,
			events=[{"source": "cli_stderr", "code": "SUBSCRIPTION_SESSION_NOT_FOUND", "message": "not found"}],
		)

		result, mock_db, mock_challenge, mock_park, mock_mark = self._run_with_turn_result(turn_result)

		# Failed run, not parked -- and no auth-challenge/park/auth-state calls.
		self.assertFalse(result["success"])
		self.assertEqual(result["status"], "Failed")
		self.assertIn("not an authentication problem", result["response"])
		mock_challenge.assert_not_called()
		mock_park.assert_not_called()
		mock_mark.assert_not_called()

		# Conversation binding marked Unavailable via session_binding.binding_for_missing_session().
		set_value_calls = [
			c for c in mock_db.set_value.call_args_list if c.args[0] == "Agent Conversation"
		]
		self.assertEqual(len(set_value_calls), 1)
		self.assertEqual(
			set_value_calls[0].args[2],
			{"subscription_provider_session_status": "Unavailable"},
		)

	def test_session_resume_failed_also_treated_as_session_lost(self):
		turn_result = SubscriptionTurnResult(
			status="error",
			final_text=None,
			provider_session_id=None,
			events=[{"source": "cli_stderr", "code": "SUBSCRIPTION_SESSION_RESUME_FAILED", "message": "boom"}],
		)

		result, mock_db, mock_challenge, mock_park, mock_mark = self._run_with_turn_result(turn_result)

		self.assertEqual(result["status"], "Failed")
		mock_challenge.assert_not_called()
		mock_park.assert_not_called()
		mock_mark.assert_not_called()

	def test_auth_required_code_still_parks_not_fails(self):
		"""Contrast case: a genuine auth failure (even mid-turn, classified via
		the adapter's error-code event rather than status='auth_required')
		must still park the run and mark the runtime's auth state -- never the
		Unavailable/session-lost path."""
		turn_result = SubscriptionTurnResult(
			status="error",
			final_text=None,
			provider_session_id=None,
			auth_reason="not logged in",
			events=[{"source": "cli_stderr", "code": "SUBSCRIPTION_AUTH_REQUIRED", "message": "not logged in"}],
		)

		result, mock_db, mock_challenge, mock_park, mock_mark = self._run_with_turn_result(turn_result)

		self.assertFalse(result["success"])
		self.assertEqual(result["status"], "Waiting Authentication")
		mock_mark.assert_called_once()
		mock_challenge.assert_called_once()
		mock_park.assert_called_once()
		self.assertEqual(mock_park.call_args.args[0], "RUN-1")

		# Never marks the conversation Unavailable for a real auth failure.
		set_value_calls = [
			c for c in mock_db.set_value.call_args_list if c.args[0] == "Agent Conversation"
		]
		self.assertEqual(set_value_calls, [])


if __name__ == "__main__":
	unittest.main()
