"""Direct, per-conversation execution analytics for Agent Conversation.

`Agent Run Analytics Rollup` (see `agent_run_analytics.py` / `agent_run_analytics_api.py`)
is recomputed on a 5-minute cron. That lag is fine for aggregate/trend views
spanning many entities, but a single conversation typically holds only tens
of runs, and a just-finished turn missing from its own conversation's
analytics reads as a bug, not staleness. So this module never reads the
rollup: it queries `Agent Run` directly, filtered to one conversation and
ordered by `sequence`, trading a small per-request query cost for
correctness at "just typed" latency.

Rule of thumb this module follows: **rollups for aggregate/trend across
entities, direct `Agent Run` query for one entity's detail.**

Response shape keeps two different quantities structurally apart so a UI
cannot conflate them:

  - `totals` is CUMULATIVE — summed across every run in the conversation.
  - `current` is a SNAPSHOT of the latest run (highest `sequence`) only.
    `peak_context_tokens` in particular must never be summed across runs;
    it describes the size of the context window at one point in time, not
    a quantity that accumulates.

Every division in this module is guarded against a zero or `None`
denominator (see `_compute_current`, `_compute_cache_effectiveness`, and
the per-run delta in `_build_series`). Malformed `usage_snapshot` values
(NULL, non-JSON, non-dict, missing keys) degrade to "no data" and never
raise, matching the handling in `agent_run_analytics.py`.
"""

from __future__ import annotations

import json

import frappe


RUN_KINDS = ("agent", "tool", "orchestrator")

# The orphaned-tool-run disclosure is a slow-moving historical figure; an hour
# of staleness is immaterial next to scanning Agent Run on every request.
ORPHAN_COUNT_CACHE_SECONDS = 3600

RUN_FIELDS = [
    "name",
    "sequence",
    "run_kind",
    "status",
    "start_time",
    "input_tokens",
    "billed_input_tokens",
    "output_tokens",
    "cached_tokens",
    "cache_creation_tokens",
    "peak_context_tokens",
    "model_context_window",
    "cost",
    "usage_snapshot",
]


def _require_conversation_access(conversation: str):
    """Gate on the conversation itself, since this is per-conversation data.

    A missing conversation is handled cleanly (DoesNotExistError, not a
    permission error or a 500) before any permission check runs.
    """
    if not frappe.db.exists("Agent Conversation", conversation):
        frappe.throw(f"Agent Conversation {conversation} not found", frappe.DoesNotExistError)

    conversation_doc = frappe.get_doc("Agent Conversation", conversation)
    if not frappe.has_permission("Agent Conversation", "read", doc=conversation_doc):
        frappe.throw(
            "You do not have permission to view this conversation's analytics",
            frappe.PermissionError,
        )
    return conversation_doc


def _billed_input(row: dict) -> int:
    """`billed_input_tokens` is NULL on every pre-instrumentation row; fall
    back to the legacy `input_tokens` column for those, same convention as
    `agent_run_analytics._recompute_rollup`."""
    value = row.get("billed_input_tokens")
    return value if value is not None else (row.get("input_tokens") or 0)


def _row_is_missing_billed_input(row: dict) -> bool:
    return row.get("billed_input_tokens") is None


def _load_usage_snapshot(raw) -> dict:
    """Parse a run's usage_snapshot into a dict.

    NULL, empty, malformed JSON, and non-dict values all degrade to {} (no
    data), the same "not measured" semantics used elsewhere for this field.
    Never raises.
    """
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _empty_totals() -> dict:
    return {
        "cumulative": True,
        "run_count": 0,
        "run_count_by_kind": {kind: 0 for kind in RUN_KINDS},
        "billed_input_tokens": 0,
        "output_tokens": 0,
        "cost": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    }


def _compute_totals(rows: list[dict]) -> tuple[dict, int]:
    """Sum cumulative totals across every run. Returns (totals, runs_missing_billed_input)."""
    totals = _empty_totals()
    totals["run_count"] = len(rows)
    runs_missing_billed_input = 0

    for row in rows:
        kind = row.get("run_kind") or "agent"
        if kind not in totals["run_count_by_kind"]:
            kind = "agent"
        totals["run_count_by_kind"][kind] += 1

        if _row_is_missing_billed_input(row):
            runs_missing_billed_input += 1

        totals["billed_input_tokens"] += _billed_input(row)
        totals["output_tokens"] += row.get("output_tokens") or 0
        totals["cost"] += row.get("cost") or 0
        totals["cache_read_tokens"] += row.get("cached_tokens") or 0
        totals["cache_write_tokens"] += row.get("cache_creation_tokens") or 0

    return totals, runs_missing_billed_input


def _compute_current(latest_row: dict | None) -> dict | None:
    """Build the SNAPSHOT for the latest run (highest `sequence`).

    Never a sum. `context_fullness` is `None` whenever either
    `peak_context_tokens` or `model_context_window` is missing -- no
    default window is ever substituted for an unknown one.
    """
    if latest_row is None:
        return None

    peak_context_tokens = latest_row.get("peak_context_tokens")
    model_context_window = latest_row.get("model_context_window")
    context_fullness = None
    if peak_context_tokens is not None and model_context_window:
        context_fullness = peak_context_tokens / model_context_window

    snapshot = _load_usage_snapshot(latest_row.get("usage_snapshot"))
    segment_tokens = snapshot.get("segment_tokens")
    if not isinstance(segment_tokens, dict):
        segment_tokens = None

    return {
        "run": latest_row.get("name"),
        "sequence": latest_row.get("sequence"),
        "peak_context_tokens": peak_context_tokens,
        "model_context_window": model_context_window,
        "context_fullness": context_fullness,
        "segment_tokens": segment_tokens,
        "tool_exchange_tokens": snapshot.get("tool_exchange_tokens"),
    }


