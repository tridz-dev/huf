import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.solutions import loader
from huf.ai.solutions.tests._fixtures import make_agent, make_binding, make_gateway, make_solution


class TestLoader(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.gw = make_gateway().name
		self.agent = make_agent()

	def tearDown(self):
		frappe.db.rollback()

	def test_rules_ordering_and_splitting(self):
		s = make_solution().name
		b_late = make_binding(self.gw, self.agent, priority=20, match_type="Keyword",
			match_value="Order,  track ,", solution=s)
		b_tag = make_binding(self.gw, self.agent, priority=5, match_type="Ad or link tag",
			match_value="spring, summer", solution=s)
		b_tie = make_binding(self.gw, self.agent, priority=20, match_type="Catch-all", solution=s)
		rules = loader.load_rules(self.gw)
		self.assertEqual([r["name"] for r in rules], [b_tag.name, b_late.name, b_tie.name])
		self.assertEqual(rules[0]["match_values"], ["spring", "summer"])
		self.assertEqual(rules[1]["match_values"], ["Order", "track"])
		self.assertEqual(rules[2]["match_values"], [])
		self.assertEqual(
			set(rules[0]), {"name", "priority", "match_type", "match_values", "target_type",
				"agent", "flow", "solution", "is_enabled"})
		self.assertIs(rules[0]["is_enabled"], True)

	def test_rules_scoped_to_gateway(self):
		other = make_gateway().name
		make_binding(other, self.agent, match_type="Catch-all")
		self.assertEqual(loader.load_rules(self.gw), [])

	def test_solution_states(self):
		live = make_solution(title="Live one")
		paused = make_solution(status="Paused")
		test = make_solution(test_mode=1)
		st = loader.load_solution_states([live.name, paused.name, test.name])
		self.assertEqual(st[live.name], {"status": "Live", "test_mode": False, "title": "Live one"})
		self.assertEqual(st[paused.name]["status"], "Paused")
		self.assertTrue(st[test.name]["test_mode"])
		self.assertEqual(st[test.name]["status"], "Paused")
		self.assertEqual(set(loader.load_solution_states([live.name])), {live.name})
		self.assertEqual(loader.load_solution_states([]), {})
		self.assertTrue({live.name, paused.name} <= set(loader.load_solution_states()))

	def test_gateway_settings_defaults(self):
		s = loader.load_gateway_settings(self.gw)
		self.assertEqual(s, {"pin_ttl_hours": 24, "keyword_beats_pin": False, "default": None})

	def test_gateway_settings_values(self):
		gw = make_gateway(pin_ttl_hours=6, keyword_beats_pin=1, default_target_type="Agent",
			default_agent=self.agent).name
		s = loader.load_gateway_settings(gw)
		self.assertEqual(s["pin_ttl_hours"], 6)
		self.assertIs(s["keyword_beats_pin"], True)
		self.assertEqual(s["default"], {"target_type": "Agent", "agent": self.agent, "flow": None})

	def test_gateway_settings_missing_gateway(self):
		self.assertEqual(loader.load_gateway_settings("nope-gw")["pin_ttl_hours"], 24)
