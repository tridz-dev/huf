# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""Bounded result reads.

Every view enforces server-side byte/row/token limits regardless of what the
caller (model or UI) requests.
"""

import json
import re
from typing import Any

import frappe

from huf.ai.results import policy
from huf.ai.results.envelope import build_envelope, build_error_envelope
from huf.ai.results.permissions import require_result_read_permission
from huf.ai.results.store import load_payload
from huf.ai.results.tokens import estimate_tokens


VIEWS = {"summary", "schema", "preview", "page", "range", "path", "filter", "row"}


def _resolve_result_doc(ref) -> "frappe.Document":
    """Load an ``Agent Execution Result`` from a ref string, name, or doc."""
    if hasattr(ref, "doctype") and ref.doctype == "Agent Execution Result":
        return ref

    name = ref
    if isinstance(name, str) and name.startswith("result://"):
        name = name[len("result://") :]
    return frappe.get_doc("Agent Execution Result", name)


def _parse_json_payload(data: bytes, result_type: str):
    """Parse payload bytes into a Python object when possible."""
    text = data.decode("utf-8", errors="replace")
    if result_type in ("json", "table", "collection"):
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            pass
    return text


def _token_cap_trim(value: Any, max_tokens: int) -> Any:
    """Return ``value`` trimmed so its JSON representation is under ``max_tokens``."""
    if max_tokens <= 0:
        return value
    text = json.dumps(value, default=str)
    if estimate_tokens(text) <= max_tokens:
        return value
    # Trim by characters (heuristic: 1 token ≈ 4 chars).
    max_chars = max_tokens * 4
    trimmed_text = text[:max_chars]
    # Try to keep valid JSON by trimming at the last safe boundary.
    try:
        return json.loads(trimmed_text)
    except (json.JSONDecodeError, TypeError):
        return trimmed_text


def _bytes_cap_trim(value: Any, max_bytes: int) -> Any:
    """Return ``value`` trimmed so its UTF-8 JSON representation is under ``max_bytes``."""
    if max_bytes <= 0:
        return value
    text = json.dumps(value, default=str)
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    trimmed = encoded[:max_bytes].decode("utf-8", errors="ignore")
    try:
        return json.loads(trimmed)
    except (json.JSONDecodeError, TypeError):
        return trimmed


def _apply_output_limits(value: Any, max_tokens: int, max_bytes: int) -> Any:
    """Apply token and byte caps to a view result."""
    value = _bytes_cap_trim(value, max_bytes)
    value = _token_cap_trim(value, max_tokens)
    return value


def _view_summary(result_doc, limits: dict) -> dict:
    """Return the bounded envelope itself as the summary view."""
    envelope = build_envelope(result_doc)
    return _apply_output_limits(envelope, limits["max_tokens"], limits["max_bytes"])


def _view_schema(result_doc, limits: dict) -> dict:
    schema = json.loads(result_doc.schema_json) if result_doc.schema_json else {}
    return _apply_output_limits(
        {"result_ref": f"result://{result_doc.name}", "schema": schema},
        limits["max_tokens"],
        limits["max_bytes"],
    )


def _view_preview(result_doc, limits: dict) -> dict:
    preview = json.loads(result_doc.preview_json) if result_doc.preview_json else {}
    return _apply_output_limits(
        {"result_ref": f"result://{result_doc.name}", "preview": preview},
        limits["max_tokens"],
        limits["max_bytes"],
    )


def _view_page(result_doc, limits: dict, page: int | None, page_size: int | None) -> dict:
    page = max(1, page or 1)
    page_size = limits["page_size"]
    start = (page - 1) * page_size
    end = start + page_size

    data = load_payload(result_doc)
    parsed = _parse_json_payload(data, result_doc.result_type or "text")

    if isinstance(parsed, list):
        rows = parsed[start:end]
        total = len(parsed)
    elif isinstance(parsed, str):
        lines = parsed.splitlines()
        rows = lines[start:end]
        total = len(lines)
    else:
        rows = []
        total = 0

    result = {
        "result_ref": f"result://{result_doc.name}",
        "view": "page",
        "page": page,
        "page_size": page_size,
        "total": total,
        "rows": rows,
    }
    return _apply_output_limits(result, limits["max_tokens"], limits["max_bytes"])


def _view_range(result_doc, limits: dict, selector: str | None) -> dict:
    data = load_payload(result_doc)
    parsed = _parse_json_payload(data, result_doc.result_type or "text")

    rows = []
    total = 0
    if isinstance(parsed, list):
        total = len(parsed)
        start, end = _parse_range_selector(selector, total)
        rows = parsed[start:end]
    elif isinstance(parsed, str):
        lines = parsed.splitlines()
        total = len(lines)
        start, end = _parse_range_selector(selector, total)
        rows = lines[start:end]

    result = {
        "result_ref": f"result://{result_doc.name}",
        "view": "range",
        "selector": selector,
        "total": total,
        "start": start,
        "end": end,
        "rows": rows,
    }
    # Also cap by max_rows.
    if isinstance(rows, list) and len(rows) > limits["max_rows"]:
        result["rows"] = rows[: limits["max_rows"]]
        result["truncated"] = True
    return _apply_output_limits(result, limits["max_tokens"], limits["max_bytes"])


def _parse_range_selector(selector: str | None, total: int) -> tuple[int, int]:
    """Parse selectors like ``rows[10:20]``, ``10:20``, or ``[5:15]``."""
    if not selector:
        return 0, min(policy.HARD_MAX_ROWS, total)

    match = re.search(r"(\d*):(\d*)", selector)
    if not match:
        return 0, min(policy.HARD_MAX_ROWS, total)

    start_str, end_str = match.groups()
    start = int(start_str) if start_str else 0
    end = int(end_str) if end_str else total
    start = max(0, min(start, total))
    end = max(start, min(end, total))
    return start, end


def _view_path(result_doc, limits: dict, selector: str | None) -> dict:
    """Return a JSON-path slice of the result.

    Supported selectors:
    - ``orders[0:20].items`` — slice a list then pick a key.
    - ``orders[5]`` — single item.
    - ``meta.title`` — dotted key path.
    """
    data = load_payload(result_doc)
    parsed = _parse_json_payload(data, result_doc.result_type or "json")
    if not isinstance(parsed, (dict, list)):
        return {
            "result_ref": f"result://{result_doc.name}",
            "view": "path",
            "selector": selector,
            "error": "path view requires a JSON object or list",
        }

    value = parsed
    tokens = _tokenize_selector(selector or "")
    for token in tokens:
        if isinstance(value, dict):
            value = value.get(token)
        elif isinstance(value, list):
            try:
                value = value[int(token)]
            except (ValueError, IndexError):
                value = None
        else:
            value = None
        if value is None:
            break

    result = {
        "result_ref": f"result://{result_doc.name}",
        "view": "path",
        "selector": selector,
        "value": value,
    }
    return _apply_output_limits(result, limits["max_tokens"], limits["max_bytes"])


def _tokenize_selector(selector: str) -> list[str]:
    """Tokenize a path selector into keys and indices."""
    if not selector:
        return []
    # Normalize bracket notation to dotted notation.
    normalized = selector.replace("[", ".").replace("]", "")
    return [t for t in normalized.split(".") if t != ""]


def _view_filter(result_doc, limits: dict, filter_spec, columns: list | None) -> dict:
    data = load_payload(result_doc)
    parsed = _parse_json_payload(data, result_doc.result_type or "text")

    if not isinstance(parsed, list):
        return {
            "result_ref": f"result://{result_doc.name}",
            "view": "filter",
            "error": "filter view requires a list result",
        }

    filter_spec = filter_spec or {}
    if isinstance(filter_spec, str):
        try:
            filter_spec = json.loads(filter_spec)
        except (json.JSONDecodeError, TypeError):
            filter_spec = {}

    rows = []
    for row in parsed:
        match = True
        for key, expected in filter_spec.items():
            value = row.get(key) if isinstance(row, dict) else None
            if value != expected:
                match = False
                break
        if match:
            rows.append(row)
            if len(rows) >= limits["max_rows"]:
                break

    if columns and rows:
        rows = [
            {k: row.get(k) for k in columns if k in row}
            if isinstance(row, dict)
            else row
            for row in rows
        ]

    result = {
        "result_ref": f"result://{result_doc.name}",
        "view": "filter",
        "filter": filter_spec,
        "matched": len(rows),
        "rows": rows,
    }
    return _apply_output_limits(result, limits["max_tokens"], limits["max_bytes"])


def _view_row(result_doc, limits: dict, selector: str | None) -> dict:
    data = load_payload(result_doc)
    parsed = _parse_json_payload(data, result_doc.result_type or "text")

    if not isinstance(parsed, list):
        return {
            "result_ref": f"result://{result_doc.name}",
            "view": "row",
            "error": "row view requires a list result",
        }

    indices = []
    if selector:
        for part in selector.split(","):
            part = part.strip()
            if "-" in part:
                try:
                    a, b = part.split("-", 1)
                    indices.extend(range(int(a), int(b) + 1))
                except ValueError:
                    pass
            else:
                try:
                    indices.append(int(part))
                except ValueError:
                    pass
    if not indices:
        indices = [0]

    indices = [i for i in indices if 0 <= i < len(parsed)][: limits["max_rows"]]
    rows = [parsed[i] for i in indices]

    result = {
        "result_ref": f"result://{result_doc.name}",
        "view": "row",
        "indices": indices,
        "rows": rows,
    }
    return _apply_output_limits(result, limits["max_tokens"], limits["max_bytes"])


def result_read(
    ref,
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
    """Read a bounded view of an ``Agent Execution Result``.

    All ``max_*`` client requests are capped by hard server-side limits.
    """
    if view not in VIEWS:
        return {"status": "error", "error": f"Unknown view '{view}'. Use one of: {sorted(VIEWS)}"}

    result_doc = _resolve_result_doc(ref)
    require_result_read_permission(result_doc)

    if result_doc.status == "Expired":
        return build_error_envelope(result_doc, "Result has expired.")

    limits = policy.coerce_read_limits(
        max_rows=max_rows,
        max_bytes=max_bytes,
        max_tokens=max_tokens,
        page_size=page_size,
    )

    if view == "summary":
        return _view_summary(result_doc, limits)
    if view == "schema":
        return _view_schema(result_doc, limits)
    if view == "preview":
        return _view_preview(result_doc, limits)
    if view == "page":
        return _view_page(result_doc, limits, page, page_size)
    if view == "range":
        return _view_range(result_doc, limits, selector)
    if view == "path":
        return _view_path(result_doc, limits, selector)
    if view == "filter":
        return _view_filter(result_doc, limits, filter, columns)
    if view == "row":
        return _view_row(result_doc, limits, selector)

    return {"status": "error", "error": f"View '{view}' is not implemented."}


def result_index_for_conversation(conversation_id: str) -> dict:
    """Return a compact index of results for ``conversation_id``."""
    if not frappe.db.exists("Agent Conversation", conversation_id):
        return {"status": "error", "error": "Conversation not found."}

    results = frappe.get_all(
        "Agent Execution Result",
        filters={"conversation": conversation_id},
        fields=[
            "name",
            "result_type",
            "summary",
            "source_tool",
            "size_bytes",
            "estimated_tokens",
            "available_views",
            "status",
        ],
        order_by="creation desc",
    )

    items = []
    for r in results:
        available_views = json.loads(r.available_views) if r.available_views else []
        items.append(
            {
                "ref": f"result://{r.name}",
                "type": r.result_type,
                "summary": r.summary,
                "source_tool": r.source_tool,
                "size": {
                    "bytes": r.size_bytes,
                    "estimated_tokens": r.estimated_tokens,
                },
                "available_views": available_views,
                "status": r.status,
            }
        )

    return {"status": "success", "conversation_id": conversation_id, "results": items}
