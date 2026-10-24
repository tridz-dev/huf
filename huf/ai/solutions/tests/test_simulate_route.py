import json
from datetime import timedelta

import frappe
from frappe.utils import now_datetime

from huf.ai.solutions import read_models as rm
from huf.ai.solutions.tests._fixtures import make_binding, make_gateway, make_solution, uid
from huf.ai.solutions.tests.test_read_models import ReadModelCase

DECISION_KEYS = {"solution", "target_type", "agent", "flow", "binding", "reason", "pin", "trace", "reply_text"}


class TestSimulateRoute(ReadModelCase):
	def sim(self, text="", **kw):
		req = {"gateway": self.gw, "text": text, "state": kw.pop("state", {}), **kw}
		return rm.simulate_route(req)

	def _counts(self):
		return (
			frappe.db.count("Conversation Assignment"),
			frappe.db.count("Gateway Event"),
			frappe.db.count("WhatsApp Send Key"),
			frappe.db.count("Solution"),
		)

	def test_keyword_and_shape(self):
		d = self.sim("I want to ORDER")
		self.assertEqual(set(d), DECISION_KEYS)
		self.assertEqual((d["solution"], d["reason"], d["binding"]), (self.orders, "keyword", self.b_kw))
		self.assertEqual(d["target_type"], "Agent")
		self.assertTrue(d["trace"] and set(d["trace"][0]) == {"k", "t"})
		self.assertEqual(set(d["pin"]), {"solution", "expires_at"})

	def test_catch_all_and_unrouted(self):
		self.assertEqual(self.sim("hello")["reason"], "catch_all")
		gw2 = make_gateway().name
		d = rm.simulate_route({"gateway": gw2, "text": "hi", "state": {}})
		self.assertEqual((d["reason"], d["solution"]), ("unrouted", None))

	def test_pin_wins_and_keyword_beats_pin(self):
		state = {"pin": {"solution": self.faq, "hours_left": 5}}
		d = self.sim("order please", state=state)
		self.assertEqual((d["reason"], d["solution"]), ("pin", self.faq))
		d = self.sim("order please", state=state, keyword_beats_pin=True)
		self.assertEqual((d["reason"], d["solution"]), ("keyword", self.orders))

	def test_gateway_setting_keyword_beats_pin_default(self):
		frappe.db.set_value("Gateway", self.gw, "keyword_beats_pin", 1)
		d = self.sim("order", state={"pin": {"solution": self.faq, "hours_left": 5}})
		self.assertEqual(d["reason"], "keyword")

	def test_expired_pin(self):
		d = self.sim("hello", state={"pin": {"solution": self.faq, "hours_left": 0}})
		self.assertEqual(d["reason"], "catch_all")

	def test_triage_prompt_then_answer(self):
		gw = make_gateway().name
		a = make_solution(title="Alpha desk").name
		b = make_solution(title="Beta desk").name
		make_binding(gw, self.agent, priority=1, match_type="Keyword", match_value="alpha", solution=a)
		make_binding(gw, self.agent, priority=2, match_type="Keyword", match_value="beta", solution=b)
		make_binding(gw, None, priority=99, match_type="Catch-all", target_type="Triage")
		prompt = rm.simulate_route({"gateway": gw, "text": "hello", "state": {}})
		self.assertEqual(prompt["reason"], "triage_prompt")
		self.assertIn("1 for Alpha desk", prompt["reply_text"])
		self.assertIsNone(prompt["solution"])
		answer = rm.simulate_route({"gateway": gw, "text": "2", "state": {"triage_pending": True}})
		self.assertEqual((answer["reason"], answer["solution"]), ("triage_answer", b))
		no_menu = rm.simulate_route({"gateway": gw, "text": "2", "state": {}})
		self.assertEqual(no_menu["reason"], "triage_prompt")

	def test_referral(self):
		make_binding(
			self.gw, self.agent, priority=0, match_type="Ad or link tag", match_value="spring, promo", solution=self.faq
		)
		d = self.sim("order", ref="PROMO")
		self.assertEqual((d["reason"], d["solution"]), ("referral", self.faq))
		d = self.sim("order", ref="unknown")
		self.assertEqual(d["reason"], "keyword")

	def test_paused_and_test_mode_included(self):
		frappe.db.set_value("Solution", self.orders, "status", "Paused")
		d = self.sim("order")
		self.assertEqual((d["reason"], d["solution"]), ("keyword", self.orders))
		frappe.db.set_value("Solution", self.orders, {"status": "Paused", "test_mode": 1})
		self.assertEqual(self.sim("order")["solution"], self.orders)

	def test_zero_writes(self):
		make_binding(self.gw, None, priority=99, match_type="Catch-all", target_type="Triage")
		before = self._counts()
		for text, state in [("order", {}), ("hello", {"triage_pending": True}), ("x", {"pin": {"solution": self.faq, "hours_left": 3}})]:
			self.sim(text, state=state)
		self.assertEqual(self._counts(), before)
		self.assertEqual(frappe.db.count("Conversation Assignment", {"gateway": self.gw}), 0)

	def test_json_string_request(self):
		req = json.dumps({"gateway": self.gw, "text": "order", "state": {"pin": {"solution": self.faq, "hours_left": 2}}})
		self.assertEqual(rm.simulate_route(req)["reason"], "pin")
		req = json.dumps({"gateway": self.gw, "text": "order", "state": json.dumps({"triage_pending": False})})
		self.assertEqual(rm.simulate_route(req)["reason"], "keyword")

	def test_invalid_requests(self):
		self.assertEqual(rm.simulate_route("not json{")["error"]["code"], "invalid_payload")
		self.assertEqual(rm.simulate_route({"text": "x"})["error"]["code"], "invalid_payload")
		self.assertEqual(rm.simulate_route({"gateway": "nope-zzz", "text": "x"})["error"]["code"], "not_found")

	def _draft(self, **kw):
		d = {"title": "Draft desk", "gateway": self.gw, "inbound": True,
			"entries": [{"match_type": "Keyword", "match_values": ["cake"]}]}
		d.update(kw)
		return d

	def test_draft_keyword_routes_to_title(self):
		d = self.sim("a cake please", draft=self._draft())
		self.assertEqual((d["solution"], d["reason"]), ("Draft desk", "keyword"))
		self.assertIn("Draft desk", json.dumps(d["trace"]))

	def test_draft_inbound_false_never_chosen(self):
		d = self.sim("a cake please", draft=self._draft(inbound=False))
		self.assertNotEqual(d["solution"], "Draft desk")
		self.assertEqual(d["reason"], "catch_all")

	def test_draft_for_other_gateway_ignored(self):
		d = self.sim("a cake please", draft=self._draft(gateway="other-gw"))
		self.assertNotEqual(d["solution"], "Draft desk")

	def test_draft_with_saved_solutions_normal_order(self):
		# saved keyword (priority 1, earlier name) vs draft keyword on a different word
		self.assertEqual(self.sim("order", draft=self._draft())["solution"], self.orders)
		self.assertEqual(self.sim("cake", draft=self._draft())["solution"], "Draft desk")
		# draft catch-all (8) beats saved catch-all (9) on priority
		d = self.sim("hello", draft=self._draft(entries=[{"match_type": "Catch-all", "match_values": []}]))
		self.assertEqual((d["solution"], d["reason"]), ("Draft desk", "catch_all"))
		# a live pin on a saved solution still wins over a draft keyword
		d = self.sim("cake", draft=self._draft(), state={"pin": {"solution": self.faq, "hours_left": 4}})
		self.assertEqual((d["solution"], d["reason"]), (self.faq, "pin"))

	def test_draft_json_string_and_triage_menu(self):
		draft = self._draft(entries=[{"match_type": "Triage", "match_values": []}])
		req = json.dumps({"gateway": self.gw, "text": "hi", "state": {}, "draft": draft})
		d = rm.simulate_route(req)
		self.assertIn(d["reason"], ("catch_all",))  # saved catch-all still beats triage
		gw = make_gateway().name
		draft = self._draft(gateway=gw, entries=[{"match_type": "Triage", "match_values": []}, {"match_type": "Keyword", "match_values": ["cake"]}])
		d = rm.simulate_route({"gateway": gw, "text": "hi", "state": {}, "draft": json.dumps(draft)})
		self.assertEqual(d["reason"], "triage_prompt")
		self.assertIn("Draft desk", d["reply_text"])

	def test_draft_zero_writes(self):
		before = self._counts()
		self.sim("cake", draft=self._draft(catch_all=True))
		self.assertEqual(self._counts(), before)
		self.assertFalse(frappe.db.exists("Solution", {"title": "Draft desk"}))
