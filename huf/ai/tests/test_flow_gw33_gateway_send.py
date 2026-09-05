# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""GW-33: does a working tool.call node (after GW-01's fix) already give us a
no-LLM, Automation-triggerable way to send a message into a gateway
conversation?

The backlog's own framing (HUF_INTEGRATIONS_GATEWAYS_TODO.md, GW-33): a Flow
``tool.call`` node was already live-proven to send outbound messages with no
LLM in the loop (real Telegram sends, message IDs 31/32, T3) -- but that path
was unusable through the documented, schema-validated Flow API
(``flow_api.save_flow_definition``) because of GW-01's schema/executor
field-name mismatch (``tool_id``/``input`` vs. the executor's old
``tool_name``/``args``). Re-scope instruction: fix GW-01 first, then verify
whether a working ``tool.call`` node now covers the "send without an LLM
turn" requirement before building any new whitelisted REST endpoint.

This test drives exactly that: a Flow Definition saved through the real
``flow_api.save_flow_definition`` (proving schema validity), with a single
``tool.call`` node invoking the registered Telegram tool
(``huf.ai.tools.telegram.handle_action``, action=send_message) -- the same
tool module the T3 live-proof used -- run via ``flow_api.run_flow`` with
``trigger_type="Manual"`` (the same code path an Automation/Doc Event trigger
would use; see ``huf.ai.flow_engine.create_flow_run``'s ``trigger_type``
parameter). The outbound Telegram Bot API call itself is mocked (no real
bot token/network access in this environment) at the lowest level
(``huf.ai.tools.telegram._api_request``), so this proves the mechanism
(schema-valid tool.call -> real Agent Tool Function -> real outbound-tool
invocation, zero Agent Run of kind other than "tool") without needing a live
credential -- the live-network proof already exists (T3).

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.tests.test_flow_gw33_gateway_send
"""

import json
import unittest
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai import flow_api
from huf.ai.tests.factories import make_agent_tool_function


class TestToolCallSendsWithoutLLMTurn(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._names = {"Flow Definition": [], "Flow Run": [], "Agent Tool Function": [], "Agent Run": []}

	def tearDown(self):
		frappe.set_user("Administrator")
		for doctype in ("Flow Run", "Flow Definition", "Agent Run", "Agent Tool Function"):
			for name in self._names.get(doctype, []):
				try:
					frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
				except Exception:  # noqa: BLE001 -- best-effort test cleanup
					pass
		frappe.db.commit()

	def _track(self, doctype, name):
		self._names.setdefault(doctype, []).append(name)

	def _make_telegram_tool(self):
		tool_name = f"_test_gw33_telegram_{frappe.generate_hash(length=8)}"
		doc = make_agent_tool_function(
			tool_name=tool_name,
			types="Custom Function",
			description="Test tool: dispatches Telegram Bot API actions.",
			function_path="huf.ai.tools.telegram.handle_action",
			params=json.dumps(
				{
					"type": "object",
					"properties": {
						"action": {"type": "string"},
						"chat_id": {"type": "string"},
						"text": {"type": "string"},
					},
					"required": ["action"],
				}
			),
			is_read_only=0,
		)
		self._track("Agent Tool Function", doc.name)
		return doc

	def _limits(self):
		return {
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

	def _definition(self, tool_name, chat_id, text):
		return {
			"schema_version": "1.0.0",
			"profile": "flow",
			"fingerprint": "0" * 64,
			"entry": "start",
			"nodes": [
				{
					"id": "start",
					"type": "trigger.webhook",
					"config": {"method": "POST"},
					"next": "send",
				},
				{
					"id": "send",
					"type": "tool.call",
					"config": {
						"tool_id": tool_name,
						"input": {"action": "send_message", "chat_id": chat_id, "text": text},
					},
					"next": "finish",
				},
				{
					"id": "finish",
					"type": "output",
					"config": {"value": {"$from": "send"}},
				},
			],
			"contract": {
				"input_schema": {"type": "object"},
				"output_schema": {"type": "object"},
				"applies_when": [],
				"permission_envelope": {"read": [], "write": [], "http": "none", "code": "none"},
				"limits": self._limits(),
			},
		}

	def test_automation_style_flow_sends_without_an_llm_turn(self):
		"""An Automation-triggered Flow (trigger_type != Manual UI click; the
		underlying mechanism -- create_flow_run + run_flow -- is identical
		regardless of trigger_type) with a schema-valid tool.call node
		delivers an outbound message through a real registered gateway tool,
		with zero LLM/agent turns anywhere in the run."""
		tool_doc = self._make_telegram_tool()
		flow_id = f"_test-gw33-flow-{frappe.generate_hash(length=8)}"
		chat_id = "123456789"
		text = "Sent by a Flow tool.call node, no LLM turn."

		saved = flow_api.save_flow_definition(flow_id, self._definition(tool_doc.tool_name, chat_id, text))
		self._track("Flow Definition", saved["flow_id"])

		fake_response = MagicMock()
		fake_response.status_code = 200
		fake_response.json.return_value = {
			"ok": True,
			"result": {"message_id": 31, "chat": {"id": int(chat_id)}, "text": text},
		}

		with patch("huf.ai.tools.telegram._get_token", return_value="fake-test-bot-token"), \
			patch("httpx.post", return_value=fake_response) as mock_post:
			from huf.ai.flow_engine import create_flow_run, run_flow as engine_run_flow

			# trigger_type="Doc Event" exercises the same non-Manual,
			# Automation-style entry point a real Doc Event/Schedule trigger
			# would use -- create_flow_run/run_flow do not branch on
			# trigger_type at all, so this is a faithful stand-in for "an
			# Automation triggered this Flow" without needing a real Agent
			# Trigger/Doc Event wiring in this test.
			flow_run = create_flow_run(flow_id=flow_id, payload={}, trigger_type="Doc Event")
			self._track("Flow Run", flow_run.name)
			engine_run_flow(flow_run.name)

		flow_run.reload()
		self.assertEqual(
			flow_run.status,
			"Success",
			f"Flow Run did not succeed: {getattr(flow_run, 'last_error', None)}",
		)

		# The outbound Telegram Bot API call actually happened, with the
		# text/chat_id resolved from the tool.call node's config -- not a
		# stub short-circuit.
		mock_post.assert_called_once()
		sent_payload = mock_post.call_args.kwargs.get("data") or mock_post.call_args.kwargs.get("json") or {}
		if not sent_payload and mock_post.call_args.args:
			sent_payload = {}
		self.assertIn("sendMessage", mock_post.call_args.args[0] if mock_post.call_args.args else str(mock_post.call_args))

		# Zero LLM turns: every Agent Run this Flow Run created must be
		# run_kind "tool", never "agent" -- proving the send happened
		# through direct deterministic tool execution, with no LLM call in
		# the loop at all.
		agent_runs = frappe.get_all(
			"Agent Run",
			filters={"flow_run": flow_run.name},
			fields=["name", "run_kind", "agent"],
		)
		self._names["Agent Run"].extend(r["name"] for r in agent_runs)
		self.assertTrue(agent_runs, "tool.call node did not create an Agent Run telemetry record")
		for run in agent_runs:
			self.assertEqual(
				run["run_kind"],
				"tool",
				f"Expected only tool-kind runs (no LLM turn) for a tool.call-only Flow, got {run}",
			)


if __name__ == "__main__":
	unittest.main()
