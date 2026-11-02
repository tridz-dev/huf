"""Per-key Flow state: ``state.get`` / ``state.set`` / ``state.delete`` nodes and the Flow State store."""

import json
import unittest
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import engine as flow_engine, state as flow_state
from huf.ai.graph.executor import GraphContext


class FakeBackend:
	"""In-memory stand-in for the DB-backed store, keyed (flow_id, key)."""

	def __init__(self):
		self.data = {}

	def get_state(self, flow_id, key):
		k = (flow_id, flow_state.normalize_key(key))
		return (True, self.data[k]) if k in self.data else (False, None)

	def set_state(self, flow_id, key, value, ttl_seconds=None):
		flow_state.encode_value(value)
		flow_state.normalize_ttl(ttl_seconds)
		self.data[(flow_id, flow_state.normalize_key(key))] = value

	def delete_state(self, flow_id, key):
		return self.data.pop((flow_id, flow_state.normalize_key(key)), None) is not None


class _Run:
	def __init__(self, flow_id="flow-a"):
		self.flow_id = flow_id
		self.name = "FR-1"


def _settings(data):
	return flow_engine.FlowRunContext(context=GraphContext(data))


def _exec(fn, node_type, config, data=None, flow_id="flow-a"):
	node = {"id": "n", "type": node_type, "config": config}
	return fn(_Run(flow_id), node, config, _settings(data or {}))


class TestRules(unittest.TestCase):
	def test_key(self):
		self.assertEqual(flow_state.normalize_key("wa:123"), "wa:123")
		self.assertEqual(flow_state.normalize_key(123), "123")
		for bad in ("", None, "x" * 141, ["a"], {"a": 1}, True):
			with self.assertRaises(flow_state.FlowStateError, msg=repr(bad)):
				flow_state.normalize_key(bad)

	def test_value_size_cap(self):
		flow_state.encode_value({"order": "1"})
		with self.assertRaises(flow_state.FlowStateError):
			flow_state.encode_value("x" * (flow_state.MAX_VALUE_BYTES + 1))

	def test_ttl(self):
		self.assertEqual(flow_state.normalize_ttl(None), flow_state.DEFAULT_TTL_SECONDS)
		self.assertEqual(flow_state.normalize_ttl(60), 60)
		for bad in (0, -1, flow_state.MAX_TTL_SECONDS + 1, "5", True):
			with self.assertRaises(flow_state.FlowStateError, msg=repr(bad)):
				flow_state.normalize_ttl(bad)

	def test_name_is_per_flow(self):
		self.assertEqual(flow_state.state_name("f", "k"), flow_state.state_name("f", "k"))
		self.assertNotEqual(flow_state.state_name("f", "k"), flow_state.state_name("g", "k"))
		self.assertLessEqual(len(flow_state.state_name("f", "k" * 140)), 140)


class TestNodes(unittest.TestCase):
	def setUp(self):
		self.fake = FakeBackend()
		p = patch.object(flow_engine, "flow_state", self.fake_module())
		p.start()
		self.addCleanup(p.stop)

	def fake_module(self):
		fake = self.fake

		class M:
			FlowStateError = flow_state.FlowStateError
			get_state = staticmethod(fake.get_state)
			set_state = staticmethod(fake.set_state)
			delete_state = staticmethod(fake.delete_state)

		return M

	def test_set_then_get(self):
		r = _exec(flow_engine._exec_state_set, "state.set", {"key": "wa:1", "value": {"awaiting": "order"}})
		self.assertEqual(r["status"], "success")
		g = _exec(flow_engine._exec_state_get, "state.get", {"key": "wa:1"})
		self.assertEqual(g["output"], {"found": True, "value": {"awaiting": "order"}})

	def test_get_missing_uses_default(self):
		g = _exec(flow_engine._exec_state_get, "state.get", {"key": "nope", "default": "idle"})
		self.assertEqual(g["output"], {"found": False, "value": "idle"})

	def test_key_and_value_are_references(self):
		data = {"sender_id": "9199", "step": "ask"}
		cfg = {
			"key": {"$template": "wa:{s}", "vars": {"s": {"$from": "input.sender_id"}}},
			"value": {"$from": "input.step"},
		}
		_exec(flow_engine._exec_state_set, "state.set", cfg, data)
		self.assertEqual(self.fake.data[("flow-a", "wa:9199")], "ask")

	def test_state_is_scoped_to_the_running_flow(self):
		_exec(flow_engine._exec_state_set, "state.set", {"key": "k", "value": 1}, flow_id="flow-a")
		g = _exec(flow_engine._exec_state_get, "state.get", {"key": "k"}, flow_id="flow-b")
		self.assertFalse(g["output"]["found"])

	def test_flow_cannot_be_chosen_by_config(self):
		g = _exec(flow_engine._exec_state_get, "state.get", {"key": "k", "flow": "flow-a"}, flow_id="flow-b")
		self.assertEqual(g["status"], "failed")

	def test_delete(self):
		_exec(flow_engine._exec_state_set, "state.set", {"key": "k", "value": 1})
		d = _exec(flow_engine._exec_state_delete, "state.delete", {"key": "k"})
		self.assertEqual(d["output"], {"deleted": True})
		self.assertFalse(_exec(flow_engine._exec_state_get, "state.get", {"key": "k"})["output"]["found"])

	def test_bad_key_fails_node(self):
		r = _exec(flow_engine._exec_state_set, "state.set", {"key": {"$from": "input.missing"}, "value": 1})
		self.assertEqual(r["status"], "failed")
		self.assertIn("name to save", r["error"])

	def test_registered(self):
		for t in ("state.get", "state.set", "state.delete"):
			self.assertIn(t, flow_engine._NODE_EXECUTORS)


