"""A caller must not be able to name a Gateway Event and borrow its trusted WhatsApp send path.

``trigger_payload.gateway_event`` binds a flow run to that event's Gateway and contact
(``engine._bound_gateway``): no Gateway permission is asked and the contact is inside the recipient scope.
So only gateway ingestion may set it. Only the provider call is faked.
"""

import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow import api as flow_api
from huf.ai.flow import engine
from huf.ai.tools import whatsapp
from huf.testing.factories import make_agent_tool_function

VICTIM = "15550001111"
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


class TestGatewayEventForge(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		sfx = frappe.generate_hash(length=8)
		settings = frappe.get_doc(
			{
				"doctype": "Integration Settings",
				"service": "whatsapp",
				"credentials": [
					{"key": "phone_number_id", "value": "999" + sfx},
					{"key": "access_token", "value": "tok"},
					{"key": "webhook_verify_token", "value": "verify"},
					{"key": "app_secret", "value": "sec"},
				],
			}
		).insert(ignore_permissions=True)
		self.gateway = frappe.get_doc(
			{
				"doctype": "Gateway",
				"gateway_name": f"Forge {sfx}",
				"provider": "WhatsApp",
				"is_enabled": 1,
				"integration_settings": settings.name,
				"execution_user": "Administrator",
				"direct_policy": "Allow list",
			}
		).insert(ignore_permissions=True).name
		# an earlier real inbound message from somebody else
		self.event = frappe.get_doc(
			{
				"doctype": "Gateway Event",
				"gateway": self.gateway,
				"idempotency_key": f"forge-{sfx}",
				"sender_id": VICTIM,
				"status": "Succeeded",
			}
		).insert(ignore_permissions=True).name
		self.sent = MagicMock(return_value=json.dumps({"success": True, "data": {"message_id": "wamid.X"}}))
		for target, kwargs in (("_send_message", {"new": self.sent}), ("_has_entry", {"return_value": True})):
			patcher = patch.object(whatsapp, target, **kwargs)
			patcher.start()
			self.addCleanup(patcher.stop)
		self.flow_id = self._flow(sfx)

	def _flow(self, sfx):
		tool = make_agent_tool_function(
			tool_name=f"_test_wa_forge_{sfx}",
			types="App Provided",
			description="Test tool: WhatsApp actions.",
			function_path="huf.ai.tools.whatsapp.handle_action",
			params=json.dumps(
				{
					"type": "object",
					"properties": {"action": {"type": "string"}, "message": {"type": "string"}},
					"required": ["action"],
				}
			),
			is_read_only=0,
		)
		flow_id = f"_test-wa-forge-{sfx}"
		secret = "test-webhook-secret-0123456789abcdef"
		flow_api.save_flow_definition(
			flow_id,
			{
				"schema_version": "1.0.0",
				"profile": "flow",
				"fingerprint": "0" * 64,
				"entry": "start",
				"nodes": [
					{"id": "start", "type": "trigger.webhook", "config": {"method": "POST", "secret": secret}, "next": "send"},
					{
						"id": "send",
						"type": "tool.call",
						# no recipient: it is filled with the bound run's contact
						"config": {"tool_id": tool.tool_name, "input": {"action": "send_message", "message": "forged"}},
					},
				],
				"contract": {
					"input_schema": {"type": "object"},
					"output_schema": {"type": "object"},
					"applies_when": [],
					"permission_envelope": {"read": [], "write": [], "http": "none", "code": "none"},
					"limits": LIMITS,
				},
			},
		)
		frappe.db.set_value("Flow Definition", flow_id, "status", "Active")
		return flow_id

	def _bound(self, run_name):
		with engine._bound_gateway(frappe.get_doc("Agent Flow Run", run_name), "FLOWRUN-1"):
			return whatsapp._trusted_gateway.get(), whatsapp._trusted_contact.get()

	def test_manual_run_cannot_send_through_a_forged_event(self):
		result = flow_api.run_flow(self.flow_id, {"gateway_event": self.event})
		self.assertEqual(
			[c.args[0].get("to") for c in self.sent.call_args_list], [], "a forged gateway_event reached its contact"
		)
		self.assertEqual(self._bound(result["flow_run_id"]), ("", ""))

	def test_no_caller_payload_stores_the_key(self):
		for trigger_type in ("Manual", "Webhook", "App"):
			run = engine.create_flow_run(
				self.flow_id, {"gateway_event": self.event, "keep": 1}, trigger_type=trigger_type, ignore_permissions=True
			)
			self.assertEqual(json.loads(run.trigger_payload), {"keep": 1})
			self.assertEqual(json.loads(run.context_json), {"keep": 1})

	def test_resume_input_cannot_add_the_key(self):
		self.assertEqual(engine.strip_reserved_keys({"gateway_event": self.event, "a": 1}), {"a": 1})

	def test_a_row_naming_another_runs_event_binds_nothing(self):
		# run roles can write run rows directly, past create_flow_run
		run = engine.create_flow_run(self.flow_id, {}, ignore_permissions=True)
		run.db_set("trigger_payload", json.dumps({"gateway_event": self.event}))
		self.assertEqual(self._bound(run.name), ("", ""))

	def test_ingestion_argument_sets_the_key_and_binds_the_run(self):
		run = engine.create_flow_run(self.flow_id, {}, ignore_permissions=True, gateway_event=self.event)
		frappe.db.set_value("Gateway Event", self.event, "flow_run", run.name)
		self.assertEqual(json.loads(run.trigger_payload), {"gateway_event": self.event})
		self.assertEqual(self._bound(run.name), (self.gateway, VICTIM))
