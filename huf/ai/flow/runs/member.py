"""Per-member journey state for Flow, stored in the ``Flow Member State`` doctype.

A member is whoever a run is about: a gateway sender, the document a doc-event fired for, or the
signed-in user of a manual run. Their variables survive across runs (no TTL) and are read in templates
as ``member.vars.<name>``. Every access is scoped to the running flow's id, like :mod:`huf.ai.flow.state`.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import frappe
from frappe.utils import add_to_date, now_datetime

DOCTYPE = "Flow Member State"
MAX_KEY_CHARS = 140
MAX_VARS_BYTES = 64 * 1024
MAX_HISTORY = 100
DEFAULT_RETENTION_DAYS = 365


class FlowMemberError(ValueError):
	"""Invalid member variables for a flow member operation."""


def member_name(flow: str, key: str) -> str:
	"""Deterministic primary key: one row per (flow, member key), enforced by the primary key itself."""
	return hashlib.sha256(f"{flow}\0{key}".encode()).hexdigest()[:40]


def _normalize_sender(value: Any) -> str:
	text = str(value or "").strip().lower().lstrip("@")
	if re.fullmatch(r"[+\d\s().\-]+", text):
		return re.sub(r"\D", "", text)  # a phone number: "+1 555-0100" and "15550100" are the same member
	return text


def resolve_member_key(trigger_type: str | None, payload: dict | None, run_user: str | None) -> str | None:
	"""The member a run is about, or ``None`` when it cannot be told."""
	payload = payload or {}
	key = None
	if trigger_type == "Gateway":
		key = _normalize_sender(payload.get("sender_id") or payload.get("wa_id")) or None
	elif trigger_type == "Doc Event":
		trig = payload.get("_trigger") or {}
		if trig.get("doctype") and trig.get("docname"):
			key = f"{trig['doctype']}:{trig['docname']}"
	elif trigger_type == "Manual":
		key = run_user if run_user and run_user != "Guest" else None
	return key[:MAX_KEY_CHARS] if key else None


def _load_json(raw: Any, default):
	if not raw:
		return default
	try:
		data = json.loads(raw) if isinstance(raw, str) else raw
	except (json.JSONDecodeError, TypeError):
		return default
	return data if isinstance(data, type(default)) else default


def get_member(flow: str, key: str) -> dict | None:
	row = frappe.db.get_value(DOCTYPE, member_name(flow, key), "*", as_dict=True)
	if not row:
		return None
	row["vars"] = _load_json(row.pop("vars_json", None), {})
	row["history"] = _load_json(row.pop("history_json", None), [])
	return row


def upsert_member(flow: str, key: str, run: str | None = None) -> str:
	"""Create the member on first sight, then count this run. Returns the row name."""
	name = member_name(flow, key)
	now = now_datetime()
	if not frappe.db.exists(DOCTYPE, name):
		try:
			frappe.get_doc(
				{"doctype": DOCTYPE, "flow": flow, "member_key": key, "status": "Active", "entered_at": now}
			).insert(ignore_permissions=True)
		except frappe.DuplicateEntryError:
			pass  # another run created it at the same moment
	frappe.db.sql(
		f"update `tab{DOCTYPE}` set run_count = run_count + 1, last_event_at = %s, status = 'Active',"
		" completed_at = null, active_flow_run = %s where name = %s",
		(now, run, name),
	)
	return name


def set_status(flow: str, key: str, status: str, node_id: str | None = None) -> None:
	"""Set the person's status; ``node_id`` is the step they are waiting at (cleared for any other status)."""
	frappe.db.set_value(
		DOCTYPE,
		member_name(flow, key),
		{"status": status, "current_node_id": node_id if status == "Waiting" else None},
		update_modified=False,
	)


def find_waiting_reply_run(flow: str, key: str) -> str | None:
	"""The run of this member parked on a ``member_reply`` wait, if any."""
	rows = frappe.get_all(
		"Flow Run",
		filters={"flow_id": flow, "member_key": key, "status": "Waiting Timer"},
		fields=["name", "waiting"],
		order_by="creation desc",
		limit=20,
	)
	for row in rows:
		extra = _load_json(row.waiting, {}).get("extra") or {}
		if extra.get("wait_for") == "member_reply":
			return row.name
	return None


