# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""
Prompt Cache Module
===================
Comprehensive provider and model-aware prompt caching capability detection.

Exports:
    PromptCacheCapabilities: Immutable dataclass of caching capabilities.
    resolve_capabilities: Function to resolve capabilities for any provider/model.
"""

from __future__ import annotations

from .capabilities import resolve_capabilities
from .types import PromptCacheCapabilities

__all__ = [
    "PromptCacheCapabilities",
    "resolve_capabilities",
]
