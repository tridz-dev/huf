"""Unit tests for the Gateway Decision Runtime pre-filter (T12.01, PLAN.md §3.10
"Gateways (pre-filter, PR 12)").

Frappe-free like ``huf/ai/tests/test_gateway_service.py``'s existing
``process_gateway_event`` tests: ``huf.ai.gateway_service.frappe`` is patched
wholesale (``MagicMock``) and ``huf.ai.decision.service.run_policy`` is
patched at its defining module -- ``_run_gateway_pre_filter`` does
``from huf.ai.decision import service`` *inside* the function (matching
``huf/ai/automation_runner.py``'s ``_execute_decision``), so patching the
attribute on the source module is what actually intercepts the call
regardless of when the local import runs.

Run with:
    bench --site $SITE run-tests --app huf --module huf.ai.tests.test_gateway_prefilter_decision
"""

from __future__ import annotations

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from huf.ai import gateway_service
from huf.ai.decision.types import (
	CandidateSource,
	DecisionAnswer,
	DecisionResponse,
	DecisionStatus,
	QuestionKind,
	ServiceResult,
)


def gateway(**overrides):
	values = {
		"name": "Support Telegram",
		"provider": "Telegram",
		"is_enabled": 1,
		"execution_user": "gateway-bot",
		"pre_filter_policy": "",
		"pre_filter_mode": "Off",
		"pre_filter_no_agent_reply": "",
	}
	values.update(overrides)
	return SimpleNamespace(**values)


def queued_agent_event(**overrides):
	values = dict(
		name="GATEWAY-EVENT-PF01",
		status="Queued",
		gateway="Support Telegram",
		target_type="Agent",
		target_agent="Support Agent",
		message_text="hello",
		thread_id="123",
		conversation_id="2000000001",
		sender_id="42",
	)
	values.update(overrides)
	return MagicMock(**values)


def success_result(value, *, decision_call="DC-001"):
	return ServiceResult(
		status=DecisionStatus.SUCCESS,
		response=DecisionResponse(
			status=DecisionStatus.SUCCESS,
			answers={"classification": DecisionAnswer("classification", QuestionKind.SELECT, value)},
		),
		decision_call=decision_call,
	)


def run_agent_and_deliver(event, configured_gateway, agent_doc, *, run_result=None, send_result=None):
	"""Drive process_gateway_event through the Agent path with the pre-filter's
	frappe.get_doc/run_policy/agent-access/run_agent_sync/send_gateway_reply
	collaborators already patched by the caller. Returns process_gateway_event's result."""
	run_result = run_result or {"agent_run_id": "AR-001", "response": "Hello back"}
	send_result = send_result or SimpleNamespace(provider_message_id="tg-1")
	mock_run = MagicMock(return_value=run_result)
	with patch.dict(sys.modules, {"huf.ai.agent_integration": SimpleNamespace(run_agent_sync=mock_run)}), patch(
		"huf.ai.agent_access.check_agent_access", return_value=True
	), patch("huf.ai.gateway_webhook.send_gateway_reply", return_value=send_result) as mock_send:
		result = gateway_service.process_gateway_event(event.name)
	return result, mock_run, mock_send


class TestPreFilterOffOrUnconfigured(unittest.TestCase):
	"""Off mode / no policy must be byte-identical to today: zero calls into
	the Decision Runtime, event routes to its Agent exactly as before."""

	@patch("huf.ai.gateway_service.frappe")
	def test_off_mode_never_calls_run_policy(self, mock_frappe):
		event = queued_agent_event()
		configured_gateway = gateway(pre_filter_mode="Off", pre_filter_policy="pf-policy")
		agent_doc = MagicMock(allow_guest=False)
		mock_frappe.get_doc.side_effect = [event, configured_gateway, agent_doc]

		with patch("huf.ai.decision.service.run_policy") as run_policy:
			result, mock_run, mock_send = run_agent_and_deliver(event, configured_gateway, agent_doc)

		run_policy.assert_not_called()
		self.assertEqual(result["status"], "Succeeded")
		mock_run.assert_called_once()

	@patch("huf.ai.gateway_service.frappe")
	def test_enforce_mode_with_no_policy_never_calls_run_policy(self, mock_frappe):
		event = queued_agent_event()
		configured_gateway = gateway(pre_filter_mode="Enforce", pre_filter_policy="")
		agent_doc = MagicMock(allow_guest=False)
		mock_frappe.get_doc.side_effect = [event, configured_gateway, agent_doc]

		with patch("huf.ai.decision.service.run_policy") as run_policy:
			result, mock_run, mock_send = run_agent_and_deliver(event, configured_gateway, agent_doc)

		run_policy.assert_not_called()
		self.assertEqual(result["status"], "Succeeded")
		mock_run.assert_called_once()