def has_active_run(flow: str, key: str) -> bool:
	from huf.ai.flow.engine import TERMINAL_STATUSES

	return bool(
		frappe.db.exists("Flow Run", {"flow_id": flow, "member_key": key, "status": ["not in", list(TERMINAL_STATUSES)]})
	)


def get_vars(flow: str, key: str) -> dict:
	raw = frappe.db.get_value(DOCTYPE, member_name(flow, key), "vars_json")
	return _load_json(raw, {})


def set_vars(flow: str, key: str, updates: dict) -> dict:
	"""Merge ``updates`` into the member's variables; at most ``MAX_VARS_BYTES`` encoded."""
	if not isinstance(updates, dict):
		raise FlowMemberError("The values to save for this person must be a list of names and values.")
	merged = {**get_vars(flow, key), **updates}
	try:
		encoded = json.dumps(merged)
	except (TypeError, ValueError) as exc:
		raise FlowMemberError("A value to save cannot be stored. Save text, numbers, yes/no values, lists or records only.") from exc
	if len(encoded.encode("utf-8")) > MAX_VARS_BYTES:
		raise FlowMemberError(f"What is saved for this person is too large ({MAX_VARS_BYTES // 1024} KB is the most). Save less data.")
	name = member_name(flow, key)
	if not frappe.db.exists(DOCTYPE, name):
		raise FlowMemberError("This person is not known to the flow yet.")
	frappe.db.set_value(DOCTYPE, name, "vars_json", encoded, update_modified=False)
	return merged


def record_history(flow: str, key: str, node: str, run: str | None = None) -> None:
	name = member_name(flow, key)
	history = _load_json(frappe.db.get_value(DOCTYPE, name, "history_json"), [])
	history.append({"node": node, "at": str(now_datetime()), "run": run})
	frappe.db.set_value(DOCTYPE, name, "history_json", json.dumps(history[-MAX_HISTORY:]), update_modified=False)


def remove_member(flow: str, key: str) -> bool:
	"""Forget a member: cancel their waiting run, then delete the row. True when a row existed."""
	from huf.ai.flow.runs.park import cancel_run

	name = member_name(flow, key)
	run = frappe.db.get_value(DOCTYPE, name, "active_flow_run")
	if run and frappe.db.exists("Flow Run", run):
		cancel_run(run, frappe.session.user)  # no-op when the run already finished
	if not frappe.db.exists(DOCTYPE, name):
		return False
	frappe.db.delete(DOCTYPE, {"name": name})
	return True


def purge_inactive(days: int | None = None) -> int:
	"""Delete members with no activity for ``days`` (site config ``huf_flow_member_retention_days``, default 365; 0 = keep)."""
	if days is None:
		days = int(frappe.conf.get("huf_flow_member_retention_days", DEFAULT_RETENTION_DAYS) or 0)
	if days <= 0:
		return 0
	cutoff = add_to_date(now_datetime(), days=-days)
	names = frappe.get_all(DOCTYPE, filters={"last_event_at": ["<", cutoff], "status": ["!=", "Waiting"]}, pluck="name")
	for name in names:
		frappe.db.delete(DOCTYPE, {"name": name})
	return len(names)


def run_member_context(flow_run) -> dict | None:
	"""The ``member`` template root for a run (key, status, vars, run count, entry time); None when it has no member."""
	member_key = getattr(flow_run, "member_key", None)
	row = get_member(flow_run.flow_id, member_key) if member_key else None
	if not row:
		return None
	return {
		"key": member_key,
		"status": row.status,
		"vars": row.vars,
		"run_count": row.run_count,
		"entered_at": row.entered_at,
	}


def key_for_new_run(trigger_type: str | None, payload: dict | None, mode: str) -> str | None:
	"""The member a new run is about (real runs only; a test run has none)."""
	return resolve_member_key(trigger_type, payload, frappe.session.user) if mode == "real" else None


def scoped_state_key(flow_run, key) -> str | None:
	"""A flow-state key kept per person (``member:<key>:<key>``); None when the run does not know its member."""
	member_key = getattr(flow_run, "member_key", None)
	return f"member:{member_key}:{key}" if member_key else None
