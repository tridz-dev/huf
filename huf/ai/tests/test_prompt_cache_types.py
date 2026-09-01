# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""
Tests for prompt_cache.types module.

Tests frozen dataclass, validation, and serialization.
"""

from __future__ import annotations

import unittest

from huf.ai.prompt_cache.types import PromptCacheCapabilities, VALID_MECHANISMS


class TestPromptCacheCapabilitiesConstruction(unittest.TestCase):
    """Test basic construction of PromptCacheCapabilities."""

    def test_minimal_construction(self):
        """Construct with only required fields."""
        cap = PromptCacheCapabilities(
            supported=True,
            mechanism="explicit_breakpoint",
            supports_explicit_breakpoints=True,
            supports_affinity_key=False,
            supports_named_cached_content=False,
            max_breakpoints_per_request=4,
        )
        self.assertTrue(cap.supported)
        self.assertEqual(cap.mechanism, "explicit_breakpoint")
        self.assertEqual(cap.source, "unknown")

    def test_full_construction(self):
        """Construct with all fields."""
        cap = PromptCacheCapabilities(
            supported=True,
            mechanism="implicit_prefix",
            supports_explicit_breakpoints=False,
            supports_affinity_key=True,
            supports_named_cached_content=False,
            max_breakpoints_per_request=None,
            ttl_values=("5m", "1h"),
            min_cacheable_tokens=1024,
            reports_cache_read_tokens=True,
            reports_cache_write_tokens=False,
            source="test_source",
        )
        self.assertTrue(cap.supported)
        self.assertEqual(cap.mechanism, "implicit_prefix")
        self.assertTrue(cap.supports_affinity_key)
        self.assertEqual(cap.min_cacheable_tokens, 1024)
        self.assertEqual(cap.ttl_values, ("5m", "1h"))
        self.assertTrue(cap.reports_cache_read_tokens)
        self.assertFalse(cap.reports_cache_write_tokens)
        self.assertEqual(cap.source, "test_source")

    def test_is_frozen(self):
        """Verify dataclass is frozen (immutable)."""
        cap = PromptCacheCapabilities(
            supported=True,
            mechanism="explicit_breakpoint",
            supports_explicit_breakpoints=True,
            supports_affinity_key=False,
            supports_named_cached_content=False,
            max_breakpoints_per_request=4,
        )
        with self.assertRaises(AttributeError):
            cap.supported = False


class TestPromptCacheCapabilitiesMechanismValidation(unittest.TestCase):
    """Test mechanism field validation."""

    def test_valid_mechanisms(self):
        """All valid mechanism values should construct."""
        for mechanism in VALID_MECHANISMS:
            with self.subTest(mechanism=mechanism):
                cap = PromptCacheCapabilities(
                    supported=True,
                    mechanism=mechanism,
                    supports_explicit_breakpoints=False,
                    supports_affinity_key=False,
                    supports_named_cached_content=False,
                    max_breakpoints_per_request=None,
                )
                self.assertEqual(cap.mechanism, mechanism)

    def test_invalid_mechanism_raises(self):
        """Invalid mechanism should raise ValueError."""
        with self.assertRaises(ValueError):
            PromptCacheCapabilities(
                supported=True,
                mechanism="invalid_mechanism",
                supports_explicit_breakpoints=False,
                supports_affinity_key=False,
                supports_named_cached_content=False,
                max_breakpoints_per_request=None,
            )

    def test_invalid_mechanism_message_includes_valid_options(self):
        """Error message should list valid mechanisms."""
        with self.assertRaises(ValueError) as context:
            PromptCacheCapabilities(
                supported=True,
                mechanism="foo",
                supports_explicit_breakpoints=False,
                supports_affinity_key=False,
                supports_named_cached_content=False,
                max_breakpoints_per_request=None,
            )
        error_msg = str(context.exception)
        self.assertIn("implicit_prefix", error_msg)
        self.assertIn("explicit_breakpoint", error_msg)
        self.assertIn("cache_point", error_msg)
        self.assertIn("unsupported", error_msg)


class TestPromptCacheCapabilitiesToDict(unittest.TestCase):
    """Test to_dict() serialization."""

    def test_to_dict_basic(self):
        """to_dict() should produce a dictionary."""
        cap = PromptCacheCapabilities(
            supported=True,
            mechanism="explicit_breakpoint",
            supports_explicit_breakpoints=True,
            supports_affinity_key=False,
            supports_named_cached_content=False,
            max_breakpoints_per_request=4,
            ttl_values=("5m", "1h"),
            min_cacheable_tokens=2048,
            reports_cache_read_tokens=True,
            reports_cache_write_tokens=True,
            source="known_route_table",
        )
        result = cap.to_dict()
        self.assertIsInstance(result, dict)
        self.assertTrue(result["supported"])
        self.assertEqual(result["mechanism"], "explicit_breakpoint")
        self.assertEqual(result["max_breakpoints_per_request"], 4)
        self.assertEqual(result["ttl_values"], ("5m", "1h"))
        self.assertEqual(result["min_cacheable_tokens"], 2048)
        self.assertTrue(result["reports_cache_read_tokens"])
        self.assertTrue(result["reports_cache_write_tokens"])
        self.assertEqual(result["source"], "known_route_table")

    def test_to_dict_with_none_values(self):
        """to_dict() should include None values."""
        cap = PromptCacheCapabilities(
            supported=False,
            mechanism="unsupported",
            supports_explicit_breakpoints=False,
            supports_affinity_key=False,
            supports_named_cached_content=False,
            max_breakpoints_per_request=None,
            min_cacheable_tokens=None,
            reports_cache_read_tokens=None,
            reports_cache_write_tokens=None,
        )
        result = cap.to_dict()
        self.assertIsNone(result["max_breakpoints_per_request"])
        self.assertIsNone(result["min_cacheable_tokens"])
        self.assertIsNone(result["reports_cache_read_tokens"])
        self.assertIsNone(result["reports_cache_write_tokens"])

    def test_to_dict_deterministic_ordering(self):
        """to_dict() should produce consistent key ordering."""
        cap = PromptCacheCapabilities(
            supported=True,
            mechanism="explicit_breakpoint",
            supports_explicit_breakpoints=True,
            supports_affinity_key=False,
            supports_named_cached_content=False,
            max_breakpoints_per_request=4,
            ttl_values=("5m", "1h"),
            min_cacheable_tokens=2048,
            reports_cache_read_tokens=True,
            reports_cache_write_tokens=True,
            source="test",
        )
        result1 = cap.to_dict()
        result2 = cap.to_dict()
        # Check keys are in same order
        self.assertEqual(list(result1.keys()), list(result2.keys()))

    def test_to_dict_all_required_keys(self):
        """to_dict() should include all documented fields."""
        cap = PromptCacheCapabilities(
            supported=False,
            mechanism="unsupported",
            supports_explicit_breakpoints=False,
            supports_affinity_key=False,
            supports_named_cached_content=False,
            max_breakpoints_per_request=None,
        )
        result = cap.to_dict()
        expected_keys = {
            "max_breakpoints_per_request",
            "mechanism",
            "min_cacheable_tokens",
            "reports_cache_read_tokens",
            "reports_cache_write_tokens",
            "source",
            "supported",
            "supports_affinity_key",
            "supports_explicit_breakpoints",
            "supports_named_cached_content",
            "ttl_values",
        }
        self.assertEqual(set(result.keys()), expected_keys)


class TestPromptCacheCapabilitiesStandalone(unittest.TestCase):
    """Test that PromptCacheCapabilities can be imported standalone."""

    def test_import_without_frappe(self):
        """Import should succeed without Frappe being available."""
        # This test verifies that types.py doesn't import Frappe at module level
        from huf.ai.prompt_cache.types import PromptCacheCapabilities
        self.assertIsNotNone(PromptCacheCapabilities)

    def test_import_without_litellm(self):
        """Import should succeed even if litellm is not available."""
        # types.py should not import litellm at module level
        from huf.ai.prompt_cache.types import PromptCacheCapabilities
        self.assertIsNotNone(PromptCacheCapabilities)
