import frappe

from huf.huf.doctype.huf_data_table.permissions import sync_data_table_permissions


def execute():
	"""
	Backfill DocType permissions for existing Huf Data Tables.

	On fresh installs where the Huf Data Table registry does not exist yet,
	this patch no-ops gracefully.
	"""
	if not frappe.db.table_exists("Huf Data Table"):
		return

	try:
		sync_data_table_permissions()
	except Exception:
		frappe.log_error(
			title="Patch: failed to sync data table permissions",
			message=frappe.get_traceback(),
		)
