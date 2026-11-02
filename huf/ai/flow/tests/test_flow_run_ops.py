# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""Flow Run listing / stale-run API: UTC times, flow-step labels, "Mark as failed".

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_run_ops
"""

import json

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from huf.ai.flow import api as flow_api
from huf.testing.factories import make_user


class TestFlowRunOps(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._docs = []
		self.flow_id = f"_test-run-ops-{frappe.generate_hash(length=8)}"
		flow = frappe.get_doc(
			{
				"doctype": "Flow Definition",
				"flow_id": self.flow_id,
				"flow_name": "Run Ops Flow",
				"status": "Draft",
				"definition_json": json.dumps(
					{"nodes": [{"id": "n1", "type": "tool.call", "_label": "Send the email"}]}
				),
			}
		)
		flow.flags.ignore_validate = True
		flow.insert(ignore_permissions=True)
		self.flow_name_doc = flow.name
		self._docs.append(("Flow Definition", flow.name))

	def tearDown(self):
		frappe.set_user("Administrator")
		for doctype, name in reversed(self._docs):
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _run(self, status="Running", minutes_ago=0):
		run = frappe.get_doc(
			{
				"doctype": "Flow Run",
				"flow_definition": self.flow_name_doc,
				"flow_id": self.flow_id,
				"status": status,
				"trigger_type": "Manual",
				"started_at": add_to_date(now_datetime(), minutes=-minutes_ago),
			}
		)
		run.insert(ignore_permissions=True)
		self._docs.append(("Flow Run", run.name))
		stamp = add_to_date(now_datetime(), minutes=-minutes_ago)
		frappe.db.set_value("Flow Run", run.name, "modified", stamp, update_modified=False)
		return run.name

	def test_utc_iso_converts_site_time_to_utc(self):
		from zoneinfo import ZoneInfo

		from frappe.utils import get_system_timezone

		naive = "2026-10-28 12:00:00.123456"
		expected_offset = ZoneInfo(get_system_timezone()).utcoffset(__import__("datetime").datetime(2026, 10, 28, 12))
		out = flow_api._utc_iso(naive)
		self.assertTrue(out.endswith("Z"))
		self.assertNotIn(".", out)
		from datetime import datetime

		self.assertEqual(
			datetime.strptime(out, "%Y-%m-%dT%H:%M:%SZ"),
			datetime(2026, 10, 28, 12) - expected_offset,
		)
		self.assertIsNone(flow_api._utc_iso(None))

	def test_list_page_carries_flow_name_and_utc_times(self):
		name = self._run(status="Success")
		res = flow_api.list_flow_runs_page(search="Run Ops Flow")
		row = next(r for r in res["items"] if r["name"] == name)
		self.assertEqual(row["flow_name"], "Run Ops Flow")
		self.assertTrue(row["started_at"].endswith("Z"))
		self.assertGreaterEqual(res["total"], 1)

	def test_step_label(self):
		name = self._run()
		out = flow_api.get_flow_step_labels([{"flow_run": name, "flow_node_id": "n1"}, {"flow_run": "nope"}])
		self.assertEqual(out, ["Flow: Run Ops Flow > Send the email", None])

	def test_untitled_step_gets_its_type_title_not_its_id(self):
		frappe.db.set_value(
			"Flow Definition",
			self.flow_name_doc,
			"definition_json",
			json.dumps({"nodes": [{"id": "n7", "type": "router.llm"}, {"id": "zz", "type": "mystery"}]}),
		)
		labels = flow_api._node_labels(self.flow_name_doc)
		self.assertEqual(labels["n7"], "LLM Router")
		self.assertEqual(labels["zz"], "zz")

	def test_mark_failed_requires_stale_run(self):
		fresh = self._run(status="Running", minutes_ago=1)
		with self.assertRaises(frappe.ValidationError):
			flow_api.mark_flow_run_failed(fresh)
		self.assertEqual(frappe.db.get_value("Flow Run", fresh, "status"), "Running")

		done = self._run(status="Success", minutes_ago=60)
		with self.assertRaises(frappe.ValidationError):
			flow_api.mark_flow_run_failed(done)

	def test_mark_failed_transitions_stale_run(self):
		stuck = self._run(status="Running", minutes_ago=60)
		detail = flow_api.get_flow_run(stuck)
		self.assertTrue(detail["stale"])
		self.assertTrue(detail["can_mark_failed"])

		res = flow_api.mark_flow_run_failed(stuck)
		self.assertEqual(res["status"], "Failed")
		doc = frappe.get_doc("Flow Run", stuck)
		self.assertIn("Marked as failed", doc.last_error)
		self.assertIsNotNone(doc.completed_at)

	def test_mark_failed_denied_for_non_system_manager(self):
		stuck = self._run(status="Queued", minutes_ago=60)
		user = make_user(roles=("Huf Manager",))
		self._docs.append(("User", user.name))
		frappe.set_user(user.name)
		self.assertFalse(flow_api.get_flow_run(stuck)["can_mark_failed"])
		with self.assertRaises(frappe.PermissionError):
			flow_api.mark_flow_run_failed(stuck)
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Flow Run", stuck, "status"), "Queued")
