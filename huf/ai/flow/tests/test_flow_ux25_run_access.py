# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""Security round 2 (DECISIONS 13): actions on a run are checked on THAT run and THAT run's flow, not on the role alone.

Two flows, one editor who is restricted (User Permission) to flow A. Everything on flow B's runs must be refused for
them; everything on flow A's runs works.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_ux25_run_access
"""

import json

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from huf.ai.flow import api as flow_api
from huf.ai.flow import run_identity_api
from huf.ai.flow.runs import actions
from huf.testing.factories import make_user


class TestRunAccess(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._docs = []
		self.a = self._flow("A")
		self.b = self._flow("B")
		self.run_a = self._run(self.a)
		self.run_b = self._run(self.b)
		self.editor = self._user("Huf Manager")
		self._restrict(self.editor, self.a)

	def tearDown(self):
		frappe.set_user("Administrator")
		for doctype, name in reversed(self._docs):
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _flow(self, label):
		flow_id = f"_test-ux25-{label.lower()}-{frappe.generate_hash(length=6)}"
		doc = frappe.get_doc({"doctype": "Flow Definition", "flow_id": flow_id, "flow_name": f"UX25 {label}", "status": "Draft", "definition_json": json.dumps({"nodes": [{"id": "n1", "type": "output", "config": {}}]})})
		doc.flags.ignore_validate = True
		doc.insert(ignore_permissions=True)
		self._docs.append(("Flow Definition", doc.name))
		return doc.name

	def _run(self, flow_name, status="Queued"):
		run = frappe.get_doc({"doctype": "Flow Run", "flow_definition": flow_name, "flow_id": flow_name, "status": status, "trigger_type": "Manual", "started_at": now_datetime()})
		run.insert(ignore_permissions=True)
		self._docs.append(("Flow Run", run.name))
		return run.name

	def _user(self, *roles):
		user = make_user(roles=roles)
		self._docs.append(("User", user.name))
		return user.name

	def _restrict(self, user, flow_name):
		perm = frappe.get_doc({"doctype": "User Permission", "user": user, "allow": "Flow Definition", "for_value": flow_name, "apply_to_all_doctypes": 1})
		perm.insert(ignore_permissions=True)
		self._docs.append(("User Permission", perm.name))
		frappe.clear_cache(user=user)

	# --- cancel -------------------------------------------------------------------------------------------------

	def test_cancel_works_on_a_run_of_a_flow_the_editor_may_edit(self):
		frappe.set_user(self.editor)
		out = actions.cancel_flow_run(self.run_a)
		self.assertEqual(out["status"], "Failed")

	def test_cancel_is_refused_for_a_run_of_another_flow(self):
		frappe.set_user(self.editor)
		with self.assertRaises(frappe.PermissionError):
			actions.cancel_flow_run(self.run_b)
		self.assertEqual(frappe.db.get_value("Flow Run", self.run_b, "status"), "Queued")

	def test_cancel_is_refused_for_someone_who_can_edit_no_flow(self):
		frappe.set_user(self._user("Huf User"))
		with self.assertRaises(frappe.PermissionError):
			actions.cancel_flow_run(self.run_a)

	def test_cancel_of_a_missing_run_is_not_found(self):
		with self.assertRaises(frappe.DoesNotExistError):
			actions.cancel_flow_run("no-such-run")

	# --- mark failed ---------------------------------------------------------------------------------------------

	def test_mark_failed_still_needs_a_system_manager(self):
		frappe.set_user(self.editor)
		with self.assertRaises(frappe.PermissionError):
			flow_api.mark_flow_run_failed(self.run_a)

	def test_mark_failed_checks_the_runs_flow_too(self):
		sm = self._user("System Manager", "Huf Manager")
		self._restrict(sm, self.a)
		frappe.set_user(sm)
		with self.assertRaises(frappe.PermissionError):
			flow_api.mark_flow_run_failed(self.run_b)

	# --- reading ---------------------------------------------------------------------------------------------------

	def test_run_details_of_another_flow_are_refused(self):
		frappe.set_user(self.editor)
		self.assertEqual(flow_api.get_flow_run(self.run_a)["flow_run_id"], self.run_a)
		with self.assertRaises(frappe.PermissionError):
			flow_api.get_flow_run(self.run_b)
		self.assertIn("error", flow_api.handle_get_flow_run(self.run_b))
		self.assertTrue(flow_api.handle_get_flow_run(self.run_a).get("success"))

	def test_identity_of_another_flows_run_is_refused(self):
		frappe.set_user(self.editor)
		self.assertIn("run_number", run_identity_api.get_flow_run_identity(self.run_a))
		with self.assertRaises(frappe.PermissionError):
			run_identity_api.get_flow_run_identity(self.run_b)

	def test_lists_leave_out_the_other_flows_runs(self):
		frappe.set_user(self.editor)
		names = {r["name"] for r in flow_api.list_flow_runs(limit=200)}
		self.assertIn(self.run_a, names)
		self.assertNotIn(self.run_b, names)
		page = flow_api.list_flow_runs_page(limit=200)
		self.assertNotIn(self.run_b, {r["name"] for r in page["items"]})
		with self.assertRaises(frappe.PermissionError):
			flow_api.list_flow_runs(flow_id=self.b)
		with self.assertRaises(frappe.PermissionError):
			flow_api.list_flow_runs_page(flow_id=self.b)

	def test_step_labels_skip_runs_the_caller_may_not_open(self):
		frappe.set_user(self.editor)
		out = flow_api.get_flow_step_labels([{"flow_run": self.run_a, "flow_node_id": "n1"}, {"flow_run": self.run_b, "flow_node_id": "n1"}])
		self.assertIsNotNone(out[0])
		self.assertIsNone(out[1])

	def test_resume_of_another_flows_run_is_refused(self):
		frappe.set_user(self.editor)
		with self.assertRaises(frappe.PermissionError):
			flow_api.resume_flow_run(self.run_b)
		self.assertIn("error", flow_api.handle_resume_flow_run(self.run_b))

	def test_starting_and_reading_another_flow_is_refused(self):
		frappe.set_user(self.editor)
		with self.assertRaises(frappe.PermissionError):
			flow_api.run_flow(self.b, {})
		with self.assertRaises(frappe.PermissionError):
			flow_api.get_flow_definition(self.b)
		self.assertEqual(flow_api.get_flow_definition(self.a)["flow_id"], self.a)

	def test_an_administrator_is_unaffected(self):
		self.assertEqual(flow_api.get_flow_run(self.run_b)["flow_run_id"], self.run_b)
		self.assertIn(self.run_b, {r["name"] for r in flow_api.list_flow_runs(limit=200)})
