# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""Shared helpers for whitelisted endpoints (Backend API standard, WP E).

Location: ``huf/ai/`` is where the feature packages and the shared cross-feature modules
(``permissions_api``, ``http_handler``...) already live; ``huf/utils.py`` is a flat grab-bag and
``huf/api/v1`` is reserved for the public versioned contract, so neither fits.

The standard
------------
* Placement: desk/SPA endpoints live in ``huf/ai/<feature>/api.py`` (legacy ones stay where they
  are until migrated). Webhooks live in ``huf/ai/<feature>/webhooks.py``. The public versioned
  API lives only in ``huf/api/v1``.
* Permission check FIRST: the first statement of a whitelisted function checks authority
  (``require_permission``, ``frappe.has_permission``, ``frappe.only_for``, a ``_can_manage_*``
  helper...) before any read, write or parsing of data.
* Errors: new endpoints either raise (``frappe.throw``/``frappe.PermissionError``, via
  ``require_permission``/``parse_json_arg``) or return the contract shape from ``api_error``,
  ``{"error": {"code", "message"}}``. Never ``{"success": False}`` in new code. Success returns
  the plain payload (there is no ``api_ok`` wrapper).
* Arguments: JSON-string arguments are parsed with ``parse_json_arg``, not by hand.
* Lists: take ``start``/``limit`` and return ``{"items", "total", "start", "limit"}`` via ``paginate``.
* Guest endpoints (``allow_guest=True``) verify a signature/token before doing any work.
* Mutating endpoints are POST (``methods=["POST"]``).

``scripts/check_whitelist.py`` enforces the permission, guest and POST rules against a baseline.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Iterable

import frappe
from frappe import _

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


def api_error(code: str, message: str = "", **extra: Any) -> dict[str, Any]:
	"""The contract error shape ``{"error": {"code", "message"}}``; extra keys go inside ``error``."""
	error: dict[str, Any] = {"code": code, "message": message}
	error.update(extra)
	return {"error": error}


def parse_json_arg(value: Any, default: Any = None, expected: type | tuple[type, ...] | None = None) -> Any:
	"""Return a Python value from a dict/list or a JSON string argument.

	``None`` and blank strings give ``default``. ``expected`` (``dict``, ``list`` or a tuple of
	types) is checked against the result. Anything unparsable or of the wrong type raises
	``frappe.ValidationError``.
	"""
	if value is None or (isinstance(value, str) and not value.strip()):
		return default
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except (TypeError, ValueError):
			frappe.throw(_("Invalid JSON argument"), frappe.ValidationError)
		if value is None:
			return default
	if expected is not None and not isinstance(value, expected):
		names = expected if isinstance(expected, tuple) else (expected,)
		frappe.throw(
			_("Expected {0} argument").format(" or ".join(t.__name__ for t in names)),
			frappe.ValidationError,
		)
	return value


def _clamp(value: Any, low: int, high: int | None, fallback: int) -> int:
	try:
		number = int(value)
	except (TypeError, ValueError):
		number = fallback
	number = max(number, low)
	return min(number, high) if high is not None else number


def paginate(
	rows_or_query: Iterable[Any] | dict[str, Any],
	start: Any = 0,
	limit: Any = DEFAULT_LIMIT,
	max_limit: int = MAX_LIMIT,
) -> dict[str, Any]:
	"""Page a list endpoint's result as ``{"items", "total", "start", "limit"}``.

	``limit`` is clamped to ``1..max_limit`` and ``start`` to ``>= 0``. ``rows_or_query`` is
	either a sequence (sliced in memory) or a dict of ``frappe.get_list`` arguments (``doctype``
	plus ``filters``/``fields``/``order_by``...), which applies user permissions and counts the
	total with the same filters.
	"""
	start = _clamp(start, 0, None, 0)
	limit = _clamp(limit, 1, max_limit, min(DEFAULT_LIMIT, max_limit))
	if isinstance(rows_or_query, dict):
		query = dict(rows_or_query)
		doctype = query.pop("doctype")
		filters = query.get("filters")
		items = frappe.get_list(doctype, limit_start=start, limit_page_length=limit, **query)
		counted = frappe.get_list(
			doctype,
			filters=filters,
			or_filters=query.get("or_filters"),
			fields=["count(name) as total"],
			order_by=None,
		)
		total = int(counted[0]["total"]) if counted else 0
	else:
		rows = rows_or_query if isinstance(rows_or_query, (list, tuple)) else list(rows_or_query)
		total = len(rows)
		items = list(rows[start : start + limit])
	return {"items": items, "total": total, "start": start, "limit": limit}


def require_permission(check: bool | Callable[[], Any], message: str = "Not permitted") -> None:
	"""Raise ``frappe.PermissionError`` unless ``check`` (a value or a no-arg callable) is truthy.

	Usage: ``require_permission(frappe.has_permission("Agent", "write"), "Not permitted to edit agents")``.
	"""
	allowed = check() if callable(check) else check
	if not allowed:
		raise frappe.PermissionError(_(message))
