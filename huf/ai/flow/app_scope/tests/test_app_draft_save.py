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
from huf.ai.flow.app_scope import access, docperms, targets
from huf.ai.flow.app_scope import gateways as app_gateway_list
from huf.ai.flow.app_scope.ownership import create_app_flow
from huf.ai.flow.gateways.api import get_app_flow_gateways
from huf.ai.flow.runs.preflight import run_preflight
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

	def _bound(self, step):
		"""The step as the app's server stored it: its Gateway is already bound to this flow."""
		frappe.db.set_value(
			"Flow Definition", FLOW, "definition_json", json.dumps(_defn(step, first=step["id"]))
		)

	def test_handoff_step_can_be_saved_and_edited(self):
		config = {"gateway": "test-secsave-gw", "recipient": "$member", "message": ""}
		step = {"id": "human", "type": "handoff", "config": config, "next": "end"}
		self._bound(step)
		step["config"] = {**config, "summary": "Needs a person"}
		flow_api.save_flow_definition(FLOW, _defn(step, first="human"))
		self.assertEqual(self._stored()["nodes"][1]["config"]["summary"], "Needs a person")

	def test_handoff_may_only_target_the_runs_member(self):
		good = {"gateway": "test-secsave-gw", "recipient": "$member", "message": ""}
		step = {"id": "human", "type": "handoff", "config": good, "next": "end"}
		self._bound(step)
		bad = {
			"literal recipient": {**good, "recipient": "+919999999999"},
			"referenced recipient": {**good, "recipient": {"$from": "trigger.phone"}},
			"conversation": {**good, "conversation": "CONV-0001"},
			"message": {**good, "message": "Hello"},
			"gateway default message": {k: v for k, v in good.items() if k != "message"},
			"another gateway": {**good, "gateway": "someone-elses-gw"},
			"computed gateway": {**good, "gateway": {"$from": "trigger.gateway"}},
		}
		for label, config in bad.items():
			with self.subTest(label):
				self._refused(_defn({**step, "config": config}, first="human"))

	def test_send_step_needs_authority_over_a_new_gateway(self):
		config = {"gateway": "someone-elses-gw", "recipient": "$member"}
		self._refused(_defn({"id": "tell", "type": "send.message", "config": config, "next": "end"}, first="tell"))

	def _gateway(self):
		"""A stored Gateway row; the channel's own setup checks are not under test."""
		name = f"AppGW {frappe.generate_hash(length=8)}"
		doc = frappe.get_doc({"doctype": "Gateway", "gateway_name": name, "provider": "Telegram"})
		doc.name = name
		doc.db_insert()
		return name

	def _sending(self, gateway):
		config = {"gateway": gateway, "recipient": "$member", "message": ""}
		return _defn({"id": "human", "type": "handoff", "config": config, "next": "end"}, first="human")

	def test_gateway_listed_by_the_app_saves_and_passes_preflight(self):
		name = self._gateway()
		self.assertEqual(get_app_flow_gateways(FLOW), {"restricted": True, "gateways": []})
		self._refused(self._sending(name))  # no hook registered: nothing new may be named
		self.assertIn("APP_GATEWAY_NOT_ALLOWED", self._codes(self._sending(name)))
		with mock.patch.object(targets, "app_gateways", return_value={name}):
			self.assertNotIn("APP_GATEWAY_NOT_ALLOWED", self._codes(self._sending(name)))
			flow_api.save_flow_definition(FLOW, self._sending(name))
		# Once stored it stays usable, without the hook.
		self.assertNotIn("APP_GATEWAY_NOT_ALLOWED", self._codes(self._sending(name)))
		self.assertEqual([g["name"] for g in get_app_flow_gateways(FLOW)["gateways"]], [name])

	def _codes(self, definition):
		return {f.code for f in run_preflight(definition, FLOW)}

	def test_hook_answers_fail_closed(self):
		def call(**kwargs):
			with (
				mock.patch.object(frappe, "get_hooks", return_value={"huf": ["a.b"]}),
				mock.patch.object(frappe, "get_attr", **kwargs),
			):
				return app_gateway_list.app_gateways("huf", USER)

		self.assertEqual(call(return_value=lambda app, user: ["gw"]), {"gw"})
		self.assertEqual(call(return_value=lambda app, user: "gw"), set())
		self.assertEqual(call(return_value=lambda app, user: [1]), set())
		self.assertEqual(call(side_effect=ImportError), set())
		self.assertEqual(app_gateway_list.app_gateways("huf", USER), set())

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
