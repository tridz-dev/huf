"""Canonical-args hashing and timestamp helpers for tool confirmations."""

from __future__ import annotations

import hashlib
import hmac
import json

from frappe.utils import get_datetime, get_system_timezone

_TRANSIENT_ARGS = ("ignore_permissions",)


def canonical_args(args: dict | None) -> dict:
	out = dict(args or {})
	for k in _TRANSIENT_ARGS:
		out.pop(k, None)
	return out


def _hmac_key() -> bytes:
	from frappe.utils.password import get_encryption_key

	return str(get_encryption_key()).encode()


def args_hash(args: dict | None) -> str:
	"""HMAC-SHA256 (site encryption key) of the canonical args: a DB-only writer cannot forge a matching hash."""
	blob = json.dumps(canonical_args(args), sort_keys=True, separators=(",", ":"), default=str)
	return hmac.new(_hmac_key(), blob.encode(), hashlib.sha256).hexdigest()


def verify_args_hash(args: dict | None, expected: str) -> bool:
	return hmac.compare_digest(args_hash(args), str(expected or ""))


def iso_utc(value) -> str | None:
	"""Naive server-local (site time zone) datetime -> ISO-8601 UTC with offset, e.g. 2026-11-17T10:15:00+00:00."""
	if not value:
		return None
	import pytz

	dt = get_datetime(value).replace(microsecond=0)
	if dt.tzinfo is None:
		dt = pytz.timezone(get_system_timezone()).localize(dt)
	return dt.astimezone(pytz.utc).isoformat()
