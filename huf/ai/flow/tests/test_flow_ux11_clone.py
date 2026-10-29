# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""UX-11 / UX-20: copy a flow and start from a template.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_ux11_clone
"""

import json

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import api as flow_api
from huf.ai.flow import clone
from huf.ai.flow.tests.test_flow_ux11_cards import _graph

SECRET = "ux11-original-secret-0123456789abcdef0123456789"


class CloneBase(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.created = []
		self._users = []
		self.source_id = f"_test-ux11c-{frappe.generate_hash(length=8)}"
		graph = _graph({"id": "t", "type": "trigger.webhook", "config": {"method": "POST", "secret": SECRET}, "next": "c"})
		flow_api.save_flow_definition(self.source_id, graph)
		frappe.db.set_value(
			"Flow Definition", self.source_id, {"flow_name": f"Order alert {self.source_id}", "description": "Tells the team", "category": "Sales"}
		)
		frappe.db.commit()
		self.created.append(self.source_id)

	def tearDown(self):
		frappe.set_user("Administrator")
		for flow_id in self.created:
			if frappe.db.exists("Flow Definition", flow_id):
				frappe.delete_doc("Flow Definition", flow_id, ignore_permissions=True, force=True)
		for email in self._users:
			if frappe.db.exists("User", email):
				frappe.delete_doc("User", email, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _user(self, *roles):
		email = f"ux11-{frappe.generate_hash(length=6)}@example.com"
		user = frappe.get_doc({"doctype": "User", "email": email, "first_name": "Ux11", "send_welcome_email": 0, "roles": [{"role": r} for r in roles]})
		user.flags.ignore_permissions = True
		user.insert()
		self._users.append(email)
		return email


class TestCloneFlow(CloneBase):
	def test_copy_is_a_draft_with_a_new_name_and_a_new_secret(self):
		result = clone.clone_flow(self.source_id)
		self.created.append(result["flow_id"])
		doc = frappe.get_doc("Flow Definition", result["flow_id"])
		self.assertNotEqual(doc.flow_id, self.source_id)
		self.assertEqual(doc.status, "Draft")
		self.assertEqual(doc.flow_name, f"Order alert {self.source_id} (copy)")
		self.assertEqual((doc.description, doc.category), ("Tells the team", "Sales"))
		secret = json.loads(doc.definition_json)["nodes"][0]["config"]["secret"]
		self.assertNotEqual(secret, SECRET)
		self.assertGreaterEqual(len(secret), 32)
		# the original is untouched
		self.assertEqual(json.loads(frappe.db.get_value("Flow Definition", self.source_id, "definition_json"))["nodes"][0]["config"]["secret"], SECRET)

	def test_copy_of_a_published_flow_starts_as_a_draft_and_names_do_not_collide(self):
		frappe.db.set_value("Flow Definition", self.source_id, "status", "Active")
		first = clone.clone_flow(self.source_id)
		second = clone.clone_flow(self.source_id)
		self.created += [first["flow_id"], second["flow_id"]]
		self.assertEqual(frappe.db.get_value("Flow Definition", first["flow_id"], "status"), "Draft")
		self.assertTrue(first["flow_name"].endswith("(copy)"))
		self.assertTrue(second["flow_name"].endswith("(copy 2)"))
		third = clone.clone_flow(first["flow_id"])  # a copy of a copy does not stack suffixes
		self.created.append(third["flow_id"])
		self.assertTrue(third["flow_name"].endswith("(copy 3)"))
		self.assertEqual(third["flow_name"].count("(copy"), 1)

	def test_a_missing_flow_is_refused(self):
		with self.assertRaises(frappe.DoesNotExistError):
			clone.clone_flow("no-such-flow")

	def test_viewers_cannot_copy_but_managers_can(self):
		frappe.set_user(self._user("Huf Viewer"))
		with self.assertRaises(frappe.PermissionError):
			clone.clone_flow(self.source_id)
		frappe.set_user(self._user("Huf Manager"))
		result = clone.clone_flow(self.source_id)
		self.created.append(result["flow_id"])
		self.assertTrue(frappe.db.exists("Flow Definition", result["flow_id"]))

	def test_unconnected_integration_steps_are_listed_as_needing_setup(self):
		tool = {"id": "tool", "type": "tool.call", "config": {"tool_id": "slack_send_message", "input": {"channel": "C1", "text": "hi"}}, "_label": "Post to Slack"}
		flow_id = f"_test-ux11c-{frappe.generate_hash(length=8)}"
		flow_api.save_flow_definition(flow_id, _graph(extra_nodes=[tool]))
		self.created.append(flow_id)
		from huf.ai.flow import integrations

		original = integrations.is_connected
		clone.is_connected = lambda service: False
		try:
			result = clone.clone_flow(flow_id)
		finally:
			clone.is_connected = original
		self.created.append(result["flow_id"])
		self.assertEqual([n["title"] for n in result["needs_setup"]], ["Post to Slack"])
		self.assertEqual(result["needs_setup"][0]["service"], "slack")


class TestCreateFromTemplate(CloneBase):
	def test_template_gets_a_unique_name_a_fresh_secret_and_is_a_draft(self):
		graph = _graph({"id": "t", "type": "trigger.webhook", "config": {"method": "POST"}, "next": "c"})
		first = clone.create_flow_from_template("Order alert template", json.dumps(graph), "Does a thing", "Starter")
		second = clone.create_flow_from_template("Order alert template", graph, "Does a thing", "Starter")
		self.created += [first["flow_id"], second["flow_id"]]
		self.assertEqual(first["flow_name"], "Order alert template")
		self.assertEqual(second["flow_name"], "Order alert template 2")
		doc = frappe.get_doc("Flow Definition", first["flow_id"])
		self.assertEqual((doc.status, doc.category, doc.description), ("Draft", "Starter", "Does a thing"))
		secret1 = json.loads(doc.definition_json)["nodes"][0]["config"]["secret"]
		secret2 = json.loads(frappe.db.get_value("Flow Definition", second["flow_id"], "definition_json"))["nodes"][0]["config"]["secret"]
		self.assertGreaterEqual(len(secret1), 32)
		self.assertNotEqual(secret1, secret2)

	def test_agent_template_without_any_agent_asks_to_create_one(self):
		node = {"id": "a", "type": "agent.run", "config": {"agent": "", "prompt": "Say hi"}, "next": None}
		graph = _graph(extra_nodes=[node])
		graph["nodes"][2]["next"] = None
		original = clone._first_agent
		clone._first_agent = lambda: None
		try:
			with self.assertRaises(frappe.ValidationError):
				clone.create_flow_from_template("Needs agent", graph)
			clone._first_agent = lambda: "Some Agent"
			result = clone.create_flow_from_template("Has agent", graph)
		finally:
			clone._first_agent = original
		self.created.append(result["flow_id"])
		saved = json.loads(frappe.db.get_value("Flow Definition", result["flow_id"], "definition_json"))
		self.assertEqual(next(n for n in saved["nodes"] if n["id"] == "a")["config"]["agent"], "Some Agent")

	def test_viewers_cannot_create_from_a_template(self):
		frappe.set_user(self._user("Huf Viewer"))
		with self.assertRaises(frappe.PermissionError):
			clone.create_flow_from_template("Nope", _graph())
