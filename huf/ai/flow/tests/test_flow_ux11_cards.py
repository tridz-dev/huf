# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""UX-11: the Flows list card data (``list_flow_cards``).

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_ux11_cards
"""

import json

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow.listing import cards as flow_cards
from huf.ai.flow import api as flow_api

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


def _graph(trigger=None, extra_nodes=None):
	trigger = trigger or {"id": "t", "type": "trigger.webhook", "config": {"method": "POST", "secret": "s" * 40}, "next": "c"}
	nodes = [
		trigger,
		{"id": "c", "type": "condition", "config": {"expression": "input['a'] > 1", "on_true": "yes", "on_false": "no"}, "_label": "Big?"},
		{"id": "yes", "type": "output", "config": {"value": "big"}, "_label": "Big"},
		{"id": "no", "type": "output", "config": {"value": "small"}, "_label": "Small"},
	]
	extra_nodes = extra_nodes or []
	if extra_nodes:  # the extra steps sit on the "yes" path so every step is reachable
		nodes[1]["config"]["on_true"] = extra_nodes[0]["id"]
		extra_nodes[-1]["next"] = "yes"
	return {
		"schema_version": "1.0.0",
		"profile": "flow",
		"fingerprint": "0" * 64,
		"entry": [trigger["id"]],
		"nodes": nodes + extra_nodes,
		"contract": {
			"input_schema": {"type": "object"},
			"output_schema": {"type": "object"},
			"applies_when": [],
			"permission_envelope": {"read": [], "write": [], "http": "none", "code": "none"},
			"limits": LIMITS,
		},
	}


class TestSummarizeDefinition(IntegrationTestCase):
	def test_trigger_steps_and_count_in_reading_order(self):
		summary = flow_cards.summarize_definition(_graph())
		self.assertEqual(summary["trigger"], {"type": "webhook", "method": "POST"})
		self.assertEqual([s["type"] for s in summary["steps"]], ["condition", "output", "output"])
		self.assertEqual(summary["step_count"], 3)

	def test_the_webhook_secret_never_appears_in_the_summary(self):
		self.assertNotIn("s" * 40, json.dumps(flow_cards.summarize_definition(_graph())))

	def test_schedule_and_data_triggers_keep_their_plain_settings(self):
		sched = _graph({"id": "t", "type": "trigger.schedule", "config": {"cron": "0 9 * * *"}, "next": "c"})
		self.assertEqual(flow_cards.summarize_definition(sched)["trigger"], {"type": "schedule", "cron": "0 9 * * *"})
		data = _graph({"id": "t", "type": "trigger.doc-event", "config": {"doctype": "ToDo", "event": "after_insert"}, "next": "c"})
		self.assertEqual(
			flow_cards.summarize_definition(data)["trigger"], {"type": "doc-event", "doctype": "ToDo", "event": "after_insert"}
		)

	def test_unset_trigger_and_empty_graph(self):
		unset = _graph({"id": "t", "type": "trigger.unset", "config": {}, "next": None})
		self.assertEqual(flow_cards.summarize_definition(unset)["trigger"], {"type": "unset"})
		self.assertEqual(flow_cards.summarize_definition({})["step_count"], 0)

	def test_tool_steps_carry_the_tool_id(self):
		tool = {"id": "tool", "type": "tool.call", "config": {"tool_id": "slack_send_message", "input": {}}}
		summary = flow_cards.summarize_definition(_graph(extra_nodes=[tool]))
		self.assertIn({"type": "tool.call", "tool_id": "slack_send_message"}, summary["steps"])


class TestListFlowCards(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.tag = frappe.generate_hash(length=6)
		self.ids = []
		for name, desc, category in (
			(f"Alpha {self.tag}", f"Sends a welcome note {self.tag}", "Sales"),
			(f"Beta {self.tag}", "", f"Cat{self.tag}"),
		):
			flow_id = f"_test-ux11-{frappe.generate_hash(length=8)}"
			flow_api.save_flow_definition(flow_id, _graph())
			frappe.db.set_value("Flow Definition", flow_id, {"flow_name": name, "description": desc, "category": category})
			self.ids.append(flow_id)
		frappe.db.commit()

	def tearDown(self):
		frappe.set_user("Administrator")
		for flow_id in self.ids:
			frappe.db.delete("Flow Run", {"flow_id": flow_id})
			frappe.delete_doc("Flow Definition", flow_id, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _names(self, **kw):
		return [i["flow_name"] for i in flow_cards.list_flow_cards(**kw)["items"]]

	def test_search_covers_name_description_and_category(self):
		self.assertEqual(self._names(search=f"alpha {self.tag}"), [f"Alpha {self.tag}"])
		self.assertEqual(self._names(search=f"welcome note {self.tag}"), [f"Alpha {self.tag}"])
		self.assertEqual(self._names(search=f"cat{self.tag}"), [f"Beta {self.tag}"])

	def test_category_status_and_sort(self):
		self.assertEqual(self._names(category="sales", search=self.tag), [f"Alpha {self.tag}"])
		self.assertEqual(self._names(status="Active", search=self.tag), [])
		self.assertEqual(self._names(search=self.tag, sort="name"), [f"Alpha {self.tag}", f"Beta {self.tag}"])

	def test_total_counts_all_matches_not_just_the_page(self):
		result = flow_cards.list_flow_cards(search=self.tag, limit=1)
		self.assertEqual(len(result["items"]), 1)
		self.assertEqual(result["total"], 2)

	def test_card_has_summary_and_last_run(self):
		flow_id = self.ids[0]
		run = frappe.get_doc({"doctype": "Flow Run", "flow_id": flow_id, "flow_definition": flow_id, "status": "Failed", "current_node_id": "c", "trigger_type": "Manual"})
		run.insert(ignore_permissions=True)
		frappe.db.commit()
		item = next(i for i in flow_cards.list_flow_cards(search=self.tag)["items"] if i["flow_id"] == flow_id)
		self.assertEqual(item["trigger"]["type"], "webhook")
		self.assertEqual(item["step_count"], 3)
		self.assertEqual(item["last_run"]["status"], "Failed")
		self.assertEqual(item["last_run"]["failed_step"], "Big?")
		other = next(i for i in flow_cards.list_flow_cards(search=self.tag)["items"] if i["flow_id"] != flow_id)
		self.assertIsNone(other["last_run"])


class TestCardsForReadOnlyPeople(IntegrationTestCase):
	"""A person who may only read flows (Huf Viewer, Huf User) still gets the list, without any webhook secret."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.flow_id = f"_test-ux11v-{frappe.generate_hash(length=8)}"
		flow_api.save_flow_definition(self.flow_id, _graph())
		frappe.db.commit()
		self.users = []

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.delete_doc("Flow Definition", self.flow_id, ignore_permissions=True, force=True)
		for email in self.users:
			if frappe.db.exists("User", email):
				frappe.delete_doc("User", email, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _user(self, role):
		email = f"ux11v-{frappe.generate_hash(length=6)}@example.com"
		user = frappe.get_doc({"doctype": "User", "email": email, "first_name": "Ux11", "send_welcome_email": 0, "roles": [{"role": role}]})
		user.flags.ignore_permissions = True
		user.insert()
		self.users.append(email)
		return email

	def test_viewers_and_users_get_cards_without_the_secret(self):
		for role in ("Huf Viewer", "Huf User"):
			frappe.set_user(self._user(role))
			result = flow_cards.list_flow_cards(search=self.flow_id[:12], limit=5)
			item = next(i for i in result["items"] if i["flow_id"] == self.flow_id)
			self.assertEqual(item["trigger"]["type"], "webhook", role)
			self.assertEqual(item["step_count"], 3, role)
			self.assertNotIn("s" * 40, json.dumps(result), role)
			self.assertEqual(flow_cards.list_flow_categories.__name__, "list_flow_categories")
