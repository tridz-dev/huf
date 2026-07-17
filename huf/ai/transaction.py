"""
huf/ai/transaction.py

Centralized transaction management for the HUF platform.
This module abstracts explicit commits required for background workers,
long-running jobs, and UI progress tracking, ensuring we don't interfere
with Frappe's standard request lifecycle.
"""

import frappe


def safe_commit():
    """
    Safely commit, ignoring _realtime_log errors which occur in certain contexts.
    Replaces scattered try/except blocks.
    """
    if getattr(frappe.local, "_realtime_log", None) is None:
        frappe.local._realtime_log = []
    try:
        frappe.db.commit()
    except AttributeError as e:
        if "_realtime_log" in str(e):
            pass
        else:
            raise


def commit_if_background():
    """
    Commit only when Frappe's automatic transaction management is unavailable.
    Required for code that executes in both HTTP Requests (where frappe auto-commits)
    and Background Workers (which require explicit commits).
    """
    if not getattr(frappe.local, "request", None):
        safe_commit()


def transaction_checkpoint(reason: str):
    """
    Force a commit to persist intermediate state for long-running operations.
    Used ONLY when UI polling, progress tracking, or worker recovery
    depend on the committed state (e.g., Agent Streaming, Flow Engine nodes).
    """
    # Documenting the reason helps future audits
    safe_commit()
