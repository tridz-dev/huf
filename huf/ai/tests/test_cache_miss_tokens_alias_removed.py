# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
D3: the `cache_miss_tokens` alias is gone.

`huf/ai/tests/test_usage_extraction.py` already thoroughly covers that
`extract_round_usage` does not fold `cache_miss_tokens` into
`cache_write_tokens` (`test_cache_miss_tokens_does_not_leak_into_cache_write`,
both with and without a real cache-write key present alongside it). This file
adds only what that suite does not already assert: that the key
`cache_miss_tokens` itself never appears anywhere in the dict
`extract_round_usage` produces, for any input -- not just that its value
doesn't leak into `cache_write_tokens`, but that it isn't echoed through
under its own name either. `extract_round_usage`'s docstring guarantees its
result always has exactly four keys; this pins that guarantee specifically
against the retired alias.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _stub_env  # noqa: E402

_stub_env.install()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from huf.ai.usage_extraction import extract_round_usage  # noqa: E402


class TestCacheMissTokensAliasIsGone(unittest.TestCase):
    def test_cache_miss_tokens_key_never_appears_in_result(self):
        usage = {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "cache_miss_tokens": 999,
        }
        result = extract_round_usage(usage)
        self.assertNotIn("cache_miss_tokens", result)

    def test_result_keys_are_exactly_the_documented_four(self):
        usage = {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "cache_miss_tokens": 999,
            "cached_tokens": 3,
            "cache_creation_tokens": 4,
        }
        result = extract_round_usage(usage)
        self.assertEqual(
            set(result.keys()),
            {"input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"},
        )

    def test_cache_miss_tokens_absent_even_with_no_other_cache_fields(self):
        # A payload where cache_miss_tokens is the ONLY cache-shaped field
        # present must still come back with cache_write_tokens == 0, not
        # cache_miss_tokens's value under any key.
        usage = {"prompt_tokens": 1, "completion_tokens": 1, "cache_miss_tokens": 500}
        result = extract_round_usage(usage)
        self.assertEqual(result["cache_write_tokens"], 0)
        self.assertNotIn(500, result.values())


if __name__ == "__main__":
    unittest.main()
