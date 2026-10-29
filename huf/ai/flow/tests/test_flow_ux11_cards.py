# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""UX-11: the Flows list card data (``list_flow_cards``).

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_ux11_cards
"""

import json

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import flow_cards
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
	return {
		"schema_version": "1.0.0",
		"profile": "flow",
		"fingerprint": "0" * 64,
		"entry": [trigger["id"]],
		"nodes": nodes + (extra_nodes or []),
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
			(f"Alpha {self.tag}", "Sends a welcome note", "Sales"),
			(f"Beta {self.tag}", "", "Support"),
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
		self.assertEqual(self._names(search="welcome note"), [f"Alpha {self.tag}"])
		self.assertEqual(self._names(search=f"Support"), [f"Beta {self.tag}"])

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
