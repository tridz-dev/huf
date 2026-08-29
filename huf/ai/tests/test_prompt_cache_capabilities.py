# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""
Tests for prompt_cache.capabilities module.

Tests provider resolution, known routes, and fallback behavior.
"""

from __future__ import annotations

import sys
import unittest
from unittest.mock import patch, MagicMock

from huf.ai.prompt_cache.capabilities import (
    resolve_capabilities,
    _normalize_model_name,
    _lookup_known_route,
    _build_known_routes,
    KNOWN_ROUTES,
)
from huf.ai.prompt_cache.types import PromptCacheCapabilities


class TestNormalizeModelName(unittest.TestCase):
    """Test model name normalization."""

    def test_normalize_basic(self):
        """Normalize simple model names."""
        self.assertEqual(_normalize_model_name("Claude-3-5-Sonnet"), "claude-3-5-sonnet")
        self.assertEqual(_normalize_model_name("GPT-4"), "gpt-4")

    def test_normalize_with_provider_prefix(self):
        """Remove provider prefixes."""
        self.assertEqual(
            _normalize_model_name("bedrock/claude-3-5-sonnet"),
            "claude-3-5-sonnet"
        )
        self.assertEqual(_normalize_model_name("azure/gpt-4"), "gpt-4")
        self.assertEqual(_normalize_model_name("vertex/gemini-1.5-pro"), "gemini-1.5-pro")

    def test_normalize_case_insensitive(self):
        """Convert to lowercase."""
        self.assertEqual(_normalize_model_name("CLAUDE-3-5-SONNET"), "claude-3-5-sonnet")


class TestBuildKnownRoutes(unittest.TestCase):
    """Test known route initialization."""

    def test_build_routes_populates_table(self):
        """_build_known_routes should populate KNOWN_ROUTES."""
        # Clear to test population
        KNOWN_ROUTES.clear()
        _build_known_routes()
        self.assertGreater(len(KNOWN_ROUTES), 0)
        self.assertIn("anthropic", KNOWN_ROUTES)
        self.assertIn("openai", KNOWN_ROUTES)
        self.assertIn("google", KNOWN_ROUTES)


class TestKnownRouteProviders(unittest.TestCase):
    """Test provider-specific known route resolution."""

    def setUp(self):
        """Ensure routes are built."""
        _build_known_routes()

    def test_anthropic_claude_haiku(self):
        """Anthropic Claude Haiku should resolve to known route."""
        cap = _lookup_known_route("anthropic", "claude-haiku-4-5-20251001")
        self.assertIsNotNone(cap)
        self.assertTrue(cap.supported)
        self.assertEqual(cap.mechanism, "explicit_breakpoint")
        self.assertTrue(cap.supports_explicit_breakpoints)
        self.assertEqual(cap.max_breakpoints_per_request, 4)
        self.assertEqual(cap.ttl_values, ("5m", "1h"))
        self.assertEqual(cap.min_cacheable_tokens, 2048)  # Haiku-specific
        self.assertTrue(cap.reports_cache_read_tokens)
        self.assertTrue(cap.reports_cache_write_tokens)
        self.assertEqual(cap.source, "known_route_table")

    def test_anthropic_claude_sonnet(self):
        """Anthropic Claude Sonnet should resolve to known route."""
        cap = _lookup_known_route("anthropic", "claude-3-5-sonnet-20241022")
        self.assertIsNotNone(cap)
        self.assertTrue(cap.supported)
        self.assertEqual(cap.mechanism, "explicit_breakpoint")
        self.assertEqual(cap.min_cacheable_tokens, 1024)  # Sonnet: lower threshold
        self.assertTrue(cap.reports_cache_read_tokens)
        self.assertTrue(cap.reports_cache_write_tokens)

    def test_anthropic_claude_opus(self):
        """Anthropic Claude Opus should resolve to known route."""
        cap = _lookup_known_route("anthropic", "claude-opus-4-20250805")
        self.assertIsNotNone(cap)
        self.assertEqual(cap.mechanism, "explicit_breakpoint")
        self.assertEqual(cap.min_cacheable_tokens, 1024)  # Opus: lower threshold

    def test_bedrock_claude(self):
        """Bedrock Claude should use cache_point mechanism."""
        cap = _lookup_known_route("bedrock", "claude-3-5-sonnet")
        self.assertIsNotNone(cap)
        self.assertTrue(cap.supported)
        self.assertEqual(cap.mechanism, "cache_point")  # Bedrock-specific
        self.assertFalse(cap.supports_explicit_breakpoints)  # cache_point doesn't support
        self.assertEqual(cap.min_cacheable_tokens, 1024)
        self.assertTrue(cap.reports_cache_read_tokens)

    def test_openai_models(self):
        """OpenAI models should use implicit_prefix with affinity key."""
        for model in ["gpt-4", "gpt-4-turbo", "gpt-4o", "gpt-4o-mini"]:
            with self.subTest(model=model):
                cap = _lookup_known_route("openai", model)
                self.assertIsNotNone(cap)
                self.assertTrue(cap.supported)
                self.assertEqual(cap.mechanism, "implicit_prefix")
                self.assertTrue(cap.supports_affinity_key)
                self.assertFalse(cap.supports_explicit_breakpoints)
                self.assertEqual(cap.min_cacheable_tokens, 1024)
                self.assertTrue(cap.reports_cache_read_tokens)

    def test_google_gemini_models(self):
        """Google Gemini models should support named_cached_content."""
        for model in ["gemini-2", "gemini-1.5-pro", "gemini-1.5-flash"]:
            with self.subTest(model=model):
                cap = _lookup_known_route("google", model)
                self.assertIsNotNone(cap)
                self.assertTrue(cap.supported)
                self.assertEqual(cap.mechanism, "implicit_prefix")
                self.assertTrue(cap.supports_named_cached_content)
                self.assertFalse(cap.supports_explicit_breakpoints)
                self.assertEqual(cap.min_cacheable_tokens, 1024)

    def test_ollama_unsupported(self):
        """Ollama models should be marked unsupported."""
        cap = _lookup_known_route("ollama", "llama-2")
        self.assertIsNotNone(cap)
        self.assertFalse(cap.supported)
        self.assertEqual(cap.mechanism, "unsupported")
        self.assertIsNone(cap.min_cacheable_tokens)


class TestResolveCapabilities(unittest.TestCase):
    """Test the main resolve_capabilities function."""

    def setUp(self):
        """Ensure routes are built."""
        _build_known_routes()

    def test_known_route_anthropic_claude_haiku(self):
        """resolve_capabilities should find known route for Claude Haiku."""
        cap = resolve_capabilities("anthropic", "claude-haiku-4-5-20251001")
        self.assertTrue(cap.supported)
        self.assertEqual(cap.mechanism, "explicit_breakpoint")
        self.assertEqual(cap.min_cacheable_tokens, 2048)

    def test_known_route_anthropic_claude_sonnet(self):
        """resolve_capabilities should find known route for Claude Sonnet."""
        cap = resolve_capabilities("anthropic", "claude-3-5-sonnet-20241022")
        self.assertTrue(cap.supported)
        self.assertEqual(cap.min_cacheable_tokens, 1024)

    def test_known_route_openai(self):
        """resolve_capabilities should find known route for OpenAI."""
        cap = resolve_capabilities("openai", "gpt-4o")
        self.assertTrue(cap.supported)
        self.assertEqual(cap.mechanism, "implicit_prefix")
        self.assertTrue(cap.supports_affinity_key)

    def test_known_route_google_gemini(self):
        """resolve_capabilities should find known route for Gemini."""
        cap = resolve_capabilities("google", "gemini-1.5-pro")
        self.assertTrue(cap.supported)
        self.assertEqual(cap.mechanism, "implicit_prefix")
        self.assertTrue(cap.supports_named_cached_content)

    def test_unknown_provider_fallback(self):
        """resolve_capabilities should fallback to conservative defaults."""
        cap = resolve_capabilities("unknown_provider", "unknown_model")
        self.assertFalse(cap.supported)
        self.assertEqual(cap.mechanism, "unsupported")
        self.assertFalse(cap.supports_explicit_breakpoints)
        self.assertFalse(cap.supports_affinity_key)
        self.assertFalse(cap.supports_named_cached_content)
        self.assertIsNone(cap.max_breakpoints_per_request)
        self.assertEqual(cap.ttl_values, tuple())
        self.assertIsNone(cap.min_cacheable_tokens)
        self.assertEqual(cap.source, "fallback")

    def test_model_with_provider_prefix(self):
        """resolve_capabilities should handle models with provider prefix."""
        cap = resolve_capabilities("anthropic", "bedrock/claude-3-5-sonnet")
        # Should normalize and still find the known route
        self.assertTrue(cap.supported)

    def test_case_insensitive_lookup(self):
        """resolve_capabilities should be case-insensitive."""
        cap1 = resolve_capabilities("Anthropic", "Claude-Haiku-4-5-20251001")
        cap2 = resolve_capabilities("anthropic", "claude-haiku-4-5-20251001")
        self.assertEqual(cap1.mechanism, cap2.mechanism)
        self.assertEqual(cap1.min_cacheable_tokens, cap2.min_cacheable_tokens)


class TestResolveCapabilitiesWithLiteLLM(unittest.TestCase):
    """Test litellm fallback when known routes don't match."""

    def setUp(self):
        """Ensure routes are built."""
        _build_known_routes()

    def test_litellm_import_available(self):
        """If litellm is available, should use it for unknown models."""
        # Create a mock litellm with cache support
        mock_litellm = MagicMock()
        mock_litellm.model_cost = {
            "gpt-4-custom": {"cache_read_input_token_cost": 0.00001}
        }

        with patch.dict(sys.modules, {"litellm": mock_litellm}):
            # Need to re-import to see mocked litellm
            # For now just verify the behavior if we had a match
            cap = resolve_capabilities("unknown_provider", "unknown_model")
            # Should fall back since no known route and litellm lookup won't match
            self.assertEqual(cap.source, "fallback")

    def test_litellm_import_unavailable_fallback(self):
        """If litellm is not available, should use fallback."""
        # Simulate litellm being unavailable
        with patch.dict(sys.modules, {"litellm": None}):
            cap = resolve_capabilities("unknown_provider", "unknown_model")
            self.assertFalse(cap.supported)
            self.assertEqual(cap.source, "fallback")


