"""Archive Agent Run Analytics Rollup rows with conversation dimension.

WP-10 removes 'conversation' from DIMENSION_FIELDS (ST-10.2) because the per-
conversation rollup grouping causes O(conversations x buckets) scaling in
refresh_rollups. Existing rows with conversation set must be archived before
the dimension change takes effect, so they can never be decoded against the
new 4-field tuple (which would silently misinterpret their stored dimension_key).

This patch:
1. Ensures Agent Run Analytics Rollup Archive doctype exists.
2. Copies all rows with conversation set from Agent Run Analytics Rollup to
   Agent Run Analytics Rollup Archive, adding archived_at timestamp.
3. Does NOT delete archived rows from the live table — that is left to an
   explicit operator command, preserving history visibility and rollback safety.
"""

import frappe
from frappe.utils import now_datetime


def execute():
    """Archive conversation-dimensioned rollup rows."""
    # Ensure the archive doctype exists (skip if already present)
    if not frappe.db.exists("DocType", "Agent Run Analytics Rollup Archive"):
        frappe.reload_doc("huf", "doctype", "Agent Run Analytics Rollup Archive")

    # Query all rollup rows with conversation set (these are the ones to archive)
    rows_to_archive = frappe.db.get_all(
        "Agent Run Analytics Rollup",
        filters={"conversation": ["is", "set"]},
        fields=["*"],
        limit_page_length=0,
    )

    if not rows_to_archive:
        frappe.logger().info("No Agent Run Analytics Rollup rows with conversation dimension to archive")
        return

    # Prepare rows for bulk insert: copy all fields plus archived_at timestamp
    archived_rows = []
    archived_at = now_datetime()
    for row in rows_to_archive:
        archived_row = dict(row)
        archived_row["archived_at"] = archived_at
        # Remove the 'name' field to let bulk_insert auto-generate new document IDs
        archived_row.pop("name", None)
        archived_rows.append(archived_row)

    # Insert in batches of 1000 to avoid locking the table for too long
    batch_size = 1000
    for i in range(0, len(archived_rows), batch_size):
        batch = archived_rows[i : i + batch_size]
        frappe.db.bulk_insert("Agent Run Analytics Rollup Archive", batch)

    frappe.logger().info(
        f"Archived {len(archived_rows)} Agent Run Analytics Rollup rows "
        f"with a conversation dimension"
    )
