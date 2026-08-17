"""Indexes supporting the pinned-chats list query (Conversation Pin)."""

import frappe


def _add_index(doctype, fields, name):
    try:
        frappe.db.add_index(doctype, fields, name)
    except Exception as error:
        # A previously deployed/manual index must not make migrate fail.
        if "Duplicate key name" not in str(error):
            raise


def execute():
    if frappe.db.has_column("Conversation Pin", "pinned_at"):
        _add_index("Conversation Pin", ["user", "pinned_at"], "idx_conversation_pin_user_pinned_at")
