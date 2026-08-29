import frappe

BATCH_SIZE = 500


def execute():
	"""Migrate prompt caching configuration from four fields to single prompt_cache_mode field.

	All existing Agents (regardless of enable_prompt_caching value) migrate to prompt_cache_mode='Auto'.
	This patch is idempotent: an Agent is updated only if prompt_cache_mode is unset and at least
	one old field is non-null/non-zero.

	The old fields remain in the database schema but are no longer used by the runtime.
	See agent_config_api.py, litellm.py, context_segments.py, and agent.js for runtime removals.
	"""

	if not frappe.db.has_column("Agent", "prompt_cache_mode"):
		frappe.logger().warning(
			"migrate_prompt_caching_fields: prompt_cache_mode column does not exist. "
			"Doctype migration may not have completed. Skipping patch."
		)
		return

	# Check if old fields exist (they may be dropped in a later migration)
	old_fields = [
		col for col in (
			"enable_prompt_caching",
			"cache_control_type",
			"cache_system_message",
			"cache_conversation_history",
		)
		if frappe.db.has_column("Agent", col)
	]

	if not old_fields:
		frappe.logger().info("migrate_prompt_caching_fields: old fields not found; already migrated.")
		return

	total_updated = 0
	last_name = ""

	while True:
		rows = frappe.get_all(
			"Agent",
			filters={"name": [">", last_name]},
			fields=["name", "prompt_cache_mode"] + old_fields,
			order_by="name asc",
			limit_page_length=BATCH_SIZE,
		)
		if not rows:
			break

		for row in rows:
			last_name = row.name

			# Update only if prompt_cache_mode is unset AND at least one old field is set
			if row.get("prompt_cache_mode"):
				continue  # Already migrated

			has_old_data = any(
				row.get(field) for field in old_fields
			)

			if has_old_data:
				frappe.db.set_value(
					"Agent",
					row.name,
					"prompt_cache_mode",
					"Auto",
					update_modified=False,
				)
				total_updated += 1

		frappe.db.commit()

		if len(rows) < BATCH_SIZE:
			break

	frappe.logger().info(
		f"migrate_prompt_caching_fields: migrated {total_updated} Agent row(s) to prompt_cache_mode='Auto'"
	)
