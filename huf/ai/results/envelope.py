# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""Bounded result envelopes.

Envelopes are the only representation of a result that enters model context.
They never contain the full raw payload.
"""

import json

import frappe


def _safe_load_json(value: str | None) -> dict | list | None:
    """Parse a JSON field value, returning ``None`` on failure."""
    if not value:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def build_envelope(result_doc, status: str = "success") -> dict:
    """Return a bounded envelope for ``result_doc``.

    The envelope contains metadata, schema, preview, size, available views,
    and source lineage.  It deliberately excludes the raw payload.
    """
    schema = _safe_load_json(result_doc.schema_json)
    preview = _safe_load_json(result_doc.preview_json)
    available_views = _safe_load_json(result_doc.available_views) or []

    size = {
        "bytes": result_doc.size_bytes or 0,
        "estimated_tokens": result_doc.estimated_tokens or 0,
    }
    if isinstance(schema, dict) and "row_count" in schema:
        size["rows"] = schema["row_count"]
    if isinstance(schema, dict) and "item_count" in schema:
        size["items"] = schema["item_count"]

    return {
        "status": status,
        "result_ref": f"result://{result_doc.name}",
        "result_type": result_doc.result_type or "text",
        "summary": result_doc.summary or "",
        "schema": schema,
        "preview": preview,
        "size": size,
        "available_views": available_views,
        "source": {
            "run_id": result_doc.agent_run,
            "tool_call_id": result_doc.tool_call,
            "source_tool": result_doc.source_tool,
        },
    }


def build_error_envelope(result_doc, error: str) -> dict:
    """Return an envelope for a failed or expired result read."""
    envelope = build_envelope(result_doc, status="error")
    envelope["error"] = error
    return envelope
