"""``send.message`` node (H-W2-03): bind, guard chain, transport; no send path bypasses the chain."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.channels.outbound import guard, guard_steps, token_binder
from huf.ai.flow import engine
from huf.ai.flow.runs import preflight
from huf.ai.flow.nodes import send
from huf.ai.flow.runs import park
from huf.ai.flow.support import step_keys
from huf.ai.flow.support.node_schemas import build_node_schemas
from huf.ai.graph.executor import GraphContext

NODE = {"id": "s1", "type": "send.message", "next": "n2"}
CONFIG = {"gateway": "gw", "recipient": "+91 98765 43210", "template": "promo", "category": "marketing"}
SENTINEL = "SENTINEL-VALUE-93"


def run_doc(**extra):
	return SimpleNamespace(
		name="RUN-1",
		flow_id="flow-1",
		flow_version="3",
		member_key="m1",
		run_mode="",
		status="Running",
		waiting=None,
		**extra,
	)


class TestSendMessageNode(IntegrationTestCase):
	def setUp(self):
		self.hooks = {}
		self.transport = MagicMock(return_value=None)
		self.requests = []
		for patcher in (
			patch.object(guard, "BUILTIN_STEPS", [("record", self._record)]),
			patch.object(guard, "_hook_paths", side_effect=lambda: list(self.hooks)),
			patch.object(guard_steps, "window_resolvers", return_value=[]),
			patch.object(guard_steps, "resolve_caps", return_value=[]),
			patch.object(frappe, "get_attr", side_effect=lambda p: self.hooks[p]),
			patch.object(send, "_enqueue", self.transport),
			patch.object(send, "channel_of", return_value="whatsapp"),
			patch("huf.ai.flow.testrun.gate.live_send_on", return_value=True),  # H-W2-05: live needs live_send
			patch("huf.ai.flow.testrun.gate.pin_is_current", return_value=True),  # H-W2-18: run is on the current version
			patch.object(engine, "_context_of", return_value=GraphContext()),
			patch.object(engine, "_persist_context"),
			patch.object(engine, "_transition_run", return_value=True),
		):
			patcher.start()
			self.addCleanup(patcher.stop)

	def _record(self, request):
		self.requests.append(request)
		return {"allow": True}

	def run_node(self, flow_run=None, **config):
		node = step_keys.with_key(NODE, frappe.generate_hash())  # the engine always attaches a step key
		return send.exec_send_message(flow_run or run_doc(), node, {**CONFIG, **config}, {})

	def test_send_without_step_key_is_not_queued(self):
		result = send.exec_send_message(run_doc(), NODE, dict(CONFIG), {})
		self.assertEqual(result["status"], "failed")
		self.transport.assert_not_called()

	def test_allowed_send_is_queued_exactly_once(self):
		result = self.run_node()
		self.assertEqual(result["output"], {"status": "queued"})
		self.assertEqual(result["next_node_id"], "n2")
		self.transport.assert_called_once()
		request = self.requests[0]
		self.assertEqual(request["recipient"], "+919876543210")
		self.assertTrue(request["live"])
		self.assertEqual(request["category"], "marketing")
		self.assertIn("header", request)

	def test_any_hook_error_blocks_without_transport(self):
		def boom(request):
			raise RuntimeError("x")

		for verdict in (
			boom,
			lambda r: None,
			lambda r: {"allowed": True},
			lambda r: {"allow": False, "reason": "opted_out"},
		):
			with self.subTest(verdict=verdict):
				self.hooks = {"app.step": verdict}
				result = self.run_node()
				self.assertEqual(result["status"], "success")
				self.assertEqual(result["output"]["status"], "blocked")
		self.transport.assert_not_called()

	def test_bad_recipient_blocks(self):
		with patch.object(guard, "BUILTIN_STEPS", list(guard_steps.STEPS[:1])):
			result = self.run_node(recipient="98765")
		self.assertEqual(result["output"], {"status": "blocked", "reason": "bad_recipient"})
		self.transport.assert_not_called()

	def test_tokens_bound_before_guard_and_values_never_in_output_or_request(self):
		with patch.object(token_binder, "bind", return_value={"1": SENTINEL}) as bind:
			result = self.run_node(variables=["1"])
		bind.assert_called_once()
		self.assertEqual(self.requests[0]["token_names"], ["1"])
		self.assertNotIn(SENTINEL, frappe.as_json(self.requests[0]))
		self.assertNotIn(SENTINEL, frappe.as_json(result))
		# values are bound again at delivery, never queued
		self.assertNotIn(SENTINEL, frappe.as_json(self.transport.call_args.args[0]))

	def test_unbound_token_blocks_before_guard(self):
		with patch.object(token_binder, "bind", side_effect=token_binder.TokenUnbound(["1"])):
			result = self.run_node(variables=["1"])
		self.assertEqual(result["output"], {"status": "blocked", "reason": "token_unbound"})
		self.assertEqual(self.requests, [])
		self.transport.assert_not_called()

	def test_test_run_is_previewed_not_sent(self):
		with patch("huf.ai.flow.testrun.gate.is_test_run", return_value=True):
			result = self.run_node()
		self.assertEqual(result["output"], {"status": "previewed"})
		self.assertFalse(self.requests[-1]["live"])
		self.transport.assert_not_called()

	def test_window_defers_and_exhausted_blocks(self):
		until = datetime(2030, 1, 7, 3, 30, tzinfo=timezone.utc)
		deferred = guard.GuardResult(False, None, "send_window", until)
		with (
			patch.object(guard, "evaluate", return_value=deferred),
			patch.object(park, "defer_send", return_value="PARKED") as defer,
			patch("huf.ai.flow.runs.member.set_status"),
		):
			self.assertEqual(self.run_node(), "PARKED")
			defer.assert_called_once()
			defer.return_value = None
			self.assertEqual(
				self.run_node()["output"], {"status": "blocked", "reason": "window_defer_exhausted"}
			)
		self.transport.assert_not_called()

	def test_bad_config_fails_before_any_check(self):
		for config in (
			{"gateway": ""},
			{"category": "other"},
			{"text": "hi"},
			{"extra": 1},
			{"recipient": ""},
		):
			with self.subTest(config=config):
				self.assertEqual(self.run_node(**config)["status"], "failed")
		self.assertEqual(self.requests, [])

	def test_node_is_in_catalog_and_preflight_checks_guard_config(self):
		self.assertIn("send.message", build_node_schemas())
		self.assertIn("send.message", engine._NODE_TYPES)
		defn = {"nodes": [{"id": "s1", "type": "send.message", "config": {"text": "hi"}}]}
		codes = {f.code for f in preflight._send_checks(defn, None)}
		self.assertIn("SEND_GUARD_CONFIG_MISSING", codes)
		defn["nodes"][0]["config"] = {"text": "hi", "gateway": "gw", "recipient": "+1", "category": "service"}
		codes = {f.code for f in preflight._send_checks(defn, None)}
		self.assertNotIn("SEND_GUARD_CONFIG_MISSING", codes)


class TestSendOutboxWiring(IntegrationTestCase):
	"""H-W2-15 wiring: the send step queues on the outbox; a decided send is never run again (G2)."""

	def test_enqueue_maps_literal_recipient_to_block_and_other_channels_refused(self):
		from huf.ai.channels.outbound import outbox

		with patch.object(outbox, "enqueue", side_effect=outbox.LiteralRecipient("recipient_ref")):
			self.assertEqual(send._enqueue({"channel": "whatsapp"}), "bad_recipient")
		with patch.object(outbox, "enqueue") as enqueue:
			self.assertEqual(send._enqueue({"channel": "telegram"}), "channel_unsupported")
			self.assertIsNone(send._enqueue({"channel": "whatsapp", "step_key": "k"}))
		enqueue.assert_called_once_with({"channel": "whatsapp", "step_key": "k"})

	def test_engine_replays_decided_send_inside_error_handler(self):
		from huf.ai.flow.support import step_keys

		ctx = GraphContext()
		first = step_keys.step_key("RUN-1", "s1", 1)
		decided = {"status": "success", "output": {"status": "blocked", "reason": "opted_out"}}
		step_keys.record(ctx.data, "s1", first, decided)
		step_keys.advance(ctx.data, "s1")
		second = step_keys.with_key(NODE, step_keys.key_for("RUN-1", "s1", ctx.data))
		with (
			patch.object(engine, "_context_of", return_value=ctx),
			patch("huf.ai.flow.nodes.error_handler.first_error", return_value=None),
		):
			self.assertIsNone(engine._decided_send(run_doc(), second, {}))  # a forward loop visit may send
			self.assertEqual(engine._decided_send(run_doc(), step_keys.with_key(NODE, first), {}), decided)
		with (
			patch.object(engine, "_context_of", return_value=ctx),
			patch("huf.ai.flow.nodes.error_handler.first_error", return_value={"node_id": "x"}),
		):
			self.assertEqual(engine._decided_send(run_doc(), second, {}), decided)
