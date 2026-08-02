# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""Agent-callable tools for bounded result access.

These tools are registered in ``huf.ai.sdk_tools.create_agent_tools`` and are
the only way the model should read result payloads.  They enforce the same
hard limits as the UI API.
"""

import json

import frappe

from huf.ai.results.views import result_index_for_conversation, result_read


def result_read_tool(
    ref: str,
    view: str = "summary",
    selector: str | None = None,
    page: int | None = None,
    page_size: int | None = None,
    filter=None,
    columns: list | None = None,
    max_tokens: int | None = None,
    max_rows: int | None = None,
    max_bytes: int | None = None,
) -> dict:
    """Read a bounded view of a stored execution result.

    Args:
        ref: ``result://RES-00001`` or the result document name.
        view: one of ``summary`` (default), ``schema``, ``preview``, ``page``,
            ``range``, ``path``, ``filter``, ``row``.
        selector: optional range/path/row selector.
        page: 1-based page number for ``page`` view.
        page_size: requested page size (capped server-side).
        filter: dict of column-value filters for ``filter`` view.
        columns: list of columns to include for ``filter`` view.
        max_tokens: requested token cap (capped server-side).
        max_rows: requested row cap (capped server-side).
        max_bytes: requested byte cap (capped server-side).
    """
    try:
        return result_read(
            ref=ref,
            view=view,
            selector=selector,
            page=page,
            page_size=page_size,
            filter=filter,
            columns=columns,
            max_tokens=max_tokens,
            max_rows=max_rows,
            max_bytes=max_bytes,
        )
    except frappe.PermissionError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        frappe.logger("huf").warning(f"result_read_tool failed: {e!s}\n{frappe.get_traceback()}")
        return {"status": "error", "error": str(e)}


def result_index_tool(conversation_id: str) -> dict:
    """Return a compact index of results for the current conversation."""
    try:
        if not conversation_id:
            return {"status": "error", "error": "conversation_id is required."}
        conversation = frappe.get_doc("Agent Conversation", conversation_id)
        if not frappe.has_permission("Agent Conversation", "read", doc=conversation):
            return {"status": "error", "error": "Not permitted to read this conversation."}
        return result_index_for_conversation(conversation_id)
    except frappe.PermissionError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        frappe.logger("huf").warning(f"result_index_tool failed: {e!s}\n{frappe.get_traceback()}")
        return {"status": "error", "error": str(e)}
