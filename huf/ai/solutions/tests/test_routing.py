import unittest
from datetime import datetime, timedelta

from huf.ai.solutions.routing import decide_route

NOW = datetime(2026, 10, 24, 12, 0, 0)


def S(title, status="Live", test_mode=False):
	return {"status": status, "test_mode": test_mode, "title": title}


def R(name, priority, match_type, values, solution, agent="A", target_type="Agent", flow=None, enabled=1):
	return {
		"name": name, "priority": priority, "match_type": match_type, "match_values": values,
		"target_type": target_type, "agent": agent, "flow": flow, "solution": solution, "is_enabled": enabled,
	}


SOLS = {"orders": S("Orders"), "care": S("Customer care"), "paused": S("Old", "Paused"), "beta": S("Beta", test_mode=True)}
RULES = [
	R("ref1", 1, "Ad or link tag", ["Weekend_Special"], "orders", agent="ag-orders"),
	R("kw-orders", 2, "Keyword", ["cake", "pickup"], "orders", agent="ag-orders"),
	R("kw-care", 3, "Keyword", ["refund"], "care", agent="ag-care"),
	R("kw-paused", 4, "Keyword", ["legacyword"], "paused", agent="ag-p"),
	R("kw-beta", 5, "Keyword", ["betaword"], "beta", agent="ag-b"),
]
DEFAULT = {"target_type": "Agent", "agent": "ag-default", "flow": None}


def go(**kw):
	args = dict(
		text="", referral_tag=None, button_payload=None, now=NOW, rules=RULES, pin=None,
		triage_pending_until=None, solutions=SOLS, keyword_beats_pin=False, gateway_default=None,
	)
	args.update(kw)
	return decide_route(**args)


def pin(sol, hours=10):
	return {"solution": sol, "expires_at": NOW + timedelta(hours=hours)}


def texts(d):
	return [e["t"] for e in d["trace"]]