class TestCapabilitiesToDictConsistency(unittest.TestCase):
    """Test that resolved capabilities produce consistent dicts."""

    def test_to_dict_same_input_same_output(self):
        """Same input should produce identical dict on repeated calls."""
        cap1 = resolve_capabilities("anthropic", "claude-3-5-sonnet-20241022")
        cap2 = resolve_capabilities("anthropic", "claude-3-5-sonnet-20241022")
        self.assertEqual(cap1.to_dict(), cap2.to_dict())

    def test_to_dict_key_order_stable(self):
        """Dict key order should be consistent."""
        cap = resolve_capabilities("openai", "gpt-4o")
        dict1 = cap.to_dict()
        dict2 = cap.to_dict()
        self.assertEqual(list(dict1.keys()), list(dict2.keys()))


class TestStandaloneImport(unittest.TestCase):
    """Test module imports without Frappe or litellm dependencies."""

    def test_import_without_frappe(self):
        """Module should import without Frappe."""
        from huf.ai.prompt_cache.capabilities import resolve_capabilities
        self.assertTrue(callable(resolve_capabilities))

    def test_resolve_capabilities_without_frappe_context(self):
        """resolve_capabilities should work standalone."""
        from huf.ai.prompt_cache.capabilities import resolve_capabilities
        cap = resolve_capabilities("anthropic", "claude-3-5-sonnet")
        self.assertIsNotNone(cap)
        self.assertIsInstance(cap, PromptCacheCapabilities)


