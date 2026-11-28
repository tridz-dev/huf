"""Stored Frappe session rows: sid hashing and sessiondata parsing for Telegram web-access enforcement."""

import json
from typing import Any

import frappe


def _stored_sid(sid: str) -> str:
	"""``sid`` as keyed in ``tabSessions`` and the session cache (newer Frappe stores a hash of it)."""
	from frappe import sessions

	hasher = getattr(sessions, "hash_sid", None)
	return hasher(sid) if hasher else sid


def _session_row_data(raw: str | None) -> Any:
	"""Parse ``tabSessions.sessiondata``: JSON on newer Frappe, a Python repr on older."""
	try:
		return json.loads(raw or "{}")
	except ValueError:
		return frappe.safe_eval(raw)
