import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from huf.ai.solutions import assignment, handoff
from huf.ai.solutions.tests._fixtures import make_agent, make_gateway, make_solution


def make_flow_solution():
	import uuid

	fid = uuid.uuid4().hex[:8]
	flow = frappe.get_doc(
		{"doctype": "Flow Definition", "flow_id": f"h-{fid}", "flow_name": f"H {fid}", "definition_json": "{}"}
	)
	flow.flags.ignore_validate = True
	flow.insert(ignore_permissions=True)
	return make_solution(primary_target_type="Flow", primary_flow=flow.name)


def _agent_solution(**kw):
	return make_solution(primary_target_type="Agent", primary_agent=make_agent(), **kw)


def _seed_source(sol, gateway, key, texts):
	"""A source conversation with alternating user/agent messages."""
	from huf.ai.conversation_manager import ConversationManager

	cm = ConversationManager(agent_name=sol.primary_agent, channel=f"gateway:{gateway}", external_id=key)
	conv = cm.get_or_create_conversation()
	for i, t in enumerate(texts):
		cm.add_message(conv, "user" if i % 2 == 0 else "agent", t, None, None, sol.primary_agent)
	return conv


def _system_notes(agent, gateway, key):
	conv = frappe.get_all(
		"Agent Conversation",
		filters={"agent": agent, "session_id": f"gateway:{gateway}:{key}"},
		pluck="name",
	)
	if not conv:
		return []
	return frappe.get_all(
		"Agent Message", filters={"conversation": ["in", conv], "role": "system"}, pluck="content"
	)


class TestHandoff(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.gw = make_gateway(pin_ttl_hours=5).name
		self.src = _agent_solution()
		self.dst = _agent_solution()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_rewrites_pin_and_ttl(self):
		assignment.set_pin(self.gw, "c1", self.src.name, "rule", ttl_hours=1)
		out = handoff.reassign(self.gw, "c1", self.dst.name)
		pin = assignment.get_pin(self.gw, "c1")
		self.assertEqual(pin["solution"], self.dst.name)
		self.assertEqual(pin["set_by"], "handoff")
		self.assertAlmostEqual((pin["expires_at"] - now_datetime()).total_seconds(), 5 * 3600, delta=60)
		self.assertEqual(out["pin"]["solution"], self.dst.name)
		self.assertFalse(out["note_added"])

	def test_refuses_paused_test_mode_missing(self):
		paused = make_solution(status="Paused")
		for target, code in ((paused.name, "invalid_payload"), ("nope-xyz", "not_found")):
			with self.assertRaises(handoff.HandoffError) as cm:
				handoff.reassign(self.gw, "c1", target)
			self.assertEqual(cm.exception.code, code)
		test_sol = make_solution(test_mode=1)
		with self.assertRaises(handoff.HandoffError):
			handoff.reassign(self.gw, "c1", test_sol.name)
		self.assertIsNone(assignment.get_pin(self.gw, "c1"))

	def test_note_injected_once_into_target(self):
		assignment.set_pin(self.gw, "c1", self.src.name, "rule")
		_seed_source(self.src, self.gw, "c1", ["hello", "hi there", "need refund"])
		out = handoff.reassign(self.gw, "c1", self.dst.name, note_messages=2)
		self.assertTrue(out["note_added"])
		notes = _system_notes(self.dst.primary_agent, self.gw, "c1")
		self.assertEqual(len(notes), 1)
		self.assertIn("need refund", notes[0])
		self.assertIn("hi there", notes[0])
		self.assertNotIn("hello", notes[0])

	def test_note_skipped_without_target_agent(self):
		flow_target = make_solution()  # no primary agent
		assignment.set_pin(self.gw, "c1", self.src.name, "rule")
		_seed_source(self.src, self.gw, "c1", ["hello"])
		out = handoff.reassign(self.gw, "c1", flow_target.name, note_messages=3)
		self.assertFalse(out["note_added"])
		self.assertEqual(out["note_skipped_reason"], "target_has_no_primary_agent")
		self.assertEqual(assignment.current_solution(self.gw, "c1"), flow_target.name)

	def test_flow_target_changes_assignment_only(self):
		flow = make_flow_solution()
		out = handoff.reassign(self.gw, "c1", flow.name, note_messages=2)
		self.assertEqual(assignment.current_solution(self.gw, "c1"), flow.name)
		self.assertFalse(out["note_added"])

	def test_group_style_space_key(self):
		group = "120363025246125486@g.us"
		assignment.set_pin(self.gw, group, self.src.name, "rule")
		_seed_source(self.src, self.gw, group, ["group q"])
		out = handoff.reassign(self.gw, group, self.dst.name, note_messages=1)
		self.assertTrue(out["note_added"])
		self.assertEqual(assignment.current_solution(self.gw, group), self.dst.name)
		self.assertEqual(len(_system_notes(self.dst.primary_agent, self.gw, group)), 1)

	def test_api_permission_denied_for_non_admin(self):
		frappe.set_user("Guest")
		out = handoff.reassign_conversation(self.gw, "c1", self.dst.name)
		self.assertEqual(out["error"]["code"], "not_permitted")
		self.assertIn("message", out["error"])
		frappe.set_user("Administrator")
		self.assertIsNone(assignment.get_pin(self.gw, "c1"))

	def test_api_errors_and_success(self):
		self.assertEqual(handoff.reassign_conversation("no-gw", "c1", self.dst.name)["error"]["code"], "not_found")
		self.assertEqual(handoff.reassign_conversation(self.gw, "c1", "nope-xyz")["error"]["code"], "not_found")
		paused = make_solution(status="Paused")
		self.assertEqual(handoff.reassign_conversation(self.gw, "c1", paused.name)["error"]["code"], "invalid_payload")
		out = handoff.reassign_conversation(self.gw, "c1", self.dst.name, "0")
		self.assertNotIn("error", out)
		self.assertEqual(out["pin"]["solution"], self.dst.name)
