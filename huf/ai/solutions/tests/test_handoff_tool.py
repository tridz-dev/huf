import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.solutions import assignment
from huf.ai.solutions.tests._fixtures import make_agent, make_binding, make_gateway, make_solution
from huf.ai.tools import handoff as tool
from huf.ai.tools._registry import ALL_INTEGRATION_TOOLS

def make_flow_solution():
	import uuid

	fid = uuid.uuid4().hex[:8]
	flow = frappe.get_doc(
		{"doctype": "Flow Definition", "flow_id": f"h-{fid}", "flow_name": f"H {fid}", "definition_json": "{}"}
	)
	flow.flags.ignore_validate = True
	flow.insert(ignore_permissions=True)
	return make_solution(primary_target_type="Flow", primary_flow=flow.name)


_real_get_value = frappe.db.get_value


def _fake_get_value(conv_name):
	def inner(doctype, *a, **kw):
		if doctype == "Agent Run":
			return conv_name
		return _real_get_value(doctype, *a, **kw)

	return inner


class TestHandoffTool(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.gw = make_gateway().name
		self.src = make_solution(primary_target_type="Agent", primary_agent=make_agent())
		self.dst = make_solution(primary_target_type="Agent", primary_agent=make_agent())
		make_binding(self.gw, solution=self.dst.name, match_type="Catch-all", agent=make_agent())
		self.addCleanup(setattr, frappe.flags, "huf_current_agent_run_id", None)

	def tearDown(self):
		frappe.db.rollback()

	def _conversation(self, channel, external_id):
		return frappe.get_doc(
			{
				"doctype": "Agent Conversation",
				"title": "t",
				"agent": self.src.primary_agent,
				"session_id": f"{channel}:{external_id}",
				"channel": channel,
				"external_id": external_id,
				"is_active": 1,
			}
		).insert(ignore_permissions=True)

	def _call(self, conv, **kwargs):
		frappe.flags.huf_current_agent_run_id = "RUN-1"
		with patch.object(frappe.db, "get_value", _fake_get_value(conv.name if conv else None)):
			return json.loads(tool.handle_handoff_to_solution(**kwargs))

	def test_registered(self):
		reg = {t["tool_name"]: t for t in ALL_INTEGRATION_TOOLS}
		self.assertEqual(reg["handoff_to_solution"]["function_path"], "huf.ai.tools.handoff.handle_handoff_to_solution")

	def test_resolves_context_and_reassigns(self):
		conv = self._conversation(f"gateway:{self.gw}", "chat-9")
		out = self._call(conv, solution=self.dst.name, reason="billing")
		self.assertTrue(out["success"])
		pin = assignment.get_pin(self.gw, "chat-9")
		self.assertEqual(pin["solution"], self.dst.name)
		self.assertEqual(pin["set_by"], "handoff")

	def test_title_resolves(self):
		conv = self._conversation(f"gateway:{self.gw}", "chat-9")
		out = self._call(conv, solution=self.dst.title)
		self.assertTrue(out["success"])

	def test_group_space_key(self):
		conv = self._conversation(f"gateway:{self.gw}", "120363@g.us")
		self.assertTrue(self._call(conv, solution=self.dst.name)["success"])
		self.assertEqual(assignment.current_solution(self.gw, "120363@g.us"), self.dst.name)

	def test_refuses_outside_gateway_run(self):
		frappe.flags.huf_current_agent_run_id = None
		out = json.loads(tool.handle_handoff_to_solution(solution=self.dst.name))
		self.assertEqual(out["error"], "gateway_context_required")
		chat = self._conversation("Chat", "x")
		out = self._call(chat, solution=self.dst.name)
		self.assertEqual(out["error"], "gateway_context_required")

	def test_refuses_not_live_and_missing(self):
		conv = self._conversation(f"gateway:{self.gw}", "chat-9")
		paused = make_solution(status="Paused")
		self.assertEqual(self._call(conv, solution=paused.name)["error"], "invalid_payload")
		self.assertEqual(self._call(conv, solution="nope-xyz")["error"], "not_found")
		self.assertEqual(self._call(conv, solution="")["error"], "invalid_payload")
		self.assertIsNone(assignment.get_pin(self.gw, "chat-9"))

	def test_flow_target_assignment_only(self):
		flow = make_flow_solution()
		make_binding(self.gw, solution=flow.name, match_type="Catch-all", agent=make_agent())
		conv = self._conversation(f"gateway:{self.gw}", "chat-9")
		self.assertTrue(self._call(conv, solution=flow.name)["success"])
		self.assertEqual(assignment.current_solution(self.gw, "chat-9"), flow.name)

	def test_target_on_other_gateway_rejected(self):
		other = make_gateway().name
		far = make_solution(primary_target_type="Agent", primary_agent=make_agent())
		make_binding(other, solution=far.name, match_type="Catch-all", agent=make_agent())
		conv = self._conversation(f"gateway:{self.gw}", "chat-9")
		out = self._call(conv, solution=far.name)
		self.assertEqual(out["error"], "not_on_gateway")
		self.assertNotIn(far.title, json.dumps(out))
		self.assertIsNone(assignment.get_pin(self.gw, "chat-9"))

	def test_pin_key_follows_router_conversation_id(self):
		frappe.get_doc(
			{
				"doctype": "Gateway Event",
				"gateway": self.gw,
				"idempotency_key": f"pk-{self.gw}",
				"status": "Recorded",
				"sender_id": "sender-1",
				"conversation_id": "conv-1",
				"thread_id": "thread-1",
			}
		).insert(ignore_permissions=True, ignore_links=True)
		conv = self._conversation(f"gateway:{self.gw}", "thread-1")
		self.assertTrue(self._call(conv, solution=self.dst.name)["success"])
		self.assertEqual(assignment.current_solution(self.gw, "conv-1"), self.dst.name)
		self.assertIsNone(assignment.get_pin(self.gw, "thread-1"))
