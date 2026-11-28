"""H-W7-07: Flow Definition ``owner_app`` is set once, by the server, and copied onto runs.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.app_scope.tests.test_ownership
"""

import json

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow.app_scope.ownership import create_app_flow
from huf.ai.flow.tests.test_flow_draft_validation import _end, _graph, _trigger

APP_FLOW = "test-hw707-app"
NATIVE_FLOW = "test-hw707-native"


def _defn():
	return _graph([_trigger("end"), _end()])


class TestFlowOwnership(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		for name in (APP_FLOW, NATIVE_FLOW):
			frappe.db.delete("Agent Flow Run", {"flow_definition": name})
			frappe.db.delete("Flow Definition", {"name": name})
		self.app_flow = create_app_flow("huf", APP_FLOW, "HW707 app", _defn())

	def _reload(self):
		return frappe.get_doc("Flow Definition", APP_FLOW)

	def test_create_sets_owner_app(self):
		self.assertEqual(self._reload().owner_app, "huf")
		self.assertEqual(self._reload().status, "Draft")

	def test_unknown_app_raises(self):
		with self.assertRaises(frappe.ValidationError):
			create_app_flow("no_such_app_hw707", "test-hw707-x", "x", _defn())
		self.assertFalse(frappe.db.exists("Flow Definition", "test-hw707-x"))

	def test_form_change_refused(self):
		doc = self._reload()
		doc.owner_app = "frappe"
		with self.assertRaises(frappe.PermissionError):
			doc.save()
		doc = self._reload()
		doc.owner_app = None
		with self.assertRaises(frappe.PermissionError):
			doc.save()
		self.assertEqual(self._reload().owner_app, "huf")

	def test_api_paths_refused(self):
		with self.assertRaises(frappe.PermissionError):
			frappe.client.set_value("Flow Definition", APP_FLOW, "owner_app", "frappe")
		doc = self._reload().as_dict()
		doc["owner_app"] = "frappe"
		with self.assertRaises(frappe.PermissionError):
			frappe.client.save(doc)
		self.assertEqual(self._reload().owner_app, "huf")

	def test_db_set_refused(self):
		with self.assertRaises(frappe.PermissionError):
			self._reload().db_set("owner_app", "frappe")
		with self.assertRaises(frappe.PermissionError):
			self._reload().db_set({"owner_app": None, "flow_name": "y"})
		self.assertEqual(self._reload().owner_app, "huf")

	def test_other_edits_still_save(self):
		doc = self._reload()
		doc.flow_name = "HW707 renamed"
		doc.save()
		self.assertEqual(self._reload().owner_app, "huf")

	def test_native_insert_cannot_set_owner_app(self):
		doc = frappe.get_doc(
			{
				"doctype": "Flow Definition",
				"flow_id": NATIVE_FLOW,
				"flow_name": "native",
				"status": "Draft",
				"definition_json": json.dumps(_defn()),
				"owner_app": "huf",
			}
		)
		with self.assertRaises(frappe.PermissionError):
			doc.insert()
		doc.owner_app = None
		doc.insert()
		self.assertIsNone(frappe.db.get_value("Flow Definition", NATIVE_FLOW, "owner_app"))

	def test_run_copies_owner_app(self):
		run = frappe.get_doc(
			{
				"doctype": "Agent Flow Run",
				"flow_definition": APP_FLOW,
				"flow_id": APP_FLOW,
				"status": "Queued",
				"owner_app": "frappe",
			}
		).insert(ignore_permissions=True)
		self.assertEqual(run.owner_app, "huf")
