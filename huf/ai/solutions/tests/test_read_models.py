import json
from datetime import timedelta

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from huf.ai.solutions import read_models as rm
from huf.ai.solutions.tests._fixtures import make_agent, make_binding, make_gateway, make_solution, uid

SUMMARY_KEYS = {
	"name", "title", "description", "purpose", "status", "test_mode", "runs_on", "shared",
	"entry_count", "primary", "chats_7d",
}
OVERVIEW_KEYS = SUMMARY_KEYS | {"health", "reach", "activity", "cost", "limits"}
ENTRY_KEYS = {
	"name", "gateway", "priority", "match_type", "match_values", "target_type", "agent", "flow",
	"cap_per_day", "scope_override", "allow_first_message", "ceiling", "ceiling_source",
}
NUMBER_KEYS = {"gateway", "label", "phone", "solutions", "routing_order", "quality", "blame"}
INTENT_KEYS = {"id", "name", "desc", "icon", "sample_name", "entry", "keywords", "ref", "suggested_templates", "policy"}


def make_event(gateway, conversation_id, text, solution=None, received_at=None):
	return frappe.get_doc({
		"doctype": "Gateway Event", "gateway": gateway, "idempotency_key": f"b2-{uid()}-{uid()}",
		"conversation_id": conversation_id, "message_text": text, "solution": solution,
		"received_at": received_at or now_datetime(), "status": "Recorded",
	}).insert(ignore_permissions=True, ignore_links=True)


def make_send_key(gateway, solution, hours_ago=1):
	return frappe.get_doc({
		"doctype": "WhatsApp Send Key", "key_hash": frappe.generate_hash(length=40), "gateway": gateway,
		"status": "Sent", "claimed_at": add_to_date(now_datetime(), hours=-hours_ago), "solution": solution or None,
	}).insert(ignore_permissions=True, ignore_links=True)


def set_token_cache(gateway, quality=None, tier=None):
	from huf.ai.whatsapp.token_check import _result_key

	frappe.cache().set_value(
		_result_key(gateway), {"phone": {"display": "+1 555 0100", "quality": quality, "tier": tier}}, expires_in_sec=60
	)


def clear_token_cache(gateway):
	from huf.ai.whatsapp.token_check import _result_key

	frappe.cache().delete_value(_result_key(gateway))


