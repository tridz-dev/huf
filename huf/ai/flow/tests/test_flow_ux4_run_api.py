# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""Run story fields on get_flow_run / list_flow_runs and cancelling a queued run (UX-4).

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_ux4_run_api
"""

import json

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from huf.ai.flow import api as flow_api
from huf.ai.flow.runs.actions import cancel_flow_run

DEFN = {
	"nodes": [
		{"id": "t", "type": "trigger.webhook", "_label": "Webhook"},
		{"id": "h", "type": "human.approval", "_label": "Wait for approval"},
		{"id": "end", "type": "output", "_label": "Rejected", "config": {"value": "rejected"}},
		{"id": "loop", "type": "foreach", "_label": "Each item", "config": {"body": ["x"]}},
	]
}


class TestFlowUx4RunApi(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._docs = []
		self.flow_id = f"_test-ux4-{frappe.generate_hash(length=8)}"
		flow = frappe.get_doc(
			{
				"doctype": "Flow Definition",
				"flow_id": self.flow_id,
				"flow_name": "UX4 Flow",
				"status": "Draft",
				"definition_json": json.dumps(DEFN),
			}
		)
		flow.flags.ignore_validate = True
		flow.insert(ignore_permissions=True)
		self._docs.append(("Flow Definition", flow.name))
		self.flow_doc = flow.name

	def tearDown(self):
		frappe.set_user("Administrator")
		for doctype, name in reversed(self._docs):
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _run(self, status="Success", ctx=None, current="end"):
		run = frappe.get_doc(
			{
				"doctype": "Flow Run",
				"flow_definition": self.flow_doc,
				"flow_id": self.flow_id,
				"status": status,
				"trigger_type": "Manual",
				"current_node_id": current,
				"context_json": json.dumps(ctx or {}),
				"started_at": add_to_date(now_datetime(), minutes=-3),
			}
		)
		run.insert(ignore_permissions=True)
		self._docs.append(("Flow Run", run.name))
		return run.name

	def test_detail_carries_the_story_fields(self):
		ctx = {"amount": 42, "__node_outputs__": {"h": {"decision": "rejected", "decided_by": "Administrator"}, "end": "rejected"}}
		detail = flow_api.get_flow_run(self._run(ctx=ctx))
		self.assertEqual(detail["outcome"], {"label": "Rejected", "tone": "bad"})
		self.assertEqual(detail["step_meta"]["loop"]["body"], ["x"])
		self.assertEqual(detail["step_meta"]["h"]["type"], "human.approval")
		self.assertEqual(detail["started_by"], "Administrator")
		self.assertTrue(detail["started_by_name"])
		self.assertEqual(detail["run_number"], 1)
		self.assertTrue(detail["modified_at"].endswith("Z"))

	def test_list_rows_carry_title_hint_and_outcome(self):
		ctx = {"amount": 150, "note": "walkthrough", "__node_outputs__": {"h": {"decision": "approved"}}}
		self._run(ctx=ctx)
		self._run(status="Failed", ctx={}, current="h")
		rows = [r for r in flow_api.list_flow_runs(flow_id=self.flow_id) if r["flow_id"] == self.flow_id]
		by_status = {r["status"]: r for r in rows}
		ok = by_status["Success"]
		self.assertEqual(ok["input_hint"], "amount 150, note walkthrough")
		self.assertEqual(ok["outcome"], {"label": "Approved", "tone": "good"})
		self.assertEqual({r["run_number"] for r in rows}, {1, 2})
		self.assertIsNone(by_status["Failed"]["outcome"])
		for r in rows:
			self.assertNotIn("context_json", r)
			self.assertNotIn("creation", r)

	def test_cancel_only_a_queued_run(self):
		queued = self._run(status="Queued", current="")
		res = cancel_flow_run(queued)
		self.assertEqual(res["status"], "Failed")
		self.assertIn("Cancelled by", frappe.db.get_value("Flow Run", queued, "last_error"))
		with self.assertRaises(frappe.ValidationError):
			cancel_flow_run(self._run(status="Success"))
