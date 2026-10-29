"""Short-lived secret stash: keeps credentials out of LLM context and run logs.

The UI (or an ``ask_user`` secret form) calls ``stash_secret`` with plaintext
values and receives an opaque ``credentials_ref``. Agent tools only ever see
the ref; ``resolve_and_consume`` swaps it for plaintext server-side, once.
"""

from __future__ import annotations

import contextvars
import json
import re
from contextlib import contextmanager
from datetime import timedelta
from typing import Any

import frappe
from frappe import _
from frappe.utils import now_datetime

STASH_TTL_MINUTES = 30
STASH_RATE_LIMIT_PER_HOUR = 20
MASK = "***REDACTED***"

# ---------------------------------------------------------------------------
# Agent tool-execution marker (set by the tool invocation paths, never by a caller arg)
# ---------------------------------------------------------------------------
_in_agent_tool_call: contextvars.ContextVar = contextvars.ContextVar("huf_in_agent_tool_call", default=False)


@contextmanager
def agent_tool_context():
	token = _in_agent_tool_call.set(True)
	try:
		yield
	finally:
		_in_agent_tool_call.reset(token)


def in_agent_tool_call() -> bool:
	return bool(_in_agent_tool_call.get())


# ---------------------------------------------------------------------------
# Stash
# ---------------------------------------------------------------------------
def _rate_limit(user: str) -> None:
	key = f"huf_secret_stash:{user}"
	cache = frappe.cache()
	count = int(cache.get_value(key) or 0) + 1
	cache.set_value(key, count, expires_in_sec=3600)
	if count > STASH_RATE_LIMIT_PER_HOUR:
		frappe.throw(_("Too many secret stashes; try again later."), frappe.TooManyRequestsError)


@frappe.whitelist()
def stash_secret(values, purpose: str, gateway: str | None = None) -> dict[str, Any]:
	"""Store secret values; return ``{"credentials_ref", "fields"}`` (never the values)."""
	from huf.permissions import has_capability

	user = frappe.session.user
	if not has_capability(user, "system.integrations.manage"):
		frappe.throw(_("Not permitted to stash integration secrets."), frappe.PermissionError)
	if isinstance(values, str):
		try:
			values = json.loads(values)
		except ValueError:
			frappe.throw(_("values must be a JSON object."))
	if not isinstance(values, dict) or not values:
		frappe.throw(_("values must be a non-empty object."))
	if not purpose:
		frappe.throw(_("purpose is required."))

	_rate_limit(user)

	doc = frappe.get_doc(
		{
			"doctype": "Huf Secret Stash",
			"purpose": purpose,
			"gateway": gateway or None,
			"expires_at": now_datetime() + timedelta(minutes=STASH_TTL_MINUTES),
			"consumed": 0,
			"field_names": ", ".join(str(k) for k in values),
			"secret_fields": [{"field_id": str(k), "value": str(v)} for k, v in values.items()],
		}
	)
	doc.insert()
	return {"credentials_ref": doc.name, "fields": [str(k) for k in values]}


def resolve_and_consume(ref: str, user: str | None = None) -> dict[str, str]:
	"""Return the stashed plaintext once. Raises on owner mismatch/expiry/reuse."""
	user = user or frappe.session.user
	if not ref or not frappe.db.exists("Huf Secret Stash", ref):
		frappe.throw(_("Unknown credentials_ref."), frappe.ValidationError)
	doc = frappe.get_doc("Huf Secret Stash", ref)
	if doc.owner != user:
		frappe.throw(_("credentials_ref does not belong to you."), frappe.PermissionError)
	if doc.consumed:
		frappe.throw(_("credentials_ref was already used."), frappe.ValidationError)
	if doc.expires_at and frappe.utils.get_datetime(doc.expires_at) < now_datetime():
		frappe.throw(_("credentials_ref has expired."), frappe.ValidationError)
	out = {row.field_id: row.get_password("value", raise_exception=False) or "" for row in doc.secret_fields}
	doc.db_set({"consumed": 1, "consumed_at": now_datetime()}, update_modified=False)
	return out


def purge_expired() -> None:
	"""Scheduler: delete expired or consumed stashes."""
	names = frappe.get_all(
		"Huf Secret Stash",
		or_filters=[["consumed", "=", 1], ["expires_at", "<", now_datetime()]],
		pluck="name",
	)
	for name in names:
		frappe.delete_doc("Huf Secret Stash", name, ignore_permissions=True, force=True)


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------
_TOKEN_RE = re.compile(r"EAA[A-Za-z0-9]{10,}")
_SECRET_KEY_RE = re.compile(r"(token|secret|password|app_secret|access_token|api_key)", re.I)


def redact(obj: Any) -> Any:
	"""Return a copy of ``obj`` with token shapes and secret-keyed values masked."""
	if isinstance(obj, str):
		return _TOKEN_RE.sub(MASK, obj)
	if isinstance(obj, dict):
		out = {}
		for k, v in obj.items():
			if isinstance(k, str) and _SECRET_KEY_RE.search(k) and isinstance(v, str) and len(v) >= 8:
				out[k] = MASK
			else:
				out[k] = redact(v)
		return out
	if isinstance(obj, (list, tuple)):
		return [redact(v) for v in obj]
	return obj


def redact_json_field(value: Any) -> Any:
	"""Redact a JSON-field value that may be a dict/list or a JSON/plain string."""
	if value is None or value == "":
		return value
	if isinstance(value, str):
		try:
			parsed = json.loads(value)
		except ValueError:
			return redact(value)
		return json.dumps(redact(parsed), default=str)
	return redact(value)
