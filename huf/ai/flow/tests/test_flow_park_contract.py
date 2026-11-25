"""Park / resume contract (flow/park.py): park, wake, cancel, re-entry, token hashing."""

import json
from datetime import datetime
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import engine as flow_engine, park
from huf.ai.flow.park import ParkRequest

NODE = {"id": "w1", "type": "wait"}


def _make_flow():
	flow_id = f"_test-park-{frappe.generate_hash(length=8)}"
	flow = frappe.get_doc(
		{
			"doctype": "Flow Definition",
			"flow_id": flow_id,
			"flow_name": "Park Contract Flow",
			"status": "Draft",
			"definition_json": json.dumps({"nodes": [{"id": "w1", "type": "wait"}]}),
		}
	)
	flow.flags.ignore_validate = True
	flow.insert(ignore_permissions=True)
	return flow


class TestParkContract(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.flow = _make_flow()
		self.run_doc = frappe.get_doc(
			{
				"doctype": "Flow Run",
				"flow_definition": self.flow.name,
				"flow_id": self.flow.flow_id,
				"status": "Running",
				"trigger_type": "Manual",
			}
		).insert(ignore_permissions=True)
		self.when = datetime(2030, 1, 1, 9, 0, 0)

	def tearDown(self):
		frappe.delete_doc("Flow Run", self.run_doc.name, ignore_permissions=True, force=True)
		frappe.delete_doc("Flow Definition", self.flow.name, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _park(self, **kw):
		return park.park_run(self.run_doc, NODE, ParkRequest(reason="wait", resume_at=self.when, **kw))

	def _row(self):
		return frappe.db.get_value("Flow Run", self.run_doc.name, ["status", "resume_at", "waiting"], as_dict=True)

	def test_park_sets_waiting_timer_and_resume_at(self):
		outcome = self._park()
		row = self._row()
		self.assertEqual(row.status, "Waiting Timer")
		self.assertEqual(row.resume_at, self.when)
		self.assertTrue(outcome.is_paused)
		self.assertEqual(outcome.pause.status_label, "Waiting Timer")
		self.assertEqual(json.loads(row.waiting)["node_id"], "w1")

	def test_park_refused_on_terminal(self):
		flow_engine._complete_flow_run(self.run_doc)
		self._park()
		self.assertEqual(self._row().status, "Success")

	def test_wake_only_one_winner(self):
		self._park()
		self.assertTrue(self._wake())
		self.assertFalse(self._wake())

	def _wake(self):
		with patch("frappe.enqueue") as enq:
			ok = park.wake_run(self.run_doc.name, "timer")
			if ok:
				enq.assert_called_once()
				self.assertEqual(enq.call_args.kwargs["queue"], "short")
		return ok

	def test_cancel_then_wake_noops(self):
		self._park()
		self.assertTrue(park.cancel_run(self.run_doc.name, "Administrator"))
		row = self._row()
		self.assertEqual(row.status, "Cancelled")
		self.assertFalse(self._wake())
		self.assertEqual(self._row().status, "Cancelled")
		self.assertIn("Cancelled by Administrator", frappe.db.get_value("Flow Run", self.run_doc.name, "last_error"))

	def test_token_never_stored(self):
		park.park_run(self.run_doc, NODE, ParkRequest(reason="wait", resume_at=None, token=True))
		self.run_doc.reload()
		raw = park.resume_token(self.run_doc)
		self.assertTrue(raw)
		self.assertNotIn(raw, self._row().waiting)
		self.assertTrue(park.verify_token(self.run_doc, raw))
		self.assertFalse(park.verify_token(self.run_doc, "nope"))

	def test_repark_voids_old_token(self):
		park.park_run(self.run_doc, NODE, ParkRequest(reason="wait", resume_at=None, token=True))
		self.run_doc.reload()
		old = park.resume_token(self.run_doc)
		self._wake()
		self.run_doc.reload()
		park.park_run(self.run_doc, NODE, ParkRequest(reason="wait", resume_at=None, token=True))
		self.run_doc.reload()
		self.assertFalse(park.verify_token(self.run_doc, old))

	def test_is_reentry_matches_node_only(self):
		self._park()
		self._wake()
		self.run_doc.reload()
		self.assertEqual(self.run_doc.status, "Running")
		self.assertIsNotNone(park.is_reentry(self.run_doc, NODE))
		self.assertIsNone(park.is_reentry(self.run_doc, {"id": "other"}))

	def test_is_reentry_false_while_waiting(self):
		self._park()
		self.run_doc.reload()
		self.assertIsNone(park.is_reentry(self.run_doc, NODE))

	def test_wake_lock_held_returns_false(self):
		self._park()
		with patch.object(flow_engine, "_acquire_run_lock", return_value=False):
			self.assertFalse(park.wake_run(self.run_doc.name, "timer"))
		self.assertEqual(self._row().status, "Waiting Timer")
