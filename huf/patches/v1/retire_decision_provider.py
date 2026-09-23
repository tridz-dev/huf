# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Retire Decision Provider DocType.

Decision Provider is superseded by AI Provider (decision D1).
This patch logs any existing rows to Error Log and deletes the DocType.
Idempotent: safe to run twice.
"""

import frappe


def execute():
	"""Delete Decision Provider DocType with logging for any existing rows."""

	# Check if the DocType still exists; if not, already deleted or never existed
	if not frappe.db.table_exists("decision_provider"):
		frappe.logger().info("retire_decision_provider: Decision Provider table does not exist. Skipping.")
		return

	# Log any existing rows to Error Log before deletion
	try:
		existing_rows = frappe.get_all("Decision Provider", fields=["name"])
		if existing_rows:
			row_names = ", ".join([row.name for row in existing_rows])
			frappe.log_error(
				title="Retire Decision Provider DocType",
				message=f"Decision Provider rows found before deletion: {row_names}. "
				f"These have been deleted as Decision Provider is retired and replaced by AI Provider."
			)
			frappe.logger().warning(
				f"retire_decision_provider: Found {len(existing_rows)} Decision Provider row(s): {row_names}"
			)
	except Exception as error:
		frappe.logger().warning(
			f"retire_decision_provider: Could not fetch existing rows (table may already be gone): {error}"
		)

	# Delete the DocType using frappe.delete_doc
	try:
		frappe.delete_doc("DocType", "Decision Provider", ignore_missing=True, force=True)
		frappe.logger().info("retire_decision_provider: Decision Provider DocType deleted successfully.")
	except Exception as error:
		frappe.logger().error(
			f"retire_decision_provider: Failed to delete Decision Provider DocType: {error}\n{frappe.get_traceback()}"
		)
		raise
