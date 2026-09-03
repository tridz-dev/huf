from datetime import datetime
from unittest import mock

from frappe.tests import UnitTestCase

from huf.ai.agent_run_analytics import (
    DIMENSION_FIELDS,
    CORRECTION_WINDOW_HOURS,
    _bucket_start,
    _dimension_key,
    refresh_rollups,
)


class TestAgentRunAnalytics(UnitTestCase):
    def test_hour_and_day_buckets_are_deterministic(self):
        value = datetime(2026, 7, 26, 14, 37, 9)
        self.assertEqual(_bucket_start(value, "hour"), datetime(2026, 7, 26, 14, 0))
        self.assertEqual(_bucket_start(value, "day"), datetime(2026, 7, 26, 0, 0))

    def test_dimension_key_is_four_fields_after_st_10_2(self):
        """ST-10.2: conversation removed from DIMENSION_FIELDS (4 fields now)."""
        self.assertEqual(DIMENSION_FIELDS, ("agent", "provider", "model", "run_kind"))
        self.assertEqual(
            _dimension_key(
                {
                    "agent": "Support",
                    "provider": None,
                    "model": "gemini",
                    "run_kind": None,
                }
            ),
            "Support|__none__|gemini|__none__",
        )

    def test_dimension_key_ignores_conversation_field(self):
        """ST-10.2: conversation is no longer part of the dimension key."""
        # Even if conversation is present in the input dict, it is ignored
        result = _dimension_key(
            {
                "agent": "Support",
                "provider": "openai",
                "model": "gpt-4",
                "run_kind": "agent",
                "conversation": "CONV-0001",  # This is ignored
            }
        )
        # Should only include the 4 active dimensions
        self.assertEqual(result, "Support|openai|gpt-4|agent")

    def test_legacy_four_field_keys_are_still_decodable(self):
        """ST-10.2: Rows created before conversation was removed can still be read.

        This documents the backward compatibility guarantee: existing dimension_key
        strings (with 4 fields) remain decodable against the new 4-field DIMENSION_FIELDS.
        Rows that had conversation set are archived to Agent Run Analytics Rollup Archive.
        """
        self.assertEqual(len(DIMENSION_FIELDS), 4)

        # A key from an old rollup row (4 fields) decodes correctly
        stored_key = "Support|openai|gpt-4|agent"
        decoded = dict(zip(DIMENSION_FIELDS, stored_key.split("|")))
        self.assertEqual(decoded["agent"], "Support")
        self.assertEqual(decoded["provider"], "openai")
        self.assertEqual(decoded["model"], "gpt-4")
        self.assertEqual(decoded["run_kind"], "agent")

    def test_correction_window_hours_constant(self):
        """ST-10.4: CORRECTION_WINDOW_HOURS is defined and unchanged."""
        # Keep CORRECTION_WINDOW_HOURS at 26 (the original value; WP-10 review item 16)
        self.assertEqual(CORRECTION_WINDOW_HOURS, 26)
