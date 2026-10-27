"""R2: the solution is stamped on Huf-owned rows (Agent Conversation, Agent Run, Send Key)."""

import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai import gateway_service as gsvc
from huf.ai.conversation_manager import ConversationManager
from huf.ai.solutions import assignment as a
from huf.ai.solutions.tests import test_gateway_routing_integration as routing
from huf.ai.solutions.tests._fixtures import make_agent, make_binding, make_gateway, make_solution, uid
from huf.ai.whatsapp import send_keys


def make_run(agent, solution=None, channel="gateway:x", external="u1"):
	"""A queued Agent Run created through the real run_agent_sync (the queue is stubbed)."""
	from huf.ai.agent.integration import run_agent_sync

	kwargs = {"solution": solution} if solution else {}
	with patch("frappe.enqueue"), patch("huf.ai.agent.integration.safe_commit"):
		res = run_agent_sync(agent_name=agent, prompt="hi", channel_id=channel, external_id=external, **kwargs)
	return res["agent_run_id"]


class TestConversationStamp(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.agent = make_agent()
		self.gw = make_gateway()
		self.sol = make_solution()
		self.addCleanup(frappe.db.rollback)

	def cm(self, ext="u1", channel=None):
		return ConversationManager(self.agent, channel=channel or f"gateway:{self.gw.name}", external_id=ext)

	def test_create_new_stamped_from_assignment(self):
		a.set_pin(self.gw.name, "u1", self.sol.name, "rule")
		conv = self.cm().create_new_conversation()
		self.assertEqual(conv.solution, self.sol.name)
		self.assertEqual(frappe.db.get_value("Agent Conversation", conv.name, "solution"), self.sol.name)

	def test_get_or_create_stamped_from_assignment(self):
		a.set_pin(self.gw.name, "u1", self.sol.name, "rule")
		conv = self.cm().get_or_create_conversation()
		self.assertEqual(frappe.db.get_value("Agent Conversation", conv.name, "solution"), self.sol.name)

	def test_explicit_solution_wins_over_assignment(self):
		other = make_solution()
		a.set_pin(self.gw.name, "u1", self.sol.name, "rule")
		conv = self.cm().create_new_conversation(solution=other.name)
		self.assertEqual(conv.solution, other.name)
		conv2 = self.cm("u2").get_or_create_conversation(solution=other.name)
		self.assertEqual(conv2.solution, other.name)

	def test_no_assignment_means_no_solution(self):
		conv = self.cm().create_new_conversation()
		self.assertFalse(conv.solution)

	def test_non_gateway_channel_never_looks_up_assignment(self):
		a.set_pin(self.gw.name, "u1", self.sol.name, "rule")
		with patch.object(a, "current_solution") as cs:
			conv = self.cm(channel="api").create_new_conversation()
		cs.assert_not_called()
		self.assertFalse(conv.solution)

	def test_lookup_key_unchanged_and_existing_conversation_not_restamped(self):
		other = make_solution()
		a.set_pin(self.gw.name, "u1", self.sol.name, "rule")
		first = self.cm().get_or_create_conversation()
		self.assertEqual(first.session_id, f"gateway:{self.gw.name}:u1")
		a.set_pin(self.gw.name, "u1", other.name, "handoff")
		second = self.cm().get_or_create_conversation()
		self.assertEqual(second.name, first.name)
		self.assertEqual(frappe.db.get_value("Agent Conversation", first.name, "solution"), self.sol.name)


class TestRunStamp(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.agent = make_agent()
		self.sol = make_solution()
		self.addCleanup(frappe.db.rollback)

	def test_run_stamped(self):
		run = make_run(self.agent, self.sol.name)
		self.assertEqual(frappe.db.get_value("Agent Run", run, "solution"), self.sol.name)
		conv = frappe.db.get_value("Agent Run", run, "conversation")
		self.assertEqual(frappe.db.get_value("Agent Conversation", conv, "solution"), self.sol.name)

	def test_run_without_solution_unchanged(self):
		run = make_run(self.agent, None)
		self.assertFalse(frappe.db.get_value("Agent Run", run, "solution"))

	def test_unknown_solution_is_ignored(self):
		run = make_run(self.agent, f"no-such-{uid()}")
		self.assertFalse(frappe.db.get_value("Agent Run", run, "solution"))


class TestGatewayServicePassesSolution(routing._Base):
	def process(self, event_name):
		calls = []

		def fake(run_fn, **kw):
			calls.append(kw)
			return {"success": False, "error": "stub"}

		with patch.object(gsvc, "_run_agent_serialised", side_effect=fake), patch.object(gsvc, "_commit_unless_testing"):
			try:
				gsvc._process_gateway_event(event_name)
			except Exception:
				pass
		return calls

	def test_event_solution_reaches_run_agent_sync(self):
		s, _ = self.sol("Orders", value="order", priority=1)
		r = self.ingest("my order")
		calls = self.process(r["event_name"])
		self.assertEqual(len(calls), 1)
		self.assertEqual(calls[0].get("solution"), s)

	def test_event_without_solution_passes_none(self):
		make_binding(self.gw, self.agent, match_type="Any conversation", priority=1)
		r = self.ingest("hello")
		calls = self.process(r["event_name"])
		self.assertEqual(len(calls), 1)
		self.assertIsNone(calls[0].get("solution"))


class TestSendKeyStamp(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.agent = make_agent()
		self.sol = make_solution()
		p = patch.object(frappe.db, "commit")
		p.start()
		self.addCleanup(p.stop)
		self.addCleanup(frappe.db.rollback)

	def claim(self, run, key):
		self.assertTrue(send_keys._claim("GW-R2", key, "send_message", run, "15550001111"))
		return frappe.db.get_value("WhatsApp Send Key", key, ["solution", "agent_run"], as_dict=True)

	def test_claim_stamps_run_solution(self):
		run = make_run(self.agent, self.sol.name)
		row = self.claim(run, "k" * 16 + uid())
		self.assertEqual((row.solution, row.agent_run), (self.sol.name, run))

	def test_claim_without_solution_or_run(self):
		run = make_run(self.agent, None)
		self.assertFalse(self.claim(run, "a" * 16 + uid()).solution)
		self.assertFalse(self.claim("", "b" * 16 + uid()).solution)
		self.assertFalse(self.claim("RUN-DOES-NOT-EXIST", "c" * 16 + uid()).solution)

	def test_derive_key_unchanged_by_solution(self):
		run = make_run(self.agent, self.sol.name)
		other = make_run(self.agent, None)
		k1 = send_keys.derive_key("GW", run, "call1", "send_message", {"to": "15550001111", "text": "x"})
		k2 = send_keys.derive_key("GW", run, "call1", "send_message", {"to": "15550001111", "text": "x"})
		self.assertEqual(k1, k2)
		self.assertNotEqual(k1, send_keys.derive_key("GW", other, "call1", "send_message", {"to": "15550001111", "text": "x"}))
