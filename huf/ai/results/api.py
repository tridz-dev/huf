# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""Whitelisted REST API for result reads.

The UI can call these endpoints the same way it calls
``agentContextArtifactApi.ts`` endpoints.  They enforce DocType permissions
and the same hard limits as the agent tools.
"""

import json

import frappe
from frappe import _

from huf.ai.results.views import result_index_for_conversation, result_read as _result_read_view


@frappe.whitelist()
def result_read(
    result_name: str,
    view: str = "summary",
    selector: str | None = None,
    page: int | None = None,
    page_size: int | None = None,
    filter=None,
    columns: str | list | None = None,
    max_tokens: int | None = None,
    max_rows: int | None = None,
    max_bytes: int | None = None,
):
    """Whitelisted bounded read of an ``Agent Execution Result``."""
    result_doc = frappe.get_doc("Agent Execution Result", result_name)
    if not frappe.has_permission("Agent Execution Result", "read", doc=result_doc):
        frappe.throw(
            _("Not permitted to read Agent Execution Result {0}").format(result_name),
            frappe.PermissionError,
        )

    if isinstance(columns, str):
        try:
            columns = json.loads(columns)
        except (json.JSONDecodeError, TypeError):
            columns = [c.strip() for c in columns.split(",") if c.strip()]

    if isinstance(filter, str):
        try:
            filter = json.loads(filter)
        except (json.JSONDecodeError, TypeError):
            filter = {}

    return _result_read_view(
        ref=result_name,
        view=view,
        selector=selector,
        page=int(page) if page is not None else None,
        page_size=int(page_size) if page_size is not None else None,
        filter=filter,
        columns=columns,
        max_tokens=int(max_tokens) if max_tokens is not None else None,
        max_rows=int(max_rows) if max_rows is not None else None,
        max_bytes=int(max_bytes) if max_bytes is not None else None,
    )


@frappe.whitelist()
def result_index(conversation_id: str):
    """Whitelisted compact index of results for a conversation."""
    conversation = frappe.get_doc("Agent Conversation", conversation_id)
    if not frappe.has_permission("Agent Conversation", "read", doc=conversation):
        frappe.throw(
            _("Not permitted to read conversation {0}").format(conversation_id),
            frappe.PermissionError,
        )
    return result_index_for_conversation(conversation_id)