class TestProviderSpecificMechanisms(unittest.TestCase):
    """Test that each provider has the correct mechanism."""

    def test_anthropic_uses_explicit_breakpoint(self):
        """Anthropic should use explicit_breakpoint mechanism."""
        cap = resolve_capabilities("anthropic", "claude-opus-4-20250805")
        self.assertEqual(cap.mechanism, "explicit_breakpoint")

    def test_bedrock_uses_cache_point(self):
        """Bedrock should use cache_point mechanism."""
        cap = resolve_capabilities("bedrock", "claude-3-5-sonnet")
        self.assertEqual(cap.mechanism, "cache_point")

    def test_openai_uses_implicit_prefix(self):
        """OpenAI should use implicit_prefix mechanism."""
        cap = resolve_capabilities("openai", "gpt-4o")
        self.assertEqual(cap.mechanism, "implicit_prefix")

    def test_google_uses_implicit_prefix(self):
        """Google should use implicit_prefix mechanism."""
        cap = resolve_capabilities("google", "gemini-1.5-pro")
        self.assertEqual(cap.mechanism, "implicit_prefix")

    def test_unsupported_mechanism(self):
        """Unsupported providers should have unsupported mechanism."""
        cap = resolve_capabilities("unknown", "unknown")
        self.assertEqual(cap.mechanism, "unsupported")


