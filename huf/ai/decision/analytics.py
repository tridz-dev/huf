"""Decision spend analytics — whitelisted read-only API for aggregating Decision Call metrics.

Provides aggregated spend metrics (cost, tokens, call counts) over time and by dimension
(policy, agent, surface, deployment, origin_type, mode). Respects D5 permission filtering
via get_permission_query_conditions from Decision Call.

PLAN.md §3.13 Observability: "Analytics (PR 10): per policy/version metrics from IP §19.3;
decision spend over time by policy, agent, surface and deployment. Spend accounting itself
is not in PR 10 (see D15, §4.7)."
"""

from __future__ import annotations

from datetime import datetime, timedelta

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime, convert_utc_to_system_timezone


# Valid dimensions for group_by parameter
VALID_GROUP_BY = {"policy", "agent", "surface", "deployment", "origin_type", "mode"}

# Valid bucket sizes for timeseries
VALID_BUCKETS = {"hour", "day"}

# Maximum lookback window (days)
MAX_WINDOW_DAYS = 93


def _to_system_naive(dt):
	"""Normalise a datetime to the site's naive local convention.

	Same pattern as agent_run_analytics_api._to_system_naive: get_datetime() on an ISO
	string with offset/Z returns timezone-aware UTC, but now_datetime() and frappe.db
	queries are naive in the site's local timezone. Converting via Frappe's own
	convert_utc_to_system_timezone avoids silently shifting the window.
	"""
	if dt.tzinfo is not None:
		dt = convert_utc_to_system_timezone(dt).replace(tzinfo=None)
	return dt


def _build_permission_where(user=None) -> str | None:
	"""Get permission query condition (SQL WHERE clause) for Decision Call visibility.

	Returns None for admins (see all), or a SQL WHERE clause for non-admins.
	Delegates to Decision Call's get_permission_query_conditions hook.
	"""
	from huf.huf.doctype.decision_call.decision_call import get_permission_query_conditions
	return get_permission_query_conditions(user)


def _time_bucket_name(dt: datetime, bucket: str) -> str:
	"""Return the bucket start time for a given datetime and bucket size."""
	if bucket == "hour":
		return dt.replace(minute=0, second=0, microsecond=0).isoformat()
	elif bucket == "day":
		return dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
	else:
		raise ValueError(f"Invalid bucket: {bucket}")


def _format_row(row: dict) -> dict:
	"""Format a database row for API response (compute derived fields, ensure keys present)."""
	# Ensure all expected keys exist
	row.setdefault("call_count", 0)
	row.setdefault("input_tokens", 0)
	row.setdefault("output_tokens", 0)
	row.setdefault("cost", 0.0)

	# Compute derived fields
	row["total_tokens"] = row["input_tokens"] + row["output_tokens"]

	return row


