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

DEFAULT_CONTEXT_WINDOW = 200000


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

    # AI Model does not carry a context-window field today; DEFAULT_CONTEXT_WINDOW
    # is a placeholder until model metadata exposes one (see PHASE2_VisualCache.md).
    return {
        "segment_tokens": snapshot.get("segment_tokens"),
        "total_tokens": snapshot.get("total_tokens"),
        "context_window": DEFAULT_CONTEXT_WINDOW,
        "prefix_breakpoints": snapshot.get("prefix_breakpoints") or [],
        "cache_skipped_unsupported_model": snapshot.get("cache_skipped_unsupported_model"),
        "metrics": metrics,
    }