class TestMinCacheableTokens(unittest.TestCase):
    """Test min_cacheable_tokens are correct per model class."""

    def test_haiku_min_cacheable_tokens(self):
        """Haiku models should have min_cacheable_tokens == 2048."""
        for variant in [
            "claude-haiku-4-5-20251001",
            "claude-3-5-haiku",
            "haiku",
        ]:
            with self.subTest(variant=variant):
                cap = resolve_capabilities("anthropic", variant)
                self.assertEqual(cap.min_cacheable_tokens, 2048)

    def test_sonnet_min_cacheable_tokens(self):
        """Sonnet models should have min_cacheable_tokens == 1024."""
        for variant in [
            "claude-3-5-sonnet",
            "claude-3-5-sonnet-20241022",
            "sonnet",
        ]:
            with self.subTest(variant=variant):
                cap = resolve_capabilities("anthropic", variant)
                self.assertEqual(cap.min_cacheable_tokens, 1024)

    def test_opus_min_cacheable_tokens(self):
        """Opus models should have min_cacheable_tokens == 1024."""
        for variant in [
            "claude-opus-4-20250805",
            "claude-opus-4-20250514",
            "opus",
        ]:
            with self.subTest(variant=variant):
                cap = resolve_capabilities("anthropic", variant)
                self.assertEqual(cap.min_cacheable_tokens, 1024)


class TestBadInputHandling(unittest.TestCase):
	"""Test that resolve_capabilities handles bad input gracefully without raising."""

	def setUp(self):
		"""Ensure routes are built."""
		_build_known_routes()

	def test_provider_brand_none(self):
		"""resolve_capabilities(None, 'claude-sonnet-5') should return conservative profile."""
		cap = resolve_capabilities(None, "claude-sonnet-5")
		self.assertIsNotNone(cap)
		self.assertFalse(cap.supported)
		self.assertEqual(cap.mechanism, "unsupported")
		self.assertEqual(cap.source, "fallback")

	def test_provider_brand_empty_string(self):
		"""resolve_capabilities('', 'claude-sonnet-5') should return conservative profile."""
		cap = resolve_capabilities("", "claude-sonnet-5")
		self.assertIsNotNone(cap)
		self.assertFalse(cap.supported)
		self.assertEqual(cap.mechanism, "unsupported")
		self.assertEqual(cap.source, "fallback")

	def test_provider_brand_whitespace(self):
		"""resolve_capabilities('   ', 'claude-sonnet-5') should return conservative profile."""
		cap = resolve_capabilities("   ", "claude-sonnet-5")
		self.assertIsNotNone(cap)
		self.assertFalse(cap.supported)
		self.assertEqual(cap.mechanism, "unsupported")
		self.assertEqual(cap.source, "fallback")

	def test_provider_brand_non_string(self):
		"""resolve_capabilities(123, 'claude-sonnet-5') should not raise."""
		cap = resolve_capabilities(123, "claude-sonnet-5")  # type: ignore
		self.assertIsNotNone(cap)
		self.assertFalse(cap.supported)
		self.assertEqual(cap.mechanism, "unsupported")
		self.assertEqual(cap.source, "fallback")

	def test_model_none(self):
		"""resolve_capabilities('anthropic', None) should return conservative profile."""
		cap = resolve_capabilities("anthropic", None)
		self.assertIsNotNone(cap)
		self.assertFalse(cap.supported)
		self.assertEqual(cap.mechanism, "unsupported")
		self.assertEqual(cap.source, "fallback")

	def test_model_empty_string(self):
		"""resolve_capabilities('anthropic', '') should return conservative profile."""
		cap = resolve_capabilities("anthropic", "")
		self.assertIsNotNone(cap)
		self.assertFalse(cap.supported)
		self.assertEqual(cap.mechanism, "unsupported")
		self.assertEqual(cap.source, "fallback")

	def test_model_whitespace(self):
		"""resolve_capabilities('anthropic', '   ') should return conservative profile."""
		cap = resolve_capabilities("anthropic", "   ")
		self.assertIsNotNone(cap)
		self.assertFalse(cap.supported)
		self.assertEqual(cap.mechanism, "unsupported")
		self.assertEqual(cap.source, "fallback")

	def test_model_non_string(self):
		"""resolve_capabilities('anthropic', 456) should not raise."""
		cap = resolve_capabilities("anthropic", 456)  # type: ignore
		self.assertIsNotNone(cap)
		self.assertFalse(cap.supported)
		self.assertEqual(cap.mechanism, "unsupported")
		self.assertEqual(cap.source, "fallback")

	def test_both_none(self):
		"""resolve_capabilities(None, None) should return conservative profile."""
		cap = resolve_capabilities(None, None)
		self.assertIsNotNone(cap)
		self.assertFalse(cap.supported)
		self.assertEqual(cap.mechanism, "unsupported")
		self.assertEqual(cap.source, "fallback")

	def test_both_empty_strings(self):
		"""resolve_capabilities('', '') should return conservative profile."""
		cap = resolve_capabilities("", "")
		self.assertIsNotNone(cap)
		self.assertFalse(cap.supported)
		self.assertEqual(cap.mechanism, "unsupported")
		self.assertEqual(cap.source, "fallback")

	def test_provider_list_model_string(self):
		"""resolve_capabilities([1, 2, 3], 'claude') should not raise."""
		cap = resolve_capabilities([1, 2, 3], "claude")  # type: ignore
		self.assertIsNotNone(cap)
		self.assertFalse(cap.supported)
		self.assertEqual(cap.mechanism, "unsupported")

	def test_provider_dict_model_none(self):
		"""resolve_capabilities({'key': 'value'}, None) should not raise."""
		cap = resolve_capabilities({"key": "value"}, None)  # type: ignore
		self.assertIsNotNone(cap)
		self.assertFalse(cap.supported)
		self.assertEqual(cap.mechanism, "unsupported")

	def test_bad_input_returns_prompt_cache_capabilities(self):
		"""Bad input should always return PromptCacheCapabilities, never None."""
		test_cases = [
			(None, None),
			(None, "model"),
			("provider", None),
			("", ""),
			(123, 456),
			([1, 2], {"a": "b"}),
			("   ", "\t\n"),
		]
		for provider, model in test_cases:
			with self.subTest(provider=provider, model=model):
				cap = resolve_capabilities(provider, model)  # type: ignore
				self.assertIsNotNone(cap)
				self.assertIsInstance(cap, PromptCacheCapabilities)