@frappe.whitelist(methods=["GET"])
def get_decision_spend_summary(
	from_date: str | None = None,
	to_date: str | None = None,
	group_by: str = "policy",
) -> dict:
	"""Return aggregated decision spend metrics over a date range, grouped by dimension.

	Args:
		from_date: Start date (ISO string, defaults to 7 days ago).
		to_date: End date (ISO string, defaults to now).
		group_by: Dimension to group by. One of: policy, agent, surface, deployment,
			origin_type, mode. Defaults to policy.

	Returns:
		{
			"summary": {
				"call_count": int,
				"input_tokens": int,
				"output_tokens": int,
				"total_tokens": int,
				"cost": float
			},
			"breakdowns": [
				{
					"<group_by>": str,  # e.g. "my-policy" if group_by="policy"
					"call_count": int,
					"input_tokens": int,
					"output_tokens": int,
					"total_tokens": int,
					"cost": float
				},
				...
			],
			"metadata": {
				"granularity": "summary",
				"group_by": str,
				"from": datetime,
				"to": datetime,
				"breakdowns_total_count": int
			}
		}
	"""
	# Validate parameters
	if group_by not in VALID_GROUP_BY:
		frappe.throw(f"group_by must be one of: {', '.join(sorted(VALID_GROUP_BY))}")

	# Parse dates and apply defaults
	end = _to_system_naive(get_datetime(to_date)) if to_date else now_datetime()
	start = _to_system_naive(get_datetime(from_date)) if from_date else add_to_date(end, days=-7)

	if start > end or (end - start).days > MAX_WINDOW_DAYS:
		frappe.throw(f"Date range must be between zero and {MAX_WINDOW_DAYS} days")

	# Build base query
	user = frappe.session.user
	perm_where = _build_permission_where(user)

	# Map group_by dimension to database field name
	dimension_field_map = {
		"policy": "`tabDecision Call`.policy",
		"agent": "`tabDecision Call`.agent",
		"surface": "`tabDecision Call`.surface",
		"deployment": "`tabDecision Call`.resolved_deployment",
		"origin_type": "`tabDecision Call`.origin_type",
		"mode": "`tabDecision Call`.mode",
	}
	group_field = dimension_field_map[group_by]

	# Query for summary (all calls in range)
	summary_sql = f"""
		SELECT
			COUNT(*) as call_count,
			COALESCE(SUM(`tabDecision Call`.input_tokens), 0) as input_tokens,
			COALESCE(SUM(`tabDecision Call`.output_tokens), 0) as output_tokens,
			COALESCE(SUM(`tabDecision Call`.cost), 0.0) as cost
		FROM `tabDecision Call`
		WHERE `tabDecision Call`.started_at >= {frappe.db.escape(start)}
		  AND `tabDecision Call`.started_at < {frappe.db.escape(end)}
	"""

	if perm_where:
		summary_sql += f"\n		AND {perm_where}"

	summary_result = frappe.db.sql(summary_sql, as_dict=True)
	summary = summary_result[0] if summary_result else {
		"call_count": 0,
		"input_tokens": 0,
		"output_tokens": 0,
		"cost": 0.0,
	}
	summary = _format_row(summary)

	# Query for breakdowns by dimension
	breakdown_sql = f"""
		SELECT
			{group_field} as dimension_value,
			COUNT(*) as call_count,
			COALESCE(SUM(`tabDecision Call`.input_tokens), 0) as input_tokens,
			COALESCE(SUM(`tabDecision Call`.output_tokens), 0) as output_tokens,
			COALESCE(SUM(`tabDecision Call`.cost), 0.0) as cost
		FROM `tabDecision Call`
		WHERE `tabDecision Call`.started_at >= {frappe.db.escape(start)}
		  AND `tabDecision Call`.started_at < {frappe.db.escape(end)}
	"""

	if perm_where:
		breakdown_sql += f"\n		AND {perm_where}"

	breakdown_sql += f"""
		GROUP BY dimension_value
		ORDER BY call_count DESC
	"""

	breakdown_results = frappe.db.sql(breakdown_sql, as_dict=True)

	# Format breakdown rows
	breakdowns = []
	for row in breakdown_results:
		formatted_row = _format_row(row)
		# Rename dimension_value to the actual group_by field name
		formatted_row[group_by] = formatted_row.pop("dimension_value") or "Unknown"
		breakdowns.append(formatted_row)

	return {
		"summary": summary,
		"breakdowns": breakdowns,
		"metadata": {
			"granularity": "summary",
			"group_by": group_by,
			"from": start,
			"to": end,
			"breakdowns_total_count": len(breakdowns),
		},
	}


