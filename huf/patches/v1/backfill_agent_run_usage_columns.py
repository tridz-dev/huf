import json

import frappe

BATCH_SIZE = 500


def execute():
	"""Backfill the new flat Agent Run usage columns from usage_snapshot.

	Agent Run gained flat columns for the metrics that used to live only inside the
	usage_snapshot JSON blob, so they can finally be summed/filtered in SQL. Of those
	new columns, only three were ever actually recorded historically, because
	agent_integration.py only ever wrote these keys into usage_snapshot:

	  - cache_creation_tokens         <- usage_snapshot.cache_creation_tokens
	  - total_tokens                  <- usage_snapshot.total_tokens
	  - cache_skipped_unsupported_model <- usage_snapshot.cache_skipped_unsupported_model

	billed_input_tokens, peak_context_tokens, round_count, model_context_window,
	provider_path and execution_mode are NOT backfilled here and must be left NULL.
	They were never captured for historical runs, and the UI treats NULL as "not
	measured" for these metrics. Writing 0 instead would silently distort every
	historical average/rollup that reads these columns going forward - do not
	"helpfully" zero-fill them in a future edit of this patch.

	Idempotent and safe to re-run: a row is only touched when the flat column is
	still NULL/0 (its pre-migration/unset state) and the snapshot actually carries
	a value for it. Malformed, empty, or non-dict usage_snapshot values are skipped
	rather than raising, so a single corrupt row cannot fail the whole backfill.
	"""
	if not frappe.db.has_column("Agent Run", "usage_snapshot"):
		return

	target_columns = [
		column
		for column in (
			"cache_creation_tokens",
			"total_tokens",
			"cache_skipped_unsupported_model",
		)
		if frappe.db.has_column("Agent Run", column)
	]
	if not target_columns:
		return

	total_updated = 0
	last_name = ""

	while True:
		rows = frappe.get_all(
			"Agent Run",
			filters={"name": [">", last_name]},
			fields=["name", "usage_snapshot", *target_columns],
			order_by="name asc",
			limit_page_length=BATCH_SIZE,
		)
		if not rows:
			break

		for row in rows:
			last_name = row.name
			updates = _build_updates(row, target_columns)
			if updates:
				frappe.db.set_value("Agent Run", row.name, updates, update_modified=False)
				total_updated += 1

		frappe.db.commit()

		if len(rows) < BATCH_SIZE:
			break

	frappe.logger().info(
		f"backfill_agent_run_usage_columns: backfilled {total_updated} Agent Run row(s) "
		f"from usage_snapshot"
	)


def _build_updates(row, target_columns):
	"""Return a dict of column -> value to set on this row, or None if nothing to do."""
	snapshot = row.get("usage_snapshot")
	if not snapshot:
		return None

	if isinstance(snapshot, str):
		try:
			snapshot = json.loads(snapshot)
		except (TypeError, ValueError):
			return None

	if not isinstance(snapshot, dict):
		return None

	updates = {}

	if "cache_creation_tokens" in target_columns and not row.get("cache_creation_tokens"):
		value = snapshot.get("cache_creation_tokens")
		if isinstance(value, (int, float)) and not isinstance(value, bool):
			updates["cache_creation_tokens"] = int(value)

	if "total_tokens" in target_columns and not row.get("total_tokens"):
		value = snapshot.get("total_tokens")
		if isinstance(value, (int, float)) and not isinstance(value, bool):
			updates["total_tokens"] = int(value)

	if "cache_skipped_unsupported_model" in target_columns and not row.get(
		"cache_skipped_unsupported_model"
	):
		if "cache_skipped_unsupported_model" in snapshot:
			updates["cache_skipped_unsupported_model"] = (
				1 if snapshot.get("cache_skipped_unsupported_model") else 0
			)

	return updates or None
