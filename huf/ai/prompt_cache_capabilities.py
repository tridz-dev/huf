# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""
Prompt Cache Capabilities
=========================
Determines LLM prompt caching support using LiteLLM pricing metadata.

This module implements a professional, data-driven approach. It identifies 
feature support by verifying the presence of pricing for cache operations 
(cache hits/reads). This avoids hardcoded model lists and ensures compatibility 
with future model releases or provider changes.
"""

from __future__ import annotations


def model_supports_prompt_caching(model_name: str, provider_name: str) -> bool:
    """
    Return True if *model_name* from *provider_name* supports prompt caching.

    Standard & Data-Driven Implementation:
    1. Feature support is defined by the existence of pricing metadata 
       (``cache_read_input_token_cost``) in LiteLLM's pricing database.
    2. Pricing is the only definitive "production" indicator of feature 
       readiness in LiteLLM. This correctly distinguishes between legacy 
       models (without caching prices) and newer revisions (with caching 
       prices) without hardcoding model names.
    3. Uses a segment-aware lookup to reliably resolve model names across 
       different key formats (Azure, Vertex, Bedrock prefixes, etc.).
    """
    try:
        import litellm
        import re
    except ImportError:
        return False

    target_model = model_name.split("/", 1)[-1].lower() if "/" in model_name else model_name.lower()
    
    escaped_target = re.escape(target_model)
    segment_pattern = re.compile(rf"(^|[/\-.:@]){escaped_target}([/\-:@]|$)")

    for db_key, entry in litellm.model_cost.items():
        if segment_pattern.search(db_key.lower()):
            if entry.get("cache_read_input_token_cost") is not None:
                return True

    return False
