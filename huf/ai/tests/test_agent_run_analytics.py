from datetime import datetime

from frappe.tests import UnitTestCase

from huf.ai.agent_run_analytics import DIMENSION_FIELDS, _bucket_start, _dimension_key


class TestAgentRunAnalytics(UnitTestCase):
    def test_hour_and_day_buckets_are_deterministic(self):
        value = datetime(2026, 7, 26, 14, 37, 9)
        self.assertEqual(_bucket_start(value, "hour"), datetime(2026, 7, 26, 14, 0))
        self.assertEqual(_bucket_start(value, "day"), datetime(2026, 7, 26, 0, 0))

    def test_dimension_key_preserves_missing_dimensions(self):
        self.assertEqual(
            _dimension_key(
                {
                    "agent": "Support",
                    "provider": None,
                    "model": "gemini",
                    "run_kind": None,
                    "conversation": None,
                }
            ),
            "Support|__none__|gemini|__none__|__none__",
        )

    def test_dimension_key_includes_conversation(self):
        self.assertEqual(
            _dimension_key(
                {
                    "agent": "Support",
                    "provider": "openai",
                    "model": "gpt-4",
                    "run_kind": "agent",
                    "conversation": "CONV-0001",
                }
            ),
            "Support|openai|gpt-4|agent|CONV-0001",
        )

    def test_conversation_is_appended_last_so_stored_keys_stay_decodable(self):
        # dimension_key strings are persisted on existing rollup rows. Appending
        # conversation keeps every previously-stored 4-field key decodable: it
        # simply reads back with conversation == "__none__". Inserting it earlier
        # would silently reinterpret every stored key's remaining fields.
        self.assertEqual(DIMENSION_FIELDS[:4], ("agent", "provider", "model", "run_kind"))
        self.assertEqual(DIMENSION_FIELDS[-1], "conversation")

        stored_legacy_key = "Support|openai|gpt-4|agent"
        decoded = dict(zip(DIMENSION_FIELDS, stored_legacy_key.split("|")))
        self.assertEqual(decoded["agent"], "Support")
        self.assertEqual(decoded["run_kind"], "agent")
        self.assertNotIn("conversation", decoded)
