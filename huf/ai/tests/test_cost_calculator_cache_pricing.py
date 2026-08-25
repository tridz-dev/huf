# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Tests for huf.ai.cost_calculator._calculate_from_custom_pricing.

Cache reads (`cached_tokens`) and cache writes (`cache_creation_tokens`) are
both SUBSETS of `input_tokens` as reported by the provider, not additional
tokens layered on top of it. So when a cache rate IS configured, that
portion is billed at the cache rate and subtracted from the pool billed at
the base input rate; when a cache rate is NOT configured, those tokens stay
in the base-rate pool rather than being dropped or double-charged.

Covers:
  - no cache rates configured at all -> everything (including tokens that
    happen to be cache reads/writes) billed at the base input rate
  - a cache READ rate only -> read tokens billed separately, subtracted from
    the base pool; write tokens (no rate configured) stay at base rate
  - both cache rates configured -> both subtracted from the base pool and
    billed at their own rates
  - cache-write rate handling for 0 vs None, and the asymmetry with the
    cache-READ rate's 0-is-a-valid-free-price treatment -- see the
    "IMPORTANT" note below; this test file demonstrates and reports what
    `_calculate_from_custom_pricing` actually does with a raw 0, since that
    is the exact input shape the plan calls out as the case worth pinning.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _stub_env  # noqa: E402

_stub_env.install()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from huf.ai.cost_calculator import _calculate_from_custom_pricing  # noqa: E402


def _pricing(input_price=1.0, output_price=2.0, read_price=None, write_price=None):
    return {
        "input_cost_per_1m_tokens": input_price,
        "output_cost_per_1m_tokens": output_price,
        "cached_input_cost_per_1m_tokens": read_price,
        "cached_input_write_cost_per_1m_tokens": write_price,
    }


class TestNoCacheRatesConfigured(unittest.TestCase):
    def test_everything_billed_at_base_rate_when_no_cache_rates_set(self):
        pricing = _pricing(input_price=1.0, output_price=2.0, read_price=None, write_price=None)
        cost = _calculate_from_custom_pricing(
            pricing, input_tokens=1000, output_tokens=500, cached_tokens=200, cache_creation_tokens=100
        )
        # 1000 input tokens (cache reads/writes are a subset, not extra, and
        # with no cache rate configured they are billed at the base rate
        # like every other input token) + 500 output tokens.
        expected = (1000 / 1_000_000) * 1.0 + (500 / 1_000_000) * 2.0
        self.assertAlmostEqual(cost, expected)

    def test_zero_cached_and_cache_creation_tokens_is_a_no_op(self):
        pricing = _pricing(input_price=1.0, output_price=2.0)
        cost = _calculate_from_custom_pricing(
            pricing, input_tokens=1000, output_tokens=500, cached_tokens=0, cache_creation_tokens=0
        )
        expected = (1000 / 1_000_000) * 1.0 + (500 / 1_000_000) * 2.0
        self.assertAlmostEqual(cost, expected)


class TestReadRateOnly(unittest.TestCase):
    def test_read_tokens_billed_separately_and_subtracted_from_base_pool(self):
        pricing = _pricing(input_price=1.0, output_price=2.0, read_price=0.5, write_price=None)
        cost = _calculate_from_custom_pricing(
            pricing, input_tokens=1000, output_tokens=500, cached_tokens=200, cache_creation_tokens=100
        )
        # 200 read tokens at 0.5/1M, remaining (1000-200)=800 input tokens at
        # base rate 1.0/1M -- cache_creation_tokens (100) has no configured
        # write rate here, so it stays inside the base-rate pool untouched
        # (it was never subtracted out).
        expected = (200 / 1_000_000) * 0.5 + (800 / 1_000_000) * 1.0 + (500 / 1_000_000) * 2.0
        self.assertAlmostEqual(cost, expected)

    def test_read_rate_of_zero_is_a_valid_free_price_not_unconfigured(self):
        # Unlike the write rate (see TestCacheWriteRateZeroVsNone below),
        # `_calculate_from_custom_pricing` treats a read price of 0 as an
        # explicitly configured, genuinely free rate: `cached_price is not
        # None` is True for 0, so the branch runs and 200 tokens are pulled
        # out of the base-rate pool for zero cost -- not billed as regular
        # input tokens.
        pricing = _pricing(input_price=1.0, output_price=2.0, read_price=0.0, write_price=None)
        cost = _calculate_from_custom_pricing(
            pricing, input_tokens=1000, output_tokens=500, cached_tokens=200, cache_creation_tokens=0
        )
        expected = (0 / 1_000_000) * 0.0 + (800 / 1_000_000) * 1.0 + (500 / 1_000_000) * 2.0
        self.assertAlmostEqual(cost, expected)