class TestRouting(unittest.TestCase):
	def test_referral_exact_case_insensitive(self):
		d = go(referral_tag="weekend_special")
		self.assertEqual((d["solution"], d["reason"], d["binding"], d["agent"]), ("orders", "referral", "ref1", "ag-orders"))
		self.assertEqual(d["trace"][0], {"k": "win", "t": 'Ad tag "weekend_special" → Orders'})

	def test_referral_no_match_traced_and_falls_through(self):
		d = go(referral_tag="nope", text="refund")
		self.assertEqual(d["trace"][0], {"k": "skip", "t": 'Ad tag "nope" matches nothing on this number'})
		self.assertEqual(d["reason"], "keyword")

	def test_referral_beats_pin(self):
		d = go(referral_tag="weekend_special", pin=pin("care"))
		self.assertEqual((d["solution"], d["reason"]), ("orders", "referral"))

	def test_referral_to_paused_solution_ignored(self):
		rules = RULES + [R("refp", 9, "Ad or link tag", ["old"], "paused")]
		d = go(referral_tag="old", rules=rules)
		self.assertNotEqual(d["solution"], "paused")

	def test_button_payload_live(self):
		d = go(button_payload="sol:care|tpl:x")
		self.assertEqual((d["solution"], d["reason"], d["agent"]), ("care", "referral", "ag-care"))
		self.assertIn("Template reply payload", d["trace"][0]["t"])

	def test_button_payload_paused_ignored(self):
		d = go(button_payload="sol:paused|x", text="hello", gateway_default=DEFAULT)
		self.assertEqual(d["reason"], "default")

	def test_button_payload_malformed_ignored(self):
		self.assertEqual(go(button_payload="garbage", text="hi")["reason"], "unrouted")

	def test_triage_prompt_then_answer(self):
		rules = RULES + [R("tri", 9, "Catch-all", [], None, target_type="Triage", agent=None)]
		rules = [r for r in rules if r["name"] != "kw-paused"]
		d = go(rules=rules, text="hello")
		self.assertEqual(d["reason"], "triage_prompt")
		self.assertEqual(d["reply_text"], "Hi, this is us. Reply:\n1 for Customer care\n2 for Orders")
		self.assertEqual(d["triage_pending_until"], NOW + timedelta(minutes=30))
		self.assertIsNone(d["solution"])
		pend = NOW + timedelta(minutes=5)
		a1 = go(rules=rules, text="1", triage_pending_until=pend)
		self.assertEqual((a1["solution"], a1["reason"]), ("care", "triage_answer"))
		self.assertIsNone(a1["triage_pending_until"])
		a2 = go(rules=rules, text=" 2. ", triage_pending_until=pend)
		self.assertEqual(a2["solution"], "orders")

	def test_triage_answer_expired_not_used(self):
		d = go(text="1", triage_pending_until=NOW - timedelta(seconds=1))
		self.assertNotEqual(d["reason"], "triage_answer")

	def test_invalid_triage_answer_falls_through(self):
		d = go(text="refund please", triage_pending_until=NOW + timedelta(minutes=5))
		self.assertEqual((d["solution"], d["reason"]), ("care", "keyword"))
		d = go(text="9", triage_pending_until=NOW + timedelta(minutes=5))
		self.assertEqual(d["reason"], "unrouted")

	def test_pin_wins_default_toggle(self):
		d = go(text="refund", pin=pin("orders", 10))
		self.assertEqual((d["solution"], d["reason"], d["binding"]), ("orders", "pin", "kw-orders"))
		self.assertEqual(
			texts(d)[:2],
			['Keyword "refund" would route to Customer care', "Pinned to Orders (10h left). Pinned chat wins."],
		)
		self.assertEqual([e["k"] for e in d["trace"][:2]], ["skip", "win"])

	def test_keyword_beats_pin(self):
		d = go(text="refund", pin=pin("orders"), keyword_beats_pin=True)
		self.assertEqual((d["solution"], d["reason"]), ("care", "keyword"))
		self.assertEqual(
			texts(d)[:2],
			['Keyword "refund" would route to Customer care', "Rule: keyword beats the pin → Customer care"],
		)

	def test_pin_same_solution_keyword(self):
		d = go(text="cake", pin=pin("orders", 3))
		self.assertEqual((d["solution"], d["reason"]), ("orders", "pin"))
		self.assertEqual(d["trace"][0], {"k": "win", "t": "Pinned to Orders (3h left)"})

	def test_pin_no_keyword(self):
		d = go(text="hello", pin=pin("care"))
		self.assertEqual((d["solution"], d["reason"], d["agent"]), ("care", "pin", "ag-care"))

	def test_expired_pin(self):
		d = go(text="refund", pin={"solution": "orders", "expires_at": NOW})
		self.assertEqual((d["solution"], d["reason"]), ("care", "keyword"))
		self.assertEqual(d["trace"][0], {"k": "info", "t": "Earlier pin expired after 24h. Routing from scratch."})

	def test_pin_to_paused_solution_not_used(self):
		d = go(text="cake", pin=pin("paused"))
		self.assertEqual((d["solution"], d["reason"]), ("orders", "keyword"))

	def test_keyword_case_insensitive_substring_priority(self):
		d = go(text="Is my CAKE ready? refund!")
		self.assertEqual((d["solution"], d["binding"]), ("orders", "kw-orders"))
		self.assertEqual(d["trace"][0]["t"], 'Keyword "cake" → Orders')

	def test_paused_and_test_mode_skipped(self):
		self.assertEqual(go(text="legacyword")["reason"], "unrouted")
		self.assertEqual(go(text="betaword")["reason"], "unrouted")

	def test_include_inactive(self):
		d = go(text="legacyword", include_inactive=True)
		self.assertEqual((d["solution"], d["reason"]), ("paused", "keyword"))
		d = go(text="betaword", include_inactive=True)
		self.assertEqual(d["solution"], "beta")

	def test_disabled_rule_ignored(self):
		rules = [R("k", 1, "Keyword", ["cake"], "orders", enabled=0)]
		self.assertEqual(go(text="cake", rules=rules)["reason"], "unrouted")

	def test_catch_all(self):
		rules = RULES + [R("ca", 8, "Catch-all", [], "care", agent="ag-care")]
		d = go(text="hello", rules=rules, gateway_default=DEFAULT)
		self.assertEqual((d["solution"], d["reason"], d["binding"]), ("care", "catch_all", "ca"))

	def test_legacy_fallthrough(self):
		rules = RULES + [R("old", 8, "Contains", ["x"], None)]
		d = go(text="hello", rules=rules, gateway_default=DEFAULT)
		self.assertTrue(d["legacy_fallthrough"])
		self.assertIsNone(d["solution"])
		self.assertFalse(go(text="hello")["legacy_fallthrough"])
		self.assertFalse(go(text="cake", rules=rules)["legacy_fallthrough"])

	def test_gateway_default(self):
		d = go(text="hello", gateway_default=DEFAULT)
		self.assertEqual((d["reason"], d["agent"], d["target_type"], d["solution"]), ("default", "ag-default", "Agent", None))

	def test_unrouted(self):
		d = go(text="hello")
		self.assertEqual((d["reason"], d["solution"], d["reply_text"], d["pin"]), ("unrouted", None, None, None))
		self.assertIn("gets no reply", d["trace"][-1]["t"])

	def test_pin_refreshed_and_ttl(self):
		d = go(text="cake")
		self.assertEqual(d["pin"], {"solution": "orders", "expires_at": NOW + timedelta(hours=24)})
		d = decide_route(
			text="cake", referral_tag=None, button_payload=None, now=NOW, rules=RULES, pin=None,
			triage_pending_until=None, solutions=SOLS, keyword_beats_pin=False, gateway_default=None, pin_ttl_hours=2,
		)
		self.assertEqual(d["pin"]["expires_at"], NOW + timedelta(hours=2))
		self.assertEqual(d["trace"][-1]["t"], "Pinned this chat to Orders for 2h")

	def test_flow_target(self):
		rules = [R("f", 1, "Keyword", ["book"], "orders", target_type="Flow", agent=None, flow="flow-1")]
		d = go(text="book", rules=rules)
		self.assertEqual((d["target_type"], d["flow"], d["agent"]), ("Flow", "flow-1", None))

	def test_deterministic(self):
		kw = dict(text="Refund", pin=pin("orders"), keyword_beats_pin=True)
		self.assertEqual(go(**kw), go(**kw))

	def test_inputs_not_mutated(self):
		import copy
		before = copy.deepcopy(RULES)
		go(text="cake")
		self.assertEqual(before, RULES)


