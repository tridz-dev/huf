"""Read-only aggregate API for execution analytics."""

from __future__ import annotations

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime


ROLLUP_DOCTYPE = "Agent Run Analytics Rollup"
MAX_WINDOW_DAYS = 93


def _require_analytics_access():
    if "System Manager" not in frappe.get_roles():
        frappe.throw("Execution analytics requires System Manager access", frappe.PermissionError)


@frappe.whitelist(methods=["GET"])
def get_execution_analytics(from_date: str | None = None, to_date: str | None = None, granularity: str = "hour"):
    """Return precomputed analytics only; never query or group Agent Run rows."""
    _require_analytics_access()
    if granularity not in {"hour", "day"}:
        frappe.throw("granularity must be 'hour' or 'day'")
    end = get_datetime(to_date) if to_date else now_datetime()
    start = get_datetime(from_date) if from_date else add_to_date(end, days=-7)
    if start > end or (end - start).days > MAX_WINDOW_DAYS:
        frappe.throw(f"Date range must be between zero and {MAX_WINDOW_DAYS} days")
    if not frappe.db.exists("DocType", ROLLUP_DOCTYPE):
        return {"summary": {}, "series": [], "breakdowns": [], "metadata": {"freshness": None, "granularity": granularity}}

    rows = frappe.db.get_all(
        ROLLUP_DOCTYPE,
        filters={"granularity": granularity, "bucket_start": ["between", [start, end]]},
        fields=["bucket_start", "agent", "provider", "model", "run_kind", "run_count", "success_count", "failed_count", "input_tokens", "output_tokens", "cached_tokens", "total_cost", "duration_ms_sum", "duration_count", "last_recomputed_at"],
        order_by="bucket_start asc",
        limit_page_length=0,
    )
    summary = {"run_count": 0, "success_count": 0, "failed_count": 0, "input_tokens": 0, "output_tokens": 0, "cached_tokens": 0, "total_cost": 0, "duration_ms_sum": 0, "duration_count": 0}
    series_by_bucket, provider_by_name = {}, {}
    freshness = None
    for row in rows:
        row = row.as_dict()
        for key in summary:
            summary[key] += row.get(key) or 0
        bucket = series_by_bucket.setdefault(row["bucket_start"], {"bucket_start": row["bucket_start"], **{key: 0 for key in summary}})
        for key in summary:
            bucket[key] += row.get(key) or 0
        provider = row.get("provider") or "Unknown"
        breakdown = provider_by_name.setdefault(provider, {"dimension": provider, **{key: 0 for key in summary}})
        for key in summary:
            breakdown[key] += row.get(key) or 0
        if row.get("last_recomputed_at") and (freshness is None or row["last_recomputed_at"] > freshness):
            freshness = row["last_recomputed_at"]
    summary["success_rate"] = (summary["success_count"] / summary["run_count"] * 100) if summary["run_count"] else None
    summary["average_duration_ms"] = (summary["duration_ms_sum"] / summary["duration_count"]) if summary["duration_count"] else None
    summary["cache_ratio"] = (summary["cached_tokens"] / summary["input_tokens"] * 100) if summary["input_tokens"] else None
    return {
        "summary": summary,
        "series": list(series_by_bucket.values()),
        "breakdowns": sorted(provider_by_name.values(), key=lambda item: item["run_count"], reverse=True)[:10],
        "metadata": {"granularity": granularity, "from": start, "to": end, "freshness": freshness, "source": "scheduled_rollup"},
    }