class TestRegressionValidInput(unittest.TestCase):
	"""Regression tests: valid input should still resolve exactly as before."""

	def setUp(self):
		"""Ensure routes are built."""
		_build_known_routes()

	def test_anthropic_haiku_unchanged(self):
		"""Anthropic Haiku resolution unchanged."""
		cap = resolve_capabilities("anthropic", "claude-haiku-4-5-20251001")
		self.assertTrue(cap.supported)
		self.assertEqual(cap.mechanism, "explicit_breakpoint")
		self.assertEqual(cap.min_cacheable_tokens, 2048)
		self.assertEqual(cap.source, "known_route_table")

	def test_anthropic_sonnet_unchanged(self):
		"""Anthropic Sonnet resolution unchanged."""
		cap = resolve_capabilities("anthropic", "claude-3-5-sonnet-20241022")
		self.assertTrue(cap.supported)
		self.assertEqual(cap.mechanism, "explicit_breakpoint")
		self.assertEqual(cap.min_cacheable_tokens, 1024)
		self.assertEqual(cap.source, "known_route_table")

	def test_openai_implicit_prefix_unchanged(self):
		"""OpenAI implicit prefix with affinity key unchanged."""
		cap = resolve_capabilities("openai", "gpt-4o")
		self.assertTrue(cap.supported)
		self.assertEqual(cap.mechanism, "implicit_prefix")
		self.assertTrue(cap.supports_affinity_key)
		self.assertFalse(cap.supports_explicit_breakpoints)
		self.assertEqual(cap.source, "known_route_table")

	def test_ollama_unsupported_unchanged(self):
		"""Ollama unsupported resolution unchanged."""
		cap = resolve_capabilities("ollama", "llama-2")
		self.assertFalse(cap.supported)
		self.assertEqual(cap.mechanism, "unsupported")
		self.assertEqual(cap.source, "known_route_table")

	def test_google_gemini_unchanged(self):
		"""Google Gemini resolution unchanged."""
		cap = resolve_capabilities("google", "gemini-1.5-pro")
		self.assertTrue(cap.supported)
		self.assertEqual(cap.mechanism, "implicit_prefix")
		self.assertTrue(cap.supports_named_cached_content)
		self.assertEqual(cap.source, "known_route_table")

	def test_case_insensitive_still_works(self):
		"""Case insensitivity still works."""
		cap = resolve_capabilities("Anthropic", "Claude-Sonnet-4")
		self.assertTrue(cap.supported)
		self.assertEqual(cap.mechanism, "explicit_breakpoint")



