# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Five derived context/cache metrics, computed once server-side and reused by
every surface (chat header, run detail, agent/fleet views). Composition
(segment_tokens) answers "what fills the window"; these metrics answer
"is caching paying off" — never recomputed client-side.

Approximation note: effective_input_multiplier and counterfactual_savings
use fixed token-cost multipliers (cache read ~=0.1x, cache write ~=1.25x,
uncached 1x) rather than a per-model dollar lookup. Actual provider rates
vary; treat these as directional, not invoiced figures. Wiring in
per-model rates from cost_calculator.get_model_pricing() is deferred —
see PHASE2_VisualCache.md.
"""

CACHE_READ_MULTIPLIER = 0.1
CACHE_WRITE_MULTIPLIER = 1.25
UNCACHED_MULTIPLIER = 1.0


def _load_usage_snapshot(run_doc):
    raw = run_doc.get("usage_snapshot") if hasattr(run_doc, "get") else getattr(run_doc, "usage_snapshot", None)
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    import json

    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return {}


def _prefix_signature(snapshot):
    breakpoints = snapshot.get("prefix_breakpoints") or []
    if not breakpoints:
        return None
    return tuple(sorted((bp.get("marker"), bp.get("prefix_hash")) for bp in breakpoints if bp.get("prefix_hash")))


def compute_run_metrics(run_doc, previous_run_doc=None):
    """Compute the five metrics for one run. Fields are `None`, never 0,
    when the inputs needed to calculate them are unavailable."""
    snapshot = _load_usage_snapshot(run_doc)

    input_tokens = snapshot.get("input_tokens")
    cache_read = snapshot.get("cache_read_tokens")
    cache_write = snapshot.get("cache_creation_tokens")
    cost = run_doc.get("cost") if hasattr(run_doc, "get") else getattr(run_doc, "cost", None)

    cache_read_share = None
    effective_input_multiplier = None
    if input_tokens:
        if cache_read is not None:
            cache_read_share = cache_read / input_tokens
        if cache_read is not None and cache_write is not None:
            uncached = max(input_tokens - cache_read - cache_write, 0)
            effective_input_multiplier = (
                cache_read * CACHE_READ_MULTIPLIER
                + cache_write * CACHE_WRITE_MULTIPLIER
                + uncached * UNCACHED_MULTIPLIER
            ) / input_tokens

    counterfactual_savings = None
    if cost is not None and effective_input_multiplier is not None and effective_input_multiplier > 0:
        # cost scales roughly with the multiplier; back out the no-cache cost.
        counterfactual_savings = round(cost * (1 / effective_input_multiplier - 1) * effective_input_multiplier, 6)

    prefix_stability = "unavailable"
    this_signature = _prefix_signature(snapshot)
    if previous_run_doc is not None:
        previous_signature = _prefix_signature(_load_usage_snapshot(previous_run_doc))
        if this_signature is None or previous_signature is None:
            prefix_stability = "unknown"
        elif this_signature == previous_signature:
            prefix_stability = "stable"
        else:
            prefix_stability = "changed"
    elif this_signature is not None:
        prefix_stability = "unknown"

    return {
        "cache_read_share": cache_read_share,
        "effective_input_multiplier": effective_input_multiplier,
        "wasted_writes_tokens": None,  # needs read-after-write tracking; not captured yet
        "prefix_stability": prefix_stability,
        "counterfactual_savings": counterfactual_savings,
    }
