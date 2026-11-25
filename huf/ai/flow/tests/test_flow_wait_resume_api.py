"""Token resume endpoint and continue-now for runs parked on a wait step."""

import json
from datetime import datetime
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow.runs import resume_api as flow_api
from huf.ai.flow.runs import park
from huf.ai.flow.runs.park import ParkRequest
from huf.ai.flow.runs import actions
from huf.testing.factories import make_user


class TestWaitResumeApi(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._docs = []
		flow = frappe.get_doc(
			{
				"doctype": "Flow Definition",
				"flow_id": f"_test-resume-{frappe.generate_hash(length=8)}",
				"flow_name": "Resume Flow",
				"status": "Draft",
				"definition_json": json.dumps({"nodes": [{"id": "w1", "type": "wait"}]}),
			}
		)
		flow.flags.ignore_validate = True
		flow.insert(ignore_permissions=True)
		self._docs.append(("Flow Definition", flow.name))
		self.run = frappe.get_doc(
			{
				"doctype": "Flow Run",
				"flow_definition": flow.name,
				"flow_id": flow.flow_id,
				"status": "Running",
				"trigger_type": "Manual",
			}
		).insert(ignore_permissions=True)
		self._docs.append(("Flow Run", self.run.name))
		park.park_run(self.run, {"id": "w1", "type": "wait"}, ParkRequest(reason="wait", resume_at=None, token=True))
		self.token = park.resume_token(self.run)

	def tearDown(self):
		frappe.set_user("Administrator")
		for doctype, name in reversed(self._docs):
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _status(self):
		return frappe.db.get_value("Flow Run", self.run.name, "status")

	def _resume(self, **kw):
		with patch("frappe.enqueue") as enq:
			out = flow_api.resume_waiting_run(self.run.name, **kw)
		return out, enq

	def test_right_token_resumes_and_enqueues_short(self):
		out, enq = self._resume(token=self.token, payload={"answer": "yes"})
		self.assertEqual(out["status"], "resumed")
		self.assertEqual(self._status(), "Running")
		self.assertEqual(enq.call_args.kwargs["queue"], "short")
		woke = json.loads(frappe.db.get_value("Flow Run", self.run.name, "waiting"))["woke"]
		self.assertEqual((woke["reason"], woke["payload"]), ("resumed", {"answer": "yes"}))

	def test_wrong_token_refused(self):
		with self.assertRaises(frappe.PermissionError):
			self._resume(token="not-the-token")
		self.assertEqual(self._status(), "Waiting Timer")

	def test_token_single_use(self):
		self._resume(token=self.token)
		with self.assertRaises(frappe.PermissionError):
			self._resume(token=self.token)

	def test_payload_cap(self):
		with self.assertRaises(frappe.ValidationError):
			self._resume(token=self.token, payload={"blob": "x" * (park.MAX_PAYLOAD_BYTES + 1)})
		self.assertEqual(self._status(), "Waiting Timer")

	def test_guest_without_token_refused(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			flow_api.resume_waiting_run(self.run.name)
		with self.assertRaises(frappe.PermissionError):
			flow_api.resume_waiting_run("no-such-run", token="x")
		frappe.set_user("Administrator")
		self.assertEqual(self._status(), "Waiting Timer")

	def test_guest_with_token_resumes(self):
		frappe.set_user("Guest")
		self._resume(token=self.token)
		frappe.set_user("Administrator")
		self.assertEqual(self._status(), "Running")

	def test_rate_limited(self):
		self.assertTrue(hasattr(flow_api.resume_waiting_run, "__wrapped__"), "rate_limit wrapper missing")
		self.assertEqual((flow_api.RESUME_RATE_LIMIT, flow_api.RESUME_RATE_WINDOW_SECONDS), (20, 60))

	def test_continue_now_requires_write(self):
		user = make_user(roles=("Huf User",))
		self._docs.append(("User", user.name))
		frappe.set_user(user.name)
		with self.assertRaises(frappe.PermissionError):
			actions.continue_waiting_run(self.run.name)
		frappe.set_user("Administrator")
		self.assertEqual(self._status(), "Waiting Timer")
		with patch("frappe.enqueue") as enq:
			out = actions.continue_waiting_run(self.run.name)
		self.assertEqual(out["status"], "Running")
		self.assertEqual(enq.call_args.kwargs["queue"], "short")
		with self.assertRaises(frappe.ValidationError):
			actions.continue_waiting_run(self.run.name)

	def test_resume_link_for_editors_works_once(self):
		link = actions.get_resume_link(self.run.name)
		self.assertIn(self.token, link["url"])
		self.assertIn("resume_waiting_run", link["url"])
		out, _ = self._resume(token=self.token)
		self.assertEqual(out, {"status": "resumed"})
		with self.assertRaises(frappe.ValidationError):
			actions.get_resume_link(self.run.name)

	def test_resume_link_requires_write(self):
		user = make_user(roles=("Huf User",))
		self._docs.append(("User", user.name))
		frappe.set_user(user.name)
		with self.assertRaises(frappe.PermissionError):
			actions.get_resume_link(self.run.name)

	def test_refusal_copy(self):
		with self.assertRaises(frappe.PermissionError) as cm:
			self._resume(token="wrong")
		self.assertIn("already been used or is not valid", str(cm.exception))
