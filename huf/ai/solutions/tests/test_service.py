from datetime import timedelta

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from huf.ai.solutions import assignment as a
from huf.ai.solutions.service import route_for_event
from huf.ai.solutions.tests._fixtures import make_agent, make_binding, make_gateway, make_solution


class TestRouteForEvent(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.agent = make_agent()
		self.gw = make_gateway().name
		self.orders = make_solution(title="Orders desk").name
		self.support = make_solution(title="Support desk").name
		self.b_orders = make_binding(self.gw, self.agent, priority=1, match_type="Keyword",
			match_value="order", solution=self.orders).name
		self.b_support = make_binding(self.gw, self.agent, priority=2, match_type="Keyword",
			match_value="help", solution=self.support).name
		self.now = now_datetime()

	def tearDown(self):
		frappe.db.rollback()

	def _route(self, text, **kw):
		return route_for_event(self.gw, "c1", text, now=self.now, **kw)

	def _rows(self):
		return frappe.db.count("Conversation Assignment", {"gateway": self.gw})

	def test_keyword_routes(self):
		d = self._route("where is my ORDER")
		self.assertEqual((d["solution"], d["reason"], d["binding"]), (self.orders, "keyword", self.b_orders))

	def test_read_only_writes_nothing(self):
		self._route("order")
		self.assertEqual(self._rows(), 0)

	def test_commit_pin_writes_exactly_one_row(self):
		self._route("order", commit_pin=True)
		self._route("order please", commit_pin=True)
		self.assertEqual(self._rows(), 1)
		pin = a.get_pin(self.gw, "c1", now=self.now)
		self.assertEqual(pin["solution"], self.orders)
		self.assertEqual(pin["set_by"], "rule")
		self.assertEqual(pin["source_binding"], self.b_orders)

	def test_pin_wins_over_keyword(self):
		a.set_pin(self.gw, "c1", self.support, "rule", now=self.now)
		d = self._route("order")
		self.assertEqual((d["solution"], d["reason"]), (self.support, "pin"))

	def test_keyword_beats_pin_when_flag_set(self):
		frappe.db.set_value("Gateway", self.gw, "keyword_beats_pin", 1)
		a.set_pin(self.gw, "c1", self.support, "rule", now=self.now)
		d = self._route("order")
		self.assertEqual((d["solution"], d["reason"]), (self.orders, "keyword"))

	def test_paused_solution_skipped(self):
		frappe.db.set_value("Solution", self.orders, "status", "Paused")
		d = self._route("order")
		self.assertNotEqual(d["solution"], self.orders)
		self.assertEqual(d["reason"], "unrouted")

	def test_test_mode_skipped_unless_include_inactive(self):
		frappe.db.set_value("Solution", self.orders, {"test_mode": 1, "status": "Paused"})
		self.assertNotEqual(self._route("order")["solution"], self.orders)
		d = self._route("order", include_inactive=True)
		self.assertEqual(d["solution"], self.orders)

	def test_referral_sets_set_by_referral(self):
		make_binding(self.gw, self.agent, priority=0, match_type="Ad or link tag",
			match_value="spring", solution=self.orders)
		d = self._route("hi", referral_tag="spring", commit_pin=True)
		self.assertEqual(d["reason"], "referral")
		self.assertEqual(a.get_pin(self.gw, "c1", now=self.now)["set_by"], "referral")

	def test_pin_ttl_from_gateway(self):
		frappe.db.set_value("Gateway", self.gw, "pin_ttl_hours", 3)
		self._route("order", commit_pin=True)
		pin = a.get_pin(self.gw, "c1", now=self.now)
		self.assertAlmostEqual((pin["expires_at"] - self.now).total_seconds(), 3 * 3600, delta=1)

	def test_triage_prompt_sets_pending_and_answer_pins(self):
		gw = make_gateway().name
		make_binding(gw, self.agent, priority=1, match_type="Keyword", match_value="order",
			solution=self.orders)
		make_binding(gw, self.agent, priority=2, match_type="Keyword", match_value="help",
			solution=self.support)
		make_binding(gw, None, priority=99, match_type="Catch-all", target_type="Triage")
		d = route_for_event(gw, "c9", "hello", now=self.now, commit_pin=True)
		self.assertEqual(d["reason"], "triage_prompt")
		self.assertIsNone(d["solution"])
		self.assertEqual(d["triage_pending_until"], self.now + timedelta(minutes=30))
		got = a.get_triage_pending(gw, "c9", now=self.now)
		self.assertAlmostEqual((got - self.now).total_seconds(), 1800, delta=1)
		self.assertEqual(frappe.db.count("Conversation Assignment", {"gateway": gw}), 1)
		# the answer: options sorted by title -> 1 = Orders desk
		d2 = route_for_event(gw, "c9", "1", now=self.now, commit_pin=True)
		self.assertEqual((d2["reason"], d2["solution"]), ("triage_answer", self.orders))
		self.assertEqual(a.get_pin(gw, "c9", now=self.now)["set_by"], "triage")
		self.assertIsNone(a.get_triage_pending(gw, "c9", now=self.now))
		self.assertEqual(frappe.db.count("Conversation Assignment", {"gateway": gw}), 1)


class TestTriageOwner(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.agent = make_agent()
		self.gw = make_gateway().name
		self.cat = make_solution(title="Catering desk", primary_target_type="Agent", primary_agent=self.agent).name
		self.ord = make_solution(title="Orders desk").name
		make_binding(self.gw, None, priority=1, match_type="Catch-all", target_type="Triage", solution=self.cat)
		make_binding(self.gw, self.agent, priority=2, match_type="Keyword", match_value="cater", solution=self.cat)
		make_binding(self.gw, self.agent, priority=3, match_type="Keyword", match_value="order", solution=self.ord)
		self.now = now_datetime()

	def tearDown(self):
		frappe.db.rollback()

	def test_menu_uses_gateway_name(self):
		d = route_for_event(self.gw, "c9", "hello", now=self.now)
		self.assertEqual(d["reason"], "triage_prompt")
		self.assertTrue(d["reply_text"].startswith(f"Hi, this is {self.gw}. Reply:"))

	def test_triage_answer_routes_owner_to_agent(self):
		route_for_event(self.gw, "c9", "hello", now=self.now, commit_pin=True)
		d = route_for_event(self.gw, "c9", "1", now=self.now, commit_pin=True)
		self.assertEqual((d["solution"], d["reason"]), (self.cat, "triage_answer"))
		self.assertEqual((d["target_type"], d["agent"]), ("Agent", self.agent))
		self.assertNotEqual(frappe.db.get_value("Gateway Binding", d["binding"], "target_type"), "Triage")

	def test_pinned_owner_routes_next_plain_message(self):
		a.set_pin(self.gw, "c9", self.cat, "triage", ttl_hours=24, now=self.now)
		d = route_for_event(self.gw, "c9", "thanks", now=self.now)
		self.assertEqual((d["reason"], d["solution"], d["agent"]), ("pin", self.cat, self.agent))