class TestPreFilterEnforceSpam(unittest.TestCase):
	@patch("huf.ai.gateway_service.frappe")
	def test_spam_answer_rejects_event_with_audit_and_skips_agent(self, mock_frappe):
		event = queued_agent_event()
		configured_gateway = gateway(pre_filter_mode="Enforce", pre_filter_policy="pf-policy")
		mock_frappe.get_doc.side_effect = [event, configured_gateway]

		mock_run = MagicMock()
		with patch(
			"huf.ai.decision.service.run_policy", return_value=success_result("spam")
		) as run_policy, patch.dict(
			sys.modules, {"huf.ai.agent_integration": SimpleNamespace(run_agent_sync=mock_run)}
		):
			result = gateway_service.process_gateway_event(event.name)

		self.assertEqual(result, {"event_name": event.name, "status": "Rejected"})
		mock_run.assert_not_called()
		rejection = event.db_set.call_args.args[0]
		self.assertEqual(rejection["status"], "Rejected")
		self.assertIn("spam", rejection["error_message"])
		self.assertIn("DC-001", rejection["error_message"])

		call_kwargs = run_policy.call_args.kwargs
		self.assertEqual(call_kwargs["mode"], "Enforce")
		self.assertEqual(call_kwargs["surface"], "gateway")
		self.assertEqual(call_kwargs["candidate_source"], CandidateSource.POLICY_OPTIONS)
		self.assertEqual(call_kwargs["origin"].origin_type, "Gateway")
		self.assertEqual(call_kwargs["origin"].owner_user, "gateway-bot")
		self.assertEqual(run_policy.call_args.args[0], "pf-policy")


class TestPreFilterEnforceNoAgentNeeded(unittest.TestCase):
	@patch("huf.ai.gateway_service.frappe")
	def test_canned_reply_sent_and_event_succeeds_without_running_agent(self, mock_frappe):
		event = queued_agent_event()
		configured_gateway = gateway(
			pre_filter_mode="Enforce",
			pre_filter_policy="pf-policy",
			pre_filter_no_agent_reply="Thanks, no action needed right now.",
		)
		mock_frappe.get_doc.side_effect = [event, configured_gateway]

		mock_run = MagicMock()
		with patch(
			"huf.ai.decision.service.run_policy", return_value=success_result("no_agent_needed")
		), patch.dict(
			sys.modules, {"huf.ai.agent_integration": SimpleNamespace(run_agent_sync=mock_run)}
		), patch(
			"huf.ai.gateway_webhook.send_gateway_reply",
			return_value=SimpleNamespace(provider_message_id="tg-reply-1"),
		) as mock_send:
			result = gateway_service.process_gateway_event(event.name)

		self.assertEqual(
			result,
			{"event_name": event.name, "status": "Succeeded", "provider_message_id": "tg-reply-1"},
		)
		mock_send.assert_called_once_with(configured_gateway, event, "Thanks, no action needed right now.")
		mock_run.assert_not_called()
		event.db_set.assert_called_with({"status": "Succeeded"})

	@patch("huf.ai.gateway_service.frappe")
	def test_no_canned_reply_configured_falls_back_to_normal_routing(self, mock_frappe):
		event = queued_agent_event()
		configured_gateway = gateway(
			pre_filter_mode="Enforce", pre_filter_policy="pf-policy", pre_filter_no_agent_reply=""
		)
		agent_doc = MagicMock(allow_guest=False)
		mock_frappe.get_doc.side_effect = [event, configured_gateway, agent_doc]

		with patch("huf.ai.decision.service.run_policy", return_value=success_result("no_agent_needed")):
			result, mock_run, mock_send = run_agent_and_deliver(event, configured_gateway, agent_doc)

		self.assertEqual(result["status"], "Succeeded")
		mock_run.assert_called_once()


