"""Scheduled, idempotent rollups for Agent Run analytics.

The browser and API only read rollups. Raw Agent Runs are grouped here in a
bounded correction window so terminal updates are reflected without exposing
or repeatedly aggregating raw executions at request time.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import timedelta

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime


ROLLUP_DOCTYPE = "Agent Run Analytics Rollup"
TERMINAL_STATUSES = ("Success", "Failed")
CORRECTION_WINDOW_HOURS = 26

# Single source of truth for the rollup's grouping dimensions. `_dimension_key()`,
# `_affected_dimensions()`, and `_recompute_rollup()` all derive from this tuple so
# they can never drift out of agreement with each other or with the doc fields they
# populate. `conversation` is appended at the END, not inserted alongside the other
# fields: `dimension_key` values are persisted in existing rollup rows, and appending
# keeps every previously-stored key string decodable positionally (old rows simply
# decode with `conversation == "__none__"`). Inserting it earlier in the tuple would
# silently reinterpret every stored key's remaining fields.
DIMENSION_FIELDS = ("agent", "provider", "model", "run_kind", "conversation")


def _bucket_start(value, granularity: str):
    value = get_datetime(value)
    if granularity == "day":
        return value.replace(hour=0, minute=0, second=0, microsecond=0)
    return value.replace(minute=0, second=0, microsecond=0)


def _dimension_key(row: dict) -> str:
    return "|".join(str(row.get(field) or "__none__") for field in DIMENSION_FIELDS)


def _affected_dimensions(since):
    rows = frappe.db.get_all(
        "Agent Run",
        filters={"status": ["in", TERMINAL_STATUSES], "start_time": [">=", since]},
        fields=["start_time", *DIMENSION_FIELDS],
        limit_page_length=0,
    )
    affected = set()
    for row in rows:
        if not row.start_time:
            continue
        row = dict(row)
        for granularity in ("hour", "day"):
            affected.add((granularity, _bucket_start(row["start_time"], granularity), _dimension_key(row)))
    return affected


def _load_segment_tokens(usage_snapshot) -> dict:
    """Best-effort extraction of segment_tokens from a run's usage_snapshot.

    Returns {} (no segments) on any malformed input: missing snapshot, a JSON
    string that fails to parse, an already-parsed dict, or a snapshot with no
    segment_tokens key. Never raises.
    """
    if not usage_snapshot:
        return {}
    if isinstance(usage_snapshot, str):
        try:
            usage_snapshot = json.loads(usage_snapshot)
        except (TypeError, ValueError):
            return {}
    if not isinstance(usage_snapshot, dict):
        return {}
    segment_tokens = usage_snapshot.get("segment_tokens")
    return segment_tokens if isinstance(segment_tokens, dict) else {}


def _accumulate_composition(totals: dict, segment_tokens: dict) -> None:
    """Fold one run's segment_tokens into the bucket's running composition totals.

    `None` in a segment means "could not be counted" (see context_segments.py) and
    must never be coerced to 0. A segment's bucket total is represented as `None`
    (unknown) as soon as ANY contributing run reports `None` for it, and stays
    `None` for the rest of the bucket regardless of later runs — an unknown run
    poisons the sum rather than being silently dropped. This makes "unknown" and
    "zero" impossible to confuse: a consumer sees either a number (every
    contributing run counted that segment) or `None` (at least one could not),
    never a number that quietly excludes unmeasured runs.
    """
    for segment, value in segment_tokens.items():
        if segment in totals and totals[segment] is None:
            continue
        if value is None:
            totals[segment] = None
        elif isinstance(value, (int, float)):
            totals[segment] = (totals.get(segment) or 0) + value
        # Non-numeric, non-None values are ignored rather than raising.


def _recompute_rollup(granularity: str, bucket_start, dimension_key: str):
    bucket_end = add_to_date(bucket_start, hours=1 if granularity == "hour" else 24)
    dimensions = dimension_key.split("|")
    filters = [
        ["status", "in", TERMINAL_STATUSES],
        ["start_time", ">=", bucket_start],
        ["start_time", "<", bucket_end],
    ]
    for field, value in zip(DIMENSION_FIELDS, dimensions):
        filters.append([field, "is", "not set"] if value == "__none__" else [field, "=", value])

    rows = frappe.db.get_all(
        "Agent Run",
        filters=filters,
        fields=[
            "status",
            "input_tokens",
            "billed_input_tokens",
            "output_tokens",
            "cached_tokens",
            "cache_creation_tokens",
            "cost",
            "start_time",
            "end_time",
            "usage_snapshot",
        ],
        limit_page_length=0,
    )
    if not rows:
        existing = frappe.db.exists(ROLLUP_DOCTYPE, {"granularity": granularity, "bucket_start": bucket_start, "dimension_key": dimension_key})
        if existing:
            frappe.delete_doc(ROLLUP_DOCTYPE, existing, force=True, ignore_permissions=True)
        return

    metrics = defaultdict(float)
    metrics["run_count"] = len(rows)
    composition_totals: dict = {}
    for row in rows:
        metrics["success_count"] += int(row.status == "Success")
        metrics["failed_count"] += int(row.status == "Failed")
        # billed_input_tokens is the new canonical, path-independent column, but it is
        # NULL on every historical row (never captured before this branch). Falling
        # back to input_tokens keeps existing dashboards correct across the cutover
        # using the best available number, without a second rollup field.
        metrics["input_tokens"] += row.billed_input_tokens if row.billed_input_tokens is not None else (row.input_tokens or 0)
        metrics["output_tokens"] += row.output_tokens or 0
        metrics["cached_tokens"] += row.cached_tokens or 0
        metrics["cache_creation_tokens"] += row.cache_creation_tokens or 0
        metrics["total_cost"] += row.cost or 0
        if row.start_time and row.end_time:
            duration = (get_datetime(row.end_time) - get_datetime(row.start_time)).total_seconds() * 1000
            if duration >= 0:
                metrics["duration_ms_sum"] += duration
                metrics["duration_count"] += 1
        _accumulate_composition(composition_totals, _load_segment_tokens(row.usage_snapshot))

    existing = frappe.db.exists(ROLLUP_DOCTYPE, {"granularity": granularity, "bucket_start": bucket_start, "dimension_key": dimension_key})
    doc = frappe.get_doc(ROLLUP_DOCTYPE, existing) if existing else frappe.new_doc(ROLLUP_DOCTYPE)
    dimension_values = {
        field: (None if value == "__none__" else value) for field, value in zip(DIMENSION_FIELDS, dimensions)
    }
    doc.update({
        "granularity": granularity,
        "bucket_start": bucket_start,
        "dimension_key": dimension_key,
        **dimension_values,
        **metrics,
        # Serialised explicitly, matching how this codebase writes every other JSON
        # field. An empty dict is stored as NULL rather than "{}": no segment was
        # measured at all, which is "not measured", not "measured as zero".
        "composition_totals": json.dumps(composition_totals) if composition_totals else None,
        "last_recomputed_at": now_datetime(),
    })
    doc.flags.ignore_permissions = True
    doc.save() if existing else doc.insert()


def refresh_rollups(full_backfill: bool = False):
    """Recompute recent or full rollup window; safe to retry and safe on empty sites."""
    if not frappe.db.exists("DocType", ROLLUP_DOCTYPE):
        return
    has_rollups = bool(frappe.db.count(ROLLUP_DOCTYPE))
    window_days = 90 if (full_backfill or not has_rollups) else 7
    since = add_to_date(now_datetime(), days=-window_days)
    for granularity, bucket_start, dimension_key in _affected_dimensions(since):
        try:
            _recompute_rollup(granularity, bucket_start, dimension_key)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Agent Run analytics rollup refresh failed")
    frappe.db.commit()
