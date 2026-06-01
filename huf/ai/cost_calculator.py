# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
HUF Cost Calculator
===================
Single source of truth for all LLM cost calculations.

Priority order:
  1. Custom prices defined on the AI Model DocType (user-configured, highest priority)
  2. litellm.completion_cost() auto-lookup from LiteLLM's built-in price table
  3. 0.0 with source="unknown" (never silently wrong)

Formula (industry standard — same as Langfuse, Portkey, Anthropic):
  cost = (input_tokens  / 1_000_000) * input_cost_per_1m_tokens
       + (output_tokens / 1_000_000) * output_cost_per_1m_tokens
       + (cached_tokens / 1_000_000) * cached_input_cost_per_1m_tokens  # optional

Usage:
  from huf.ai.cost_calculator import calculate_cost

  cost_usd, source = calculate_cost(
      model_name="gpt-4o",
      input_tokens=1000,
      output_tokens=500,
      cached_tokens=200,
      litellm_response=response,   # pass the raw litellm response for auto-fallback
  )
  # source is one of: "custom" | "litellm" | "unknown"
"""

import frappe

# Redis TTL for cached pricing data (seconds)
_PRICING_CACHE_TTL = 600  # 10 minutes


def get_model_pricing(model_name: str) -> dict | None:
    """
    Return custom pricing from AI Model DocType, or None if not configured.

    Result is cached in Redis (10-minute TTL) to avoid a DB hit on every
    request. Cache is explicitly invalidated by AIModel.on_update().

    Returns a dict with keys:
        input_cost_per_1m_tokens       (float)
        output_cost_per_1m_tokens      (float)
        cached_input_cost_per_1m_tokens (float | None)
    or None if no custom pricing is configured for the model.
    """
    if not model_name:
        return None

    cache_key = f"huf_model_pricing:{model_name}"

    try:
        cached = frappe.cache().get_value(cache_key)
        if cached is not None:
            # Sentinel: empty dict means "we checked, no custom pricing"
            return cached if cached else None
    except Exception:
        pass

    try:
        model_doc = frappe.db.get_value(
            "AI Model",
            model_name,
            [
                "use_custom_pricing",
                "input_cost_per_1m_tokens",
                "output_cost_per_1m_tokens",
                "cached_input_cost_per_1m_tokens",
            ],
            as_dict=True,
        )
    except Exception:
        return None

    if not model_doc:
        return None

    # Gate: user must explicitly enable custom pricing
    if not model_doc.get("use_custom_pricing"):
        # Cache sentinel (empty dict) so we don't re-query on every request
        try:
            frappe.cache().set_value(cache_key, {}, expires_in_sec=_PRICING_CACHE_TTL)
        except Exception:
            pass
        return None

    input_price = model_doc.get("input_cost_per_1m_tokens")
    output_price = model_doc.get("output_cost_per_1m_tokens")

    # Both prices must be present (0 is valid — free model)
    if input_price is None or output_price is None:
        try:
            frappe.cache().set_value(cache_key, {}, expires_in_sec=_PRICING_CACHE_TTL)
        except Exception:
            pass
        return None

    pricing = {
        "input_cost_per_1m_tokens": float(input_price),
        "output_cost_per_1m_tokens": float(output_price),
        "cached_input_cost_per_1m_tokens": (
            float(model_doc["cached_input_cost_per_1m_tokens"])
            if model_doc.get("cached_input_cost_per_1m_tokens") is not None
            else None
        ),
    }

    try:
        frappe.cache().set_value(cache_key, pricing, expires_in_sec=_PRICING_CACHE_TTL)
    except Exception:
        pass

    return pricing


def _calculate_from_custom_pricing(
    pricing: dict,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
) -> float:
    """
    Apply the standard token-cost formula using custom pricing.

    Industry standard formula:
      cost = (input  / 1M) × input_price
           + (output / 1M) × output_price
           + (cached / 1M) × cached_price    (if cached_price is set)

    For cached tokens: if no explicit cached_price is configured we do NOT
    double-charge them — they are already counted inside input_tokens by the
    provider, so we simply skip the separate cached line.
    """
    input_price = pricing["input_cost_per_1m_tokens"]
    output_price = pricing["output_cost_per_1m_tokens"]
    cached_price = pricing.get("cached_input_cost_per_1m_tokens")

    cost = (input_tokens / 1_000_000) * input_price
    cost += (output_tokens / 1_000_000) * output_price

    if cached_price is not None and cached_tokens > 0:
        # Add explicit cache-read cost (e.g. Anthropic charges $0.30/1M for cache reads)
        cost += (cached_tokens / 1_000_000) * cached_price

    return round(cost, 10)


def calculate_cost(
    model_name: str,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
    litellm_response=None,
) -> tuple[float, str]:
    """
    Calculate the cost of an LLM call and return ``(cost_usd, source)``.

    source values:
      "custom"  — HUF custom pricing from AI Model DocType
      "litellm" — LiteLLM built-in price table
      "unknown" — neither source has pricing; cost is 0.0

    Args:
        model_name:       The model name (AI Model docname, e.g. "gpt-4o")
        input_tokens:     Number of prompt/input tokens
        output_tokens:    Number of completion/output tokens
        cached_tokens:    Number of cached tokens (prompt cache hits), default 0
        litellm_response: Raw litellm completion response object for fallback
    """
    # ── Priority 1: HUF custom pricing ──────────────────────────────────────
    try:
        pricing = get_model_pricing(model_name)
        if pricing is not None:
            cost = _calculate_from_custom_pricing(
                pricing,
                input_tokens=int(input_tokens or 0),
                output_tokens=int(output_tokens or 0),
                cached_tokens=int(cached_tokens or 0),
            )
            return cost, "custom"
    except Exception as e:
        frappe.log_error(
            f"HUF custom cost calculation failed for '{model_name}': {str(e)}",
            "Cost Calculator",
        )

    # ── Priority 2: LiteLLM auto-lookup ─────────────────────────────────────
    if litellm_response is not None:
        try:
            from litellm import completion_cost

            litellm_cost = completion_cost(completion_response=litellm_response)
            if litellm_cost and float(litellm_cost) > 0:
                return float(litellm_cost), "litellm"
        except Exception:
            # LiteLLM silently returns 0 for unknown models; that falls through
            pass

    # ── Priority 3: Unknown ──────────────────────────────────────────────────
    return 0.0, "unknown"


def register_model_pricing_with_litellm(model_name: str, pricing: dict):
    """
    Register custom pricing into LiteLLM's in-memory price registry.

    This ensures that litellm.completion_cost() also respects HUF's custom
    prices, making the two cost paths consistent.

    LiteLLM registry format uses cost-per-token (not per-1M), so we divide.
    """
    if not model_name or not pricing:
        return

    try:
        import litellm

        input_price_per_1m = pricing.get("input_cost_per_1m_tokens")
        output_price_per_1m = pricing.get("output_cost_per_1m_tokens")

        if input_price_per_1m is None or output_price_per_1m is None:
            return

        model_info = {
            "input_cost_per_token": float(input_price_per_1m) / 1_000_000,
            "output_cost_per_token": float(output_price_per_1m) / 1_000_000,
        }

        cached_price_per_1m = pricing.get("cached_input_cost_per_1m_tokens")
        if cached_price_per_1m is not None:
            model_info["cache_read_input_token_cost"] = float(cached_price_per_1m) / 1_000_000

        litellm.register_model({model_name: model_info})

    except Exception as e:
        frappe.log_error(
            f"Failed to register '{model_name}' pricing with LiteLLM: {str(e)}",
            "Cost Calculator",
        )


def sync_all_model_pricing():
    """
    Sync all AI Models that have custom pricing into LiteLLM's in-memory
    price registry.

    Called from install.after_migrate() so that the registry is always
    populated after a server restart or bench migrate.
    """
    try:
        models = frappe.get_all(
            "AI Model",
            filters={"use_custom_pricing": 1},
            fields=[
                "name",
                "model_name",
                "input_cost_per_1m_tokens",
                "output_cost_per_1m_tokens",
                "cached_input_cost_per_1m_tokens",
            ],
        )

        synced = 0
        for m in models:
            pricing = {
                "input_cost_per_1m_tokens": m.input_cost_per_1m_tokens,
                "output_cost_per_1m_tokens": m.output_cost_per_1m_tokens,
                "cached_input_cost_per_1m_tokens": m.get("cached_input_cost_per_1m_tokens"),
            }
            register_model_pricing_with_litellm(m.name, pricing)
            synced += 1

        if synced:
            frappe.log_error(
                f"Synced custom pricing for {synced} AI Model(s) into LiteLLM registry.",
                "Cost Calculator Sync",
            )

    except Exception as e:
        frappe.log_error(
            f"sync_all_model_pricing failed: {str(e)}",
            "Cost Calculator Sync Error",
        )


def invalidate_model_pricing_cache(model_name: str):
    """
    Invalidate the Redis pricing cache for a specific model.
    Called from AIModel.on_update().
    """
    if not model_name:
        return
    try:
        frappe.cache().delete_key(f"huf_model_pricing:{model_name}")
    except Exception:
        pass