class TestPreFilterShadowNeverGates(unittest.TestCase):
	@patch("huf.ai.gateway_service.frappe")
	def test_shadow_ignores_the_answer_and_always_continues(self, mock_frappe):
		"""D18: Shadow enqueues only. Even a 'spam' answer must never drop,
		reply, or delay -- the event routes through exactly as if Off."""
		event = queued_agent_event()
		configured_gateway = gateway(pre_filter_mode="Shadow", pre_filter_policy="pf-policy")
		agent_doc = MagicMock(allow_guest=False)
		mock_frappe.get_doc.side_effect = [event, configured_gateway, agent_doc]

		with patch(
			"huf.ai.decision.service.run_policy", return_value=ServiceResult(status="shadow_enqueued")
		) as run_policy:
			result, mock_run, mock_send = run_agent_and_deliver(event, configured_gateway, agent_doc)

		self.assertEqual(run_policy.call_args.kwargs["mode"], "Shadow")
		self.assertEqual(result["status"], "Succeeded")
		mock_run.assert_called_once()


class TestPreFilterFallsBackOnFailure(unittest.TestCase):
	@patch("huf.ai.gateway_service.frappe")
	def test_run_policy_exception_falls_back_to_normal_routing(self, mock_frappe):
		mock_frappe.get_traceback.return_value = "Traceback (most recent call last):\nRuntimeError: boom"
		event = queued_agent_event()
		configured_gateway = gateway(pre_filter_mode="Enforce", pre_filter_policy="pf-policy")
		agent_doc = MagicMock(allow_guest=False)
		mock_frappe.get_doc.side_effect = [event, configured_gateway, agent_doc]

		with patch("huf.ai.decision.service.run_policy", side_effect=RuntimeError("boom")):
			result, mock_run, mock_send = run_agent_and_deliver(event, configured_gateway, agent_doc)

		self.assertEqual(result["status"], "Succeeded")
		mock_run.assert_called_once()
		mock_frappe.log_error.assert_called_once()

	@patch("huf.ai.gateway_service.frappe")
	def test_non_success_status_falls_back_to_normal_routing(self, mock_frappe):
		event = queued_agent_event()
		configured_gateway = gateway(pre_filter_mode="Enforce", pre_filter_policy="pf-policy")
		agent_doc = MagicMock(allow_guest=False)
		mock_frappe.get_doc.side_effect = [event, configured_gateway, agent_doc]

		with patch(
			"huf.ai.decision.service.run_policy", return_value=ServiceResult(status=DecisionStatus.TIMEOUT)
		):
			result, mock_run, mock_send = run_agent_and_deliver(event, configured_gateway, agent_doc)

		self.assertEqual(result["status"], "Succeeded")
		mock_run.assert_called_once()

	@patch("huf.ai.gateway_service.frappe")
	def test_unrecognized_answer_falls_back_to_normal_routing(self, mock_frappe):
		event = queued_agent_event()
		configured_gateway = gateway(pre_filter_mode="Enforce", pre_filter_policy="pf-policy")
		agent_doc = MagicMock(allow_guest=False)
		mock_frappe.get_doc.side_effect = [event, configured_gateway, agent_doc]

		with patch("huf.ai.decision.service.run_policy", return_value=success_result("continue")):
			result, mock_run, mock_send = run_agent_and_deliver(event, configured_gateway, agent_doc)

		self.assertEqual(result["status"], "Succeeded")
		mock_run.assert_called_once()


if __name__ == "__main__":
	unittest.main()