class TestBothRatesConfigured(unittest.TestCase):
    def test_both_read_and_write_subtracted_from_base_pool_and_billed_separately(self):
        pricing = _pricing(input_price=1.0, output_price=2.0, read_price=0.5, write_price=1.25)
        cost = _calculate_from_custom_pricing(
            pricing, input_tokens=1000, output_tokens=500, cached_tokens=200, cache_creation_tokens=150
        )
        remaining = 1000 - 200 - 150  # 650
        expected = (
            (200 / 1_000_000) * 0.5
            + (150 / 1_000_000) * 1.25
            + (remaining / 1_000_000) * 1.0
            + (500 / 1_000_000) * 2.0
        )
        self.assertAlmostEqual(cost, expected)

    def test_remaining_input_never_goes_negative(self):
        # Pathological input where cached + cache_creation exceed input_tokens
        # (e.g. a provider miscount) must not produce a negative base pool.
        pricing = _pricing(input_price=1.0, output_price=0.0, read_price=0.5, write_price=0.5)
        cost = _calculate_from_custom_pricing(
            pricing, input_tokens=100, output_tokens=0, cached_tokens=80, cache_creation_tokens=80
        )
        expected = (80 / 1_000_000) * 0.5 + (80 / 1_000_000) * 0.5 + (0 / 1_000_000) * 1.0
        self.assertAlmostEqual(cost, expected)
        self.assertGreaterEqual(cost, 0)


class TestCacheWriteRateZeroVsNone(unittest.TestCase):
    """A cache-write rate of 0 means "not configured", exactly like None.

    The AI Model field is a plain Float with no separate presence flag, so a
    bare 0 cannot be distinguished from unset. `get_model_pricing()` normalises
    0 -> None before building the pricing dict, and
    `_calculate_from_custom_pricing` independently treats a falsy write rate as
    unconfigured, so the invariant holds even for a caller that constructs a
    pricing dict without going through `get_model_pricing`.

    "Not configured" must mean the cache-creation tokens stay in the pool
    billed at the ordinary input rate -- NOT that they are billed as free and
    pulled out of that pool, which would silently understate cost.

    Note the deliberate asymmetry with the cache-READ rate, which keeps an
    `is not None` check: 0 has always meant a genuinely free read there, and
    changing that would alter costs already being reported.
    """

    def test_write_rate_of_none_leaves_cache_creation_tokens_at_base_rate(self):
        pricing = _pricing(input_price=1.0, output_price=2.0, read_price=None, write_price=None)
        cost = _calculate_from_custom_pricing(
            pricing, input_tokens=1000, output_tokens=0, cached_tokens=0, cache_creation_tokens=200
        )
        expected_if_treated_as_base_rate = (1000 / 1_000_000) * 1.0
        self.assertAlmostEqual(cost, expected_if_treated_as_base_rate)

    def test_write_rate_of_raw_zero_behaves_exactly_like_none(self):
        # A raw 0 must not be read as "cache writes are free". Both dicts must
        # bill the 200 cache-creation tokens at the ordinary input rate.
        pricing_with_none = _pricing(input_price=1.0, output_price=2.0, write_price=None)
        pricing_with_raw_zero = _pricing(input_price=1.0, output_price=2.0, write_price=0.0)

        cost_with_none = _calculate_from_custom_pricing(
            pricing_with_none, input_tokens=1000, output_tokens=0, cached_tokens=0, cache_creation_tokens=200
        )
        cost_with_raw_zero = _calculate_from_custom_pricing(
            pricing_with_raw_zero, input_tokens=1000, output_tokens=0, cached_tokens=0, cache_creation_tokens=200
        )

        self.assertAlmostEqual(cost_with_none, cost_with_raw_zero)
        # And both are the full base-rate cost, with nothing billed as free.
        self.assertAlmostEqual(cost_with_raw_zero, (1000 / 1_000_000) * 1.0)

    def test_a_real_nonzero_write_rate_is_still_applied(self):
        # Guard against "treat falsy as unconfigured" being over-applied: a
        # genuine rate must still be honoured and removed from the base pool.
        pricing = _pricing(input_price=1.0, output_price=0.0, read_price=None, write_price=5.0)
        cost = _calculate_from_custom_pricing(
            pricing, input_tokens=1000, output_tokens=0, cached_tokens=0, cache_creation_tokens=200
        )
        expected = (800 / 1_000_000) * 1.0 + (200 / 1_000_000) * 5.0
        self.assertAlmostEqual(cost, expected)
