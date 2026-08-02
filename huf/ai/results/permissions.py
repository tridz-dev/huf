# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""Permission helpers for ``Agent Execution Result``.

Role permissions mirror ``Agent Tool Call`` (System Manager all; Huf Manager
and Huf User create/read/write).  This module adds conversation ownership and
participant scoping on top of those role permissions.
"""

import frappe
from frappe import _


def _is_conversation_participant(conversation_name: str) -> bool:
    """Return True if the current user owns or participates in the conversation."""
    if not conversation_name:
        return False

    user = frappe.session.user
    if user == "Administrator":
        return True

    conv = frappe.db.get_value(
        "Agent Conversation",
        conversation_name,
        ["owner", "session_id"],
        as_dict=True,
    )
    if not conv:
        return False

    if conv.owner == user:
        return True

    # Anyone who has already written an Agent Message in this conversation is a
    # participant.  This covers assistant/tool messages as well as multi-user
    # conversations.
    participant = frappe.db.exists(
        "Agent Message",
        {"conversation": conversation_name, "owner": ("!=", "Administrator"), "owner": user},
    )
    if participant:
        return True

    return False


def can_read_result(result_doc) -> bool:
    """Return True if the current user may read ``result_doc``."""
    if not result_doc:
        return False

    if frappe.has_permission("Agent Execution Result", "read", doc=result_doc):
        return True

    # Role permission denied; still allow conversation participants to read
    # results attached to their own conversations.
    return _is_conversation_participant(result_doc.conversation)


def can_write_result(result_doc) -> bool:
    """Return True if the current user may write ``result_doc``."""
    if not result_doc:
        return False

    if frappe.has_permission("Agent Execution Result", "write", doc=result_doc):
        return True

    return _is_conversation_participant(result_doc.conversation)


def require_result_read_permission(result_doc):
    """Throw ``PermissionError`` if the current user cannot read the result."""
    if not can_read_result(result_doc):
        frappe.throw(
            _("Not permitted to read Agent Execution Result {0}").format(result_doc.name),
            frappe.PermissionError,
        )


def require_result_write_permission(result_doc):
    """Throw ``PermissionError`` if the current user cannot write the result."""
    if not can_write_result(result_doc):
        frappe.throw(
            _("Not permitted to write Agent Execution Result {0}").format(result_doc.name),
            frappe.PermissionError,
        )
