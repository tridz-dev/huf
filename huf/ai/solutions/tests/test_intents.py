import unittest

from huf.ai.solutions import intents as mod

EXPECTED_IDS = ["answer", "orders", "support", "bookings", "updates", "team"]
VALID_ENTRY = {"keywords", "catchall", "allowlist", "none"}
INTENT_FIELDS = {"id", "name", "desc", "icon", "sample_name", "entry", "keywords", "ref", "suggested_templates", "policy"}


class TestIntents(unittest.TestCase):
	def test_exactly_six_intents_with_mockup_ids(self):
		self.assertEqual([i["id"] for i in mod.INTENTS], EXPECTED_IDS)
		self.assertEqual(mod.intent_ids(), EXPECTED_IDS)

	def test_ids_unique(self):
		ids = [i["id"] for i in mod.INTENTS]
		self.assertEqual(len(ids), len(set(ids)))

	def test_fields_match_contract(self):
		for intent in mod.INTENTS:
			self.assertEqual(set(intent.keys()), INTENT_FIELDS, intent["id"])

	def test_entry_kinds_valid(self):
		for intent in mod.INTENTS:
			self.assertIn(intent["entry"], VALID_ENTRY, intent["id"])

	def test_keywords_empty_for_non_keyword_entries(self):
		for intent in mod.INTENTS:
			if intent["entry"] in ("catchall", "allowlist", "none"):
				self.assertEqual(intent["keywords"], [], intent["id"])

	def test_keyword_entries_have_keywords(self):
		for intent in mod.INTENTS:
			if intent["entry"] == "keywords":
				self.assertTrue(intent["keywords"], intent["id"])

	def test_get_intent(self):
		self.assertEqual(mod.get_intent("orders")["name"], "Take orders")
		self.assertIsNone(mod.get_intent("missing"))

	def test_purposes_order(self):
		self.assertEqual(mod.PURPOSES, ("answer", "orders", "support", "bookings", "updates", "team", "custom"))


if __name__ == "__main__":
	unittest.main()
