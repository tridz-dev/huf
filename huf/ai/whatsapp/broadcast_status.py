# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WhatsApp Broadcast: apply Meta delivery statuses and user stops to Broadcast Recipient rows.

Rows only ever move forward in rank (queued/deferred 0 < sending 1 < sent/unknown 2 < failed < delivered 3
< read 4). ``failed`` never overwrites delivered/read, and a replayed (wamid, status) is a no-op because it
cannot raise the rank, so Meta's retries and out-of-order deliveries are safe. Callers wrap these in
try/except; a failure here must never break webhook ingest.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import frappe

RECIPIENT = "WhatsApp Broadcast Recipient"
PAUSE_ON_FAILURE_CODES = frozenset({135000})
# A stopped contact must not be messaged by a broadcast that has not finished.
_LIVE_BROADCAST = ("Queued", "Running", "Paused")

# status -> (rank, column holding its timestamp)
_RANK = {"queued": 0, "deferred": 0, "sending": 1, "sent": 2, "unknown": 2, "failed": 2.5, "delivered": 3, "read": 4}
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


def _find_row(wamid: str | None, opaque_ref: str | None) -> dict | None:
	fields = ["name", "broadcast", "status", "wamid"]
	if wamid:
		rows = frappe.get_all(RECIPIENT, filters={"wamid": wamid}, fields=fields, limit_page_length=1)
		if rows:
			return rows[0]
	if opaque_ref and len(str(opaque_ref)) <= 256:
		rows = frappe.get_all(RECIPIENT, filters={"name": str(opaque_ref)}, fields=fields, limit_page_length=1)
		if rows:
			return rows[0]
	return None


def _recount(broadcast: str) -> None:
	frappe.get_doc("WhatsApp Broadcast", broadcast).recount()


def apply_status(
	wamid: str | None,
	status: str,
	timestamp: int | str | None = None,
	errors: list | None = None,
	opaque_ref: str | None = None,
) -> bool:
	"""Apply one Meta status to its recipient row (wamid first, then opaque_ref). True if a row changed."""
	meta = _META.get(str(status or "").lower())
	if not meta or not (wamid or opaque_ref):
		return False
	new, time_col = meta
	row = _find_row(str(wamid) if wamid else None, opaque_ref)
	if not row:
		return False
	current = row["status"]
	if current == "skipped" or _RANK.get(new, 0) <= _RANK.get(current, 0):
		return False  # never backwards, never overwrite delivered/read with failed, replays are no-ops

	values: dict[str, Any] = {"status": new, time_col: _when(timestamp)}
	code = None
	if new == "failed":
		code, message = _first_error(errors)
		values.update({"error_code": code, "error_message": message})
	if not row.get("wamid") and wamid:
		values["wamid"] = wamid
	# Conditional UPDATE: a concurrent webhook that already advanced the row wins.
	set_sql = ", ".join(f"`{k}`=%({k})s" for k in values)
	frappe.db.sql(
		f"update `tab{RECIPIENT}` set {set_sql} where name=%(_name)s and status=%(_current)s",
		{**values, "_name": row["name"], "_current": current},
	)
	if not frappe.db.sql(f"select 1 from `tab{RECIPIENT}` where name=%s and status=%s", (row["name"], new)):
		return False
	_recount(row["broadcast"])
	if new == "failed" and code in PAUSE_ON_FAILURE_CODES:
		_pause(row["broadcast"], f"WhatsApp error {code} (messages dropped by pacing)")
	return True


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