class ReadModelCase(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.agent = make_agent()
		self.gw = make_gateway().name
		frappe.db.set_value("Gateway", self.gw, "agent_send_cap_per_day", 0)
		self.cached = [self.gw]
		self.orders = make_solution(title=f"Orders {uid()}", purpose="orders").name
		self.faq = make_solution(title=f"FAQ {uid()}", purpose="answer").name
		self.b_kw = make_binding(
			self.gw, self.agent, priority=1, match_type="Keyword", match_value="order, menu", solution=self.orders,
			cap_per_day=50,
		).name
		self.b_ca = make_binding(self.gw, self.agent, priority=9, match_type="Catch-all", solution=self.faq).name

	def tearDown(self):
		for gw in self.cached:
			clear_token_cache(gw)
		frappe.set_user("Administrator")
		frappe.db.rollback()


class TestReadModels(ReadModelCase):
	def test_list_solutions_shape_and_values(self):
		rows = {r["name"]: r for r in rm.list_solutions()}
		row = rows[self.orders]
		self.assertEqual(set(row), SUMMARY_KEYS)
		self.assertEqual(row["purpose"], "orders")
		self.assertEqual(row["entry_count"], 1)
		self.assertEqual(row["runs_on"][0]["gateway"], self.gw)
		self.assertEqual(set(row["runs_on"][0]), {"gateway", "label", "phone"})
		self.assertEqual(row["chats_7d"], 0)
		self.assertIsNone(row["primary"])

	def test_primary_label(self):
		sol = make_solution(title=f"P {uid()}", primary_target_type="Agent", primary_agent=self.agent).name
		row = next(r for r in rm.list_solutions() if r["name"] == sol)
		self.assertEqual(set(row["primary"]), {"type", "name", "label"})
		self.assertEqual((row["primary"]["type"], row["primary"]["name"]), ("Agent", self.agent))

	def test_purpose_filter(self):
		names = {r["name"] for r in rm.list_solutions(purpose="orders")}
		self.assertIn(self.orders, names)
		self.assertNotIn(self.faq, names)
		self.assertEqual({r["purpose"] for r in rm.list_solutions(purpose="orders")}, {"orders"})

	def test_shared_flag(self):
		rows = {r["name"]: r for r in rm.list_solutions()}
		self.assertTrue(rows[self.orders]["shared"])  # two live solutions on the gateway
		gw2 = make_gateway().name
		solo = make_solution(title=f"Solo {uid()}").name
		make_binding(gw2, self.agent, match_type="Catch-all", solution=solo)
		self.assertFalse({r["name"]: r for r in rm.list_solutions()}[solo]["shared"])
		# a paused neighbour does not make it shared
		frappe.db.set_value("Solution", self.faq, "status", "Paused")
		self.assertFalse({r["name"]: r for r in rm.list_solutions()}[self.orders]["shared"])

	def test_chats_7d_distinct_conversations(self):
		make_event(self.gw, "c1", "hi", self.orders)
		make_event(self.gw, "c1", "again", self.orders)
		make_event(self.gw, "c2", "yo", self.orders)
		make_event(self.gw, "c3", "old", self.orders, received_at=add_to_date(now_datetime(), days=-9))
		make_event(self.gw, "c4", "other", self.faq)
		row = next(r for r in rm.list_solutions() if r["name"] == self.orders)
		self.assertEqual(row["chats_7d"], 2)

	def test_overview_shape(self):
		make_event(self.gw, "c1", "x" * 200, self.orders)
		frappe.db.set_value("Gateway Binding", self.b_kw, "scope_override", "Allow list")
		ov = rm.get_solution_overview(self.orders)
		self.assertEqual(set(ov), OVERVIEW_KEYS)
		self.assertEqual(set(ov["health"]), {"state", "gateway", "quality", "blame"})
		self.assertEqual(set(ov["reach"]), {"contacts_7d", "new_7d"})
		self.assertEqual(set(ov["cost"]), {"sends_24h", "cap_share", "ceiling"})
		self.assertEqual(set(ov["limits"]), {"per_day", "scope"})
		self.assertEqual(set(ov["activity"][0]), {"ts", "kind", "text"})
		self.assertLess(len(ov["activity"][0]["text"]), 100)
		self.assertEqual(ov["limits"], {"per_day": 50, "scope": "Allow list"})
		self.assertEqual(ov["reach"], {"contacts_7d": 1, "new_7d": 1})

	def test_overview_new_vs_returning(self):
		make_event(self.gw, "old", "a", self.orders, received_at=add_to_date(now_datetime(), days=-20))
		make_event(self.gw, "old", "b", self.orders)
		make_event(self.gw, "fresh", "c", self.orders)
		self.assertEqual(rm.get_solution_overview(self.orders)["reach"], {"contacts_7d": 2, "new_7d": 1})

	def test_overview_activity_capped_at_10(self):
		for i in range(12):
			make_event(self.gw, f"c{i}", f"m{i}", self.orders)
		self.assertEqual(len(rm.get_solution_overview(self.orders)["activity"]), 10)

	def test_unknown_ceiling_is_none_safe(self):
		make_send_key(self.gw, self.orders)
		ov = rm.get_solution_overview(self.orders)
		self.assertEqual(ov["cost"], {"sends_24h": 1, "cap_share": None, "ceiling": None})
		ep = rm.list_entry_points(self.orders)[0]
		self.assertEqual((ep["ceiling"], ep["ceiling_source"]), (None, "none"))

	def test_gateway_cap_ceiling_and_share(self):
		frappe.db.set_value("Gateway", self.gw, "agent_send_cap_per_day", 200)
		for _ in range(5):
			make_send_key(self.gw, self.orders)
		ov = rm.get_solution_overview(self.orders)
		self.assertEqual(ov["cost"], {"sends_24h": 5, "cap_share": 2.5, "ceiling": 200})
		ep = rm.list_entry_points(self.orders)[0]
		self.assertEqual((ep["ceiling"], ep["ceiling_source"]), (200, "gateway_cap"))

	def test_meta_tier_ceiling(self):
		set_token_cache(self.gw, quality="GREEN", tier="TIER_1K")
		ep = rm.list_entry_points(self.orders)[0]
		self.assertEqual((ep["ceiling"], ep["ceiling_source"]), (1000, "meta_tier"))

	def test_quality_unknown_vs_known(self):
		ov = rm.get_solution_overview(self.orders)
		self.assertIsNone(ov["health"]["quality"])
		self.assertEqual(ov["health"]["state"], "ok")
		num = rm.get_number_summary(self.gw)
		self.assertEqual(num["quality"], {"rating": None, "source": "unknown"})
		set_token_cache(self.gw, quality="RED")
		self.assertEqual(rm.get_solution_overview(self.orders)["health"]["state"], "bad")
		set_token_cache(self.gw, quality="YELLOW")
		self.assertEqual(rm.get_solution_overview(self.orders)["health"]["state"], "warn")
		set_token_cache(self.gw, quality="GREEN")
		self.assertEqual(rm.get_solution_overview(self.orders)["health"]["quality"], "GREEN")
		self.assertEqual(rm.get_number_summary(self.gw)["quality"], {"rating": "GREEN", "source": "meta"})

	def test_blame_is_data_only(self):
		for _ in range(3):
			make_send_key(self.gw, self.orders)
		make_send_key(self.gw, self.faq)
		blame = rm.get_solution_overview(self.faq)["health"]["blame"]
		self.assertEqual(blame, {"solution": self.orders, "share_pct": 75.0})
		self.assertEqual(rm.get_number_summary(self.gw)["blame"], blame)
		self.assertNotIn("caus", json.dumps(blame).lower())

	def test_entry_points_shape(self):
		eps = {e["name"]: e for e in rm.list_entry_points(self.orders)}
		ep = eps[self.b_kw]
		self.assertEqual(set(ep), ENTRY_KEYS)
		self.assertEqual(ep["match_values"], ["order", "menu"])
		self.assertEqual((ep["cap_per_day"], ep["scope_override"], ep["match_type"]), (50, None, "Keyword"))
		self.assertIsNone(rm.list_entry_points(self.faq)[0]["cap_per_day"])
		self.assertEqual(rm.list_entry_points(self.faq)[0]["match_values"], [])

	def test_number_summary(self):
		make_send_key(self.gw, self.orders)
		frappe.db.set_value("Gateway", self.gw, "agent_send_cap_per_day", 100)
		num = rm.get_number_summary(self.gw)
		self.assertEqual(set(num), NUMBER_KEYS)
		sols = {s["name"]: s for s in num["solutions"]}
		self.assertEqual(set(sols[self.orders]), {"name", "title", "status", "usage_pct", "sends_24h"})
		self.assertEqual((sols[self.orders]["sends_24h"], sols[self.orders]["usage_pct"]), (1, 1.0))
		self.assertEqual([r["rank"] for r in num["routing_order"]], [1, 2])
		self.assertEqual([r["kind"] for r in num["routing_order"]], ["Keyword", "Catch-all"])
		self.assertEqual(set(num["routing_order"][0]), {"rank", "kind", "label", "solution"})
		self.assertEqual(num["routing_order"][0]["solution"], self.orders)

	def test_number_summary_usage_pct_none_without_ceiling(self):
		sols = rm.get_number_summary(self.gw)["solutions"]
		self.assertTrue(all(s["usage_pct"] is None for s in sols))

	def test_conversations_latest_per_conversation(self):
		t0 = add_to_date(now_datetime(), hours=-3)
		make_event(self.gw, "c1", "first", self.orders, received_at=t0)
		make_event(self.gw, "c1", "y" * 300, self.orders, received_at=add_to_date(t0, hours=1))
		make_event(self.gw, "c2", "faq q", self.faq)
		rows = rm.list_solution_conversations(self.orders)
		self.assertEqual(len(rows), 1)
		self.assertEqual(set(rows[0]), {"contact", "preview", "solution", "gateway", "ts"})
		self.assertEqual((rows[0]["contact"], rows[0]["gateway"], rows[0]["solution"]), ("c1", self.gw, self.orders))
		self.assertLess(len(rows[0]["preview"]), 100)
		everything = rm.list_solution_conversations(None)
		self.assertEqual({r["contact"] for r in everything if r["gateway"] == self.gw}, {"c1", "c2"})

	def test_get_intents(self):
		intents = rm.get_intents()
		self.assertEqual(len(intents), 6)
		self.assertTrue(all(set(i) == INTENT_KEYS for i in intents))
		orders = next(i for i in intents if i["id"] == "orders")
		self.assertEqual((orders["sample_name"], orders["entry"]), ("Order desk", "keywords"))

	def test_json_string_args(self):
		self.assertEqual(rm.get_solution_overview(json.dumps(self.orders))["name"], self.orders)
		self.assertEqual(rm.get_solution_overview(self.orders)["name"], self.orders)
		self.assertEqual(rm.get_solution_overview({"name": self.orders})["name"], self.orders)
		self.assertEqual({r["purpose"] for r in rm.list_solutions(json.dumps("orders"))}, {"orders"})
		self.assertTrue(rm.list_entry_points(json.dumps(self.orders)))
		self.assertEqual(rm.get_number_summary(json.dumps(self.gw))["gateway"], self.gw)
		self.assertEqual(rm.list_solution_conversations(json.dumps(self.orders)), [])

	def test_not_found_and_invalid(self):
		self.assertEqual(rm.get_solution_overview("nope-zzz")["error"]["code"], "not_found")
		self.assertEqual(rm.get_number_summary("nope-zzz")["error"]["code"], "not_found")
		self.assertEqual(rm.list_entry_points("nope-zzz")["error"]["code"], "not_found")
		self.assertEqual(set(rm.get_solution_overview("nope-zzz")["error"]), {"code", "message"})