@frappe.whitelist(methods=["GET"])
def get_decision_spend_timeseries(
	from_date: str | None = None,
	to_date: str | None = None,
	bucket: str = "day",
	group_by: str | None = None,
) -> dict:
	"""Return decision spend metrics aggregated over time, with optional dimension breakdown.

	Args:
		from_date: Start date (ISO string, defaults to 7 days ago).
		to_date: End date (ISO string, defaults to now).
		bucket: Time bucket size. One of: hour, day. Defaults to day.
		group_by: Optional dimension to group by within each time bucket.
			One of: policy, agent, surface, deployment, origin_type, mode.
			If provided, returns nested breakdowns per bucket.

	Returns (no group_by):
		{
			"summary": {
				"call_count": int,
				"input_tokens": int,
				"output_tokens": int,
				"total_tokens": int,
				"cost": float
			},
			"series": [
				{
					"bucket_start": datetime,
					"call_count": int,
					"input_tokens": int,
					"output_tokens": int,
					"total_tokens": int,
					"cost": float
				},
				...
			],
			"metadata": {
				"granularity": "hour" | "day",
				"group_by": null,
				"from": datetime,
				"to": datetime,
				"bucket_count": int
			}
		}

	Returns (with group_by):
		{
			"summary": {...},
			"series": [
				{
					"bucket_start": datetime,
					"call_count": int,
					...,
					"breakdowns": [
						{
							"<group_by>": str,
							"call_count": int,
							...
						},
						...
					]
				},
				...
			],
			"metadata": {
				"granularity": "hour" | "day",
				"group_by": str,
				"from": datetime,
				"to": datetime,
				"bucket_count": int
			}
		}
	"""
	# Validate parameters
	if bucket not in VALID_BUCKETS:
		frappe.throw(f"bucket must be one of: {', '.join(sorted(VALID_BUCKETS))}")

	if group_by is not None and group_by not in VALID_GROUP_BY:
		frappe.throw(f"group_by must be one of: {', '.join(sorted(VALID_GROUP_BY))}")

	# Parse dates and apply defaults
	end = _to_system_naive(get_datetime(to_date)) if to_date else now_datetime()
	start = _to_system_naive(get_datetime(from_date)) if from_date else add_to_date(end, days=-7)

	if start > end or (end - start).days > MAX_WINDOW_DAYS:
		frappe.throw(f"Date range must be between zero and {MAX_WINDOW_DAYS} days")

	# Build base query
	user = frappe.session.user
	perm_where = _build_permission_where(user)

	# Map group_by dimension to database field name
	dimension_field_map = {
		"policy": "`tabDecision Call`.policy",
		"agent": "`tabDecision Call`.agent",
		"surface": "`tabDecision Call`.surface",
		"deployment": "`tabDecision Call`.resolved_deployment",
		"origin_type": "`tabDecision Call`.origin_type",
		"mode": "`tabDecision Call`.mode",
	}

	# Determine bucket function based on bucket type
	if bucket == "hour":
		bucket_func = "DATE_FORMAT(`tabDecision Call`.started_at, '%Y-%m-%d %H:00:00')"
	else:  # day
		bucket_func = "DATE_FORMAT(`tabDecision Call`.started_at, '%Y-%m-%d 00:00:00')"

	if group_by:
		# Query with dimension breakdown per bucket
		group_field = dimension_field_map[group_by]
		series_sql = f"""
			SELECT
				{bucket_func} as bucket_start,
				{group_field} as dimension_value,
				COUNT(*) as call_count,
				COALESCE(SUM(`tabDecision Call`.input_tokens), 0) as input_tokens,
				COALESCE(SUM(`tabDecision Call`.output_tokens), 0) as output_tokens,
				COALESCE(SUM(`tabDecision Call`.cost), 0.0) as cost
			FROM `tabDecision Call`
			WHERE `tabDecision Call`.started_at >= {frappe.db.escape(start)}
			  AND `tabDecision Call`.started_at < {frappe.db.escape(end)}
		"""

		if perm_where:
			series_sql += f"\n			AND {perm_where}"

		series_sql += f"""
			GROUP BY bucket_start, dimension_value
			ORDER BY bucket_start ASC, call_count DESC
		"""
	else:
		# Query without dimension breakdown
		series_sql = f"""
			SELECT
				{bucket_func} as bucket_start,
				COUNT(*) as call_count,
				COALESCE(SUM(`tabDecision Call`.input_tokens), 0) as input_tokens,
				COALESCE(SUM(`tabDecision Call`.output_tokens), 0) as output_tokens,
				COALESCE(SUM(`tabDecision Call`.cost), 0.0) as cost
			FROM `tabDecision Call`
			WHERE `tabDecision Call`.started_at >= {frappe.db.escape(start)}
			  AND `tabDecision Call`.started_at < {frappe.db.escape(end)}
		"""

		if perm_where:
			series_sql += f"\n			AND {perm_where}"

		series_sql += """
			GROUP BY bucket_start
			ORDER BY bucket_start ASC
		"""

	series_results = frappe.db.sql(series_sql, as_dict=True)

	# Compute summary from all results
	summary = {
		"call_count": 0,
		"input_tokens": 0,
		"output_tokens": 0,
		"cost": 0.0,
	}

	# Process results into time series structure
	series_by_bucket = {}

	for row in series_results:
		bucket_start = row["bucket_start"]

		if group_by:
			# With dimension breakdown: nest breakdowns under buckets
			if bucket_start not in series_by_bucket:
				series_by_bucket[bucket_start] = {
					"bucket_start": bucket_start,
					"call_count": 0,
					"input_tokens": 0,
					"output_tokens": 0,
					"cost": 0.0,
					"breakdowns": [],
				}

			bucket_entry = series_by_bucket[bucket_start]

			# Add to bucket totals
			bucket_entry["call_count"] += row["call_count"]
			bucket_entry["input_tokens"] += row["input_tokens"]
			bucket_entry["output_tokens"] += row["output_tokens"]
			bucket_entry["cost"] += row["cost"]

			# Add breakdown entry
			breakdown_row = _format_row({
				"call_count": row["call_count"],
				"input_tokens": row["input_tokens"],
				"output_tokens": row["output_tokens"],
				"cost": row["cost"],
			})
			breakdown_row[group_by] = row["dimension_value"] or "Unknown"
			bucket_entry["breakdowns"].append(breakdown_row)
		else:
			# Without dimension breakdown: simple time series
			if bucket_start not in series_by_bucket:
				series_by_bucket[bucket_start] = {
					"bucket_start": bucket_start,
					"call_count": 0,
					"input_tokens": 0,
					"output_tokens": 0,
					"cost": 0.0,
				}

			bucket_entry = series_by_bucket[bucket_start]
			bucket_entry["call_count"] += row["call_count"]
			bucket_entry["input_tokens"] += row["input_tokens"]
			bucket_entry["output_tokens"] += row["output_tokens"]
			bucket_entry["cost"] += row["cost"]

		# Add to overall summary
		summary["call_count"] += row["call_count"]
		summary["input_tokens"] += row["input_tokens"]
		summary["output_tokens"] += row["output_tokens"]
		summary["cost"] += row["cost"]

	# Format all series entries
	series = []
	for bucket_start in sorted(series_by_bucket.keys()):
		entry = series_by_bucket[bucket_start]
		entry = _format_row(entry)
		series.append(entry)

	# Format summary
	summary = _format_row(summary)

	return {
		"summary": summary,
		"series": series,
		"metadata": {
			"granularity": bucket,
			"group_by": group_by,
			"from": start,
			"to": end,
			"bucket_count": len(series),
		},
	}
