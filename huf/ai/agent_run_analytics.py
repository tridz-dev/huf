"""Scheduled, idempotent rollups for Agent Run analytics.

The browser and API only read rollups. Raw Agent Runs are grouped here in a
bounded correction window so terminal updates are reflected without exposing
or repeatedly aggregating raw executions at request time.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime


ROLLUP_DOCTYPE = "Agent Run Analytics Rollup"
TERMINAL_STATUSES = ("Success", "Failed")
CORRECTION_WINDOW_HOURS = 26


def _bucket_start(value, granularity: str):
    value = get_datetime(value)
    if granularity == "day":
        return value.replace(hour=0, minute=0, second=0, microsecond=0)
    return value.replace(minute=0, second=0, microsecond=0)


def _dimension_key(row: dict) -> str:
    return "|".join(str(row.get(field) or "__none__") for field in ("agent", "provider", "model", "run_kind"))


def _affected_dimensions(since):
    rows = frappe.db.get_all(
        "Agent Run",
        filters={"status": ["in", TERMINAL_STATUSES], "start_time": [">=", since]},
        fields=["start_time", "agent", "provider", "model", "run_kind"],
        limit_page_length=0,
    )
    affected = set()
    for row in rows:
        if not row.start_time:
            continue
        row = row.as_dict()
        for granularity in ("hour", "day"):
            affected.add((granularity, _bucket_start(row["start_time"], granularity), _dimension_key(row)))
    return affected


def _recompute_rollup(granularity: str, bucket_start, dimension_key: str):
    bucket_end = add_to_date(bucket_start, hours=1 if granularity == "hour" else 24)
    dimensions = dimension_key.split("|")
    fields = ("agent", "provider", "model", "run_kind")
    filters = [
        ["status", "in", TERMINAL_STATUSES],
        ["start_time", ">=", bucket_start],
        ["start_time", "<", bucket_end],
    ]
    for field, value in zip(fields, dimensions):
        filters.append([field, "is", "not set"] if value == "__none__" else [field, "=", value])

    rows = frappe.db.get_all(
        "Agent Run",
        filters=filters,
        fields=["status", "input_tokens", "output_tokens", "cached_tokens", "cost", "start_time", "end_time"],
        limit_page_length=0,
    )
    if not rows:
        existing = frappe.db.exists(ROLLUP_DOCTYPE, {"granularity": granularity, "bucket_start": bucket_start, "dimension_key": dimension_key})
        if existing:
            frappe.delete_doc(ROLLUP_DOCTYPE, existing, force=True, ignore_permissions=True)
        return

    metrics = defaultdict(float)
    metrics["run_count"] = len(rows)
    for row in rows:
        metrics["success_count"] += int(row.status == "Success")
        metrics["failed_count"] += int(row.status == "Failed")
        metrics["input_tokens"] += row.input_tokens or 0
        metrics["output_tokens"] += row.output_tokens or 0
        metrics["cached_tokens"] += row.cached_tokens or 0
        metrics["total_cost"] += row.cost or 0
        if row.start_time and row.end_time:
            duration = (get_datetime(row.end_time) - get_datetime(row.start_time)).total_seconds() * 1000
            if duration >= 0:
                metrics["duration_ms_sum"] += duration
                metrics["duration_count"] += 1

    existing = frappe.db.exists(ROLLUP_DOCTYPE, {"granularity": granularity, "bucket_start": bucket_start, "dimension_key": dimension_key})
    doc = frappe.get_doc(ROLLUP_DOCTYPE, existing) if existing else frappe.new_doc(ROLLUP_DOCTYPE)
    doc.update({
        "granularity": granularity,
        "bucket_start": bucket_start,
        "dimension_key": dimension_key,
        "agent": None if dimensions[0] == "__none__" else dimensions[0],
        "provider": None if dimensions[1] == "__none__" else dimensions[1],
        "model": None if dimensions[2] == "__none__" else dimensions[2],
        "run_kind": None if dimensions[3] == "__none__" else dimensions[3],
        **metrics,
        "last_recomputed_at": now_datetime(),
    })
    doc.flags.ignore_permissions = True
    doc.save() if existing else doc.insert()


def refresh_rollups():
    """Recompute the recent mutable window; safe to retry and safe on empty sites."""
    if not frappe.db.exists("DocType", ROLLUP_DOCTYPE):
        return
    since = add_to_date(now_datetime(), hours=-CORRECTION_WINDOW_HOURS)
    for granularity, bucket_start, dimension_key in _affected_dimensions(since):
        try:
            _recompute_rollup(granularity, bucket_start, dimension_key)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Agent Run analytics rollup refresh failed")
    frappe.db.commit()
