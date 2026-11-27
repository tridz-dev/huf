"""G3 (H-W2-05): ``live = live_send AND NOT dry_run``, decided in one function; republish resets ``live_send``."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.channels import guard, guard_steps
from huf.ai.flow import engine
from huf.ai.flow.catalog import node_registry
from huf.ai.flow.nodes import send
from huf.ai.flow.testrun import gate
from huf.ai.graph.executor import GraphContext
from huf.huf.doctype.flow_definition.flow_definition import FlowDefinition

NODE = {"id": "s1", "type": "send.message", "next": "n2"}
CONFIG = {"gateway": "gw", "recipient": "+91 98765 43210", "template": "promo", "category": "marketing"}


def run_doc(run_mode=""):
	return SimpleNamespace(
		name="RUN-1", flow_id="flow-1", flow_version="3", member_key="m1", run_mode=run_mode, status="Running", waiting=None
	)


class TestIsLive(IntegrationTestCase):
	def test_truth_table(self):
		for dry, live_send, expected in ((True, True, False), (False, False, False), (True, False, False), (False, True, True)):
			with self.subTest(dry=dry, live_send=live_send):
				with (
					patch.object(gate, "is_dry_run", return_value=dry),
					patch.object(gate, "live_send_on", return_value=live_send),
				):
					self.assertIs(gate.is_live(run_doc()), expected)
					self.assertIs(send.is_live(run_doc()), expected)

	def test_test_run_and_step_test_are_dry(self):
		self.assertTrue(gate.is_dry_run(run_doc(run_mode=gate.STORED_TEST)))
		with gate.step_test_scope():
			self.assertTrue(gate.is_dry_run(run_doc()))
		self.assertFalse(gate.is_dry_run(run_doc()))

	def test_live_send_fails_closed(self):
		self.assertFalse(gate.live_send_on(None))
		with patch.object(frappe.db, "get_value", side_effect=RuntimeError("x")):
			self.assertFalse(gate.live_send_on("flow-1"))
		with patch.object(frappe.db, "get_value", return_value=None):
			self.assertFalse(gate.live_send_on("flow-1"))
		with patch.object(frappe.db, "get_value", return_value=1):
			self.assertTrue(gate.live_send_on("flow-1"))


class TestSendHonoursLive(IntegrationTestCase):
	def setUp(self):
		self.transport = MagicMock(return_value=None)
		for patcher in (
			patch.object(guard, "BUILTIN_STEPS", [("allow", lambda r: {"allow": True})]),
			patch.object(guard, "_hook_paths", return_value=[]),
			patch.object(guard_steps, "window_resolvers", return_value=[]),
			patch.object(guard_steps, "resolve_caps", return_value=[]),
			patch.object(send, "_transport", self.transport),
			patch.object(send, "channel_of", return_value="whatsapp"),
			patch.object(engine, "_context_of", return_value=GraphContext()),
			patch.object(engine, "_persist_context"),
			patch.object(engine, "_transition_run", return_value=True),
		):
			patcher.start()
			self.addCleanup(patcher.stop)

	def run_node(self, live_send, run_mode=""):
		with patch.object(gate, "live_send_on", return_value=live_send):
			return send.exec_send_message(run_doc(run_mode), NODE, dict(CONFIG), {})

	def test_dry_run_with_live_send_sends_nothing(self):
		self.assertEqual(self.run_node(True, gate.STORED_TEST)["output"], {"status": "previewed"})
		self.assertEqual(self.transport.call_count, 0)

	def test_live_send_off_sends_nothing(self):
		self.assertEqual(self.run_node(False)["output"], {"status": "previewed"})
		self.assertEqual(self.transport.call_count, 0)

	def test_live_send_on_and_not_dry_sends_once(self):
		self.assertEqual(self.run_node(True)["output"], {"status": "sent"})
		self.assertEqual(self.transport.call_count, 1)


class TestNodeCallContextLive(IntegrationTestCase):
	def test_default_is_false(self):
		ctx = node_registry.NodeCallContext(
			config={}, refs={}, run_id="R", member=None, park=lambda **k: None, is_resume=False, waiting=None
		)
		self.assertFalse(ctx.live)

	def test_dispatch_fills_live(self):
		seen = []
		node_type = SimpleNamespace(
			type="app.x", label="X", routing="next", can_wait=False, test_simulate="run", handler="app.handler"
		)
		for live in (True, False):
			with (
				patch.object(node_registry, "get_type", return_value=node_type),
				patch.object(engine, "_context_of", return_value=GraphContext()),
				patch.object(gate, "is_live", return_value=live),
				patch.object(frappe, "get_attr", return_value=lambda call: seen.append(call.live) or {}),
			):
				node_registry.executor_for("app.x")(run_doc(), {"id": "a1", "type": "app.x"}, {}, {})
		self.assertEqual(seen, [True, False])


def flow_doc(status, definition, live_send, before=None):
	doc = SimpleNamespace(status=status, definition_json=definition, live_send=live_send)
	doc.is_new = lambda: before is None
	doc.get_doc_before_save = lambda: before
	return doc


class TestRepublishResetsLiveSend(IntegrationTestCase):
	def reset(self, doc):
		FlowDefinition._reset_live_send_on_republish(doc)
		return doc.live_send

	def test_new_definition_resets(self):
		before = SimpleNamespace(status="Active", definition_json='{"a":1}')
		self.assertEqual(self.reset(flow_doc("Active", '{"a":2}', 1, before)), 0)

	def test_becoming_active_resets(self):
		before = SimpleNamespace(status="Draft", definition_json='{"a":1}')
		self.assertEqual(self.reset(flow_doc("Active", '{"a":1}', 1, before)), 0)
		self.assertEqual(self.reset(flow_doc("Active", '{"a":1}', 1)), 0)  # created Active

	def test_switching_on_without_republish_keeps_it(self):
		before = SimpleNamespace(status="Active", definition_json='{"a":1}')
		self.assertEqual(self.reset(flow_doc("Active", '{"a":1}', 1, before)), 1)
