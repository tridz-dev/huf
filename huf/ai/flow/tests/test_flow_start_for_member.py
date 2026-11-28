"""``start_flow_for_member``: one run per (flow, member, entry key)."""

import json
import threading
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import engine
from huf.ai.flow.runs.start import ENTRY_MARKER, start_flow_for_member
from huf.ai.flow.tests.test_flow_draft_validation import finished_flow

KEY = "mbr-0001"
WORKERS = 20


class TestFlowStartForMember(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		flow = frappe.get_doc(
			{
				"doctype": "Flow Definition",
				"flow_id": f"_test-start-{frappe.generate_hash(length=8)}",
				"flow_name": "Start Flow",
				"status": "Draft",
				"definition_json": "{}",
			}
		)
		flow.flags.ignore_validate = True
		flow.insert(ignore_permissions=True)
		self.flow_id = flow.name
		defn = finished_flow()
		self.trigger = next(n for n in defn["nodes"] if n["type"].startswith("trigger."))
		frappe.db.set_value(
			"Flow Definition", self.flow_id, {"definition_json": json.dumps(defn), "status": "Active"}
		)
		frappe.db.commit()
		for target in ("frappe.enqueue", "huf.ai.graph.validation.flow_validation.check_runnable"):
			patcher = patch(target)
			patcher.start()
			self.addCleanup(patcher.stop)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.db.delete("Flow Member State", {"flow": self.flow_id})
		frappe.db.delete("Agent Flow Run", {"flow_id": self.flow_id})
		frappe.delete_doc("Flow Definition", self.flow_id, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _start(self, key=KEY, **kwargs):
		return start_flow_for_member(self.flow_id, key, {"n": 2}, **kwargs)

	def _runs(self):
		return frappe.db.count("Agent Flow Run", {"flow_id": self.flow_id})

	def test_same_entry_twice_starts_one_run(self):
		self.assertTrue(self._start())
		self.assertIsNone(self._start())
		self.assertIsNone(self._start(entry_key=KEY))
		self.assertTrue(self._start(entry_key="order-2"))
		self.assertEqual(self._runs(), 2)

	def test_run_holds_only_the_member_key(self):
		run = frappe.get_doc("Agent Flow Run", self._start())
		self.assertEqual(run.member_key, KEY)
		self.assertEqual(run.current_node_id, self.trigger["id"])
		context = json.loads(run.context_json)
		self.assertEqual(set(context), {"n", ENTRY_MARKER})
		rows = frappe.get_all("Flow Member State", {"flow": self.flow_id}, ["member_key", "run_count"])
		self.assertEqual(rows, [{"member_key": KEY, "run_count": 1}])

	def test_key_differing_in_case_is_the_same_member(self):
		self.assertTrue(self._start())
		self.assertIsNone(self._start(KEY.upper()))
		run = self._start(KEY.upper(), entry_key="order-2")
		self.assertEqual(frappe.db.get_value("Agent Flow Run", run, "member_key"), KEY)
		self.assertEqual(frappe.db.count("Flow Member State", {"flow": self.flow_id}), 1)

	def test_paused_flow_starts_nothing(self):
		frappe.db.set_value("Flow Definition", self.flow_id, "status", "Paused")
		self.assertIsNone(self._start())
		self.assertEqual(self._runs(), 0)

	def test_invalid_arguments_raise(self):
		for key in ("", " x", "x" * 141):
			self.assertRaises(ValueError, self._start, key)
		self.assertRaises(ValueError, self._start, trigger_node_id="cond")
		self.assertRaises(ValueError, self._start, run_as="Guest")

	def test_inline_run_restores_the_session(self):
		frappe.set_user("Guest")
		seen = []
		with patch.object(engine, "run_flow", lambda name: seen.append(frappe.session.user)):
			self.assertTrue(self._start(run_as="Administrator", enqueue=False))
		self.assertEqual(seen, ["Administrator"])
		self.assertEqual(frappe.session.user, "Guest")

	def test_parallel_calls_start_one_run(self):
		site, sites_path = frappe.local.site, frappe.local.sites_path
		barrier = threading.Barrier(WORKERS)
		results, errors = [], []

		def fire(index):
			try:
				frappe.init(site, sites_path=sites_path)
				frappe.connect()
				frappe.set_user("Administrator")
				barrier.wait(timeout=60)
				results.append(self._start(KEY if index % 2 else KEY.upper()))
				frappe.db.commit()
			except Exception as exc:  # noqa: BLE001 - reported by the assertion below
				errors.append(repr(exc))
			finally:
				frappe.destroy()

		threads = [threading.Thread(target=fire, args=(i,)) for i in range(WORKERS)]
		for thread in threads:
			thread.start()
		for thread in threads:
			thread.join(timeout=120)
		frappe.db.rollback()  # a fresh snapshot that sees the threads' commits
		self.assertEqual(errors, [])
		self.assertEqual(len(results), WORKERS)
		self.assertEqual(len([r for r in results if r]), 1)
		self.assertEqual(self._runs(), 1)
		self.assertEqual(frappe.db.count("Flow Member State", {"flow": self.flow_id}), 1)
