# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""Durable storage for tool/API execution results.

This module owns result-size classification, schema/preview generation,
checksum computation, private-file storage, and idempotent writes.  Callers
should route every tool result through :func:`persist_result` and use the
bounded envelope it returns; they must not re-implement size classification.
"""

import hashlib
import json
import os
from typing import Any

import frappe
from frappe.utils.file_manager import save_file
from frappe.utils import get_site_path

from huf.ai.results import policy
from huf.ai.results.tokens import estimate_tokens
from huf.ai.results.envelope import build_envelope


def _normalize_payload(value: Any) -> tuple[str | bytes, int]:
    """Return ``(normalized, is_binary)`` for ``value``.

    Strings and UTF-8-decodable bytes are treated as text.  Other bytes are
    kept as binary and classified as ``file`` results.
    """
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8"), False
        except UnicodeDecodeError:
            return value, True
    if isinstance(value, str):
        return value, False
    return json.dumps(value, default=str), False


def _classify_result_type(text: str | bytes, parsed: Any | None) -> str:
    """Return one of the ``Agent Execution Result`` result_type values."""
    if isinstance(text, bytes):
        return "file"
    if isinstance(parsed, list):
        if parsed and all(isinstance(r, dict) for r in parsed):
            return "table"
        return "collection"
    if isinstance(parsed, dict):
        return "json"
    return "text"


def _build_schema(result_type: str, parsed: Any, text: str | bytes) -> dict:
    """Build structural metadata for the result."""
    if result_type == "table" and isinstance(parsed, list) and parsed:
        first = parsed[0]
        if isinstance(first, dict):
            columns = list(first.keys())
            return {"columns": columns, "row_count": len(parsed)}
        if isinstance(first, list):
            return {"columns": len(first), "row_count": len(parsed)}
    if result_type == "collection" and isinstance(parsed, list):
        return {"item_count": len(parsed)}
    if result_type == "json" and isinstance(parsed, dict):
        return {"keys": list(parsed.keys())}
    if result_type == "text":
        return {"chars": len(text)}
    if result_type == "file":
        return {"binary": True, "bytes": len(text)}
    return {}


def _build_preview(
    result_type: str,
    parsed: Any,
    text: str | bytes,
    max_rows: int = policy.DEFAULT_PREVIEW_ROWS,
    max_items: int = policy.DEFAULT_PREVIEW_ITEMS,
    max_chars: int = policy.DEFAULT_PREVIEW_CHARS,
) -> dict:
    """Build a bounded preview of the result."""
    if result_type == "table" and isinstance(parsed, list):
        rows = parsed[:max_rows]
        return {"rows": rows, "truncated": len(parsed) > max_rows}
    if result_type == "collection" and isinstance(parsed, list):
        items = parsed[:max_items]
        return {"items": items, "truncated": len(parsed) > max_items}
    if result_type == "json" and isinstance(parsed, dict):
        preview = {}
        for key in list(parsed.keys())[:max_items]:
            value = parsed[key]
            if isinstance(value, (dict, list)):
                preview[key] = f"<{type(value).__name__}: {len(value)} items>"
            else:
                preview[key] = value
        return {"keys": list(preview.keys()), "sample": preview}
    if isinstance(text, bytes):
        return {"bytes": len(text), "note": "binary payload stored as private file"}
    return {"text": text[:max_chars], "truncated": len(text) > max_chars}


def _compute_hash(data: bytes) -> str:
    """Return ``sha256:<hex>`` for ``data``."""
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _available_views(result_type: str, size_bytes: int) -> list[str]:
    """Return the views advertised for this result."""
    base = ["summary", "schema", "preview"]
    if size_bytes <= policy.SCHEMA_ONLY_THRESHOLD_BYTES:
        if result_type in ("table", "collection"):
            base.extend(["page", "range", "filter", "row"])
        elif result_type in ("json", "text"):
            base.extend(["page", "range", "path"])
        elif result_type == "file":
            base.extend(["range", "row"])
    return base


def _build_summary(result_type: str, parsed: Any, text: str | bytes, size_bytes: int) -> str:
    """Build a human/model-readable summary."""
    if result_type == "table" and isinstance(parsed, list):
        return f"Table result with {len(parsed)} rows and {len(parsed[0]) if parsed else 0} columns ({size_bytes} bytes)"
    if result_type == "collection" and isinstance(parsed, list):
        return f"Collection with {len(parsed)} items ({size_bytes} bytes)"
    if result_type == "json" and isinstance(parsed, dict):
        return f"JSON object with {len(parsed)} keys ({size_bytes} bytes)"
    if result_type == "file":
        return f"Binary file ({size_bytes} bytes)"
    chars = len(text) if isinstance(text, str) else size_bytes
    return f"Text result ({chars} characters, {size_bytes} bytes)"


def _find_existing_result(
    idempotency_key: str | None,
    tool_call: str,
    run: str,
) -> "frappe.Document | None":
    """Return an existing result when an idempotency key matches."""
    if not idempotency_key:
        return None
    name = frappe.db.get_value(
        "Agent Execution Result",
        {
            "idempotency_key": idempotency_key,
            "tool_call": tool_call,
            "agent_run": run,
        },
        "name",
    )
    if name:
        return frappe.get_doc("Agent Execution Result", name)
    return None


def _save_payload_file(result_doc, data: bytes, filename: str) -> str:
    """Save ``data`` as a private file attached to ``result_doc``.

    Files are stored as private files with a ``result_`` prefix for
    organization.  Returns the ``file_url`` stored in ``payload_file``.
    """
    target_name = f"result_{result_doc.name}_{filename}"

    saved = save_file(
        target_name,
        data,
        "Agent Execution Result",
        result_doc.name,
        is_private=True,
    )
    file_url = getattr(saved, "file_url", None) or (
        saved.get("file_url") if isinstance(saved, dict) else None
    )
    if not file_url:
        raise ValueError(f"save_file returned no file_url for result {result_doc.name}")
    return file_url


def _load_payload_file(file_url: str) -> bytes:
    """Load raw bytes from a private payload file."""
    file_doc = frappe.get_doc(
        "File",
        {"file_url": file_url},
    )
    with open(file_doc.get_full_path(), "rb") as fh:
        return fh.read()


def persist_result(
    result_content: Any,
    run: str,
    tool_call: str,
    conversation: str,
    source_tool: str | None = None,
    visibility: str = "model_visible",
    idempotency_key: str | None = None,
    expires_on=None,
    agent_doc=None,
    status: str = "Completed",
) -> tuple["frappe.Document", dict]:
    """Persist ``result_content`` and return ``(result_doc, envelope)``.

    Args:
        result_content: the raw tool/API output.
        run: ``Agent Run`` name.
        tool_call: ``Agent Tool Call`` name.
        conversation: ``Agent Conversation`` name.
        source_tool: denormalized tool name for indexing.
        visibility: one of the visibility select values.
        idempotency_key: optional retry-deduplication key.
        expires_on: optional retention timestamp.
        agent_doc: optional Agent document (used only for backward-compatible
            ``max_context_chars`` logging; classification is owned here).
        status: ``Completed`` or ``Failed``.

    Returns:
        A tuple of ``(Agent Execution Result document, bounded envelope dict)``.
    """
    if not run or not tool_call or not conversation:
        raise ValueError("run, tool_call, and conversation are required")

    existing = _find_existing_result(idempotency_key, tool_call, run)
    if existing:
        return existing, build_envelope(existing)

    # Normalize payload ------------------------------------------------------
    text, is_binary = _normalize_payload(result_content)
    if is_binary:
        raw_bytes = text if isinstance(text, bytes) else text.encode("utf-8", errors="replace")
    else:
        raw_bytes = text.encode("utf-8") if isinstance(text, str) else b""

    # Enforce absolute size cap
    original_size = len(raw_bytes)
    truncated = False
    if original_size > policy.ABSOLUTE_MAX_BYTES:
        raw_bytes = raw_bytes[: policy.ABSOLUTE_MAX_BYTES]
        truncated = True
        frappe.log_error(
            f"Result for tool_call={tool_call} truncated from {original_size} to "
            f"{policy.ABSOLUTE_MAX_BYTES} bytes",
            "Result Store Size Limit",
        )

    size_bytes = len(raw_bytes)
    estimated_tokens = estimate_tokens(raw_bytes)

    # Parse structured payloads
    parsed = None
    if not is_binary:
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            parsed = text

    result_type = _classify_result_type(text, parsed)
    schema = _build_schema(result_type, parsed, text)
    preview = _build_preview(result_type, parsed, text)
    summary = _build_summary(result_type, parsed, text, size_bytes)
    if truncated:
        summary = f"{summary} [truncated to {policy.ABSOLUTE_MAX_BYTES} bytes]"

    # Size classification ----------------------------------------------------
    inline_payload = None
    payload_file = None
    if size_bytes <= policy.INLINE_THRESHOLD_BYTES and not is_binary:
        inline_payload = parsed if parsed is not None else text
    else:
        # Large or binary: always stored as a private file.
        payload_file = "__pending__"

    available_views = _available_views(result_type, size_bytes)

    doc = frappe.get_doc(
        {
            "doctype": "Agent Execution Result",
            "conversation": conversation,
            "agent_run": run,
            "tool_call": tool_call,
            "source_tool": source_tool,
            "status": status,
            "result_type": result_type,
            "summary": summary,
            "schema_json": json.dumps(schema, default=str),
            "preview_json": json.dumps(preview, default=str),
            "inline_payload": json.dumps(inline_payload, default=str) if inline_payload is not None else None,
            "payload_file": payload_file,
            "content_hash": _compute_hash(raw_bytes),
            "size_bytes": size_bytes,
            "estimated_tokens": estimated_tokens,
            "available_views": json.dumps(available_views),
            "expires_on": expires_on,
            "visibility": visibility,
            "idempotency_key": idempotency_key,
        }
    )
    doc.insert(ignore_permissions=True)

    if payload_file == "__pending__":
        filename = "payload.bin" if is_binary else "payload.json"
        file_url = _save_payload_file(doc, raw_bytes, filename)
        doc.payload_file = file_url
        doc.save(ignore_permissions=True)

    return doc, build_envelope(doc)


def load_payload(result_doc) -> bytes:
    """Load the raw payload bytes for ``result_doc``.

    Raises ``ValueError`` if the payload is missing or cannot be loaded.
    """
    if result_doc.inline_payload:
        try:
            parsed = json.loads(result_doc.inline_payload)
        except (json.JSONDecodeError, TypeError):
            parsed = result_doc.inline_payload
        text = json.dumps(parsed, default=str) if not isinstance(parsed, str) else parsed
        return text.encode("utf-8")

    if result_doc.payload_file:
        return _load_payload_file(result_doc.payload_file)

    raise ValueError(f"Agent Execution Result {result_doc.name} has no payload")
