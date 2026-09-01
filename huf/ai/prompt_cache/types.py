# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""
Prompt Cache Types
==================
Type definitions for prompt caching capabilities and diagnostics.

This module defines frozen dataclasses for modeling LLM prompt caching
capabilities across different providers and models. It is intentionally
free of provider-specific imports (litellm, frappe, etc.) at module
import time to enable standalone usage and testability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# Valid mechanism values
VALID_MECHANISMS = {
    "implicit_prefix",
    "explicit_breakpoint",
    "cache_point",
    "named_cached_content",
    "unsupported",
}


@dataclass(frozen=True)
class PromptCacheCapabilities:
    """
    Immutable specification of LLM prompt caching capabilities.

    Attributes:
        supported: Whether the model supports prompt caching at all.
        mechanism: How caching is triggered (implicit_prefix, explicit_breakpoint,
                   cache_point, named_cached_content, or unsupported).
        supports_explicit_breakpoints: Whether the provider supports explicit
                                      cache breakpoints/control points.
        supports_affinity_key: Whether the provider supports affinity keys
                              for cache reuse across requests.
        supports_named_cached_content: Whether the provider supports named
                                      cached content (e.g., Gemini's @cached).
        max_breakpoints_per_request: Maximum number of breakpoints/cache points
                                    per single request (None = unlimited or unknown).
        ttl_values: Tuple of supported TTL values as strings (e.g., ("5m", "1h")).
        min_cacheable_tokens: Minimum number of tokens required in the cached
                             prefix to actually trigger caching (None = unknown).
        reports_cache_read_tokens: Whether the provider reports cache read token
                                  counts in the response (None = unknown).
        reports_cache_write_tokens: Whether the provider reports cache write token
                                   counts in the response (None = unknown).
        source: Provenance identifier (e.g., "known_route_table", "litellm", "fallback").
    """
    supported: bool
    mechanism: str
    supports_explicit_breakpoints: bool
    supports_affinity_key: bool
    supports_named_cached_content: bool
    max_breakpoints_per_request: Optional[int]
    ttl_values: tuple[str, ...] = field(default_factory=tuple)
    min_cacheable_tokens: Optional[int] = None
    reports_cache_read_tokens: Optional[bool] = None
    reports_cache_write_tokens: Optional[bool] = None
    source: str = "unknown"

    def __post_init__(self) -> None:
        """Validate mechanism is one of the allowed values."""
        if self.mechanism not in VALID_MECHANISMS:
            raise ValueError(
                f"Invalid mechanism '{self.mechanism}'. Must be one of: {sorted(VALID_MECHANISMS)}"
            )

    def to_dict(self) -> dict:
        """
        Convert to a deterministic dictionary for analytics serialization.

        Keys are ordered alphabetically to ensure consistent output regardless
        of construction order or dataclass field ordering changes.
        """
        data = {
            "max_breakpoints_per_request": self.max_breakpoints_per_request,
            "mechanism": self.mechanism,
            "min_cacheable_tokens": self.min_cacheable_tokens,
            "reports_cache_read_tokens": self.reports_cache_read_tokens,
            "reports_cache_write_tokens": self.reports_cache_write_tokens,
            "source": self.source,
            "supported": self.supported,
            "supports_affinity_key": self.supports_affinity_key,
            "supports_explicit_breakpoints": self.supports_explicit_breakpoints,
            "supports_named_cached_content": self.supports_named_cached_content,
            "ttl_values": self.ttl_values,
        }
        return data
