# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""A WhatsApp gateway routed to a Flow, and a Flow sending WhatsApp.

There is no ``trigger.whatsapp`` node. The only gateway trigger is a Gateway route/default whose target is
a Flow: ``process_gateway_event`` then starts a Flow Run (``trigger_type == "Gateway"``) whose payload is
``{"gateway_event", "message", "gateway", "sender_id", "conversation_id"}`` so a Flow can address a reply and key
per-conversation state (``input.sender_id`` / ``input.conversation_id``).

The send half drives the real ``huf.ai.tools.whatsapp`` tool from a ``tool.call`` node, so the free-form 24h
window / proactive gate of the tool applies exactly as it does for an agent. Only Meta (HTTP) is faked.
Needs frappe_whatsapp (skipped otherwise).
"""

from __future__ import annotations

import json
from unittest.mock import patch

import frappe

from huf.ai.flow import api as flow_api
from huf.ai.flow.engine import run_flow
from huf.ai.gateway_service import process_gateway_event
from huf.ai.whatsapp.tests import test_whatsapp_full_stack as fs
from huf.testing.factories import make_agent_tool_function

LIMITS = {
	"max_nodes": 20,
	"max_rows": 1000,
	"max_output_bytes": 100_000,
	"max_parallel_calls": 1,
	"max_foreach_iterations": 1,
	"max_external_calls": 5,
	"max_writes": 0,
	"max_wall_time_ms": 5000,
	"fail_closed": True,
}


class TestFlowWhatsAppGatewayTrigger(fs.TestWhatsAppMultiGateway):
	# Inherit the two-gateway fixture only, not its tests.
	for _name in [n for n in dir(fs.TestWhatsAppMultiGateway) if n.startswith("test_")]:
		locals()[_name] = None
	del _name

	def setUp(self):
		super().setUp()
		self.tool = make_agent_tool_function(
			tool_name=f"_test_wa_flow_{frappe.generate_hash(length=8)}",
			types="App Provided",
			description="Test tool: WhatsApp actions.",
			function_path="huf.ai.tools.whatsapp.handle_action",
			params=json.dumps(
				{
					"type": "object",
					"properties": {k: {"type": "string"} for k in ("action", "gateway_name", "to", "message", "template_name")},
					"required": ["action"],
				}
			),
			is_read_only=0,
		)

	def _grant_flow_access(self):
		"""Flow Run create/write needs Huf User; the default "Huf Gateway User" role alone does not have it."""
		frappe.get_doc("User", fs.EXEC_USER).add_roles("Huf User")

	def _inbound(self, label, wamid, text="hello"):
		gateway, phone, waba, secret = (
			(self.gateway_a, self.PHONE_A, self.WABA_A, self.SECRET_A)
			if label == "A"
			else (self.gateway_b, self.PHONE_B, self.WABA_B, self.SECRET_B)
		)
		return self._post(gateway, self._inbound_payload(phone, waba, wamid, text), secret)

	def _flow(self, tool_input):
		flow_id = f"_test-wa-flow-{frappe.generate_hash(length=8)}"
		definition = {
			"schema_version": "1.0.0",
			"profile": "flow",
			"fingerprint": "0" * 64,
			"entry": "start",
			"nodes": [
				{"id": "start", "type": "trigger.webhook", "config": {"method": "POST"}, "next": "send"},
				{"id": "send", "type": "tool.call", "config": {"tool_id": self.tool.tool_name, "input": tool_input}},
			],
			"contract": {
				"input_schema": {"type": "object"},
				"output_schema": {"type": "object"},
				"applies_when": [],
				"permission_envelope": {"read": [], "write": [], "http": "none", "code": "none"},
				"limits": LIMITS,
			},
		}
		flow_api.save_flow_definition(flow_id, definition)
		return flow_id

	def _route_gateway_a_to(self, flow_id):
		frappe.db.set_value(
			"Gateway", self.gateway_a.name, {"default_target_type": "Flow", "default_flow": flow_id, "default_agent": None}
		)

	def _text_posts(self):
		return [
			p
			for p in self.meta.posts("/messages")
			if isinstance(p["body"], dict) and p["body"].get("type") in ("text", "template")
		]

	def _flow_run_for(self, wamid):
		event = frappe.get_doc("Gateway Event", self._events(self.gateway_a, wamid)[0])
		return event, frappe.get_doc("Flow Run", event.flow_run)

	def test_inbound_whatsapp_message_starts_a_flow_run(self):
		self._grant_flow_access()
		flow_id = self._flow({"action": "list_templates"})
		self._route_gateway_a_to(flow_id)
		self.assertTrue(self._inbound("A", "wamid.FLOW1", "start the flow")["success"])
		result = process_gateway_event(self._events(self.gateway_a, "wamid.FLOW1")[0])
		frappe.set_user("Administrator")
		self.assertEqual(result["status"], "Running")
		event, flow_run = self._flow_run_for("wamid.FLOW1")
		self.assertEqual((event.target_type, event.target_flow), ("Flow", flow_id))
		self.assertEqual(flow_run.flow_id, flow_id)
		self.assertEqual(flow_run.trigger_type, "Gateway")
		payload = json.loads(flow_run.trigger_payload)
		self.assertEqual(payload["gateway_event"], event.name)
		self.assertEqual(payload["message"], "start the flow")
		self.assertEqual(self.agent_calls, [], "a Flow-routed event must not run an agent")

	def test_flow_route_works_with_the_default_gateway_role(self):
		# WP-7: the execution user only has "Huf Gateway User"; route auth already happened, so the
		# Flow Run is created on the gateway's behalf without demanding the Huf User role.
		flow_id = self._flow({"action": "list_templates"})
		self._route_gateway_a_to(flow_id)
		self._inbound("A", "wamid.NOPERM")
		result = process_gateway_event(self._events(self.gateway_a, "wamid.NOPERM")[0])
		frappe.set_user("Administrator")
		self.assertIn("flow_run_id", result)
		self.assertEqual(frappe.db.count("Flow Run", {"flow_id": flow_id}), 1)

	def test_other_gateway_does_not_start_the_flow(self):
		self._grant_flow_access()
		flow_id = self._flow({"action": "list_templates"})
		self._route_gateway_a_to(flow_id)
		self._inbound("B", "wamid.FLOWB", "hello")
		process_gateway_event(self._events(self.gateway_b, "wamid.FLOWB")[0])
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.count("Flow Run", {"flow_id": flow_id}), 0)
		self.assertEqual(len(self.agent_calls), 1)  # B still routes to its agent

	def test_duplicate_wamid_starts_one_flow_run(self):
		self._grant_flow_access()
		flow_id = self._flow({"action": "list_templates"})
		self._route_gateway_a_to(flow_id)
		self._inbound("A", "wamid.DUPF")
		self.assertTrue(self._inbound("A", "wamid.DUPF").get("duplicates"))
		process_gateway_event(self._events(self.gateway_a, "wamid.DUPF")[0])
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.count("Flow Run", {"flow_id": flow_id}), 1)

	def _run_triggered_flow(self, wamid, tool_input):
		self._grant_flow_access()
		flow_id = self._flow(tool_input)
		self._route_gateway_a_to(flow_id)
		self._inbound("A", wamid)
		process_gateway_event(self._events(self.gateway_a, wamid)[0])
		frappe.set_user("Administrator")
		_event, flow_run = self._flow_run_for(wamid)
		run_flow(flow_run.name)
		flow_run.reload()
		return flow_run

	def _tool_output(self, flow_run):
		runs = frappe.get_all("Agent Run", filters={"flow_run": flow_run.name}, pluck="name")
		calls = frappe.get_all(
			"Agent Tool Call", filters={"agent_run": ["in", runs or [""]]}, fields=["tool_result", "error_message"]
		)
		return json.dumps(calls, default=str) + str(flow_run.last_error)

	def test_flow_free_form_send_is_allowed_while_the_window_is_open(self):
		# the inbound message that triggers the flow opens the 24h window of gateway A
		flow_run = self._run_triggered_flow(
			"wamid.W1",
			{"action": "send_message", "gateway_name": self.gateway_a.name, "to": fs.SENDER, "message": "from the flow"},
		)
		self.assertEqual(flow_run.status, "Success", flow_run.last_error)
		posts = self._text_posts()
		self.assertEqual(len(posts), 1, self.meta.calls)
		self.assertTrue(posts[0]["url"].endswith(f"/{self.PHONE_A}/messages"))
		self.assertEqual(posts[0]["body"]["text"]["body"], "from the flow")

	def test_forged_gateway_name_in_flow_tool_args_is_ignored(self):
		# gateway B is named in the args, but the flow was started by gateway A: A's number sends
		flow_run = self._run_triggered_flow(
			"wamid.W2",
			{"action": "send_message", "gateway_name": self.gateway_b.name, "to": fs.SENDER, "message": "via a"},
		)
		posts = self._text_posts()
		self.assertEqual(len(posts), 1, self._tool_output(flow_run))
		self.assertTrue(posts[0]["url"].endswith(f"/{self.PHONE_A}/messages"))

	def test_flow_without_gateway_context_fails_closed(self):
		self._grant_flow_access()
		flow_id = self._flow({"action": "send_message", "gateway_name": self.gateway_a.name, "to": fs.SENDER, "message": "x"})
		started = flow_api.run_flow(flow_id, {})
		flow_run = frappe.get_doc("Flow Run", started["flow_run_id"])
		self.assertEqual(self._text_posts(), [])
		self.assertIn("gateway_context_required", self._tool_output(flow_run))

	def test_flow_cannot_send_proactively_from_gateway_a_to_a_stranger(self):
		flow_run = self._run_triggered_flow(
			"wamid.W3",
			{"action": "send_message", "gateway_name": self.gateway_a.name, "to": "15559990000", "message": "hi stranger"},
		)
		self.assertEqual(self._text_posts(), [], self.meta.calls)
		self.assertIn("recipient_not_permitted", self._tool_output(flow_run))  # scope stops the stranger before the window gate

	# -- WP-7: flow target end to end -------------------------------------------------------

	def _reply_flow(self, value="flow says hi"):
		flow_id = f"_test-wa-reply-{frappe.generate_hash(length=8)}"
		definition = {
			"schema_version": "1.0.0",
			"profile": "flow",
			"fingerprint": "0" * 64,
			"entry": "start",
			"nodes": [
				{"id": "start", "type": "trigger.webhook", "config": {"method": "POST"}, "next": "out"},
				{"id": "out", "type": "output", "config": {"value": value}},
			],
			"contract": {
				"input_schema": {"type": "object"},
				"output_schema": {"type": "object"},
				"applies_when": [],
				"permission_envelope": {"read": [], "write": [], "http": "none", "code": "none"},
				"limits": LIMITS,
			},
		}
		flow_api.save_flow_definition(flow_id, definition)
		self._route_gateway_a_to(flow_id)
		return flow_id

	def _start(self, wamid, text="hello"):
		self._inbound("A", wamid, text)
		name = self._events(self.gateway_a, wamid)[0]
		result = process_gateway_event(name)
		frappe.set_user("Administrator")
		return name, result

	def test_event_is_running_not_queued_while_the_flow_runs(self):
		self._reply_flow()
		name, result = self._start("wamid.ST1")
		self.assertEqual(frappe.db.get_value("Gateway Event", name, "status"), "Running")
		self.assertEqual(result["status"], "Running")

	def test_flow_output_is_delivered_as_the_reply_and_event_succeeds(self):
		self._reply_flow("flow says hi")
		name, _ = self._start("wamid.RP1")
		run_flow(frappe.db.get_value("Gateway Event", name, "flow_run"))
		event = frappe.get_doc("Gateway Event", name)
		self.assertEqual(event.status, "Succeeded", event.error_message)
		posts = self._text_posts()
		self.assertEqual(len(posts), 1, self.meta.calls)
		self.assertEqual(posts[0]["body"]["text"]["body"], "flow says hi")
		self.assertTrue(event.reply_message_id)
		self.assertEqual(self.agent_calls, [])

	def test_completion_hook_replies_only_once_if_the_run_is_replayed(self):
		self._reply_flow()
		name, _ = self._start("wamid.RP2")
		run_name = frappe.db.get_value("Gateway Event", name, "flow_run")
		run_flow(run_name)
		run_flow(run_name)
		self.assertEqual(len(self._text_posts()), 1)

	def test_flow_without_output_completes_the_event_without_a_reply(self):
		self._grant_flow_access()
		flow_id = self._flow({"action": "list_templates"})
		self._route_gateway_a_to(flow_id)
		name, _ = self._start("wamid.NR1")
		run_flow(frappe.db.get_value("Gateway Event", name, "flow_run"))
		event = frappe.get_doc("Gateway Event", name)
		self.assertEqual(event.status, "Succeeded", event.error_message)
		self.assertFalse(event.reply_message_id)

	def test_failed_flow_run_fails_the_event(self):
		self._grant_flow_access()
		flow_id = self._flow({"action": "send_message", "to": fs.SENDER, "message": "x"})
		self._route_gateway_a_to(flow_id)
		name, _ = self._start("wamid.FL1")
		run_name = frappe.db.get_value("Gateway Event", name, "flow_run")
		frappe.db.set_value("Flow Run", run_name, "status", "Queued")
		with patch("huf.ai.flow.engine._execute_loop", side_effect=RuntimeError("boom")):
			run_flow(run_name)
		event = frappe.get_doc("Gateway Event", name)
		self.assertEqual(event.status, "Failed")
		self.assertIn("boom", event.error_message)

	def test_requeued_event_does_not_start_a_second_flow_run(self):
		flow_id = self._reply_flow()
		name, _ = self._start("wamid.DB1")
		frappe.db.set_value("Gateway Event", name, "status", "Queued")  # reaper / retry re-queues it
		process_gateway_event(name)
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.count("Flow Run", {"flow_id": flow_id}), 1)
		self.assertEqual(frappe.db.get_value("Gateway Event", name, "status"), "Running")

	def test_trigger_payload_is_enriched(self):
		flow_id = self._reply_flow()
		name, _ = self._start("wamid.PL1", "what time is it")
		event = frappe.get_doc("Gateway Event", name)
		payload = json.loads(frappe.get_doc("Flow Run", event.flow_run).trigger_payload)
		self.assertEqual(payload["gateway"], self.gateway_a.name)
		self.assertEqual(payload["provider"], "WhatsApp")
		self.assertEqual(payload["sender_id"], event.sender_id)
		self.assertEqual(payload["wa_id"], fs.SENDER)
		self.assertEqual(payload["conversation_id"], event.conversation_id)
		self.assertEqual(payload["message_id"], "wamid.PL1")
		self.assertEqual(payload["text"], "what time is it")
		self.assertEqual(payload["message"], "what time is it")
		self.assertEqual(payload["message_type"], "text")
		self.assertEqual(payload["attachments"], [])
		self.assertIsNone(payload["reply_to_message_id"])
		self.assertEqual(flow_id, event.target_flow)

	def test_media_is_saved_and_listed_in_the_payload(self):
		self._reply_flow()
		with patch("huf.ai.gateway_service._save_whatsapp_media", return_value=["/private/files/a.jpg"]):
			name, _ = self._start("wamid.MD1", "see attached")
		payload = json.loads(frappe.get_doc("Flow Run", frappe.db.get_value("Gateway Event", name, "flow_run")).trigger_payload)
		self.assertEqual(payload["attachments"], ["/private/files/a.jpg"])

	def test_waiting_flow_event_is_not_reaped(self):
		from huf.ai.gateway_service import reap_stuck_gateway_events

		self._reply_flow()
		name, _ = self._start("wamid.WT1")
		run_name = frappe.db.get_value("Gateway Event", name, "flow_run")
		frappe.db.set_value("Flow Run", run_name, "status", "Waiting User")
		frappe.db.sql("update `tabGateway Event` set modified = '2000-01-01 00:00:00' where name = %s", name)
		reap_stuck_gateway_events()
		self.assertEqual(frappe.db.get_value("Gateway Event", name, "status"), "Running")
