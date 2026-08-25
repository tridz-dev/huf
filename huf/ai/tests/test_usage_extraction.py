# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Unit tests for huf.ai.usage_extraction, the single source of truth for
per-round LLM usage extraction (replaces four drifted inline copies in
huf/ai/providers/litellm.py and huf/ai/agent_integration.py).
"""

import unittest
from types import SimpleNamespace

from huf.ai.usage_extraction import extract_round_usage, normalise_usage_payload


class TestExtractRoundUsage(unittest.TestCase):

    def test_none_usage_returns_zeroed_dict(self):
        result = extract_round_usage(None)
        self.assertEqual(
            result,
            {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
            },
        )

    def test_object_shaped_usage_with_object_details(self):
        usage = SimpleNamespace(
            prompt_tokens=100,
            completion_tokens=40,
            prompt_tokens_details=SimpleNamespace(cached_tokens=10, cache_creation_input_tokens=5),
        )
        result = extract_round_usage(usage)
        self.assertEqual(result["input_tokens"], 100)
        self.assertEqual(result["output_tokens"], 40)
        self.assertEqual(result["cache_read_tokens"], 10)
        self.assertEqual(result["cache_write_tokens"], 5)

    def test_dict_shaped_usage_with_dict_details(self):
        usage = {
            "prompt_tokens": 200,
            "completion_tokens": 80,
            "prompt_tokens_details": {
                "cached_tokens": 20,
                "cache_creation_input_tokens": 15,
            },
        }
        result = extract_round_usage(usage)
        self.assertEqual(result["input_tokens"], 200)
        self.assertEqual(result["output_tokens"], 80)
        self.assertEqual(result["cache_read_tokens"], 20)
        self.assertEqual(result["cache_write_tokens"], 15)

    def test_dict_details_alt_keys(self):
        usage = {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "prompt_tokens_details": {
                "cache_hit_tokens": 3,
                "cache_write_tokens": 2,
            },
        }
        result = extract_round_usage(usage)
        self.assertEqual(result["cache_read_tokens"], 3)
        self.assertEqual(result["cache_write_tokens"], 2)

    def test_object_details_alt_keys(self):
        usage = SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=5,
            prompt_tokens_details=SimpleNamespace(cache_hit_tokens=7, cache_creation_tokens=9),
        )
        result = extract_round_usage(usage)
        self.assertEqual(result["cache_read_tokens"], 7)
        self.assertEqual(result["cache_write_tokens"], 9)

    def test_prompt_tokens_vs_input_tokens_fallback(self):
        # The two legacy sites disagreed here: the sync site fell back to
        # "input_tokens", the streaming site fell back to "prompt_tokens".
        # The union must accept either.
        usage_with_prompt_tokens = {"prompt_tokens": 55, "completion_tokens": 11}
        result = extract_round_usage(usage_with_prompt_tokens)
        self.assertEqual(result["input_tokens"], 55)

        usage_with_input_tokens_only = {"input_tokens": 33, "output_tokens": 7}
        result = extract_round_usage(usage_with_input_tokens_only)
        self.assertEqual(result["input_tokens"], 33)
        self.assertEqual(result["output_tokens"], 7)

        # When both are present, prompt_tokens/completion_tokens win.
        usage_with_both = {
            "prompt_tokens": 1,
            "input_tokens": 999,
            "completion_tokens": 2,
            "output_tokens": 888,
        }
        result = extract_round_usage(usage_with_both)
        self.assertEqual(result["input_tokens"], 1)
        self.assertEqual(result["output_tokens"], 2)

    def test_cache_miss_tokens_does_not_leak_into_cache_write(self):
        usage = {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "cache_miss_tokens": 999,
        }
        result = extract_round_usage(usage)
        self.assertEqual(result["cache_write_tokens"], 0)

        # Also verify it doesn't leak when present alongside a real
        # cache-write key -- the real key should win, not cache_miss_tokens.
        usage_with_both = {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "cache_creation_tokens": 4,
            "cache_miss_tokens": 999,
        }
        result = extract_round_usage(usage_with_both)
        self.assertEqual(result["cache_write_tokens"], 4)

    def test_top_level_cache_keys_without_details_block(self):
        usage = {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "cached_tokens": 6,
            "cache_creation_input_tokens": 8,
        }
        result = extract_round_usage(usage)
        self.assertEqual(result["cache_read_tokens"], 6)
        self.assertEqual(result["cache_write_tokens"], 8)

    def test_missing_fields_default_to_zero(self):
        result = extract_round_usage({})
        self.assertEqual(
            result,
            {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
            },
        )

    def test_never_raises_on_malformed_payload(self):
        class Weird:
            @property
            def prompt_tokens(self):
                raise RuntimeError("boom")

        result = extract_round_usage(Weird())
        self.assertEqual(result["input_tokens"], 0)

    def test_result_always_has_int_values(self):
        usage = {"prompt_tokens": "12", "completion_tokens": None}
        result = extract_round_usage(usage)
        for value in result.values():
            self.assertIsInstance(value, int)


class TestNormaliseUsagePayload(unittest.TestCase):

    def test_none_returns_none(self):
        self.assertIsNone(normalise_usage_payload(None))

    def test_dict_returned_unchanged(self):
        payload = {"prompt_tokens": 1}
        self.assertIs(normalise_usage_payload(payload), payload)

    def test_object_with_dict_method(self):
        class LegacyModel:
            def dict(self):
                return {"prompt_tokens": 5}

        self.assertEqual(normalise_usage_payload(LegacyModel()), {"prompt_tokens": 5})

    def test_object_with_model_dump_method(self):
        class PydanticV2Model:
            def model_dump(self):
                return {"prompt_tokens": 9}

        self.assertEqual(normalise_usage_payload(PydanticV2Model()), {"prompt_tokens": 9})

    def test_unsupported_object_returns_none(self):
        self.assertIsNone(normalise_usage_payload(object()))


if __name__ == "__main__":
    unittest.main()
