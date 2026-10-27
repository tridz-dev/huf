# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WhatsApp Broadcast: apply Meta delivery statuses and user stops to Broadcast Recipient rows.

Rows only ever move forward in rank (queued/deferred 0 < sending 1 < unknown 1.5 < sent 2 < failed < delivered 3
< read 4). ``failed`` never overwrites delivered/read, and a replayed (wamid, status) is a no-op because it
cannot raise the rank, so Meta's retries and out-of-order deliveries are safe. Callers wrap these in
try/except; a failure here must never break webhook ingest.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import frappe

RECIPIENT = "WhatsApp Broadcast Recipient"
BROADCAST = "WhatsApp Broadcast"
_COUNTED = frozenset(("queued", "sending", "sent", "delivered", "read", "failed", "deferred", "unknown", "skipped"))
PAUSE_ON_FAILURE_CODES = frozenset({135000})
MARKETING_STOP_CODE = 131050
PER_USER_LIMIT_CODE = 131049
PER_USER_LIMIT_REASON = "per_user_marketing_limit"
# A stopped contact must not be messaged by a broadcast that has not finished.
_LIVE_BROADCAST = ("Queued", "Running", "Paused")

# status -> (rank, column holding its timestamp)
_RANK = {"queued": 0, "deferred": 0, "sending": 1, "unknown": 1.5, "sent": 2, "failed": 2.5, "delivered": 3, "read": 4}
_META = {"sent": ("sent", "sent_at"), "delivered": ("delivered", "delivered_at"), "read": ("read", "read_at"), "played": ("read", "read_at"), "failed": ("failed", "failed_at")}


def _when(timestamp: Any) -> datetime:
	try:
		ts = int(float(timestamp))
		if ts > 0:
			return datetime.fromtimestamp(ts)
	except (TypeError, ValueError, OverflowError, OSError):
		pass
	return frappe.utils.now_datetime()


def _first_error(errors: Any) -> tuple[int | None, str]:
	first = errors[0] if isinstance(errors, list) and errors and isinstance(errors[0], dict) else {}
	try:
		code = int(first.get("code"))
	except (TypeError, ValueError):
		code = None
	parts = [str(first.get("title") or first.get("message") or "").strip()]
	details = (first.get("error_data") or {}).get("details") if isinstance(first.get("error_data"), dict) else ""
	if details:
		parts.append(str(details).strip())
	return code, " - ".join(p for p in parts if p)[:500]


def _gateway_ok(row: dict, gateway: str | None) -> bool:
	"""A status may only touch rows whose Broadcast belongs to the webhook's gateway."""
	if gateway is None:
		return True
	return bool(gateway) and frappe.db.get_value(BROADCAST, row["broadcast"], "gateway") == gateway


def _find_row(wamid: str | None, opaque_ref: str | None, gateway: str | None = None) -> dict | None:
	fields = ["name", "broadcast", "status", "wamid", "recipient"]
	if wamid:
		rows = frappe.get_all(RECIPIENT, filters={"wamid": wamid}, fields=fields, limit_page_length=1)
		if rows and _gateway_ok(rows[0], gateway):
			return rows[0]
	if opaque_ref and len(str(opaque_ref)) <= 256:
		rows = frappe.get_all(RECIPIENT, filters={"name": str(opaque_ref)}, fields=fields, limit_page_length=1)
		if rows and _gateway_ok(rows[0], gateway):
			return rows[0]
	return None


def _recount(broadcast: str) -> None:
	"""O(N) reconciliation from recipient rows. Not for the webhook hot path (see ``_bump``)."""
	frappe.get_doc(BROADCAST, broadcast).recount()


def _row_count() -> int:
	return int(frappe.db.sql("select row_count()")[0][0])


def _bump(broadcast: str, old: str, new: str) -> None:
	"""Atomic counter move old -> new on the Broadcast row, in the caller's transaction."""
	if old == new or old not in _COUNTED or new not in _COUNTED:
		return
	frappe.db.sql(
		f"update `tab{BROADCAST}` set `{old}`=greatest(`{old}`, 1) - 1, `{new}`=`{new}` + 1 where name=%s",
		broadcast,
	)


def _try_update(name: str, current: str, values: dict[str, Any]) -> bool:
	set_sql = ", ".join(f"`{k}`=%({k})s" for k in values)
	frappe.db.sql(
		f"update `tab{RECIPIENT}` set {set_sql} where name=%(_name)s and status=%(_current)s",
		{**values, "_name": name, "_current": current},
	)
	return _row_count() == 1


