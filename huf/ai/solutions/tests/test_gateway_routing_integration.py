"""R1c: the solution router wired into the real inbound pipeline (_continue_ingest)."""

import secrets
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai import gateway_service as gsvc
from huf.ai.solutions import assignment as a
from huf.ai.solutions.tests._fixtures import make_agent, make_binding, make_solution


class _Base(IntegrationTestCase):
	provider = "Telegram"

	def setUp(self):
		frappe.set_user("Administrator")
		self.suffix = secrets.token_hex(3)
		self.n = 0
		self.agent = make_agent()
		self.adapter = MagicMock()
		p = patch("huf.ai.gateway_webhook.get_gateway_adapter", return_value=self.adapter)
		p.start()
		self.addCleanup(p.stop)
		e = patch.object(gsvc.frappe, "enqueue")
		self.enqueue = e.start()
		self.addCleanup(e.stop)
		self.gw = self.make_gateway()

	def tearDown(self):
		frappe.db.rollback()

	def make_gateway(self, **kw):
		name = f"r1c {self.suffix}"
		frappe.get_doc(
			{"doctype": "Gateway", "gateway_name": name, "provider": self.provider, "is_enabled": 0,
			 "direct_policy": "Pairing"}
		).insert(ignore_permissions=True)
		values = {"is_enabled": 1, "execution_user": "Administrator", "integration_settings": "x",
			"direct_policy": "Allow list", "room_policy": "Open", "room_sender_policy": "Open",
			"mention_required": 0}
		values.update(kw)
		frappe.db.set_value("Gateway", name, values)
		for sender in ("u1", "u2", "legacy-user"):
			frappe.get_doc({"doctype": "Gateway Access Entry", "gateway": name, "entry_type": "Sender",
				"provider": self.provider, "external_id": sender, "state": "Approved"}).insert(
				ignore_permissions=True)
		return name

	def ingest(self, text, sender="u1", conv=None, pid=None, raw=None, **ctx):
		self.n += 1
		context = {"sender_id": sender, "conversation_id": conv or sender, "message_text": text, **ctx}
		return gsvc.ingest_gateway_event(
			self.gw, pid or f"evt.{self.suffix}.{self.n}", context, verified_sender=True,
			raw_payload=raw if raw is not None else {},
		)

	def ev(self, result):
		return frappe.db.get_value(
			"Gateway Event", result["event_name"],
			["status", "error_message", "solution", "binding", "target_agent"], as_dict=True,
		)

	def sent(self):
		return [c.args[0].text for c in self.adapter.send_reply.call_args_list]

	def sol(self, title, kind="Keyword", value="", **kw):
		s = make_solution(title=f"{title} {self.suffix}").name
		b = make_binding(self.gw, self.agent, match_type=kind, match_value=value, solution=s, **kw).name
		return s, b


class TestSolutionRouting(_Base):
	def test_keyword_stamps_solution_and_pins_then_pin_used(self):
		s, b = self.sol("Orders", value="order", priority=1)
		r = self.ingest("my order")
		ev = self.ev(r)
		self.assertEqual((ev.status, ev.solution, ev.binding), ("Queued", s, b))
		self.assertEqual(a.get_pin(self.gw, "u1")["solution"], s)
		r2 = self.ingest("thanks")  # no keyword: pin
		self.assertEqual(self.ev(r2).solution, s)

	def test_referral_beats_pin(self):
		s1, _ = self.sol("Orders", value="order", priority=1)
		s2, _ = self.sol("Promo", "Ad or link tag", "spring", priority=2)
		self.ingest("order")
		r = self.ingest("hi", raw={"referral_tag": "spring"})
		self.assertEqual(self.ev(r).solution, s2)
		self.assertEqual(a.get_pin(self.gw, "u1")["solution"], s2)

	def test_catch_all(self):
		s, _ = self.sol("Front", "Catch-all", "", priority=50)
		self.assertEqual(self.ev(self.ingest("whatever")).solution, s)

	def test_paused_and_test_mode_skipped_fall_to_default(self):
		s, _ = self.sol("Orders", value="order")
		frappe.db.set_value("Gateway", self.gw, {"default_target_type": "Agent", "default_agent": self.agent})
		frappe.db.set_value("Solution", s, "status", "Paused")
		ev = self.ev(self.ingest("order"))
		self.assertEqual((ev.status, ev.solution), ("Queued", None))
		frappe.db.set_value("Solution", s, {"status": "Paused", "test_mode": 1})
		self.assertIsNone(self.ev(self.ingest("order", sender="u2")).solution)

	def test_unrouted_unchanged(self):
		self.sol("Orders", value="order")
		r = self.ingest("zzz")
		self.assertEqual(r["status"], "Unrouted")
		self.assertEqual(self.ev(r).status, "Unrouted")
		# No agent run and no pin; the reliability hook (gateways/reliability.py) intentionally
		# sends exactly one friendly "not set up" reply carrying the event reference.
		from huf.ai.gateways.reliability import UNROUTED_TEXT

		self.assertEqual(self.sent(), [UNROUTED_TEXT.format(ref=r["event_name"])])
		self.assertIsNone(a.get_pin(self.gw, "u1"))

	def test_legacy_binding_works_and_does_not_pin(self):
		self.sol("Orders", value="order", priority=5)
		make_binding(self.gw, self.agent, match_type="Direct message", match_value="legacy-user",
			priority=9)
		ev = self.ev(self.ingest("hello", sender="legacy-user"))
		self.assertEqual((ev.status, ev.solution), ("Queued", None))
		self.assertIsNone(a.get_pin(self.gw, "legacy-user"))

	def test_no_solution_bindings_unchanged(self):
		b = make_binding(self.gw, self.agent, match_type="Any conversation", priority=1).name
		with patch("huf.ai.solutions.service.route_for_event") as rfe:
			ev = self.ev(self.ingest("order"))
		rfe.assert_not_called()
		self.assertEqual((ev.status, ev.binding), ("Queued", b))
		self.assertEqual(frappe.db.count("Conversation Assignment", {"gateway": self.gw}), 0)


