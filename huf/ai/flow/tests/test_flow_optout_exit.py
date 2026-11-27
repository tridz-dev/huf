"""A STOP (``huf_gateway_opt_out`` kind=opt_out) cancels the member's parked runs in every flow and exits them."""

import json
from datetime import datetime, timedelta

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow.runs import member, park
from huf.ai.whatsapp.gateway_hooks import fire_hook

KEY = "15550100777"
OTHER = "15550100888"


class TestFlowOptOutExit(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.flows = [self._flow() for _ in range(2)]

	def tearDown(self):
		frappe.set_user("Administrator")
		for flow in self.flows:
			frappe.db.delete("Agent Flow Run", {"flow_id": flow})
			frappe.db.delete("Flow Member State", {"flow": flow})
			frappe.db.delete("Flow Definition", {"name": flow})

	def _flow(self) -> str:
		doc = frappe.get_doc(
			{
				"doctype": "Flow Definition",
				"flow_id": f"_test-optout-{frappe.generate_hash(length=8)}",
				"flow_name": "Opt-out Flow",
				"status": "Draft",
				"definition_json": json.dumps({"nodes": [{"id": "w1", "type": "wait"}]}),
			}
		)
		doc.flags.ignore_validate = True
		doc.insert(ignore_permissions=True)
		return doc.name

	def _parked(self, flow: str, key: str) -> str:
		run = frappe.get_doc(
			{
				"doctype": "Agent Flow Run",
				"flow_id": flow,
				"flow_definition": flow,
				"status": park.WAIT_STATUS,
				"member_key": key,
				"resume_at": datetime.now() - timedelta(minutes=1),
				"waiting": json.dumps({"node_id": "w1"}),
			}
		).insert(ignore_permissions=True)
		member.upsert_member(flow, key, run.name)
		member.set_status(flow, key, "Waiting", "w1")
		return run.name

	def _status(self, run: str) -> str:
		return frappe.db.get_value("Agent Flow Run", run, "status")

	def test_stop_cancels_parked_runs_in_all_flows_and_exits_member(self):
		runs = [self._parked(flow, KEY) for flow in self.flows]
		cancelled = member.exit_on_opt_out(
			gateway="GW", sender_id="+1 555-0100777", kind="opt_out", keyword="stop"
		)
		self.assertEqual(sorted(cancelled), sorted(runs))
		for flow, run in zip(self.flows, runs, strict=True):
			self.assertEqual(self._status(run), "Cancelled")
			row = member.get_member(flow, KEY)
			self.assertEqual(row.status, "Exited")
			self.assertIsNone(row.active_flow_run)
			self.assertIsNone(row.current_node_id)
			self.assertIn(member.OPT_OUT_REASON, frappe.db.get_value("Agent Flow Run", run, "last_error"))

	def test_later_wake_is_noop(self):
		run = self._parked(self.flows[0], KEY)
		member.exit_on_opt_out(sender_id=KEY, kind="opt_out")
		self.assertFalse(park.wake_run(run, "timer", enqueue=False))
		self.assertEqual(self._status(run), "Cancelled")

	def test_other_members_unaffected(self):
		mine = self._parked(self.flows[0], KEY)
		theirs = self._parked(self.flows[0], OTHER)
		member.exit_on_opt_out(sender_id=KEY, kind="opt_out")
		self.assertEqual(self._status(mine), "Cancelled")
		self.assertEqual(self._status(theirs), park.WAIT_STATUS)
		self.assertEqual(member.get_member(self.flows[0], OTHER).status, "Waiting")

	def test_opt_in_and_blank_sender_do_nothing(self):
		run = self._parked(self.flows[0], KEY)
		self.assertEqual(member.exit_on_opt_out(sender_id=KEY, kind="opt_in"), [])
		self.assertEqual(member.exit_on_opt_out(sender_id="", kind="opt_out"), [])
		self.assertEqual(self._status(run), park.WAIT_STATUS)

	def test_registered_on_existing_opt_out_hook(self):
		self.assertIn("huf.ai.flow.runs.member.exit_on_opt_out", frappe.get_hooks("huf_gateway_opt_out"))
		run = self._parked(self.flows[0], KEY)
		fire_hook("huf_gateway_opt_out", gateway="GW", sender_id=KEY, kind="opt_out", keyword="stop")
		self.assertEqual(self._status(run), "Cancelled")

	def test_opt_out_is_registered_reason_code(self):
		from huf.ai.flow.support import reason_codes

		self.assertEqual(reason_codes.normalize(member.OPT_OUT_REASON), "opt_out")
