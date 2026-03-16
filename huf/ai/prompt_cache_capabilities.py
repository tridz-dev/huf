# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""
Prompt Cache Capabilities
=========================

This module uses a data-driven approach to detect capabilities by inspecting
LiteLLM's pricing metadata. It avoids hardcoded model lists and provider-specific
logic to ensure future compatibility with LiteLLM updates.
"""

from __future__ import annotations


def model_supports_prompt_caching(model_name: str, provider_name: str) -> bool:
    
    try:
        import litellm
    except ImportError:
        return False

    target_model = model_name.split("/", 1)[-1].lower() if "/" in model_name else model_name.lower()
    
    candidates = [model_name, f"{provider_name.lower()}/{model_name}"]
    for key in candidates:
        entry = litellm.model_cost.get(key)
        if entry and entry.get("cache_read_input_token_cost") is not None:
            return True

    for db_key, entry in litellm.model_cost.items():
        db_model_part = db_key.split("/", 1)[-1].lower() if "/" in db_key else db_key.lower()
        
        if "." in db_model_part and not db_model_part.startswith(target_model):
            db_model_part = db_model_part.split(".", 1)[-1]

        if db_model_part == target_model or db_model_part.startswith(f"{target_model}-"):
            if entry.get("cache_read_input_token_cost") is not None:
                return True

    return False
