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

    # Prepare rows for bulk insert: copy all fields plus archived_at timestamp.
    # frappe.db.bulk_insert(doctype, fields, values) takes a column list and a
    # list of value-rows aligned to it -- it does NOT accept a list of dicts and
    # does NOT auto-generate `name`, so we keep the original row name (reused as
    # the archive doc's own name; the archive table is separate so this cannot
    # collide with a live Agent Run Analytics Rollup row) and build the two
    # parallel lists bulk_insert actually expects.
    archived_at = now_datetime()
    for row in rows_to_archive:
        row["archived_at"] = archived_at

    fields = list(rows_to_archive[0].keys())

    # Insert in batches of 1000 to avoid locking the table for too long
    batch_size = 1000
    for i in range(0, len(rows_to_archive), batch_size):
        batch = rows_to_archive[i : i + batch_size]
        values = [[row.get(field) for field in fields] for row in batch]
        frappe.db.bulk_insert("Agent Run Analytics Rollup Archive", fields, values)

    frappe.logger().info(
        f"Archived {len(rows_to_archive)} Agent Run Analytics Rollup rows "
        f"with a conversation dimension"
    )
