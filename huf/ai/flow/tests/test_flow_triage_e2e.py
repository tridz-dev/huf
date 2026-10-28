"""End-to-end: a deterministic (no LLM) support-triage flow over two runs.

Message 1 ("  REFUND please ") -> normalise (trim, lower) -> no state -> contains "refund" -> remember
that this sender owes an order number (state.set) -> reply asks for it.
Message 2 (" Order 4521 ") -> state found -> regex_extract the digits -> doc.create a ToDo -> clear
state -> templated reply "Refund logged for #4521".
"""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import api as flow_api, engine as flow_engine, state as flow_state
from huf.ai.graph.executor import GraphContext

LIMITS = {
	"max_nodes": 30,
	"max_rows": 1000,
	"max_output_bytes": 100_000,
	"max_parallel_calls": 1,
	"max_foreach_iterations": 1,
	"max_external_calls": 5,
	"max_writes": 2,
	"max_wall_time_ms": 5000,
	"fail_closed": True,
}


def _out(node_id, template, **vars_):
	return {
		"id": node_id,
		"type": "output",
		"config": {"value": {"$template": template, "vars": vars_}},
	}


def triage_graph():
	sender = {"$from": "input.sender_id"}
	key = {"$template": "wa:{s}", "vars": {"s": sender}}
	nodes = [
		{"id": "start", "type": "trigger.webhook", "config": {"method": "POST", "secret": "test-webhook-secret"}, "next": "trim"},
		{"id": "trim", "type": "transform", "config": {"op": "trim", "input": {"text": {"$from": "input.message"}}}, "next": "lower"},
		{"id": "lower", "type": "transform", "config": {"op": "lower", "input": {"text": {"$from": "trim"}}}, "next": "get_state"},
		{"id": "get_state", "type": "state.get", "config": {"key": key}, "next": "cond_awaiting"},
		{
			"id": "cond_awaiting",
			"type": "condition",
			"config": {"expression": 'get_state["found"]', "on_true": "extract_num", "on_false": "has_refund"},
		},
		{"id": "extract_num", "type": "transform", "config": {"op": "regex_extract", "input": {"text": {"$from": "lower"}, "pattern": "\\d+"}}, "next": "cond_num"},
		{
			"id": "cond_num",
			"type": "condition",
			"config": {"expression": 'extract_num != None', "on_true": "create_todo", "on_false": "reply_ask"},
		},
		{
			"id": "create_todo",
			"type": "doc.create",
			"config": {
				"doctype": "ToDo",
				"fields": {
					"description": {
						"$template": "_e2e refund for order #{o} from {s}",
						"vars": {"o": {"$from": "extract_num"}, "s": sender},
					}
				},
			},
			"next": "clear_state",
		},
		{"id": "clear_state", "type": "state.delete", "config": {"key": key}, "next": "reply_logged"},
		_out("reply_logged", "Refund logged for #{o} ({t})", o={"$from": "extract_num"}, t={"$from": "create_todo.name"}),
		{"id": "has_refund", "type": "transform", "config": {"op": "contains", "input": {"text": {"$from": "lower"}, "needle": "refund"}}, "next": "cond_refund"},
		{
			"id": "cond_refund",
			"type": "condition",
			"config": {"expression": 'has_refund == True', "on_true": "remember", "on_false": "reply_default"},
		},
		{
			"id": "remember",
			"type": "state.set",
			"config": {"key": key, "value": {"awaiting": "order_number"}, "ttl_seconds": 600},
			"next": "reply_ask",
		},
		_out("reply_ask", "Please send your order number."),
		_out("reply_default", "Thanks, an agent will reply soon."),
	]
	return {
		"schema_version": "1.0.0",
		"profile": "flow",
		"fingerprint": "0" * 64,
		"entry": "start",
		"nodes": nodes,
		"contract": {
			"input_schema": {"type": "object"},
			"output_schema": {"type": "object"},
			"applies_when": [],
			"permission_envelope": {"read": [], "write": [{"doctype": "ToDo"}], "http": "none", "code": "none"},
			"limits": LIMITS,
		},
	}


class TestTriageEndToEnd(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.flow_id = f"_test-triage-{frappe.generate_hash(length=6)}"
		flow_api.save_flow_definition(self.flow_id, triage_graph())
		self.sender = f"9199{frappe.generate_hash(length=6)}"

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("ToDo", {"description": ["like", "_e2e %"]})
		frappe.db.delete("Flow State", {"flow_id": self.flow_id})
		frappe.db.delete("Flow Run", {"flow_id": self.flow_id})
		frappe.delete_doc("Flow Definition", self.flow_id, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _run(self, message):
		payload = {"message": message, "sender_id": self.sender, "conversation_id": self.sender, "gateway": "gw"}
		run = flow_engine.create_flow_run(self.flow_id, payload=payload, trigger_type="Manual")
		seen = {}
		original = GraphContext.record_output

		def spy(ctx, node_id, output):
			seen[node_id] = output
			return original(ctx, node_id, output)

		with patch.object(GraphContext, "record_output", spy):
			flow_engine.run_flow(run.name)
		run.reload()
		return run, seen

	def _reply(self, seen):
		return next(v for k, v in seen.items() if k.startswith("reply_"))

	def test_two_turn_refund_conversation(self):
		run1, seen1 = self._run("  REFUND please ")
		self.assertEqual(run1.status, "Success", run1.last_error)
		self.assertEqual(self._reply(seen1), "Please send your order number.")
		self.assertEqual(seen1["lower"], "refund please")
		self.assertIs(seen1["has_refund"], True)
		self.assertEqual(flow_state.get_state(self.flow_id, f"wa:{self.sender}"), (True, {"awaiting": "order_number"}))
		self.assertEqual(frappe.db.count("ToDo", {"description": ["like", "_e2e %"]}), 0)

		run2, seen2 = self._run(" Order 4521 ")
		self.assertEqual(run2.status, "Success", run2.last_error)
		todo = seen2["create_todo"]["name"]
		self.assertEqual(self._reply(seen2), f"Refund logged for #4521 ({todo})")
		self.assertEqual(frappe.db.get_value("ToDo", todo, "description"), f"_e2e refund for order #4521 from {self.sender}")
		self.assertEqual(flow_state.get_state(self.flow_id, f"wa:{self.sender}"), (False, None))

	def test_unrelated_message_gets_default_and_leaves_no_state(self):
		run, seen = self._run("hello there")
		self.assertEqual(run.status, "Success", run.last_error)
		self.assertEqual(self._reply(seen), "Thanks, an agent will reply soon.")
		self.assertEqual(flow_state.get_state(self.flow_id, f"wa:{self.sender}"), (False, None))

	def test_followup_without_number_asks_again_and_keeps_state(self):
		self._run("refund")
		run, seen = self._run("sorry I forgot")
		self.assertEqual(self._reply(seen), "Please send your order number.")
		self.assertTrue(flow_state.get_state(self.flow_id, f"wa:{self.sender}")[0])

	def test_other_sender_is_independent(self):
		self._run("refund")
		self.sender = self.sender + "x"
		_run, seen = self._run("4521")
		self.assertEqual(self._reply(seen), "Thanks, an agent will reply soon.")
