import frappe

BATCH_SIZE = 500


def execute():
	"""Migrate existing AI Provider rows to new provider_mode and billing_mode fields.

	This patch handles the migration of the legacy is_local_llm field to the new
	provider_mode field, following plan §36 migration rule:
	- is_local_llm=1 → provider_mode="Local Endpoint"
	- is_local_llm=0 or unset → provider_mode="API"

	CRITICALLY: No existing row is EVER set to provider_mode="Subscription CLI"
	by this migration. That field is only set explicitly by an admin choosing
	Subscription CLI in the new UI (plan §10.3).

	All rows get billing_mode defaulted to "API" regardless of provider_mode,
	allowing admins to adjust billing separately if needed.
	"""

	# Ensure columns exist
	if not frappe.db.has_column("AI Provider", "provider_mode"):
		frappe.db.sql(
			"""
			ALTER TABLE `tabAI Provider`
			ADD COLUMN `provider_mode` varchar(140) NOT NULL DEFAULT 'API'
			"""
		)

	if not frappe.db.has_column("AI Provider", "billing_mode"):
		frappe.db.sql(
			"""
			ALTER TABLE `tabAI Provider`
			ADD COLUMN `billing_mode` varchar(140) NOT NULL DEFAULT 'API'
			"""
		)

	if not frappe.db.has_column("AI Provider", "subscription_runtime"):
		frappe.db.sql(
			"""
			ALTER TABLE `tabAI Provider`
			ADD COLUMN `subscription_runtime` varchar(140)
			"""
		)

	# Migrate existing rows
	total_updated = 0
	last_name = ""

	while True:
		rows = frappe.get_all(
			"AI Provider",
			filters={"name": [">", last_name]},
			fields=["name", "is_local_llm", "provider_mode", "billing_mode"],
			order_by="name asc",
			limit_page_length=BATCH_SIZE,
		)
		if not rows:
			break

		for row in rows:
			last_name = row.name
			updates = _build_updates(row)
			if updates:
				frappe.db.set_value("AI Provider", row.name, updates, update_modified=False)
				total_updated += 1

		frappe.db.commit()

		if len(rows) < BATCH_SIZE:
			break

	frappe.logger().info(
		f"migrate_ai_provider_mode_fields: migrated {total_updated} AI Provider row(s) "
		f"with provider_mode/billing_mode defaults"
	)


def _build_updates(row):
	"""Return a dict of column -> value to set on this row, or None if nothing to do."""
	updates = {}

	# Migrate provider_mode based on is_local_llm
	# Only update if provider_mode is still at default "API" (not yet customized)
	if row.get("provider_mode") == "API":
		is_local = row.get("is_local_llm")
		if is_local:
			updates["provider_mode"] = "Local Endpoint"
		# else: stay as "API" (already the default)

	# Ensure billing_mode is set (default to "API" for all)
	# Only update if not already set
	if not row.get("billing_mode") or row.get("billing_mode") == "API":
		updates["billing_mode"] = "API"

	return updates or None
