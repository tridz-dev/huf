# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""UX-1 (wave 0): a person who may read a flow or the agent settings but not change them.

* The webhook secret never reaches a Huf User or Huf Viewer: not through get_flow_definition, not through the
  Frappe document / list / client paths, and not through the snapshot a run keeps.
* Those people cannot change a flow (so cannot regenerate the secret) or the Agent Settings (including the
  skill destinations), through save_flow_definition, the document API or the generic client methods.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_ux1_security
"""

import json

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import api as flow_api
from huf.ai.flow import engine as flow_engine
from huf.ai.flow.support.redact import drop_webhook_secrets, hide_webhook_secrets

SECRET = "ux1-secret-0123456789abcdef0123456789abcdef"
NEW_SECRET = "ux1-new-secret-0123456789abcdef0123456789abcdef"

LIMITS = {
	"max_nodes": 20,
	"max_rows": 1000,
	"max_output_bytes": 100_000,
	"max_parallel_calls": 1,
	"max_foreach_iterations": 1,
	"max_external_calls": 5,
	"max_writes": 5,
	"max_wall_time_ms": 5000,
	"fail_closed": True,
}


def _graph(secret=SECRET):
	return {
		"schema_version": "1.0.0",
		"profile": "flow",
		"fingerprint": "0" * 64,
		"entry": "start",
		"nodes": [
			{"id": "start", "type": "trigger.webhook", "config": {"method": "POST", "secret": secret}, "next": "done"},
			{"id": "done", "type": "output", "config": {"value": "ok"}},
		],
		"contract": {
			"input_schema": {"type": "object"},
			"output_schema": {"type": "object"},
			"applies_when": [],
			"permission_envelope": {"read": [], "write": [], "http": "none", "code": "none"},
			"limits": LIMITS,
		},
	}


class TestRedactHelpers(IntegrationTestCase):
	def test_hide_replaces_the_secret_and_flags_it_without_touching_the_original(self):
		original = _graph()
		hidden = hide_webhook_secrets(original)
		config = hidden["nodes"][0]["config"]
		self.assertIsNone(config["secret"])
		self.assertTrue(config["secret_hidden"])
		self.assertEqual(config["method"], "POST")
		self.assertEqual(original["nodes"][0]["config"]["secret"], SECRET)
		self.assertNotIn(SECRET, json.dumps(hidden))

	def test_hide_handles_nodes_keyed_by_id_and_flows_without_a_secret(self):
		keyed = {"nodes": {"a": {"id": "a", "type": "trigger.webhook", "config": {"secret": SECRET}}}}
		self.assertNotIn(SECRET, json.dumps(hide_webhook_secrets(keyed)))
		bare = {"nodes": [{"id": "a", "type": "trigger.webhook", "config": {"method": "GET"}}]}
		self.assertEqual(hide_webhook_secrets(bare), bare)

	def test_drop_removes_only_the_secret(self):
		dropped = drop_webhook_secrets(_graph())
		self.assertEqual(dropped["nodes"][0]["config"], {"method": "POST"})
		self.assertEqual(dropped["nodes"][1], _graph()["nodes"][1])


class UX1Base(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._users = []
		self.flow_id = f"_test-ux1-{frappe.generate_hash(length=8)}"
		flow_api.save_flow_definition(self.flow_id, _graph())
		frappe.db.commit()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Flow Run", {"flow_id": self.flow_id})
		if frappe.db.exists("Flow Definition", self.flow_id):
			frappe.delete_doc("Flow Definition", self.flow_id, ignore_permissions=True, force=True)
		for email in self._users:
			if frappe.db.exists("User", email):
				frappe.delete_doc("User", email, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _user(self, *roles):
		email = f"ux1-{frappe.generate_hash(length=6)}@example.com"
		user = frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "Ux1", "send_welcome_email": 0, "roles": [{"role": r} for r in roles]}
		)
		user.flags.ignore_permissions = True
		user.insert()
		self._users.append(email)
		return email

	def _stored_secret(self):
		raw = frappe.db.get_value("Flow Definition", self.flow_id, "definition_json")
		return json.loads(raw)["nodes"][0]["config"]["secret"]


class TestWebhookSecretIsHidden(UX1Base):
	def test_viewer_and_user_get_the_definition_without_the_secret(self):
		for role in ("Huf Viewer", "Huf User"):
			frappe.set_user(self._user(role))
			result = flow_api.get_flow_definition(self.flow_id)
			config = result["definition_json"]["nodes"][0]["config"]
			self.assertIsNone(config["secret"], role)
			self.assertTrue(config["secret_hidden"], role)
			self.assertEqual(config["method"], "POST")
			self.assertNotIn(SECRET, json.dumps(result), role)
			self.assertEqual(len(result["definition_json"]["nodes"]), 2)  # everything else is still readable

	def test_flow_editors_and_admins_still_get_the_secret(self):
		for user in (self._user("Huf Manager"), "Administrator"):
			frappe.set_user(user)
			config = flow_api.get_flow_definition(self.flow_id)["definition_json"]["nodes"][0]["config"]
			self.assertEqual(config["secret"], SECRET, user)
			self.assertNotIn("secret_hidden", config, user)

	def test_the_stored_definition_is_not_changed_by_reading_it(self):
		frappe.set_user(self._user("Huf Viewer"))
		flow_api.get_flow_definition(self.flow_id)
		self.assertEqual(self._stored_secret(), SECRET)

	def test_document_paths_do_not_hand_the_definition_to_a_reader(self):
		frappe.set_user(self._user("Huf Viewer"))
		# frappe.client.get / REST GET /api/resource/Flow Definition/<name>
		doc = frappe.get_doc("Flow Definition", self.flow_id)
		doc.check_permission("read")
		doc.apply_fieldlevel_read_permissions()
		self.assertNotIn(SECRET, json.dumps(doc.as_dict(), default=str))
		self.assertFalse(doc.get("definition_json"))
		self.assertNotIn(SECRET, json.dumps(frappe.client.get("Flow Definition", self.flow_id), default=str))
		# frappe.getdoc (desk form load)
		from frappe.desk.form.load import getdoc

		getdoc("Flow Definition", self.flow_id)
		self.assertNotIn(SECRET, json.dumps(frappe.response.get("docs") or [], default=str))

	def test_list_paths_do_not_return_the_definition_to_a_reader(self):
		frappe.set_user(self._user("Huf User"))
		try:
			rows = frappe.get_list("Flow Definition", filters={"name": self.flow_id}, fields=["name", "definition_json"])
		except frappe.PermissionError:
			rows = []  # refusing the field is as good as leaving it out
		self.assertNotIn(SECRET, json.dumps(rows, default=str))
		rows = frappe.get_list("Flow Definition", filters={"name": self.flow_id}, fields=["*"])
		self.assertTrue(rows)
		self.assertNotIn(SECRET, json.dumps(rows, default=str))
		try:
			value = frappe.client.get_value("Flow Definition", "definition_json", self.flow_id)
		except frappe.PermissionError:
			value = None
		self.assertNotIn(SECRET, json.dumps(value, default=str))

	def test_a_flow_editor_can_still_read_and_save_the_definition_through_the_document(self):
		frappe.set_user(self._user("Huf Manager"))
		doc = frappe.get_doc("Flow Definition", self.flow_id)
		doc.apply_fieldlevel_read_permissions()
		self.assertIn(SECRET, doc.definition_json)
		doc.description = "edited by a manager"
		doc.save()
		self.assertEqual(self._stored_secret(), SECRET)

	def test_the_snapshot_a_run_keeps_has_no_secret_but_the_trigger_check_still_works(self):
		frappe.set_user("Administrator")
		run = flow_engine.create_flow_run(self.flow_id, payload={}, trigger_type="Webhook")
		pinned = frappe.db.get_value("Flow Run", run.name, "pinned_definition")
		self.assertTrue(pinned)
		self.assertNotIn(SECRET, pinned)
		self.assertEqual(self._stored_secret(), SECRET)
		defn = frappe.get_doc("Flow Definition", self.flow_id).definition_json
		from huf.ai.flow.triggers import match_webhook_trigger, parse_definition

		node, reason = match_webhook_trigger(parse_definition(defn), SECRET, "POST")
		self.assertEqual(reason, "ok")
		self.assertIsNotNone(node)
		flow_engine.run_flow(run.name)
		self.assertEqual(frappe.db.get_value("Flow Run", run.name, "status"), "Success")


class TestReadersCannotChangeTheSecret(UX1Base):
	def test_save_flow_definition_is_refused_and_the_secret_stays(self):
		for role in ("Huf Viewer", "Huf User"):
			frappe.set_user(self._user(role))
			with self.assertRaises(frappe.PermissionError, msg=role):
				flow_api.save_flow_definition(self.flow_id, _graph(NEW_SECRET))
			frappe.set_user("Administrator")
			self.assertEqual(self._stored_secret(), SECRET, role)

	def test_the_document_api_is_refused_and_the_secret_stays(self):
		for role in ("Huf Viewer", "Huf User"):
			frappe.set_user(self._user(role))
			doc = frappe.get_doc("Flow Definition", self.flow_id)
			doc.definition_json = json.dumps(_graph(NEW_SECRET))
			with self.assertRaises(frappe.PermissionError, msg=role):
				doc.save()  # REST PUT /api/resource/Flow Definition/<name>
			with self.assertRaises(frappe.PermissionError, msg=role):
				frappe.client.set_value("Flow Definition", self.flow_id, "definition_json", json.dumps(_graph(NEW_SECRET)))
			with self.assertRaises(frappe.PermissionError, msg=role):
				frappe.client.set_value("Flow Definition", self.flow_id, "flow_name", "renamed by a reader")
			with self.assertRaises(frappe.PermissionError, msg=role):
				frappe.client.delete("Flow Definition", self.flow_id)
			frappe.set_user("Administrator")
			self.assertEqual(self._stored_secret(), SECRET, role)
			self.assertNotEqual(frappe.db.get_value("Flow Definition", self.flow_id, "flow_name"), "renamed by a reader")

	def test_publish_and_unpublish_need_the_write_permission(self):
		frappe.set_user(self._user("Huf Viewer"))
		with self.assertRaises(frappe.PermissionError):
			flow_api.publish_flow(self.flow_id)
		with self.assertRaises(frappe.PermissionError):
			flow_api.unpublish_flow(self.flow_id)


class TestAgentSettingsAreForSystemManagers(IntegrationTestCase):
	"""Agent Settings (including the skill destinations) cannot be changed or read by anyone but a System Manager."""

	DESTINATIONS = json.dumps({"ux1-source": {"repo_url": "https://github.com/example/ux1", "path": "skills", "ref": "main"}})

	def setUp(self):
		frappe.set_user("Administrator")
		self._users = []
		self._before = frappe.db.get_single_value("Agent Settings", "skill_destinations")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.set_single_value("Agent Settings", "skill_destinations", self._before)
		for email in self._users:
			if frappe.db.exists("User", email):
				frappe.delete_doc("User", email, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _user(self, *roles):
		email = f"ux1-{frappe.generate_hash(length=6)}@example.com"
		user = frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "Ux1", "send_welcome_email": 0, "roles": [{"role": r} for r in roles]}
		)
		user.flags.ignore_permissions = True
		user.insert()
		self._users.append(email)
		return email

	def test_flow_editors_and_readers_cannot_save_the_settings_in_any_way(self):
		for role in ("Huf User", "Huf Viewer", "Huf Manager"):
			frappe.set_user(self._user(role))
			settings = frappe.get_doc("Agent Settings")
			settings.skill_destinations = self.DESTINATIONS
			with self.assertRaises(frappe.PermissionError, msg=role):
				settings.save()  # REST PUT /api/resource/Agent Settings/Agent Settings
			with self.assertRaises(frappe.PermissionError, msg=role):
				frappe.client.set_value("Agent Settings", "Agent Settings", "skill_destinations", self.DESTINATIONS)
			with self.assertRaises(frappe.PermissionError, msg=role):
				frappe.client.set_value("Agent Settings", "Agent Settings", {"allow_code_in_flows": 1})
			with self.assertRaises(frappe.PermissionError, msg=role):
				from frappe.desk.form.save import savedocs

				savedocs(json.dumps({"doctype": "Agent Settings", "name": "Agent Settings", "skill_destinations": self.DESTINATIONS}), "Save")
			frappe.set_user("Administrator")
			self.assertEqual(frappe.db.get_single_value("Agent Settings", "skill_destinations"), self._before, role)

	def test_they_cannot_read_the_raw_settings_either(self):
		for role in ("Huf User", "Huf Viewer", "Huf Manager"):
			frappe.set_user(self._user(role))
			with self.assertRaises(frappe.PermissionError, msg=role):
				frappe.get_doc("Agent Settings").check_permission("read")
			with self.assertRaises(frappe.PermissionError, msg=role):
				frappe.client.get("Agent Settings", "Agent Settings")

	def test_the_read_only_summary_still_lists_the_sources_for_everyone(self):
		from huf.ai.skills.api import get_skill_destinations

		frappe.set_user("Administrator")
		frappe.db.set_single_value("Agent Settings", "skill_destinations", self.DESTINATIONS)
		frappe.set_user(self._user("Huf Viewer"))
		names = [d["name"] for d in get_skill_destinations()]
		self.assertIn("ux1-source", names)
		self.assertIn("huf-skills", names)

	def test_the_system_manager_can_still_save(self):
		frappe.set_user(self._user("System Manager"))
		settings = frappe.get_doc("Agent Settings")
		settings.skill_destinations = self.DESTINATIONS
		settings.save()
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_single_value("Agent Settings", "skill_destinations"), self.DESTINATIONS)