def S2(title, ptype=None, agent=None, flow=None):
	return {**S(title), "primary_target_type": ptype, "primary_agent": agent, "primary_flow": flow}


class TestTriageOwner(unittest.TestCase):
	"""A solution that owns the Triage entry must still answer its own pinned chats."""

	def go(self, sols, rules, **kw):
		return go(solutions=sols, rules=rules, **kw)

	def owner_rules(self):
		return [
			R("tri", 1, "Catch-all", [], "cat", agent=None, target_type="Triage"),
			R("kw", 2, "Keyword", ["menu"], "cat", agent=None, target_type="Flow", flow="fl-cat"),
		]

	def test_pin_routes_to_message_rule_not_triage(self):
		rules = [
			R("tri", 1, "Catch-all", [], "cat", agent=None, target_type="Triage"),
			R("kw", 2, "Keyword", ["menu"], "cat", agent="ag-cat"),
		]
		d = self.go({"cat": S2("Catering")}, rules, text="hello", pin=pin("cat"))
		self.assertEqual((d["reason"], d["binding"], d["target_type"], d["agent"]), ("pin", "kw", "Agent", "ag-cat"))

	def test_pin_falls_back_to_primary_when_only_triage_rule(self):
		rules = [R("tri", 1, "Catch-all", [], "cat", agent=None, target_type="Triage")]
		d = self.go({"cat": S2("Catering", "Flow", flow="fl-p")}, rules, text="hello", pin=pin("cat"))
		self.assertEqual((d["target_type"], d["flow"], d["binding"]), ("Flow", "fl-p", None))
		self.assertIn("Answered by Catering's flow", texts(d))

	def test_triage_answer_and_payload_use_primary(self):
		rules = [
			R("tri", 1, "Catch-all", [], "cat", agent=None, target_type="Triage"),
			R("kw0", 2, "Keyword", ["zz"], "cat", agent=None),
			R("kw", 3, "Keyword", ["x"], "ord", agent="ag-o"),
		]
		sols = {"cat": S2("Catering", "Agent", agent="ag-p"), "ord": S2("Orders")}
		d = self.go(sols, rules, text="1", triage_pending_until=NOW + timedelta(minutes=5))
		self.assertEqual((d["solution"], d["reason"], d["agent"], d["binding"]), ("cat", "triage_answer", "ag-p", None))
		d = self.go(sols, rules, button_payload="sol:cat|x")
		self.assertEqual((d["solution"], d["agent"]), ("cat", "ag-p"))

	def test_ad_tag_rule_preferred_over_primary_never_triage(self):
		rules = [
			R("tri", 1, "Catch-all", [], "cat", agent=None, target_type="Triage"),
			R("ad", 2, "Ad or link tag", ["t"], "cat", agent="ag-ad"),
		]
		d = self.go({"cat": S2("Catering", "Agent", agent="ag-p")}, rules, text="hi", pin=pin("cat"))
		self.assertEqual((d["binding"], d["agent"]), ("ad", "ag-ad"))

	def test_no_usable_rule_no_primary_is_unanswerable_with_trace(self):
		rules = [R("tri", 1, "Catch-all", [], "cat", agent=None, target_type="Triage")]
		d = self.go({"cat": S2("Catering")}, rules, text="hello", pin=pin("cat"))
		self.assertIsNone(d["binding"])
		self.assertFalse(d["agent"] or d["flow"])
		self.assertTrue(any("no rule or primary" in t for t in texts(d)))

	def test_brand_in_menu(self):
		rules = [R("tri", 1, "Catch-all", [], "cat", agent=None, target_type="Triage"),
			R("kw", 2, "Keyword", ["x"], "ord", agent="ag-o")]
		d = self.go({"cat": S2("Catering", "Agent", agent="p"), "ord": S2("Orders")}, rules, text="zzz", brand="Harbor")
		self.assertTrue(d["reply_text"].startswith("Hi, this is Harbor. Reply:"))


if __name__ == "__main__":
	unittest.main()
