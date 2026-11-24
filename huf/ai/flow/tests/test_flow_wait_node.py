"""Wait node (flow/nodes/wait.py): park, re-entry, routing, loop guard, test-run simulation."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import engine as flow_engine, park
from huf.ai.flow.nodes.wait import exec_wait
from huf.ai.flow.testrun import gate


def _utc_now():
	return datetime.now(timezone.utc).replace(tzinfo=None)


class TestWaitNode(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.flow = frappe.get_doc(
			{
				"doctype": "Flow Definition",
				"flow_id": f"_test-wait-{frappe.generate_hash(length=8)}",
				"flow_name": "Wait Node Flow",
				"status": "Draft",
				"definition_json": json.dumps({"nodes": [{"id": "w1", "type": "wait"}]}),
			}
		)
		self.flow.flags.ignore_validate = True
		self.flow.insert(ignore_permissions=True)
		self.run_doc = frappe.get_doc(
			{
				"doctype": "Flow Run",
				"flow_definition": self.flow.name,
				"flow_id": self.flow.flow_id,
				"status": "Running",
				"trigger_type": "Manual",
			}
		).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.delete_doc("Flow Run", self.run_doc.name, ignore_permissions=True, force=True)
		frappe.delete_doc("Flow Definition", self.flow.name, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _node(self, **config):
		return {"id": "w1", "type": "wait", "next": "n2", "config": config}

	def _run(self, node):
		return exec_wait(self.run_doc, node, node["config"], {})

	def _row(self):
		return frappe.db.get_value("Flow Run", self.run_doc.name, ["status", "resume_at", "waiting"], as_dict=True)

	def _wake(self, reason="elapsed"):
		with patch("frappe.enqueue"):
			return park.wake_run(self.run_doc.name, reason)

	def _reenter(self, node):
		self.run_doc.reload()
		return self._run(node)

	def test_duration_parks_with_resume_at(self):
		out = self._run(self._node(mode="duration", duration={"value": 2, "unit": "hours"}))
		self.assertTrue(out.is_paused)
		row = self._row()
		self.assertEqual(row.status, "Waiting Timer")
		delta = row.resume_at - _utc_now()
		self.assertTrue(timedelta(minutes=118) < delta < timedelta(minutes=122))

	def test_until_past_continues_immediately(self):
		out = self._run(self._node(mode="until", until="2000-01-01T00:00:00+00:00"))
		self.assertEqual(out["status"], "success")
		self.assertEqual(out["output"]["reason"], "elapsed")
		self.assertEqual(out["next_node_id"], "n2")
		self.assertEqual(self._row().status, "Running")

	def test_until_resolves_reference_at_park(self):
		target = (_utc_now() + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
		with patch.object(flow_engine, "_context_of") as ctx_of:
			ctx_of.return_value.resolve.return_value = target
			with patch.object(flow_engine, "_persist_context"):
				out = self._run(self._node(mode="until", until={"$from": "trigger.when"}))
		self.assertTrue(out.is_paused)
		ctx_of.return_value.resolve.assert_called_once_with({"$from": "trigger.when"})
		self.assertEqual(self._row().resume_at.date(), (_utc_now() + timedelta(days=3)).date())

	def test_reentry_emits_output_once(self):
		node = self._node(mode="duration", duration={"value": 1, "unit": "minutes"})
		self._run(node)
		self.assertTrue(self._wake())
		out = self._reenter(node)
		self.assertEqual(out["status"], "success")
		self.assertEqual(out["output"]["reason"], "elapsed")
		self.assertEqual(out["next_node_id"], "n2")
		self.assertFalse(frappe.db.get_value("Flow Run", self.run_doc.name, "waiting"))
		# entered again with the record cleared: it is a fresh park, not a second output
		again = self._reenter(node)
		self.assertTrue(again.is_paused)

	def test_wait_inside_foreach_fails_clearly(self):
		wait = {"id": "w1", "type": "wait", "config": {}}
		with patch.object(flow_engine, "_flow_nodes_by_id", return_value={"w1": wait}):
			with patch.object(flow_engine, "_context_of"):
				result = flow_engine._run_sub_chain(self.run_doc, {}, ["w1"])
		self.assertEqual(result["status"], "failed")
		self.assertIn("Wait steps cannot be used inside a loop", result["error"])

	def test_max_wait_rejected(self):
		out = self._run(self._node(mode="duration", duration={"value": 400, "unit": "days"}))
		self.assertEqual(out["status"], "failed")
		self.assertEqual(self._row().status, "Running")
		with patch.dict(frappe.conf, {"huf_flow_wait_max_days": 500}):
			self.assertTrue(self._run(self._node(mode="duration", duration={"value": 400, "unit": "days"})).is_paused)

	def test_test_run_simulates_zero_delay(self):
		node = self._node(mode="duration", duration={"value": 30, "unit": "days"})
		result = gate.simulate_node(node, lambda v: v)
		self.assertEqual(result["status"], "success")
		self.assertEqual(result["next_node_id"], "n2")
		self.assertEqual(result["output"]["reason"], "simulated")

	def test_double_wake_advances_once(self):
		self._run(self._node(mode="duration", duration={"value": 1, "unit": "minutes"}))
		self.assertTrue(self._wake())
		self.assertFalse(self._wake())

	def test_resume_mode_timeout_next_routes(self):
		node = self._node(mode="resume", resume={"timeout_ms": 60000, "timeout_next": "late"})
		out = self._run(node)
		self.assertTrue(out.is_paused)
		self.assertIn("token", out.extra)
		self.assertTrue(self._wake("elapsed"))
		self.assertEqual(self._reenter(node)["next_node_id"], "late")

	def test_resume_mode_resumed_routes_next(self):
		node = self._node(mode="resume", resume={"timeout_next": "late"})
		self._run(node)
		self.assertIsNone(self._row().resume_at)
		self.assertTrue(self._wake("resumed"))
		self.assertEqual(self._reenter(node)["next_node_id"], "n2")
