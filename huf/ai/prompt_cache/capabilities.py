# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""
Prompt Cache Capabilities Resolution
=====================================
Provider and model-aware resolution of prompt caching capabilities.

Resolves caching support using a multi-tier strategy:
1. Known-route table (verified facts about real provider behavior)
2. LiteLLM pricing metadata (defensive import, never at module level)
3. Conservative fallback (unsupported)
"""

from __future__ import annotations

from typing import Optional

from .types import PromptCacheCapabilities


# Known-route table: verified provider + model patterns -> capabilities
# Organized by provider brand, with model patterns that match normalized model names.
KNOWN_ROUTES: dict[str, dict[str, PromptCacheCapabilities]] = {}


def _is_valid_string(value: object) -> bool:
	"""
	Check if value is a non-empty, non-whitespace string.
	Returns False for None, non-strings, empty strings, and whitespace-only strings.
	"""
	return isinstance(value, str) and bool(value.strip())


def _register_claude_anthropic() -> None:
	"""Register Anthropic Claude models with explicit breakpoint support."""
	# Anthropic Claude family: verified to support explicit cache breakpoints
	# Minimum cacheable token thresholds confirmed via live API testing:
	# - Haiku 4.5: 2048 tokens (observed in caching-phase0 testing)
	# - Sonnet 3.5+: 1024 tokens
	# - Opus 4: 1024 tokens

	haiku_variants = [
		"claude-3-5-haiku",
		"claude-3-5-haiku-20241022",
		"claude-haiku-4-5-20251001",
		"haiku",
	]

	sonnet_variants = [
		"claude-3-5-sonnet",
		"claude-3-5-sonnet-20241022",
		"claude-sonnet-4-20250514",
		"sonnet",
	]

	opus_variants = [
		"claude-3-opus",
		"claude-opus-4-20250805",
		"claude-opus-4-20250514",
		"opus",
	]

	# Haiku: min 2048 tokens
	haiku_cap = PromptCacheCapabilities(
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

	for variant in haiku_variants:
		if "anthropic" not in KNOWN_ROUTES:
			KNOWN_ROUTES["anthropic"] = {}
		KNOWN_ROUTES["anthropic"][variant] = haiku_cap

	# Sonnet and Opus: min 1024 tokens
	claude_cap = PromptCacheCapabilities(
		supported=True,
		mechanism="explicit_breakpoint",
		supports_explicit_breakpoints=True,
		supports_affinity_key=False,
		supports_named_cached_content=False,
		max_breakpoints_per_request=4,
		ttl_values=("5m", "1h"),
		min_cacheable_tokens=1024,
		reports_cache_read_tokens=True,
		reports_cache_write_tokens=True,
		source="known_route_table",
	)

	for variant in sonnet_variants + opus_variants:
		if "anthropic" not in KNOWN_ROUTES:
			KNOWN_ROUTES["anthropic"] = {}
		KNOWN_ROUTES["anthropic"][variant] = claude_cap


def _register_bedrock_claude() -> None:
	"""Register Bedrock Claude models with cache_point mechanism."""
	# Bedrock exposes Claude via the 'bedrock' provider but uses cache_point
	# mechanism instead of explicit breakpoints. Minimums are similar.

	bedrock_cap = PromptCacheCapabilities(
		supported=True,
		mechanism="cache_point",
		supports_explicit_breakpoints=False,
		supports_affinity_key=False,
		supports_named_cached_content=False,
		max_breakpoints_per_request=None,
		ttl_values=("5m", "1h"),
		min_cacheable_tokens=1024,
		reports_cache_read_tokens=True,
		reports_cache_write_tokens=True,
		source="known_route_table",
	)

	if "bedrock" not in KNOWN_ROUTES:
		KNOWN_ROUTES["bedrock"] = {}
	# Bedrock Claude models
	for variant in ["claude-3-5-sonnet", "claude-opus", "claude-3-5-haiku"]:
		KNOWN_ROUTES["bedrock"][variant] = bedrock_cap


def _register_openai() -> None:
	"""Register OpenAI models with implicit prefix support."""
	# OpenAI GPT models use implicit prefix caching with affinity keys
	# for cache reuse. Minimum is approximately 1024 tokens.

	openai_cap = PromptCacheCapabilities(
		supported=True,
		mechanism="implicit_prefix",
		supports_explicit_breakpoints=False,
		supports_affinity_key=True,
		supports_named_cached_content=False,
		max_breakpoints_per_request=None,
		ttl_values=tuple(),  # OpenAI doesn't expose explicit TTL control
		min_cacheable_tokens=1024,
		reports_cache_read_tokens=True,
		reports_cache_write_tokens=False,
		source="known_route_table",
	)

	if "openai" not in KNOWN_ROUTES:
		KNOWN_ROUTES["openai"] = {}
	for variant in ["gpt-4", "gpt-4-turbo", "gpt-4o", "gpt-4o-mini"]:
		KNOWN_ROUTES["openai"][variant] = openai_cap


def _register_gemini() -> None:
	"""Register Google Gemini models."""
	# Gemini supports implicit prefix caching and optional named_cached_content
	# via @cached annotations. Does NOT support explicit breakpoints.

	gemini_cap = PromptCacheCapabilities(
		supported=True,
		mechanism="implicit_prefix",
		supports_explicit_breakpoints=False,
		supports_affinity_key=False,
		supports_named_cached_content=True,
		max_breakpoints_per_request=None,
		ttl_values=("60s", "5m", "1h"),
		min_cacheable_tokens=1024,
		reports_cache_read_tokens=True,
		reports_cache_write_tokens=False,
		source="known_route_table",
	)

	if "google" not in KNOWN_ROUTES:
		KNOWN_ROUTES["google"] = {}
	for variant in ["gemini-2", "gemini-1.5-pro", "gemini-1.5-flash", "gemini-1-pro"]:
		KNOWN_ROUTES["google"][variant] = gemini_cap


def _register_ollama() -> None:
	"""Register Ollama / local models as unsupported."""
	# Local/Ollama models do not support prompt caching.

	unsupported_cap = PromptCacheCapabilities(
		supported=False,
		mechanism="unsupported",
		supports_explicit_breakpoints=False,
		supports_affinity_key=False,
		supports_named_cached_content=False,
		max_breakpoints_per_request=None,
		ttl_values=tuple(),
		min_cacheable_tokens=None,
		reports_cache_read_tokens=None,
		reports_cache_write_tokens=None,
		source="known_route_table",
	)

	if "ollama" not in KNOWN_ROUTES:
		KNOWN_ROUTES["ollama"] = {}
	KNOWN_ROUTES["ollama"]["*"] = unsupported_cap


def _build_known_routes() -> None:
	"""Initialize all known routes."""
	if not KNOWN_ROUTES:
		_register_claude_anthropic()
		_register_bedrock_claude()
		_register_openai()
		_register_gemini()
		_register_ollama()


def _normalize_model_name(model: object) -> Optional[str]:
	"""
	Normalize a model name for lookup.
	Removes common prefixes and version suffixes, converts to lowercase.
	Returns None if model is not a valid string.
	"""
	# Defensive: check for None, non-string, empty, or whitespace-only
	if not _is_valid_string(model):
		return None

	# At this point, model is a non-empty string
	model = str(model)  # type: ignore
	# Remove provider prefixes (azure/, vertex/, bedrock/, etc.)
	if "/" in model:
		model = model.split("/")[-1]
	return model.lower()


def _lookup_known_route(
	provider_brand: object, model: object
) -> Optional[PromptCacheCapabilities]:
	"""
	Look up a model in the known-route table.
	Tries exact match first, then wildcard.
	Returns None if provider_brand or model is invalid.
	"""
	_build_known_routes()

	# Defensive: check for None, non-string, empty, or whitespace-only provider_brand
	if not _is_valid_string(provider_brand):
		return None

	# Normalize model name - if invalid, return None
	normalized = _normalize_model_name(model)
	if normalized is None:
		return None

	provider_key = str(provider_brand).lower()  # type: ignore
	if provider_key not in KNOWN_ROUTES:
		return None

	provider_routes = KNOWN_ROUTES[provider_key]

	# Try exact match
	if normalized in provider_routes:
		return provider_routes[normalized]

	# Try partial matches (e.g., "claude-3-5-sonnet" matches "claude-3-5-sonnet-20241022")
	for pattern, cap in provider_routes.items():
		if pattern != "*" and pattern in normalized:
			return cap

	# Try wildcard
	if "*" in provider_routes:
		return provider_routes["*"]

	return None


def _lookup_litellm(provider_brand: object, model: object) -> Optional[PromptCacheCapabilities]:
	"""
	Attempt to resolve capabilities from LiteLLM metadata.
	Defensively imports litellm and tolerates its absence.
	Returns None if provider_brand or model is invalid.
	"""
	# Defensive: check for None, non-string, empty, or whitespace-only
	if not _is_valid_string(provider_brand) or not _is_valid_string(model):
		return None

	try:
		import litellm
	except ImportError:
		return None

	try:
		# Look for cache_read_input_token_cost in litellm.model_cost
		# following the pattern from prompt_cache_capabilities.py
		normalized = _normalize_model_name(model)

		if normalized is None:
			return None

		for db_key in litellm.model_cost.keys():
			db_key_normalized = _normalize_model_name(db_key)
			if db_key_normalized is None:
				continue
			if normalized in db_key_normalized or db_key_normalized in normalized:
				entry = litellm.model_cost[db_key]
				if entry.get("cache_read_input_token_cost") is not None:
					# LiteLLM indicates support but we don't know specifics
					return PromptCacheCapabilities(
						supported=True,
						mechanism="implicit_prefix",  # Conservative default
						supports_explicit_breakpoints=False,
						supports_affinity_key=False,
						supports_named_cached_content=False,
						max_breakpoints_per_request=None,
						ttl_values=tuple(),
						min_cacheable_tokens=None,
						reports_cache_read_tokens=None,
						reports_cache_write_tokens=None,
						source="litellm",
					)
	except (AttributeError, KeyError, TypeError):
		pass

	return None


def resolve_capabilities(provider_brand: object, model: object) -> PromptCacheCapabilities:
	"""
	Resolve prompt caching capabilities for a provider + model pair.

	Follows a resolution precedence:
	1. Known-route table (verified provider behavior)
	2. LiteLLM metadata (defensive import, tolerate absence)
	3. Conservative fallback (unsupported)

	Args:
		provider_brand: Provider name (e.g., 'anthropic', 'openai', 'google').
					   May be None or non-string; handled defensively.
		model: Model identifier (may include provider prefix like 'bedrock/claude-3-5-sonnet').
			   May be None or non-string; handled defensively.

	Returns:
		PromptCacheCapabilities with verified or inferred settings.
		Never raises; always returns a valid PromptCacheCapabilities object.
	"""
	# Try known routes first
	cap = _lookup_known_route(provider_brand, model)
	if cap is not None:
		return cap

	# Try LiteLLM metadata
	cap = _lookup_litellm(provider_brand, model)
	if cap is not None:
		return cap

	# Conservative fallback: unsupported
	return PromptCacheCapabilities(
		supported=False,
		mechanism="unsupported",
		supports_explicit_breakpoints=False,
		supports_affinity_key=False,
		supports_named_cached_content=False,
		max_breakpoints_per_request=None,
		ttl_values=tuple(),
		min_cacheable_tokens=None,
		reports_cache_read_tokens=None,
		reports_cache_write_tokens=None,
		source="fallback",
	)
