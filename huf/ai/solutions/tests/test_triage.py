import unittest

from huf.ai.solutions.triage import build_triage_prompt, parse_triage_answer, triage_options

SOLS = {
	"orders": {"status": "Live", "test_mode": False, "title": "Orders"},
	"care": {"status": "Live", "test_mode": False, "title": "Customer care"},
	"paused": {"status": "Paused", "test_mode": False, "title": "Aardvark"},
	"testing": {"status": "Live", "test_mode": True, "title": "Beta"},
}
RULES = [
	{"name": "r1", "priority": 1, "match_type": "Keyword", "match_values": ["x"], "solution": "orders", "is_enabled": 1},
	{"name": "r2", "priority": 2, "match_type": "Keyword", "match_values": ["y"], "solution": "care", "is_enabled": 1},
	{"name": "r3", "priority": 3, "match_type": "Catch-all", "match_values": [], "solution": "care", "is_enabled": 1},
	{"name": "r4", "priority": 4, "match_type": "Keyword", "match_values": ["z"], "solution": "paused", "is_enabled": 1},
	{"name": "r5", "priority": 5, "match_type": "Keyword", "match_values": ["z"], "solution": "testing", "is_enabled": 1},
	{"name": "r6", "priority": 6, "match_type": "Keyword", "match_values": ["z"], "solution": "orders", "is_enabled": 0},
]


class TestTriage(unittest.TestCase):
	def test_options_sorted_by_title_deduped_live_only(self):
		opts = triage_options(RULES, SOLS)
		self.assertEqual(
			opts,
			[
				{"index": 1, "solution": "care", "title": "Customer care"},
				{"index": 2, "solution": "orders", "title": "Orders"},
			],
		)

	def test_options_include_inactive(self):
		opts = triage_options(RULES, SOLS, include_inactive=True)
		self.assertEqual([o["solution"] for o in opts], ["paused", "testing", "care", "orders"])

	def test_prompt(self):
		opts = triage_options(RULES, SOLS)
		self.assertEqual(
			build_triage_prompt(opts, brand="Harbor Bakery"),
			"Hi, this is Harbor Bakery. Reply:\n1 for Customer care\n2 for Orders",
		)
		self.assertTrue(build_triage_prompt(opts).startswith("Hi, this is us. Reply:"))

	def test_parse(self):
		opts = triage_options(RULES, SOLS)
		self.assertEqual(parse_triage_answer("1", opts), "care")
		self.assertEqual(parse_triage_answer("2.", opts), "orders")
		self.assertEqual(parse_triage_answer("  2  ", opts), "orders")
		for bad in ("3", "0", "one", "1 please", "", None, "11", "-1"):
			self.assertIsNone(parse_triage_answer(bad, opts))


if __name__ == "__main__":
	unittest.main()
