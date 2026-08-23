"""Per-run context composition and cache-economics API.

Serves the segment_tokens breakdown and the five derived cache metrics for
a single Agent Run, for the ContextBar component (chat header, run detail).
Reads only the run's own usage_snapshot plus the prior run of the same
agent for prefix-stability comparison; never aggregates raw runs.
"""

from __future__ import annotations

import json

import frappe

from huf.ai.cache_metrics import compute_run_metrics
from huf.ai.model_metadata import resolve_model_context_window


def _resolve_context_window(run_doc):
    """Resolve the context window to measure a run's usage against.

    Most-authoritative source first:
      1. ``Agent Run.model_context_window`` — the value snapshotted at call
         time. Always wins when set, because it records what was actually
         true for this run, immune to later edits of the AI Model record.
      2. Everything else — delegated to ``resolve_model_context_window``:
         the run's ``AI Model.context_window`` (current model metadata),
         then LiteLLM's model-cost table, then ``None``.

    A field is treated as "set" only when it is a truthy, non-zero int; 0
    and NULL both mean "not set" per the AI Model field convention.
    """
    snapshot_window = run_doc.get("model_context_window")
    if snapshot_window:
        return snapshot_window

    model_link = run_doc.get("model")
    if not model_link:
        return None

    provider_brand = (
        frappe.get_cached_value("AI Provider", run_doc.get("provider"), "provider_brand")
        if run_doc.get("provider")
        else None
    )
    return resolve_model_context_window(model_link, run_doc.get("provider"), provider_brand)


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
