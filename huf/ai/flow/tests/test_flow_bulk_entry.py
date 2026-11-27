"""Bulk entry: chunked background jobs through ``start_flow_for_member``, idempotent on resubmission."""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow.runs import bulk_entry
from huf.ai.flow.tests.test_flow_draft_validation import finished_flow

MEMBERS = 1_200  # three chunks; the 10k / 100k scale runs are deferred to the pre-PR gate


class TestFlowBulkEntry(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		flow = frappe.get_doc(
			{
				"doctype": "Flow Definition",
				"flow_id": f"_test-bulk-{frappe.generate_hash(length=8)}",
				"flow_name": "Bulk Flow",
				"status": "Draft",
				"definition_json": "{}",
			}
		)
		flow.flags.ignore_validate = True
		flow.insert(ignore_permissions=True)
		self.flow_id = flow.name
		frappe.db.set_value(
			"Flow Definition",
			self.flow_id,
			{"definition_json": json.dumps(finished_flow()), "status": "Active"},
		)
		frappe.db.commit()
		self.jobs = []
		patcher = patch("frappe.enqueue", side_effect=self._enqueue)
		patcher.start()
		self.addCleanup(patcher.stop)
		check = patch("huf.ai.graph.validation.flow_validation.check_runnable")
		check.start()
		self.addCleanup(check.stop)

	def _enqueue(self, method, **kwargs):
		if method == "huf.ai.flow.runs.bulk_entry.run_chunk":
			self.jobs.append(kwargs)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.db.delete("Flow Member State", {"flow": self.flow_id})
		frappe.db.delete("Agent Flow Run", {"flow_id": self.flow_id})
		frappe.delete_doc("Flow Definition", self.flow_id, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _submit(self, keys, **kwargs):
		self.jobs = []
		result = bulk_entry.enter_members(self.flow_id, keys, **kwargs)
		for job in self.jobs:
			bulk_entry.run_chunk(job["flow_id"], job["member_keys"], job["entry_key"], job["batch_id"])
		return result

	def _runs(self):
		return frappe.db.count("Agent Flow Run", {"flow_id": self.flow_id})

	def test_bulk_entry_is_chunked_and_idempotent(self):
		keys = [f"m-{i:05d}" for i in range(MEMBERS)]
		result = self._submit(keys + keys[:10])  # repeats in one call count once
		self.assertEqual(result["total"], MEMBERS)
		self.assertEqual(result["chunks"], 3)
		self.assertEqual({len(j["member_keys"]) for j in self.jobs}, {500, 200})
		self.assertEqual(self._runs(), MEMBERS)
		rows = frappe.db.sql(
			"select member_key, count(*) from `tabAgent Flow Run` where flow_id=%s group by member_key having count(*) > 1",
			self.flow_id,
		)
		self.assertEqual(rows, ())
		progress = bulk_entry.progress(result["batch_id"])
		self.assertEqual((progress["done"], progress["started"], progress["failed"]), (MEMBERS, MEMBERS, 0))

		again = self._submit(list(reversed(keys)))
		self.assertEqual(again["batch_id"], result["batch_id"])
		self.assertEqual(self._runs(), MEMBERS)
		self.assertEqual(bulk_entry.progress(again["batch_id"])["skipped"], MEMBERS)

	def test_new_entry_key_lets_members_enter_again(self):
		keys = ["a-1", "a-2", "a-3"]
		self._submit(keys)
		self._submit(keys, entry_key="campaign-2")
		self._submit(keys, entry_key="campaign-2")
		self.assertEqual(self._runs(), 6)

	def test_needs_write_on_the_flow(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			bulk_entry.enter_members(self.flow_id, ["a-1"])

	def test_invalid_keys_raise(self):
		for bad in ([], [""], [" x"], ["x" * 500]):
			with self.assertRaises((ValueError, frappe.ValidationError)):
				bulk_entry.enter_members(self.flow_id, bad)
