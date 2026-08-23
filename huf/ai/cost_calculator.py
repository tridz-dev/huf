# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
HUF Cost Calculator
===================
Single source of truth for all LLM cost calculations.

Priority order:
  1. Custom prices defined on the AI Model DocType (user-configured, highest priority)
  2. litellm.completion_cost() auto-lookup from LiteLLM's built-in price table
  3. 0.0 with source="local_no_pricing" for local/self-hosted providers (e.g. Ollama)
  4. 0.0 with source="unknown" (never silently wrong)

Formula (industry standard — same as Langfuse, Portkey, Anthropic):
  cost = (input_tokens  / 1_000_000) * input_cost_per_1m_tokens
       + (output_tokens / 1_000_000) * output_cost_per_1m_tokens
       + (cached_tokens / 1_000_000) * cached_input_cost_per_1m_tokens              # optional
       + (cache_creation_tokens / 1_000_000) * cached_input_write_cost_per_1m_tokens  # optional

cached_tokens and cache_creation_tokens are both subsets of input_tokens (not
additional tokens on top of it), so they are subtracted from input_tokens
before the regular input rate is applied.

Usage:
  from huf.ai.cost_calculator import calculate_cost

  cost_usd, source = calculate_cost(
      model_name="gpt-4o",
      input_tokens=1000,
      output_tokens=500,
      cached_tokens=200,
      litellm_response=response,   # pass the raw litellm response for auto-fallback
  )
  # source is one of: "custom" | "litellm" | "local_no_pricing" | "unknown"
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
        cached_input_write_cost_per_1m_tokens (float | None)
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
    except Exception as exc:  # best-effort pricing cache operation
        frappe.logger("huf").debug(f"Model pricing cache operation failed: {exc!s}")

    try:
        model_doc = frappe.db.get_value(
            "AI Model",
            model_name,
            [
                "use_custom_pricing",
                "input_cost_per_1m_tokens",
                "output_cost_per_1m_tokens",
                "cached_input_cost_per_1m_tokens",
                "cached_input_write_cost_per_1m_tokens",
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
        # Cache-CREATION (write) rate. Treated as "configured" only when
        # non-zero — this Float field has no separate presence flag, so a
        # bare 0 means "not set" rather than "free cache writes".
        "cached_input_write_cost_per_1m_tokens": (
            float(model_doc["cached_input_write_cost_per_1m_tokens"])
            if model_doc.get("cached_input_write_cost_per_1m_tokens")
            else None
        ),
    }

    try:
        frappe.cache().set_value(cache_key, pricing, expires_in_sec=_PRICING_CACHE_TTL)
    except Exception as exc:  # best-effort pricing cache operation
        frappe.logger("huf").debug(f"Model pricing cache operation failed: {exc!s}")

    return pricing


def _calculate_from_custom_pricing(
    pricing: dict,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
    cache_creation_tokens: int = 0,
) -> float:
    """
    Apply the standard token-cost formula using custom pricing.

    Industry standard formula:
      cost = (input  / 1M) * input_price
           + (output / 1M) * output_price
           + (cached / 1M) * cached_price          (if cached_price is set)
           + (cache_creation / 1M) * cache_write_price  (if cache_write_price is set)

    Both cached (read) tokens and cache-creation (write) tokens are a subset
    of input_tokens as reported by the provider/LiteLLM — not additional
    tokens on top of it. If no explicit rate is configured for either one we
    do NOT double-charge them and we do NOT drop them either: they simply
    stay inside input_tokens and get billed at the regular input rate.
    """
    input_price = pricing["input_cost_per_1m_tokens"]
    output_price = pricing["output_cost_per_1m_tokens"]
    cached_price = pricing.get("cached_input_cost_per_1m_tokens")
    cache_write_price = pricing.get("cached_input_write_cost_per_1m_tokens")

    cost = 0.0
    remaining_input = input_tokens

    if cached_price is not None and cached_tokens > 0:
        # Cached (read) tokens are a subset of input tokens.
        # Bill the cached portion at the cached rate, remove it from the pool
        # billed at the regular rate.
        remaining_input = max(0, remaining_input - cached_tokens)
        cost += (cached_tokens / 1_000_000) * cached_price

    if cache_write_price is not None and cache_creation_tokens > 0:
        # Cache-creation (write) tokens are likewise a subset of input tokens.
        # Same treatment: bill separately at the write rate, remove from the
        # pool billed at the regular rate.
        remaining_input = max(0, remaining_input - cache_creation_tokens)
        cost += (cache_creation_tokens / 1_000_000) * cache_write_price

    # Regular input rate for whatever is left (i.e. everything that wasn't
    # priced separately above — including cached/cache-creation tokens when
    # no explicit rate was configured for them).
    cost += (remaining_input / 1_000_000) * input_price

    # Always add output cost
    cost += (output_tokens / 1_000_000) * output_price

    return round(cost, 10)


def _is_local_model(model_name: str, litellm_response=None) -> bool:
    """
    Return True when the model is served by a local/self-hosted provider.

    Detection order:
      1. Model prefix on the model name (or on the litellm response's model):
         ``ollama`` / ``ollama_chat``.
      2. Provider lookup: the linked AI Provider doc has ``is_local_llm`` set.
    """
    candidates = [model_name or ""]
    if litellm_response is not None:
        if isinstance(litellm_response, dict):
            resp_model = litellm_response.get("model")
        else:
            resp_model = getattr(litellm_response, "model", None)
        if resp_model:
            candidates.append(resp_model)

    for candidate in candidates:
        if "/" in candidate and candidate.split("/", 1)[0].lower() in ("ollama", "ollama_chat"):
            return True

    try:
        provider = frappe.db.get_value("AI Model", model_name, "provider")
        if provider and frappe.db.get_value("AI Provider", provider, "is_local_llm"):
            return True
    except Exception:
        pass

    return False


def calculate_cost(
    model_name: str,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
    litellm_response=None,
    *,
    cache_creation_tokens: int = 0,
) -> tuple[float, str]:
    """
    Calculate the cost of an LLM call and return ``(cost_usd, source)``.

    source values:
      "custom"          — HUF custom pricing from AI Model DocType
      "litellm"         — LiteLLM built-in price table
      "local_no_pricing"— local/self-hosted provider with no pricing; cost is 0.0
      "unknown"         — neither source has pricing; cost is 0.0

    Args:
        model_name:            The model name (AI Model docname, e.g. "gpt-4o")
        input_tokens:          Number of prompt/input tokens
        output_tokens:         Number of completion/output tokens
        cached_tokens:         Number of cached tokens (prompt cache reads), default 0
        litellm_response:      Raw litellm completion response object for fallback
        cache_creation_tokens: Number of cache-creation tokens (prompt cache writes),
                                default 0. Only consulted by the custom-pricing branch —
                                the LiteLLM branch derives it from ``litellm_response``
                                itself. Keyword-only so existing callers are unaffected.
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
                cache_creation_tokens=int(cache_creation_tokens or 0),
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
        except Exception as e:
            frappe.log_error(
                f"LiteLLM auto-lookup failed for '{model_name}': {str(e)}",
                "Cost Calculator Priority 2",
            )

    # ── Priority 3: Local provider without pricing ───────────────────────────
    if _is_local_model(model_name, litellm_response):
        return 0.0, "local_no_pricing"

    # ── Priority 4: Unknown ──────────────────────────────────────────────────
    return 0.0, "unknown"


def invalidate_model_pricing_cache(model_name: str):
    """
    Invalidate the Redis pricing cache for a specific model.
    Called from AIModel.on_update().
    """
    if not model_name:
        return
    try:
        frappe.cache().delete_key(f"huf_model_pricing:{model_name}")
    except Exception as exc:  # best-effort pricing cache operation
        frappe.logger("huf").debug(f"Model pricing cache operation failed: {exc!s}")
