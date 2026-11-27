"""FIX-sec-app-save: an app editor's definition save persists, under a server-side step allow-list.

App A is ``huf``. The user holds only the app's edit role (no Huf role, no permlevel 1).

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.app_scope.tests.test_app_draft_save
"""

import json
from unittest import mock

import frappe
import frappe.client
from frappe.tests import IntegrationTestCase

from huf.ai.flow import api as flow_api
from huf.ai.flow.app_scope import access, docperms
from huf.ai.flow.app_scope.ownership import create_app_flow
from huf.ai.flow.tests.test_flow_draft_validation import _end, _graph

FLOW, OTHER = "test-secsave-a", "test-secsave-b"
ROLE, USER = "SecSave App Editor", "secsave-a@example.com"


def _grants():
	return {"huf": {a: frozenset({ROLE}) for a in access.ACTIONS}}


def _defn(*extra, first="end"):
	trigger = {"id": "start", "type": "trigger.unset", "config": {}, "next": first}
	return _graph([trigger, *extra, _end()])


class TestAppDraftSave(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		if not frappe.db.exists("Role", ROLE):
			frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 1}).insert()
		if not frappe.db.exists("User", USER):
			frappe.get_doc(
				{"doctype": "User", "email": USER, "first_name": "secsave", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		user = frappe.get_doc("User", USER)
		user.set("roles", [])
		user.add_roles(ROLE)
		for module in (access, docperms):
			patcher = mock.patch.object(module, "app_grants", side_effect=_grants)
			patcher.start()
			cls.addClassCleanup(patcher.stop)
		docperms.sync_app_flow_docperms()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		with mock.patch.object(docperms, "app_grants", return_value={}):
			docperms.sync_app_flow_docperms()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Flow Definition", {"name": ("in", (FLOW, OTHER, FLOW + "-renamed"))})
		create_app_flow("huf", FLOW, "SecSave A", _defn())
		frappe.set_user(USER)

	def tearDown(self):
		frappe.set_user("Administrator")

	def _stored(self):
		return json.loads(frappe.db.get_value("Flow Definition", FLOW, "definition_json"))

	def _refused(self, definition):
		before = self._stored()
		with self.assertRaises(frappe.PermissionError):
			flow_api.save_flow_definition(FLOW, definition)
		self.assertEqual(self._stored(), before)

	def _labelled(self):
		defn = _defn()
		defn["nodes"][0]["_label"] = "Edited by the app editor"
		return defn

	def test_editor_definition_change_persists(self):
		flow_api.save_flow_definition(FLOW, self._labelled())
		self.assertEqual(self._stored()["nodes"][0]["_label"], "Edited by the app editor")

	def test_generic_write_paths_stay_closed(self):
		before = self._stored()
		frappe.client.set_value("Flow Definition", FLOW, "definition_json", json.dumps(self._labelled()))
		self.assertEqual(self._stored(), before)
		self.assertFalse(frappe.db.exists("Custom DocPerm", {"role": ROLE, "permlevel": (">", 0)}))

	def test_forbidden_step_types_are_refused(self):
		for node_type in ("doc.update", "tool.call", "code.run", "doc.create", "flow.call", "agent.run", "nope"):
			with self.subTest(node_type):
				self._refused(_defn({"id": "x", "type": node_type, "config": {}, "next": "end"}, first="x"))

	def test_extra_or_foreign_triggers_are_refused(self):
		extra = _defn({"id": "t2", "type": "trigger.schedule", "config": {}, "next": "end"})
		extra["entry"] = [extra["nodes"][0]["id"], "t2"]
		self._refused(extra)
		hook = _defn()
		hook["nodes"][0] = {**hook["nodes"][0], "type": "trigger.webhook"}
		self._refused(hook)

	def test_trigger_may_be_chosen(self):
		chosen = _defn()
		chosen["nodes"][0]["type"] = "trigger.app"
		chosen["nodes"][0]["config"] = {"app": "huf"}
		flow_api.save_flow_definition(FLOW, chosen)
		self.assertEqual(self._stored()["nodes"][0]["type"], "trigger.app")

	def test_handoff_step_can_be_saved_and_edited(self):
		config = {"gateway": "test-secsave-gw", "recipient": "$member", "message": ""}
		step = {"id": "human", "type": "handoff", "config": config, "next": "end"}
		flow_api.save_flow_definition(FLOW, _defn(step, first="human"))
		step["config"] = {**config, "summary": "Needs a person"}
		flow_api.save_flow_definition(FLOW, _defn(step, first="human"))
		self.assertEqual(self._stored()["nodes"][1]["config"]["summary"], "Needs a person")

	def test_malformed_definition_is_refused(self):
		self._refused({**_defn(), "nodes": {"a": {"type": "code.run"}}})

	def test_active_flow_definition_cannot_change(self):
		frappe.db.set_value("Flow Definition", FLOW, "status", "Active")  # activation itself is not under test
		self._refused(self._labelled())

	def test_rename_merge_and_flow_id_change_are_refused(self):
		with self.assertRaises(frappe.PermissionError):
			frappe.client.rename_doc("Flow Definition", FLOW, FLOW + "-renamed")
		frappe.set_user("Administrator")
		create_app_flow("huf", OTHER, "SecSave B", _defn())
		frappe.set_user(USER)
		with self.assertRaises(frappe.PermissionError):
			frappe.rename_doc("Flow Definition", FLOW, OTHER, merge=True)
		try:
			frappe.client.set_value("Flow Definition", FLOW, "flow_id", FLOW + "-renamed")
		except (frappe.ValidationError, frappe.PermissionError):
			pass
		self.assertEqual(frappe.db.get_value("Flow Definition", FLOW, "flow_id"), FLOW)
		self.assertTrue(frappe.db.exists("Flow Definition", FLOW))
