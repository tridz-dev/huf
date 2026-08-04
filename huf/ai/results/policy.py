# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""Result-store policy: thresholds, retention, and hard server-side limits.

All limits are intentionally conservative for V1.  Callers may request larger
values, but the server always caps them here.
"""

from datetime import datetime, timedelta

# Size classification ---------------------------------------------------------

# Results <= this many bytes are stored inline in ``Agent Execution Result``.
INLINE_THRESHOLD_BYTES = 8 * 1024  # 8 KB

# Results > this threshold are considered "very large": only summary/schema/
# preview views are advertised by default.  Bounded page/row reads still work.
SCHEMA_ONLY_THRESHOLD_BYTES = 256 * 1024  # 256 KB

# Absolute cap on any payload we will accept.  Anything larger is truncated.
ABSOLUTE_MAX_BYTES = 16 * 1024 * 1024  # 16 MB

# Absolute caps on rows/items for tabular/collection results.
ABSOLUTE_MAX_ROWS = 100_000
ABSOLUTE_MAX_ITEMS = 100_000

# Default preview size.
DEFAULT_PREVIEW_ROWS = 5
DEFAULT_PREVIEW_ITEMS = 5
DEFAULT_PREVIEW_CHARS = 500

# Read limits -----------------------------------------------------------------

HARD_MAX_ROWS = 100
HARD_MAX_BYTES = 32 * 1024  # 32 KB
HARD_MAX_TOKENS = 4_000
HARD_MAX_PAGE_SIZE = 100

# Retention -------------------------------------------------------------------

DEFAULT_RETENTION_DAYS = 30


def default_expires_on() -> datetime | None:
    """Return the default expiration timestamp for a new result."""
    return datetime.utcnow() + timedelta(days=DEFAULT_RETENTION_DAYS)


def coerce_read_limits(
    max_rows: int | None = None,
    max_bytes: int | None = None,
    max_tokens: int | None = None,
    page_size: int | None = None,
) -> dict:
    """Return client-requested limits capped by the hard server-side limits."""
    return {
        "max_rows": min(max_rows or HARD_MAX_ROWS, HARD_MAX_ROWS),
        "max_bytes": min(max_bytes or HARD_MAX_BYTES, HARD_MAX_BYTES),
        "max_tokens": min(max_tokens or HARD_MAX_TOKENS, HARD_MAX_TOKENS),
        "page_size": min(page_size or HARD_MAX_PAGE_SIZE, HARD_MAX_PAGE_SIZE),
    }


def expire_stale_results():
    """Daily cleanup: mark expired results and delete their private payload files."""
    import frappe

    expired = frappe.get_all(
        "Agent Execution Result",
        filters={"expires_on": ("<", frappe.utils.now()), "status": ("!=", "Expired")},
        fields=["name", "payload_file"],
    )

    for row in expired:
        if row.payload_file:
            try:
                file_doc = frappe.get_doc("File", {"file_url": row.payload_file})
                file_doc.delete(ignore_permissions=True)
            except Exception as e:
                frappe.logger("huf").warning(
                    f"Could not delete expired result file {row.payload_file}: {e!s}"
                )
        frappe.db.set_value("Agent Execution Result", row.name, "status", "Expired")

    frappe.db.commit()
