"""Read-only aggregate API for execution analytics."""

from __future__ import annotations

import json

import frappe
from frappe.utils import add_to_date, convert_utc_to_system_timezone, get_datetime, now_datetime

from huf.ai.agent_run_analytics import DIMENSION_FIELDS


ROLLUP_DOCTYPE = "Agent Run Analytics Rollup"
MAX_WINDOW_DAYS = 93
ROLLUP_FIELDS = [
    "bucket_start",
    "agent",
    "provider",
    "model",
    "run_kind",
    "conversation",
    "run_count",
    "success_count",
    "failed_count",
    "input_tokens",
    "output_tokens",
    "cached_tokens",
    "cache_creation_tokens",
    "total_cost",
    "duration_ms_sum",
    "duration_count",
    "composition_totals",
    "last_recomputed_at",
]


def _to_system_naive(dt):
    """Normalise a datetime to the site's naive local convention.

    now_datetime() and every MariaDB datetime this module compares against
    are naive, in the site's configured system timezone (System Settings ->
    Time Zone, whatever that is set to -- not assumed to be UTC). But
    get_datetime() on an ISO string carrying an offset/Z suffix -- exactly
    what a browser's Date.toISOString() sends -- returns a timezone-AWARE
    UTC datetime. Comparing/subtracting that against a naive value raises
    TypeError; naively stripping tzinfo instead would silently shift the
    window by the site's UTC offset (checked live at 2026-08-24: this site
    is Asia/Kolkata, UTC+5:30 -- a blind strip is off by 5.5 hours, not off
    by nothing). Route through Frappe's own system-timezone conversion,
    which reads the site's configured timezone rather than assuming one.
    """
    if dt.tzinfo is not None:
        dt = convert_utc_to_system_timezone(dt).replace(tzinfo=None)
    return dt


def _require_analytics_access():
    user = frappe.session.user
    if "System Manager" in frappe.get_roles(user):
        return
    from huf.permissions import has_capability, get_user_huf_role
    if get_user_huf_role(user) in ("Huf Admin", "Huf Manager") or has_capability(user, "agent.view_all"):
        return
    frappe.throw("Execution analytics requires Agent view permission", frappe.PermissionError)


def _query_rollups(granularity: str, start, end) -> list[dict]:
    return frappe.db.get_all(
        ROLLUP_DOCTYPE,
        filters={"granularity": granularity, "bucket_start": ["between", [start, end]]},
        fields=ROLLUP_FIELDS,
        order_by="bucket_start asc",
        limit_page_length=0,
    )


def _load_composition_totals(raw) -> dict:
    """Parse a rollup row's composition_totals JSON string.

    NULL, empty, malformed JSON, and non-dict values all degrade to "no data"
    (an empty dict), matching the "not measured" semantics the rollup writes.
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


def _accumulate_composition(totals: dict, segment_tokens: dict) -> None:
    """Fold one rollup row's composition totals into a running total.

    Mirrors `huf.ai.agent_run_analytics._accumulate_composition`: `None` means
    "could not be counted" and must propagate as unknown, never be coerced to
    0. A segment's total becomes (and stays) `None` as soon as any
    contributing row reports `None` for it.
    """
    for segment, value in segment_tokens.items():
        if segment in totals and totals[segment] is None:
            continue
        if value is None:
            totals[segment] = None
        elif isinstance(value, (int, float)):
            totals[segment] = (totals.get(segment) or 0) + value
        # Non-numeric, non-None values are ignored rather than raising.


@frappe.whitelist(methods=["GET"])
def get_execution_analytics(
    from_date: str | None = None,
    to_date: str | None = None,
    granularity: str = "hour",
    dimension: str = "provider",
):
    """Return execution analytics; auto-refreshes rollups if empty."""
    _require_analytics_access()
    if granularity not in {"hour", "day"}:
        frappe.throw("granularity must be 'hour' or 'day'")
    if dimension not in DIMENSION_FIELDS:
        frappe.throw(f"dimension must be one of {', '.join(DIMENSION_FIELDS)}")
    # from_date/to_date arrive as ISO strings with an offset/Z suffix (the
    # frontend sends Date.toISOString()), which get_datetime() parses as
    # timezone-aware. now_datetime()/add_to_date() and every bucket_start
    # this gets compared against are naive, in the site's own timezone --
    # see _to_system_naive's docstring for why a blind tzinfo strip would
    # be silently wrong rather than merely inconsistent.
    end = _to_system_naive(get_datetime(to_date)) if to_date else now_datetime()
    start = _to_system_naive(get_datetime(from_date)) if from_date else add_to_date(end, days=-7)
    if start > end or (end - start).days > MAX_WINDOW_DAYS:
        frappe.throw(f"Date range must be between zero and {MAX_WINDOW_DAYS} days")
    if not frappe.db.exists("DocType", ROLLUP_DOCTYPE):
        # Same shape as the populated response, so a client never has to branch on
        # which keys exist -- only on whether they are empty.
        return {
            "summary": {},
            "series": [],
            "breakdowns": [],
            "composition_totals": {},
            "metadata": {
                "granularity": granularity,
                "dimension": dimension,
                "freshness": None,
                "breakdowns_total_count": 0,
            },
        }

    rows = _query_rollups(granularity, start, end)

    # If rollups are empty for this window, attempt a quick backfill refresh once and re-query
    if not rows and frappe.db.exists("Agent Run"):
        from huf.ai.agent_run_analytics import refresh_rollups
        refresh_rollups(full_backfill=True)
        rows = _query_rollups(granularity, start, end)

    summary = {
        "run_count": 0,
        "success_count": 0,
        "failed_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_tokens": 0,
        "cache_creation_tokens": 0,
        "total_cost": 0,
        "duration_ms_sum": 0,
        "duration_count": 0,
    }
    series_by_bucket, breakdown_by_dimension = {}, {}
    composition_totals: dict = {}
    freshness = None
    for row in rows:
        row = dict(row)
        for key in summary:
            summary[key] += row.get(key) or 0
        bucket = series_by_bucket.setdefault(row["bucket_start"], {"bucket_start": row["bucket_start"], **{key: 0 for key in summary}})
        for key in summary:
            bucket[key] += row.get(key) or 0
        dimension_value = row.get(dimension) or "Unknown"
        breakdown = breakdown_by_dimension.setdefault(dimension_value, {"dimension": dimension_value, **{key: 0 for key in summary}})
        for key in summary:
            breakdown[key] += row.get(key) or 0
        _accumulate_composition(composition_totals, _load_composition_totals(row.get("composition_totals")))
        if row.get("last_recomputed_at") and (freshness is None or row["last_recomputed_at"] > freshness):
            freshness = row["last_recomputed_at"]
    summary["success_rate"] = (summary["success_count"] / summary["run_count"] * 100) if summary["run_count"] else None
    summary["average_duration_ms"] = (summary["duration_ms_sum"] / summary["duration_count"]) if summary["duration_count"] else None
    summary["cache_ratio"] = (summary["cached_tokens"] / summary["input_tokens"] * 100) if summary["input_tokens"] else None
    breakdowns_total_count = len(breakdown_by_dimension)
    return {
        "summary": summary,
        "series": list(series_by_bucket.values()),
        "breakdowns": sorted(breakdown_by_dimension.values(), key=lambda item: item["run_count"], reverse=True)[:10],
        "composition_totals": composition_totals,
        "metadata": {
            "granularity": granularity,
            "dimension": dimension,
            "from": start,
            "to": end,
            "freshness": freshness,
            "source": "scheduled_rollup",
            "breakdowns_total_count": breakdowns_total_count,
        },
    }