class TestFlowStateStore(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.flow = f"_test-state-{frappe.generate_hash(length=6)}"

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Flow State", {"flow_id": ["like", "_test-state-%"]})
		frappe.db.commit()

	def test_roundtrip_and_overwrite(self):
		self.assertEqual(flow_state.get_state(self.flow, "k"), (False, None))
		flow_state.set_state(self.flow, "k", {"a": 1})
		self.assertEqual(flow_state.get_state(self.flow, "k"), (True, {"a": 1}))
		flow_state.set_state(self.flow, "k", ["x"])
		self.assertEqual(flow_state.get_state(self.flow, "k"), (True, ["x"]))
		self.assertEqual(frappe.db.count("Flow State", {"flow_id": self.flow}), 1)

	def test_scoped_per_flow(self):
		flow_state.set_state(self.flow, "k", 1)
		self.assertEqual(flow_state.get_state(self.flow + "-other", "k"), (False, None))

	def test_falsy_value_is_found(self):
		flow_state.set_state(self.flow, "k", 0)
		self.assertEqual(flow_state.get_state(self.flow, "k"), (True, 0))

	def test_expired_is_missing_and_lazily_deleted(self):
		flow_state.set_state(self.flow, "k", 1, ttl_seconds=60)
		frappe.db.set_value("Flow State", flow_state.state_name(self.flow, "k"), "expires_at", "2000-01-01 00:00:00")
		self.assertEqual(flow_state.get_state(self.flow, "k"), (False, None))
		self.assertFalse(frappe.db.exists("Flow State", flow_state.state_name(self.flow, "k")))

	def test_purge_expired(self):
		flow_state.set_state(self.flow, "old", 1)
		flow_state.set_state(self.flow, "new", 2)
		frappe.db.set_value("Flow State", flow_state.state_name(self.flow, "old"), "expires_at", "2000-01-01 00:00:00")
		self.assertGreaterEqual(flow_state.purge_expired(), 1)
		self.assertEqual(flow_state.get_state(self.flow, "new"), (True, 2))
		self.assertFalse(frappe.db.exists("Flow State", flow_state.state_name(self.flow, "old")))

	def test_delete(self):
		flow_state.set_state(self.flow, "k", 1)
		self.assertTrue(flow_state.delete_state(self.flow, "k"))
		self.assertFalse(flow_state.delete_state(self.flow, "k"))

	def test_too_big_rejected(self):
		with self.assertRaises(flow_state.FlowStateError):
			flow_state.set_state(self.flow, "k", "x" * (flow_state.MAX_VALUE_BYTES + 1))

	def test_ordinary_huf_users_have_no_doctype_access(self):
		roles = {p.role for p in frappe.get_meta("Flow State").permissions if p.read}
		self.assertEqual(roles, {"System Manager", "Huf Manager"})

	def test_nodes_end_to_end_against_db(self):
		run = _Run(self.flow)
		ctx = _settings({})
		cfg = {"key": "wa:1", "value": {"awaiting": "order"}}
		flow_engine._exec_state_set(run, {"id": "s", "type": "state.set", "config": cfg}, cfg, ctx)
		out = flow_engine._exec_state_get(run, {"id": "g", "type": "state.get", "config": {"key": "wa:1"}}, {"key": "wa:1"}, ctx)
		self.assertEqual(out["output"]["value"], {"awaiting": "order"})


if __name__ == "__main__":
	unittest.main()
