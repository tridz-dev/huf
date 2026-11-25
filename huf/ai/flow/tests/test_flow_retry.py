"""Retry with backoff (flow/nodes/retry.py): parks on a timer, re-runs on wake, then follows on_error."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import engine as flow_engine, park
from huf.ai.flow.nodes import retry

FAIL = {"status": "failed", "error": "boom"}


def _utc_now():
	return datetime.now(timezone.utc).replace(tzinfo=None)


class TestFlowRetry(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.flow = frappe.get_doc(
			{
				"doctype": "Flow Definition",
				"flow_id": f"_test-retry-{frappe.generate_hash(length=8)}",
				"flow_name": "Retry Flow",
				"status": "Draft",
				"definition_json": json.dumps({"nodes": [{"id": "t1", "type": "tool.call"}]}),
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

	def _node(self, **policy):
		return {"id": "t1", "type": "tool.call", "config": {"retry": {"attempts": 3, **policy}}}

	def _row(self):
		return frappe.db.get_value("Flow Run", self.run_doc.name, ["status", "resume_at", "waiting"], as_dict=True)

	def _go(self, node, results):
		"""One handler pass: the step returns the next of ``results``."""
		self.run_doc.reload()
		with patch.object(flow_engine, "_context_of"), patch.object(flow_engine, "_persist_context"):
			return retry.run_with_retry(self.run_doc, node, {}, lambda: results.pop(0))

	def _wake(self):
		with patch("frappe.enqueue"):
			self.assertTrue(park.wake_run(self.run_doc.name, "elapsed"))
		self.run_doc.reload()

	def test_failure_parks_with_backoff(self):
		out = self._go(self._node(delay_seconds=300), [dict(FAIL)])
		self.assertTrue(out.is_paused)
		row = self._row()
		self.assertEqual(row.status, "Waiting Timer")
		waiting = json.loads(row.waiting)
		self.assertEqual((waiting["reason"], waiting["extra"]["attempt"]), ("retry", 1))
		self.assertGreater(row.resume_at, _utc_now() + timedelta(seconds=240))

	def test_exponential_delay_capped(self):
		policy = {"attempts": 6, "backoff": "exponential", "delay_seconds": 60, "max_delay_seconds": 300}
		self.assertEqual([retry.backoff_seconds(policy, n) for n in (1, 2, 3, 4, 5)], [60, 120, 240, 300, 300])
		self.assertEqual(retry.backoff_seconds({"backoff": "fixed", "delay_seconds": 5}, 3), 60)  # rounded up to 60 s

	def test_success_after_retry_clears_state(self):
		node = self._node(delay_seconds=60)
		self.assertTrue(self._go(node, [dict(FAIL)]).is_paused)
		self._wake()
		out = self._go(node, [{"status": "success", "output": {"ok": 1}}])
		self.assertEqual(out["status"], "success")
		self.assertFalse(self._row().waiting)

	def test_attempt_count_in_output(self):
		node = self._node(delay_seconds=60)
		self._go(node, [dict(FAIL)])
		self._wake()
		out = self._go(node, [{"status": "success", "output": {"ok": 1}}])
		self.assertEqual(out["output"], {"ok": 1, "attempts": 2})

	def test_attempt_count_added_to_a_tool_result(self):
		node = self._node(delay_seconds=60)
		self._go(node, [dict(FAIL)])
		self._wake()
		out = self._go(node, [{"status": "success", "result": {"ok": 1}}])
		self.assertEqual(out["result"], {"ok": 1, "attempts": 2})

	def test_exhausted_attempts_follow_on_error(self):
		node = self._node(attempts=2, delay_seconds=60)
		self._go(node, [dict(FAIL)])
		self._wake()
		out = self._go(node, [dict(FAIL)])
		self.assertNotIsInstance(out, flow_engine.Outcome)
		self.assertEqual(out["status"], "failed")  # the engine then takes the step's on_error route
		self.assertEqual(out["output"]["attempts"], 2)
		self.assertEqual(self._row().status, "Running")

	def test_retry_not_applied_to_non_matching_error(self):
		agent = {"id": "a1", "type": "agent.run", "config": {"retry": {"attempts": 3}}}
		self.assertIsNone(retry.policy_of(agent))
		self.assertEqual(self._go(agent, [dict(FAIL)])["status"], "failed")
		self.assertEqual(self._row().status, "Running")
		ok = self._go(self._node(), [{"status": "success", "output": {}}])
		self.assertEqual(ok["status"], "success")
		self.assertNotIn("attempts", ok["output"])  # first-try success is untouched

	def test_cancel_during_retry_wait(self):
		self._go(self._node(delay_seconds=60), [dict(FAIL)])
		self.assertTrue(park.cancel_run(self.run_doc.name, "Administrator"))
		self.assertEqual(self._row().status, "Cancelled")
		with patch("frappe.enqueue"):
			self.assertFalse(park.wake_run(self.run_doc.name, "elapsed"))

	def test_retry_in_foreach_rejected(self):
		node = self._node()
		with patch.object(flow_engine, "_flow_nodes_by_id", return_value={"t1": node}):
			with patch.object(flow_engine, "_context_of"):
				result = flow_engine._run_sub_chain(self.run_doc, {}, ["t1"])
		self.assertEqual(result["status"], "failed")
		self.assertIn("try again if it fails", result["error"])
