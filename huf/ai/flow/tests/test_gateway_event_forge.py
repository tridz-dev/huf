"""A caller must not be able to name a Gateway Event and borrow its trusted WhatsApp send path.

``trigger_payload.gateway_event`` binds a flow run to a Gateway and its contact (``engine._bound_gateway``),
so only gateway ingestion may set it. A real signed inbound message creates the Gateway Event here; the runs
that try to borrow it must send nothing.
"""

import json

from huf.ai.flow import api as flow_api
from huf.ai.flow import engine
from huf.ai.flow.tests import test_flow_whatsapp_gateway_trigger as base
from huf.ai.tools import whatsapp


class TestGatewayEventForge(base.TestFlowWhatsAppGatewayTrigger):
	# Inherit the fixture only, not its tests.
	for _name in [n for n in dir(base.TestFlowWhatsAppGatewayTrigger) if n.startswith("test_")]:
		locals()[_name] = None
	del _name

	def setUp(self):
		super().setUp()
		self.assertTrue(self._inbound("A", "wamid.VICTIM", "hi")["success"])
		self.victim = self._events(self.gateway_a, "wamid.VICTIM")[0]
		self.flow_id = self._flow({"action": "send_message", "message": "forged send"})
		base.frappe.set_user("Administrator")

	def _bound(self, run_name):
		with engine._bound_gateway(base.frappe.get_doc("Agent Flow Run", run_name), "FLOWRUN-1"):
			return whatsapp._trusted_gateway.get(), whatsapp._trusted_contact.get()

	def _assert_unbound(self, run_name):
		payload = json.loads(base.frappe.db.get_value("Agent Flow Run", run_name, "trigger_payload") or "{}")
		self.assertEqual(self._bound(run_name), ("", ""))
		return payload

	def test_manual_run_cannot_send_through_a_forged_event(self):
		result = flow_api.run_flow(self.flow_id, {"gateway_event": self.victim})
		self.assertEqual(self._text_posts(), [], "a forged gateway_event reached the victim contact")
		self.assertNotIn("gateway_event", self._assert_unbound(result["flow_run_id"]))

	def test_no_caller_path_stores_the_key(self):
		for trigger_type in ("Manual", "Webhook", "App"):
			payload = {"gateway_event": self.victim, "keep": 1}
			run = engine.create_flow_run(self.flow_id, payload, trigger_type=trigger_type, ignore_permissions=True)
			stored = self._assert_unbound(run.name)
			self.assertEqual(stored, {"keep": 1})
			self.assertNotIn("gateway_event", json.loads(run.context_json))

	def test_resume_input_cannot_add_the_key(self):
		self.assertEqual(engine.strip_reserved_keys({"gateway_event": self.victim, "a": 1}), {"a": 1})

	def test_a_row_written_with_someone_elses_event_binds_nothing(self):
		# Run roles can write run rows directly, past create_flow_run.
		run = engine.create_flow_run(self.flow_id, {}, ignore_permissions=True)
		run.db_set("trigger_payload", json.dumps({"gateway_event": self.victim}))
		self.assertEqual(self._bound(run.name), ("", ""))

	def test_ingestion_sets_the_key_and_binds_the_run(self):
		run = engine.create_flow_run(
			self.flow_id, {}, trigger_type="Gateway", ignore_permissions=True, gateway_event=self.victim
		)
		base.frappe.db.set_value("Gateway Event", self.victim, "flow_run", run.name)
		self.assertEqual(json.loads(run.trigger_payload)["gateway_event"], self.victim)
		self.assertEqual(self._bound(run.name)[0], self.gateway_a.name)
