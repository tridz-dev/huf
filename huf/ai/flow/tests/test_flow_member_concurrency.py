"""Concurrent triggers for one member: one state row, one run."""

import json
import threading
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import triggers
from huf.ai.flow.runs import member
from huf.ai.flow.tests.test_flow_draft_validation import finished_flow

KEY = "Administrator"  # the member of a Manual run is the user who started it
WORKERS = 50


class TestFlowMemberConcurrency(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		flow = frappe.get_doc(
			{
				"doctype": "Flow Definition",
				"flow_id": f"_test-race-{frappe.generate_hash(length=8)}",
				"flow_name": "Race Flow",
				"status": "Draft",
				"definition_json": "{}",
			}
		)
		flow.flags.ignore_validate = True
		flow.insert(ignore_permissions=True)
		self.flow_id = flow.name

	def tearDown(self):
		frappe.db.rollback()
		frappe.db.delete("Flow Member State", {"flow": self.flow_id})
		frappe.db.delete("Agent Flow Run", {"flow_id": self.flow_id})
		frappe.delete_doc("Flow Definition", self.flow_id, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _set_policy(self, policy):
		defn = finished_flow()
		self.trigger = next(n for n in defn["nodes"] if n["type"].startswith("trigger."))
		self.trigger.setdefault("config", {})["entry_policy"] = policy
		frappe.db.set_value("Flow Definition", self.flow_id, "definition_json", json.dumps(defn))
		frappe.db.commit()

	def _race(self):
		site, sites_path = frappe.local.site, frappe.local.sites_path
		flow_id, node_id = self.flow_id, self.trigger["id"]
		barrier = threading.Barrier(WORKERS)
		started, errors = [], []

		def fire():
			try:
				frappe.init(site, sites_path=sites_path)
				frappe.connect()
				frappe.set_user("Administrator")
				barrier.wait(timeout=60)
				run = triggers.start_flow_run(flow_id, {"n": 2}, "Manual", node_id, enqueue=True)
				frappe.db.commit()
				started.append(run.name if run else None)
			except Exception as exc:  # reported by the assertion below
				errors.append(repr(exc))
			finally:
				frappe.destroy()

		with patch("frappe.enqueue"):
			threads = [threading.Thread(target=fire) for _ in range(WORKERS)]
			for thread in threads:
				thread.start()
			for thread in threads:
				thread.join(timeout=120)
		frappe.db.rollback()  # a fresh snapshot that sees the threads' commits
		self.assertEqual(errors, [])
		self.assertEqual(len(started), WORKERS)
		return [name for name in started if name]

	def _assert_one_entry(self, runs):
		self.assertEqual(len(runs), 1)
		self.assertEqual(frappe.db.count("Agent Flow Run", {"flow_id": self.flow_id}), 1)
		rows = frappe.get_all(
			"Flow Member State", filters={"flow": self.flow_id}, fields=["member_key", "run_count", "active_flow_run"]
		)
		self.assertEqual(rows, [{"member_key": KEY, "run_count": 1, "active_flow_run": runs[0]}])

	def test_one_active_per_member_starts_one_run(self):
		self._set_policy("one_active_per_member")
		self._assert_one_entry(self._race())

	def test_one_active_per_member_re_entry_after_a_finished_run(self):
		self._set_policy("one_active_per_member")
		old = frappe.get_doc(
			{
				"doctype": "Agent Flow Run",
				"flow_definition": self.flow_id,
				"flow_id": self.flow_id,
				"status": "Success",
				"member_key": KEY,
			}
		).insert(ignore_permissions=True)
		member.upsert_member(self.flow_id, KEY, old.name)
		frappe.db.commit()
		runs = self._race()
		self.assertEqual(len(runs), 1)
		self.assertEqual(frappe.db.count("Agent Flow Run", {"flow_id": self.flow_id}), 2)
		self.assertEqual(member.get_member(self.flow_id, KEY).run_count, 2)

	def test_once_per_member_starts_one_run(self):
		self._set_policy("once_per_member")
		self._assert_one_entry(self._race())

	def test_new_run_each_time_keeps_one_state_row(self):
		self._set_policy("new_run_each_time")
		self.assertEqual(len(self._race()), WORKERS)
		self.assertEqual(frappe.db.count("Flow Member State", {"flow": self.flow_id}), 1)
		self.assertEqual(member.get_member(self.flow_id, KEY).run_count, WORKERS)

	def test_unused_claim_expires(self):
		self.assertTrue(member.claim_active_entry(self.flow_id, KEY))
		self.assertFalse(member.claim_active_entry(self.flow_id, KEY))
		frappe.db.set_value(
			"Flow Member State", member.member_name(self.flow_id, KEY), "last_event_at", "2000-01-01 00:00:00"
		)
		self.assertTrue(member.claim_active_entry(self.flow_id, KEY))