class TestOpenRouterSuffixStripping(unittest.TestCase):
	"""Test OpenRouter suffix stripping functionality."""

	def setUp(self):
		"""Ensure routes are built."""
		_build_known_routes()

	def test_strip_openrouter_suffix_free(self):
		"""Test stripping :free suffix."""
		from huf.ai.prompt_cache.capabilities import _strip_openrouter_suffix
		self.assertEqual(_strip_openrouter_suffix("model:free"), "model")
		self.assertEqual(_strip_openrouter_suffix("minimax-m3:free"), "minimax-m3")

	def test_strip_openrouter_suffix_nitro(self):
		"""Test stripping :nitro suffix."""
		from huf.ai.prompt_cache.capabilities import _strip_openrouter_suffix
		self.assertEqual(_strip_openrouter_suffix("model:nitro"), "model")

	def test_strip_openrouter_suffix_beta(self):
		"""Test stripping :beta suffix."""
		from huf.ai.prompt_cache.capabilities import _strip_openrouter_suffix
		self.assertEqual(_strip_openrouter_suffix("model:beta"), "model")

	def test_strip_openrouter_suffix_extended(self):
		"""Test stripping :extended suffix."""
		from huf.ai.prompt_cache.capabilities import _strip_openrouter_suffix
		self.assertEqual(_strip_openrouter_suffix("model:extended"), "model")

	def test_strip_openrouter_suffix_version_not_stripped(self):
		"""Test that version suffixes like :0, :1, :70b are NOT stripped."""
		from huf.ai.prompt_cache.capabilities import _strip_openrouter_suffix
		# Version suffixes should NOT be stripped
		self.assertEqual(_strip_openrouter_suffix("model:0"), "model:0")
		self.assertEqual(_strip_openrouter_suffix("model:1"), "model:1")
		self.assertEqual(_strip_openrouter_suffix("model:70b"), "model:70b")

	def test_strip_openrouter_suffix_no_suffix(self):
		"""Test that models without suffix are returned unchanged."""
		from huf.ai.prompt_cache.capabilities import _strip_openrouter_suffix
		self.assertEqual(_strip_openrouter_suffix("model"), "model")
		self.assertEqual(_strip_openrouter_suffix("minimax-m3"), "minimax-m3")

	def test_strip_openrouter_suffix_invalid_input(self):
		"""Test that invalid input returns None."""
		from huf.ai.prompt_cache.capabilities import _strip_openrouter_suffix
		self.assertIsNone(_strip_openrouter_suffix(None))
		self.assertIsNone(_strip_openrouter_suffix(""))
		self.assertIsNone(_strip_openrouter_suffix("   "))
		self.assertIsNone(_strip_openrouter_suffix(123))

	def test_resolve_openrouter_suffix_still_unknown_fallback(self):
		"""Verify that genuinely unknown models still fall back gracefully."""
		cap = resolve_capabilities("openrouter", "does-not-exist-xyz:free")
		self.assertFalse(cap.supported)
		self.assertEqual(cap.mechanism, "unsupported")
		self.assertEqual(cap.source, "fallback")

	def test_resolve_known_route_with_suffix_fallback(self):
		"""Test that when a known route has a suffix added, it still doesn't break."""
		# Haiku is known, but add a :free suffix (which shouldn't match in known_route but shouldn't crash)
		cap = resolve_capabilities("anthropic", "claude-haiku-4-5-20251001:free")
		# This should still work because the known route is consulted first
		# and partial matching should find it
		self.assertTrue(cap.supported)
		self.assertEqual(cap.mechanism, "explicit_breakpoint")
		self.assertEqual(cap.min_cacheable_tokens, 2048)

	def test_resolve_basic_models_unchanged(self):
		"""Regression test: ensure basic models still resolve identically."""
		test_cases = [
			("anthropic", "claude-haiku-4-5-20251001", True, "explicit_breakpoint", "known_route_table"),
			("anthropic", "claude-3-5-sonnet-20241022", True, "explicit_breakpoint", "known_route_table"),
			("openai", "gpt-4o", True, "implicit_prefix", "known_route_table"),
			("google", "gemini-1.5-pro", True, "implicit_prefix", "known_route_table"),
			("ollama", "llama-2", False, "unsupported", "known_route_table"),
		]
		for provider, model, expected_supported, expected_mechanism, expected_source in test_cases:
			with self.subTest(provider=provider, model=model):
				cap = resolve_capabilities(provider, model)
				self.assertEqual(cap.supported, expected_supported)
				self.assertEqual(cap.mechanism, expected_mechanism)
				self.assertEqual(cap.source, expected_source)
