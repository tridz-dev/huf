"""Per-run context composition and cache-economics API.

Serves the segment_tokens breakdown and the five derived cache metrics for
a single Agent Run, for the ContextBar component (chat header, run detail).
Reads only the run's own usage_snapshot plus the prior run of the same
agent for prefix-stability comparison; never aggregates raw runs.
"""

from __future__ import annotations

import json
import re

import frappe

from huf.ai.cache_metrics import compute_run_metrics
from huf.ai.providers.litellm import _normalize_model_name


def _context_window_from_litellm(model_name, provider_name, provider_brand):
    """Best-effort context-window lookup from LiteLLM's model-cost table.

    Mirrors the normalisation used to price a run (``_normalize_model_name``,
    also used by ``context_segments.py``) and the segment-aware key matching
    used by ``prompt_cache_capabilities.py`` to tolerate provider/vendor
    prefixes in LiteLLM's key names (Azure, Vertex, Bedrock, ...).

    Returns an int, or ``None`` if the model can't be resolved. Never raises
    — this backs a read-only analytics endpoint and a missing metadata entry
    must not fail the page.
    """
    if not model_name:
        return None

    try:
        import litellm

        normalized = _normalize_model_name(model_name, provider_name or "", brand=provider_brand)

        entry = litellm.model_cost.get(normalized)
        if entry is None:
            # normalized is "<prefix>/<model>"; the raw model name alone is
            # also a common key (e.g. "gpt-4-turbo" without "openai/").
            entry = litellm.model_cost.get(model_name)

        if entry is None:
            # Segment-aware fallback for keys LiteLLM prefixes with vendor
            # routing info that isn't captured by our own prefix mapping
            # (e.g. bedrock/, azure_ai/, region qualifiers).
            target = model_name.split("/", 1)[-1].lower()
            escaped_target = re.escape(target)
            segment_pattern = re.compile(rf"(^|[/\-.:@]){escaped_target}([/\-:@]|$)")
            for db_key, db_entry in litellm.model_cost.items():
                if segment_pattern.search(db_key.lower()):
                    entry = db_entry
                    break

        if not entry:
            return None

        context_window = entry.get("max_input_tokens")
        return int(context_window) if context_window else None
    except Exception:
        return None


def _resolve_context_window(run_doc):
    """Resolve the context window to measure a run's usage against.

    Most-authoritative source first:
      1. ``Agent Run.model_context_window`` — the value snapshotted at call
         time. Always wins when set, because it records what was actually
         true for this run, immune to later edits of the AI Model record.
      2. The run's ``AI Model.context_window`` — current model metadata.
      3. LiteLLM's model-cost table, for models that don't carry an explicit
         value on the AI Model record.
      4. ``None`` — explicitly "unknown". Never falls back to a guessed
         constant: an unmeasured context window must render as unmeasured,
         not as a confident, likely-wrong number.

    A field is treated as "set" only when it is a truthy, non-zero int; 0
    and NULL both mean "not set" per the AI Model field convention.
    """
    snapshot_window = run_doc.get("model_context_window")
    if snapshot_window:
        return snapshot_window

    model_link = run_doc.get("model")
    if model_link:
        model_doc = frappe.get_cached_doc("AI Model", model_link)
        if model_doc.get("context_window"):
            return model_doc.context_window

        return _context_window_from_litellm(
            model_doc.get("model_name"),
            run_doc.get("provider"),
            frappe.get_cached_value("AI Provider", run_doc.get("provider"), "provider_brand")
            if run_doc.get("provider")
            else None,
        )

    return None


@frappe.whitelist(methods=["GET"])
def get_run_context_metrics(run_name: str):
    run_doc = frappe.get_doc("Agent Run", run_name)
    run_doc.check_permission("read")

    snapshot_raw = run_doc.get("usage_snapshot")
    snapshot = json.loads(snapshot_raw) if snapshot_raw else {}

    previous_run_doc = None
    previous_name = frappe.db.get_value(
        "Agent Run",
        {
            "agent": run_doc.agent,
            "start_time": ["<", run_doc.start_time],
        },
        "name",
        order_by="start_time desc",
    )
    if previous_name:
        previous_run_doc = frappe.get_doc("Agent Run", previous_name)

    metrics = compute_run_metrics(run_doc, previous_run_doc)

    return {
        "segment_tokens": snapshot.get("segment_tokens"),
        "total_tokens": snapshot.get("total_tokens"),
        "context_window": _resolve_context_window(run_doc),
        "prefix_breakpoints": snapshot.get("prefix_breakpoints") or [],
        "cache_skipped_unsupported_model": snapshot.get("cache_skipped_unsupported_model"),
        "metrics": metrics,
    }
