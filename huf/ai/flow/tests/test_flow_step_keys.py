"""Idempotent step keys (H-W2-13): a re-delivered step sends once; an explicit retry gets a new key."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from frappe.tests import IntegrationTestCase

from huf.ai.channels import guard, guard_steps
from huf.ai.flow import engine
from huf.ai.flow.catalog.node_registry import NodeCallContext
from huf.ai.flow.nodes import send
from huf.ai.flow.support import step_keys
from huf.ai.graph.executor import GraphContext

NODE = {"id": "s1", "type": "send.message", "next": "n2"}
CONFIG = {"gateway": "gw", "recipient": "+91 98765 43210", "template": "promo", "category": "marketing"}


def run_doc(**extra):
	return SimpleNamespace(
		name="RUN-1", flow_id="flow-1", flow_version="3", member_key="m1", run_mode="", status="Running",
		waiting=None, **extra,
	)


class TestStepKeyPure(IntegrationTestCase):
	def test_deterministic_and_bounded(self):
		key = step_keys.step_key("RUN-1", "s1", 1)
		self.assertEqual(key, step_keys.step_key("RUN-1", "s1", 1))
		self.assertLessEqual(len(key), 64)
		self.assertNotEqual(key, step_keys.step_key("RUN-1", "s1", 2))
		self.assertNotEqual(key, step_keys.step_key("RUN-1", "s2", 1))
		self.assertNotEqual(key, step_keys.step_key("RUN-2", "s1", 1))

	def test_loop_visit_folds_into_attempt(self):
		data = {}
		first = step_keys.key_for("RUN-1", "s1", data)
		self.assertEqual(first, step_keys.key_for("RUN-1", "s1", data))  # not completed: same key
		step_keys.record(data, "s1", first, {"status": "success"})
		second = step_keys.key_for("RUN-1", "s1", data)
		self.assertNotEqual(first, second)
		self.assertNotEqual(second, step_keys.key_for("RUN-1", "s1", data, retry_attempt=2))

	def test_context_fields_default(self):
		fields = NodeCallContext.__dataclass_fields__
		self.assertEqual(fields["node_id"].default, "")
		self.assertEqual(fields["step_key"].default, "")


class TestSendStepKey(IntegrationTestCase):
	def setUp(self):
		self.ctx = GraphContext()
		self.transport = MagicMock(return_value=None)
		self.requests = []
		for patcher in (
			patch.object(guard, "BUILTIN_STEPS", [("record", self._record)]),
			patch.object(guard, "_hook_paths", return_value=[]),
			patch.object(guard_steps, "window_resolvers", return_value=[]),
			patch.object(guard_steps, "resolve_caps", return_value=[]),
			patch.object(send, "_transport", self.transport),
			patch.object(send, "channel_of", return_value="whatsapp"),
			patch("huf.ai.flow.testrun.gate.live_send_on", return_value=True),
			patch.object(engine, "_context_of", side_effect=lambda *a: self.ctx),
			patch.object(engine, "_persist_context"),
			patch.object(engine, "_transition_run", return_value=True),
		):
			patcher.start()
			self.addCleanup(patcher.stop)

	def _record(self, request):
		self.requests.append(request)
		return {"allow": True}

	def keyed(self, retry=1):
		key = step_keys.key_for("RUN-1", "s1", self.ctx.data, retry)
		return step_keys.with_key(NODE, key), key

	def test_same_step_twice_one_transport_call(self):
		node, key = self.keyed()
		first = send.exec_send_message(run_doc(), node, CONFIG, {})
		node_again = step_keys.with_key(NODE, key)  # re-delivered job: same key
		second = send.exec_send_message(run_doc(), node_again, CONFIG, {})
		self.assertEqual(first, second)
		self.transport.assert_called_once()
		self.assertEqual(self.requests[0]["step_key"], key)
		self.assertEqual(self.transport.call_args.args[-1]["step_key"], key)

	def test_explicit_retry_new_key(self):
		node, _key = self.keyed(retry=1)
		send.exec_send_message(run_doc(), node, CONFIG, {})
		retry_node = step_keys.with_key(NODE, step_keys.step_key("RUN-1", "s1", 2))
		send.exec_send_message(run_doc(), retry_node, CONFIG, {})
		self.assertEqual(self.transport.call_count, 2)
		self.assertNotEqual(self.requests[0]["step_key"], self.requests[1]["step_key"])

	def test_engine_attaches_key(self):
		node = engine._with_step_key(run_doc(), NODE, {})
		self.assertEqual(step_keys.key_of(node), step_keys.step_key("RUN-1", "s1", 1))
		self.assertNotIn(step_keys.NODE_KEY, NODE)


