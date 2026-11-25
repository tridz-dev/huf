"""Cancel API: queued and every waiting status become Cancelled; running runs are refused."""

import json

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow.runs import park
from huf.ai.flow.runs import actions
from huf.testing.factories import make_user


class TestFlowCancel(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._docs = []
		flow = frappe.get_doc(
			{
				"doctype": "Flow Definition",
				"flow_id": f"_test-cancel-{frappe.generate_hash(length=8)}",
				"flow_name": "Cancel Flow",
				"status": "Draft",
				"definition_json": json.dumps({"nodes": [{"id": "n1", "type": "output", "config": {}}]}),
			}
		)
		flow.flags.ignore_validate = True
		flow.insert(ignore_permissions=True)
		self.flow = flow
		self._docs.append(("Flow Definition", flow.name))

	def tearDown(self):
		frappe.set_user("Administrator")
		for doctype, name in reversed(self._docs):
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _run(self, status):
		run = frappe.get_doc(
			{
				"doctype": "Flow Run",
				"flow_definition": self.flow.name,
				"flow_id": self.flow.flow_id,
				"status": status,
				"trigger_type": "Manual",
			}
		).insert(ignore_permissions=True)
		self._docs.append(("Flow Run", run.name))
		return run.name

	def _row(self, name):
		return frappe.db.get_value("Flow Run", name, ["status", "last_error", "completed_at"], as_dict=True)

	def test_cancel_waiting_timer_approval_code_user_sets_cancelled(self):
		for status in ("Waiting Timer", "Waiting Approval", "Waiting Code", "Waiting User"):
			name = self._run(status)
			out = actions.cancel_flow_run(name)
			row = self._row(name)
			self.assertEqual(out["status"], "Cancelled", status)
			self.assertEqual(row.status, "Cancelled", status)
			self.assertEqual(row.last_error, "Cancelled by Administrator.")
			self.assertTrue(row.completed_at)

	def test_cancel_queued_still_works(self):
		name = self._run("Queued")
		self.assertEqual(actions.cancel_flow_run(name)["status"], "Cancelled")

	def test_wake_after_cancel_noops(self):
		name = self._run("Waiting Timer")
		actions.cancel_flow_run(name)
		self.assertFalse(park.wake_run(name, "elapsed"))
		self.assertEqual(self._row(name).status, "Cancelled")

	def test_cancel_running_refused_with_message(self):
		name = self._run("Running")
		with self.assertRaises(frappe.ValidationError) as ctx:
			actions.cancel_flow_run(name)
		self.assertIn("working right now", str(ctx.exception))
		self.assertEqual(self._row(name).status, "Running")

	def test_cancel_finished_refused(self):
		with self.assertRaises(frappe.ValidationError):
			actions.cancel_flow_run(self._run("Success"))

	def test_cancel_requires_access(self):
		name = self._run("Waiting Timer")
		user = make_user(roles=("Huf User",))
		self._docs.append(("User", user.name))
		frappe.set_user(user.name)
		with self.assertRaises(frappe.PermissionError):
			actions.cancel_flow_run(name)
		frappe.set_user("Administrator")
		self.assertEqual(self._row(name).status, "Waiting Timer")
