"""G2 (H-W2-05): a blocked send is final: never retried, never re-sent on resume; a send step cannot carry a retry."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from frappe.tests import IntegrationTestCase

from huf.ai.channels.outbound import guard, guard_steps
from huf.ai.flow import engine, preflight
from huf.ai.flow.nodes import retry, send
from huf.ai.flow.runs import park
from huf.ai.flow.testrun import gate
from huf.ai.graph.executor import GraphContext

RETRY = {"attempts": 3, "backoff": "fixed", "delay_seconds": 60}
CONFIG = {"gateway": "gw", "recipient": "+91 98765 43210", "template": "promo", "category": "marketing"}
NODE = {"id": "s1", "type": "send.message", "next": "n2", "config": CONFIG}


def run_doc(waiting=None):
	return SimpleNamespace(
		name="RUN-1",
		flow_id="flow-1",
		flow_version="3",
		member_key="m1",
		run_mode="",
		status="Running",
		waiting=waiting,
	)


class TestBlockedIsFinal(IntegrationTestCase):
	def setUp(self):
		self.transport = MagicMock(return_value=None)
		self.calls = 0
		for patcher in (
			patch.object(guard, "BUILTIN_STEPS", [("block", self._block)]),
			patch.object(guard, "_hook_paths", return_value=[]),
			patch.object(guard_steps, "window_resolvers", return_value=[]),
			patch.object(guard_steps, "resolve_caps", return_value=[]),
			patch.object(gate, "live_send_on", return_value=True),
			patch.object(gate, "pin_is_current", return_value=True),
			patch.object(send, "_enqueue", self.transport),
			patch.object(send, "channel_of", return_value="whatsapp"),
			patch.object(engine, "_context_of", return_value=GraphContext()),
			patch.object(engine, "_persist_context"),
			patch.object(engine, "_transition_run", return_value=True),
			patch("huf.ai.flow.runs.member.set_status"),
		):
			patcher.start()
			self.addCleanup(patcher.stop)

	def _block(self, request):
		self.calls += 1
		return {"allow": False, "reason": "opted_out"}

	def test_blocked_send_zero_transport_zero_retries(self):
		node = {**NODE, "config": {**CONFIG, "retry": RETRY}}
		with patch.object(park, "park_run") as park_run:
			result = retry.run_with_retry(
				run_doc(), node, {}, lambda: send.exec_send_message(run_doc(), NODE, dict(CONFIG), {})
			)
		self.assertEqual(result["output"], {"status": "blocked", "reason": "opted_out"})
		self.assertEqual(result["next_node_id"], "n2")  # normal edge, not on_error
		self.assertEqual(self.transport.call_count, 0)
		self.assertEqual(park_run.call_count, 0)  # retry counter 0
		self.assertEqual(self.calls, 1)

	def test_blocked_after_park_and_wake_stays_blocked(self):
		woken = json.dumps({"node_id": "s1", "reason": park.SEND_WINDOW_REASON, "woke": {"reason": "timer"}})
		result = send.exec_send_message(run_doc(waiting=woken), NODE, dict(CONFIG), {})
		self.assertEqual(result["output"], {"status": "blocked", "reason": "opted_out"})
		self.assertEqual(self.transport.call_count, 0)


class TestSendCannotRetry(IntegrationTestCase):
	def test_retry_policy_never_applies_to_send(self):
		self.assertIsNone(retry.policy_of({**NODE, "config": {**CONFIG, "retry": RETRY}}))

	def test_runtime_config_rejects_retry(self):
		self.assertIn("cannot try again", send.config_problem({**CONFIG, "retry": RETRY}))

	def test_preflight_forbids_retry_on_send(self):
		defn = {
			"nodes": [
				{**NODE, "config": {**CONFIG, "retry": RETRY}},
				{"id": "s2", **{k: v for k, v in NODE.items() if k != "id"}, "retry": RETRY},
			]
		}
		with patch.object(preflight, "template_exists", return_value=True):
			found = preflight._send_checks(defn, None)
		self.assertEqual([f.node_id for f in found if f.code == "SEND_RETRY_FORBIDDEN"], ["s1", "s2"])
		with patch.object(preflight, "template_exists", return_value=True):
			clean = preflight._send_checks({"nodes": [NODE]}, None)
		self.assertNotIn("SEND_RETRY_FORBIDDEN", [f.code for f in clean])
