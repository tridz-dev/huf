# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""FIX-trace-view-masking: run input and step outputs are masked when read, never when stored (G4).

bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_trace_view_masking
"""

import json

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import api as flow_api
from huf.ai.flow.support.pii import DROPPED, mask_for_view
from huf.ai.flow.tests.test_flow_ux4_run_api import TestFlowUx4RunApi

PHONE = "919876543210"
EMAIL = "asha.rao@example.com"


class TestMaskForView(IntegrationTestCase):
	def test_empty_values_pass_through(self):
		for value in (None, "", {}, []):
			self.assertEqual(mask_for_view(value), value)

	def test_unmaskable_value_keeps_its_shape(self):
		from unittest import mock

		with mock.patch("huf.ai.flow.support.pii.mask_value", return_value=None):
			self.assertEqual(mask_for_view({"phone": PHONE}), {})
			self.assertEqual(mask_for_view([PHONE]), [])
			self.assertEqual(mask_for_view(PHONE), DROPPED)


class TestTraceViewMasking(TestFlowUx4RunApi):
	def test_detail_masks_input_and_step_outputs_but_not_the_stored_run(self):
		ctx = {
			"phone": PHONE,
			"amount": 42,
			"__node_outputs__": {"h": {"email": EMAIL, "decision": "rejected"}, "end": "rejected"},
		}
		name = self._run(ctx=ctx)
		detail = flow_api.get_flow_run(name)
		text = json.dumps(detail["context_json"])
		self.assertNotIn(PHONE, text)
		self.assertNotIn(EMAIL, text)
		self.assertEqual(detail["context_json"]["amount"], 42)
		self.assertEqual(detail["context_json"]["__node_outputs__"]["h"]["decision"], "rejected")
		self.assertEqual(detail["outcome"], {"label": "Rejected", "tone": "bad"})
		stored = json.loads(frappe.db.get_value("Agent Flow Run", name, "context_json"))
		self.assertEqual(stored, ctx)

	def test_list_hint_masks_input(self):
		self._run(ctx={"phone": PHONE, "amount": 7})
		rows = flow_api.list_flow_runs(flow_id=self.flow_id)
		self.assertTrue(rows)
		self.assertNotIn(PHONE, rows[0]["input_hint"])


class TestWaitingViewMasking(TestFlowUx4RunApi):
	def test_detail_masks_waiting_but_keeps_approver_ids(self):
		waiting = {
			"type": "approval",
			"node_id": "h",
			"message": f"Call {PHONE}",
			"context": {"email": EMAIL, "amount": 5},
			"approver_type": "user",
			"approver_users": [EMAIL],
		}
		name = self._run(status="Waiting Approval", ctx={"amount": 5}, current="h")
		frappe.db.set_value("Agent Flow Run", name, "waiting", json.dumps(waiting))
		detail = flow_api.get_flow_run(name)
		shown = detail["waiting"]
		self.assertNotIn(PHONE, json.dumps(shown))
		self.assertNotIn(EMAIL, json.dumps({k: v for k, v in shown.items() if k != "approver_users"}))
		self.assertEqual(shown["approver_users"], [EMAIL])
		self.assertEqual(shown["approver_type"], "user")
		self.assertEqual(shown["node_id"], "h")
		self.assertEqual(json.loads(frappe.db.get_value("Agent Flow Run", name, "waiting")), waiting)
