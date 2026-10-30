"""Per-key state for Flow, stored in the ``Flow State`` doctype.

Used by the ``state.get`` / ``state.set`` / ``state.delete`` nodes so a flow can remember something
between runs (e.g. "awaiting an order number" for one WhatsApp sender).

Rules:
* Every row belongs to one flow. The functions here take the flow id from the *running* flow (the
  node executors pass ``flow_run.flow_id``); node config cannot name another flow, so a flow can
  never read or write another flow's state. The doctype itself is limited to System Manager / Huf
  Manager, and rows are accessed internally with ``ignore_permissions`` because the flow's run-as
  user normally has no role on this internal store.
* Keys: 1-140 chars (string or int). Values: any JSON, at most ``MAX_VALUE_BYTES`` encoded.
* Every row expires (default 24h, max 30 days). Expired rows read as missing and are deleted lazily
  on read; ``purge_expired`` (daily scheduler) removes the rest.
"""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any

import frappe
from frappe.utils import add_to_date, now_datetime

DOCTYPE = "Flow State"
MAX_KEY_CHARS = 140
MAX_VALUE_BYTES = 16 * 1024
DEFAULT_TTL_SECONDS = 24 * 3600
MAX_TTL_SECONDS = 30 * 24 * 3600


class FlowStateError(ValueError):
	"""Invalid key, value, or ttl for a flow state operation."""


def normalize_key(key: Any) -> str:
	if isinstance(key, bool) or not isinstance(key, (str, int)):
		raise FlowStateError("The name to save this under must be text or a number.")
	text = str(key)
	if not text or len(text) > MAX_KEY_CHARS:
		raise FlowStateError(f"The name to save this under must be between 1 and {MAX_KEY_CHARS} characters long.")
	return text


def normalize_ttl(ttl_seconds: Any) -> int:
	if ttl_seconds is None:
		return DEFAULT_TTL_SECONDS
	if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or not 0 < ttl_seconds <= MAX_TTL_SECONDS:
		raise FlowStateError(f"How long to keep this must be a whole number of seconds between 1 and {MAX_TTL_SECONDS}.")
	return ttl_seconds


def encode_value(value: Any) -> str:
	try:
		encoded = json.dumps(value)
	except (TypeError, ValueError) as exc:
		raise FlowStateError("The value to save cannot be stored. Save text, numbers, yes/no values, lists or records only.") from exc
	if len(encoded.encode("utf-8")) > MAX_VALUE_BYTES:
		raise FlowStateError(f"The value to save is too large ({MAX_VALUE_BYTES // 1024} KB is the most). Save less data.")
	return encoded


def state_name(flow_id: str, key: str) -> str:
	"""Deterministic primary key: one row per (flow, key), enforced by the primary key itself."""
	return hashlib.sha256(f"{flow_id}\0{key}".encode()).hexdigest()[:40]


def _scope(flow_id: Any, key: Any) -> tuple[str, str, str]:
	if not flow_id or not isinstance(flow_id, str):
		raise FlowStateError("Saved data can only be used while a flow is running.")
	key = normalize_key(key)
	return flow_id, key, state_name(flow_id, key)


def get_state(flow_id: str, key: Any) -> tuple[bool, Any]:
	"""Return ``(found, value)``. Expired rows are deleted and read as not found."""
	flow_id, _key, name = _scope(flow_id, key)
	row = frappe.db.get_value(DOCTYPE, name, ["value_json", "expires_at"], as_dict=True)
	if not row:
		return False, None
	if row.expires_at and row.expires_at <= now_datetime():
		frappe.db.delete(DOCTYPE, {"name": name})
		return False, None
	return True, json.loads(row.value_json) if row.value_json else None


def set_state(flow_id: str, key: Any, value: Any, ttl_seconds: Any = None) -> None:
	flow_id, key, name = _scope(flow_id, key)
	encoded = encode_value(value)
	expires_at = add_to_date(now_datetime(), seconds=normalize_ttl(ttl_seconds))
	if frappe.db.exists(DOCTYPE, name):
		frappe.db.set_value(
			DOCTYPE, name, {"value_json": encoded, "expires_at": expires_at}, update_modified=True
		)
		return
	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"flow_id": flow_id,
			"state_key": key,
			"value_json": encoded,
			"expires_at": expires_at,
		}
	)
	doc.flags.name = name
	try:
		doc.insert(ignore_permissions=True)
	except frappe.DuplicateEntryError:
		# lost a race with a concurrent run for the same key: last writer wins
		frappe.db.set_value(DOCTYPE, name, {"value_json": encoded, "expires_at": expires_at})


def delete_state(flow_id: str, key: Any) -> bool:
	_flow, _key, name = _scope(flow_id, key)
	if not frappe.db.exists(DOCTYPE, name):
		return False
	frappe.db.delete(DOCTYPE, {"name": name})
	return True


def purge_expired() -> int:
	"""Scheduler entry point (daily): delete every expired row. Returns the number removed."""
	expired = frappe.get_all(DOCTYPE, filters={"expires_at": ["<=", now_datetime()]}, pluck="name", limit=10000)
	for name in expired:
		frappe.db.delete(DOCTYPE, {"name": name})
	return len(expired)
