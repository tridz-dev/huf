import frappe


def execute():
    """Backfill Agent Run sequence and add the drain-loop composite index."""
    if not frappe.db.has_column("Agent Run", "sequence"):
        return

    # Backfill any pre-existing rows so the drain loop's ORDER BY sequence
    # never sees NULLs interleaved with new submissions.
    frappe.db.sql("""
        UPDATE `tabAgent Run`
        SET `sequence` = 0
        WHERE `sequence` IS NULL
    """)

    # Use Frappe's DDL helper so the implicit commit is allowed during migrate.
    frappe.db.add_index(
        "Agent Run",
        ["conversation", "status", "sequence"],
        "idx_agent_run_conv_status_seq",
    )