def _build_series(rows: list[dict]) -> list[dict]:
    """Per-run series ordered by `sequence`, with a consecutive-run delta of
    `peak_context_tokens` so growth spikes are visible without the client
    recomputing anything. Delta is `None` whenever this run or the
    immediately preceding run in the series has no `peak_context_tokens`.
    """
    series = []
    previous_row = None
    for row in rows:
        peak_context_tokens = row.get("peak_context_tokens")
        peak_context_tokens_delta = None
        if previous_row is not None:
            previous_peak = previous_row.get("peak_context_tokens")
            if peak_context_tokens is not None and previous_peak is not None:
                peak_context_tokens_delta = peak_context_tokens - previous_peak

        series.append({
            "sequence": row.get("sequence"),
            "run_kind": row.get("run_kind"),
            "peak_context_tokens": peak_context_tokens,
            "peak_context_tokens_delta": peak_context_tokens_delta,
            "billed_input_tokens": _billed_input(row),
            "output_tokens": row.get("output_tokens"),
            "cost": row.get("cost"),
            "status": row.get("status"),
            "start_time": row.get("start_time"),
        })
        previous_row = row

    return series


def _compute_cache_effectiveness(rows: list[dict]) -> dict:
    """Conversation-level cache effectiveness from SUMMED components, never
    an average of per-run ratios -- averaging ratios would weight a
    100-token run the same as a 100,000-token one.

    `uncached_input` per run is `billed_input - cache_read - cache_write`,
    floored at 0, matching the convention in `cache_metrics.py`.
    """
    sum_cache_read = 0
    sum_cache_write = 0
    sum_uncached_input = 0

    for row in rows:
        billed = _billed_input(row)
        cache_read = row.get("cached_tokens") or 0
        cache_write = row.get("cache_creation_tokens") or 0
        uncached_input = max(billed - cache_read - cache_write, 0)

        sum_cache_read += cache_read
        sum_cache_write += cache_write
        sum_uncached_input += uncached_input

    denominator = sum_cache_read + sum_cache_write + sum_uncached_input
    effectiveness = (sum_cache_read / denominator) if denominator else None

    return {
        "cache_read_tokens": sum_cache_read,
        "cache_write_tokens": sum_cache_write,
        "uncached_input_tokens": sum_uncached_input,
        "effectiveness": effectiveness,
    }


def _count_orphaned_tool_runs() -> int:
    """Historical `run_kind="tool"` runs were created with a NULL
    `conversation` and cannot be retro-linked to any conversation. This is a
    system-wide count (not scoped to the requested conversation, since those
    rows are by definition unlinkable to any conversation), surfaced so the
    UI can disclose that older, flow-heavy conversations may under-report
    tool-run totals rather than silently omitting them.
    """
    # Neither `run_kind` nor `conversation` is indexed on Agent Run, so this
    # COUNT is a full table scan. It is a slow-moving disclosure figure, not a
    # live metric -- no new tool run is created without a conversation any more
    # -- so it is cached rather than recomputed on every conversation page load.
    cache_key = "huf:analytics:orphaned_tool_runs"
    cached = frappe.cache().get_value(cache_key)
    if cached is not None:
        try:
            return int(cached)
        except (TypeError, ValueError):
            pass

    count = frappe.db.count("Agent Run", {"run_kind": "tool", "conversation": ["is", "not set"]})
    frappe.cache().set_value(cache_key, count, expires_in_sec=ORPHAN_COUNT_CACHE_SECONDS)
    return count


@frappe.whitelist(methods=["GET"])
def get_conversation_analytics(conversation: str):
    """Return direct, per-conversation execution analytics.

    Queries `Agent Run` directly (never the rollup) so a just-finished turn
    is reflected immediately. See module docstring for the cumulative
    (`totals`) vs snapshot (`current`) separation.
    """
    _require_conversation_access(conversation)

    rows = frappe.db.get_all(
        "Agent Run",
        filters={"conversation": conversation},
        fields=RUN_FIELDS,
        order_by="sequence asc",
        limit_page_length=0,
    )
    rows = [dict(row) for row in rows]

    totals, runs_missing_billed_input = _compute_totals(rows)

    latest_row = None
    for row in rows:
        if latest_row is None or (row.get("sequence") or 0) >= (latest_row.get("sequence") or 0):
            latest_row = row
    current = _compute_current(latest_row)

    series = _build_series(rows)
    cache = _compute_cache_effectiveness(rows)

    runs_missing_peak_context = sum(1 for row in rows if row.get("peak_context_tokens") is None)

    measurement = {
        "runs_missing_billed_input": runs_missing_billed_input,
        "runs_missing_peak_context": runs_missing_peak_context,
        "tool_runs_without_conversation_note": _count_orphaned_tool_runs(),
    }

    return {
        "totals": totals,
        "current": current,
        "series": series,
        "cache": cache,
        "measurement": measurement,
    }