def apply_status(
	wamid: str | None,
	status: str,
	timestamp: int | str | None = None,
	errors: list | None = None,
	opaque_ref: str | None = None,
	gateway: str | None = None,
) -> bool:
	"""Apply one Meta status to its recipient row (wamid first, then opaque_ref). True if a row changed.

	``gateway`` scopes matching to that gateway's broadcasts (None disables the check; tests only).
	Broadcast counters are moved by atomic deltas in the same transaction as the row update;
	``WhatsAppBroadcast.recount()`` stays the reconciliation path (resume_stale / completion).
	"""
	meta = _META.get(str(status or "").lower())
	if not meta or not (wamid or opaque_ref):
		return False
	new, time_col = meta
	row = _find_row(str(wamid) if wamid else None, opaque_ref, gateway)
	if not row:
		return False
	current = row["status"]
	if current == "skipped" or _RANK.get(new, 0) <= _RANK.get(current, 0):
		return False  # never backwards, never overwrite delivered/read with failed, replays are no-ops

	values: dict[str, Any] = {"status": new, time_col: _when(timestamp)}
	code = None
	limited = False
	if new == "failed":
		code, message = _first_error(errors)
		values.update({"error_code": int(code or 0), "error_message": message})  # Int column is NOT NULL
		if code == PER_USER_LIMIT_CODE:
			# terminal, never resent: the message was not delivered (failed never overwrites delivered/read)
			limited = True
			new = "skipped"
			values.pop("failed_at", None)
			values.update({"status": "skipped", "skip_reason": PER_USER_LIMIT_REASON})
	if not row.get("wamid") and wamid:
		values["wamid"] = wamid
	# Conditional UPDATE: a concurrent webhook that already advanced the row wins.
	if not _try_update(row["name"], current, values):
		# Under REPEATABLE READ our snapshot may be stale: decide from the current, locked row.
		cur = frappe.db.get_value(RECIPIENT, row["name"], "status", for_update=True)
		if cur is None or cur == "skipped" or _RANK.get(new, 0) <= _RANK.get(cur, 0):
			return False
		if not _try_update(row["name"], cur, values):
			return False
		current = cur
	_bump(row["broadcast"], current, new)
	if code == MARKETING_STOP_CODE and (new == "failed" or limited):
		_record_marketing_stop(row)
	if new == "failed" and code in PAUSE_ON_FAILURE_CODES:
		_pause(row["broadcast"], f"WhatsApp error {code} (messages dropped by pacing)")
	return True


def _record_marketing_stop(row: dict) -> None:
	"""131050 (user stopped marketing): same consent record the send path writes; it also skips the contact's other
	pending rows in live broadcasts via ``apply_user_stop``. Never raises."""
	try:
		from huf.ai.whatsapp import account_events

		gateway = frappe.db.get_value(BROADCAST, row["broadcast"], "gateway")
		if gateway and row.get("recipient"):
			account_events.record_user_preferences(
				gateway, [{"category": account_events.MARKETING, "value": "stop", "wa_id": row["recipient"], "detail": "131050"}]
			)
	except Exception:
		frappe.log_error(title="WhatsApp broadcast marketing-stop consent failed", message=frappe.get_traceback())


def _pause(broadcast: str, reason: str) -> None:
	try:
		from huf.ai.whatsapp import broadcast_runner  # written by another work package

		broadcast_runner.pause(broadcast, reason)
	except Exception:
		frappe.log_error(title="WhatsApp broadcast pause failed", message=f"{broadcast}: {reason}\n{frappe.get_traceback()}")


def apply_user_stop(gateway: str, recipient: str) -> int:
	"""Skip this contact's queued/deferred rows in unfinished broadcasts of the gateway. Returns rows skipped."""
	from huf.ai.whatsapp.account_events import _norm_sender

	key = _norm_sender(recipient)
	if not gateway or not key:
		return 0
	rows = frappe.db.sql(
		f"""select r.name, r.broadcast from `tab{RECIPIENT}` r
		join `tabWhatsApp Broadcast` b on b.name = r.broadcast
		where b.gateway=%s and b.status in %s and r.recipient=%s and r.status in ('queued','deferred')""",
		(gateway, _LIVE_BROADCAST, key),
	)
	skipped = 0
	touched = set()
	for name, broadcast in rows:
		frappe.db.sql(
			f"update `tab{RECIPIENT}` set status='skipped', skip_reason='opted_out' where name=%s and status in ('queued','deferred')",
			name,
		)
		if frappe.db.sql(f"select 1 from `tab{RECIPIENT}` where name=%s and status='skipped' and skip_reason='opted_out'", name):
			skipped += 1
			touched.add(broadcast)
	for broadcast in touched:
		_recount(broadcast)
	return skipped
