"""Gateway-triggered runs: parking sends nothing; cancelling reports the event once."""

import json
from datetime import datetime
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import park
from huf.ai.flow.park import ParkRequest


class TestWaitGateway(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.flow = frappe.get_doc(
			{
				"doctype": "Flow Definition",
				"flow_id": f"_test-wgw-{frappe.generate_hash(length=8)}",
				"flow_name": "Wait Gateway Flow",
				"status": "Draft",
				"definition_json": json.dumps({"nodes": [{"id": "w1", "type": "wait"}]}),
			}
		)
		self.flow.flags.ignore_validate = True
		self.flow.insert(ignore_permissions=True)
		self.run = frappe.get_doc(
			{
				"doctype": "Flow Run",
				"flow_definition": self.flow.name,
				"flow_id": self.flow.flow_id,
				"status": "Running",
				"trigger_type": "Gateway",
			}
		).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.delete_doc("Flow Run", self.run.name, ignore_permissions=True, force=True)
		frappe.delete_doc("Flow Definition", self.flow.name, ignore_permissions=True, force=True)
		frappe.db.commit()

	def test_waiting_timer_sends_no_reply(self):
		with patch("huf.ai.gateway_service.finish_flow_event") as finish:
			park.park_run(
				self.run, {"id": "w1", "type": "wait"}, ParkRequest(reason="wait", resume_at=datetime(2030, 1, 1))
			)
		finish.assert_not_called()

	def test_cancel_syncs_gateway_event_once(self):
		park.park_run(self.run, {"id": "w1", "type": "wait"}, ParkRequest(reason="wait", resume_at=datetime(2030, 1, 1)))
		with patch("huf.ai.gateway_service.finish_flow_event") as finish:
			self.assertTrue(park.cancel_run(self.run.name, "Administrator"))
			self.assertFalse(park.cancel_run(self.run.name, "Administrator"))
		finish.assert_called_once()
		args = finish.call_args
		self.assertEqual(args.args[:2], (self.run.name, "Cancelled"))