class TestTriage(_Base):
	def setUp(self):
		super().setUp()
		self.s1, _ = self.sol("Alpha", value="alphakw", priority=1)
		self.s2, _ = self.sol("Beta", value="betakw", priority=2)
		make_binding(self.gw, None, match_type="Catch-all", target_type="Triage", priority=99)

	def test_prompt_sent_once_for_duplicate_provider_event(self):
		r1 = self.ingest("hello", pid="same-1")
		r2 = self.ingest("hello", pid="same-1")
		self.assertTrue(r2.get("duplicate"))
		self.assertEqual(len(self.sent()), 1)
		ev = self.ev(r1)
		self.assertEqual((ev.status, ev.error_message), ("Recorded", "triage_prompt"))

	def test_prompt_not_resent_on_replay_or_dead_letter(self):
		r = self.ingest("hello")
		self.assertEqual(len(self.sent()), 1)
		gsvc._replay_event_ingest(r["event_name"])
		frappe.db.set_value("Gateway Event", r["event_name"],
			{"status": "Failed", "error_message": gsvc.DEAD_LETTER_PREFIX + "x"})
		gsvc.retry_gateway_event(r["event_name"])
		self.assertEqual(len(self.sent()), 1)

	def test_cas_loser_does_not_send(self):
		r = self.ingest("hello")
		self.adapter.send_reply.reset_mock()
		ev = frappe.get_doc("Gateway Event", r["event_name"])
		frappe.db.set_value("Gateway Event", ev.name, "status", "Received")
		with patch.object(gsvc, "_triage_cas", return_value=False):
			gsvc._continue_ingest(ev, self.gw, ev.provider_event_id, {
				"sender_id": "u1", "conversation_id": "u1", "message_text": "hello"}, True)
		self.assertEqual(self.sent(), [])

	def test_answer_routes_and_pins(self):
		self.ingest("hello")
		r = self.ingest("1")  # Alpha sorts first
		self.assertEqual(self.ev(r).solution, self.s1)
		self.assertEqual(a.get_pin(self.gw, "u1")["solution"], self.s1)
		self.assertEqual(len(self.sent()), 1)

	def test_prompt_respects_opt_out(self):
		with patch.object(gsvc, "is_opted_out", return_value=True):
			self.ingest("hello")
		self.assertEqual(self.sent(), [])

	def test_room_shares_one_pin_and_triage_state(self):
		self.ingest("hello", sender="p1", conv="group-1", is_room=True, mentioned=True)
		self.assertIsNotNone(a.get_triage_pending(self.gw, "group-1"))
		self.assertEqual(frappe.db.count("Conversation Assignment", {"gateway": self.gw}), 1)
		r = self.ingest("2", sender="p2", conv="group-1", is_room=True, mentioned=True)
		self.assertEqual(self.ev(r).solution, self.s2)
		self.ingest("anything", sender="p1", conv="group-1", is_room=True, mentioned=True)
		self.assertEqual(frappe.db.count("Conversation Assignment", {"gateway": self.gw}), 1)
		self.assertEqual(a.get_pin(self.gw, "group-1")["solution"], self.s2)
		self.assertEqual(len(self.sent()), 1)


class TestConsentNeverPins(_Base):
	provider = "WhatsApp"

	def test_stop_does_not_create_pin(self):
		self.sol("Front", "Catch-all", "", priority=1)
		frappe.get_doc({"doctype": "Gateway Access Entry", "gateway": self.gw, "entry_type": "Sender",
			"provider": "WhatsApp", "external_id": "555", "state": "Approved"}).insert(ignore_permissions=True)
		r = self.ingest("STOP", sender="555")
		self.assertEqual(self.ev(r).status, "Rejected")
		self.assertEqual(frappe.db.count("Conversation Assignment", {"gateway": self.gw}), 0)
