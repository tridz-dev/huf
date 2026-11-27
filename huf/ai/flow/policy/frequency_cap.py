"""Frequency cap store: sends per (member, channel) in a fixed time window.

The key has no flow in it, so every flow counts against the same cap. ``window`` is the window length in
seconds; windows are aligned to the Unix epoch (86400 = one UTC day). The row is keyed by the window's
length and start, so each length (day, week) counts on its own.

``incr`` COMMITS the current transaction, before and after counting. Before: MariaDB refuses to lock a row
that changed after the transaction's snapshot (error 1020), which would fail parallel senders. After: the
claim is durable before the message leaves, so a later rollback cannot let the cap be exceeded, and the row
lock is not held during the send. Call it where committing the work so far is safe. ``check`` only reads.

Every error propagates: a caller guarding a send must treat it as a block. Errors never carry the member key.
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone

import frappe
from frappe.utils import now_datetime

DOCTYPE = "Flow Send Counter"
TABLE = f"`tab{DOCTYPE}`"
MAX_KEY_CHARS = 140
MATCH_KEY = (
	"member_key = %(member_key)s and channel = %(channel)s"
	" and window_seconds = %(window_seconds)s and window_start = %(window_start)s"
)


def counter_name(member_key: str, channel: str, window_seconds: int, window_start) -> str:
	key = f"{member_key}\0{channel}\0{window_seconds}\0{window_start}"
	return hashlib.sha256(key.encode()).hexdigest()[:40]


def _key(member_key: str, channel: str, window: int) -> dict:
	for label, value in (("member_key", member_key), ("channel", channel)):
		if not isinstance(value, str) or not value.strip() or len(value) > MAX_KEY_CHARS:
			raise ValueError(f"{label} must be a non-empty text of at most {MAX_KEY_CHARS} characters")
	if type(window) is not int or window <= 0:
		raise ValueError("window must be a positive whole number of seconds")
	start = int(time.time()) // window * window
	return {
		"member_key": member_key,
		"channel": channel,
		"window_seconds": window,
		"window_start": datetime.fromtimestamp(start, timezone.utc).replace(tzinfo=None),
	}


def check(member_key: str, channel: str, window: int) -> int:
	"""Sends counted in the current window. Reads only; to claim a send under a cap use ``incr``."""
	rows = frappe.db.sql(f"select `count` from {TABLE} where {MATCH_KEY}", _key(member_key, channel, window))
	return rows[0][0] if rows else 0


def incr(member_key: str, channel: str, window: int, limit: int | None = None) -> int | None:
	"""Count one send, commit, and return the new total.

	With ``limit``, the check and the increment are one atomic step: when the window already holds
	``limit`` sends, nothing is counted and the result is ``None``.
	"""
	if limit is not None and (type(limit) is not int or limit < 0):
		raise ValueError("limit must be a whole number, zero or more")
	values = _key(member_key, channel, window)
	now = now_datetime()
	values.update(
		name=counter_name(member_key, channel, window, values["window_start"]),
		now=now,
		user=frappe.session.user,
	)
	frappe.db.commit()  # nosemgrep  start without an older snapshot
	try:
		count = _claim(values, limit)
	except Exception:
		frappe.db.rollback()
		raise
	frappe.db.commit()  # nosemgrep  make the claim durable and release the row lock
	return count


def _claim(values: dict, limit: int | None) -> int | None:
	# Creates the row or, on a duplicate, takes its exclusive lock: concurrent callers queue here.
	frappe.db.sql(
		f"insert into {TABLE} (name, creation, modified, owner, modified_by, member_key, channel, window_seconds, window_start, `count`)"
		" values (%(name)s, %(now)s, %(now)s, %(user)s, %(user)s, %(member_key)s, %(channel)s, %(window_seconds)s, %(window_start)s, 0)"
		" on duplicate key update `count` = `count`",
		values,
	)
	count = frappe.db.sql(f"select `count` from {TABLE} where {MATCH_KEY} for update", values)[0][0]
	if limit is not None and count >= limit:
		return None
	frappe.db.sql(f"update {TABLE} set `count` = %(count)s, modified = %(now)s where {MATCH_KEY}", {**values, "count": count + 1})
	return count + 1
