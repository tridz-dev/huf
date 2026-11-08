from __future__ import annotations

import json
import time
from collections.abc import Mapping
from typing import Any

import frappe

from huf.ai.external.mailbox_logic import (
	POLL_INTERVAL_SECONDS,
	clamp_wait,
	next_seq,
	select_deliverable,
)

EVENT_DOCTYPE = "External Agent Event"
SESSION_DOCTYPE = "External Agent Session"
EVENT_FIELDS = ["name", "seq", "direction", "event_type", "payload", "status", "idempotency_key"]


def post_event(
	session: str,
	direction: str,
	event_type: str,
	payload: Any = None,
	idempotency_key: str | None = None,
) -> dict:
	"""Append an event to a session's mailbox and return it as a dict.

	The session row is locked first so that sequence numbers are allocated serially. When
	``idempotency_key`` matches an existing event of the same session, that event is returned
	and nothing is inserted.

	Bypasses doctype permissions; the caller must already have authorized the session.
	"""
	row = frappe.db.get_value(SESSION_DOCTYPE, session, ["last_seq"], for_update=True)
	if row is None:
		raise _missing_session(session)

	if idempotency_key:
		# Locking read after the session lock, so a concurrent insert under the same session is seen.
		existing = frappe.db.sql(
			"select name from `tabExternal Agent Event` where session=%s and idempotency_key=%s limit 1 for update",
			(session, idempotency_key),
		)
		if existing:
			return _event_dict(frappe.get_doc(EVENT_DOCTYPE, existing[0][0]))

	seq = next_seq(row[0])
	doc = frappe.get_doc(
		{
			"doctype": EVENT_DOCTYPE,
			"session": session,
			"seq": seq,
			"direction": direction,
			"event_type": event_type,
			"payload": json.dumps(payload or {}, default=str),
			"status": "Pending",
			"idempotency_key": idempotency_key,
		}
	).insert(ignore_permissions=True)
	frappe.db.set_value(SESSION_DOCTYPE, session, "last_seq", seq, update_modified=False)
	return _event_dict(doc)


def fetch_pending(session: str, limit: int = 20) -> list[dict]:
	"""Return undelivered-or-unacked ``to_agent`` events newer than the session's ``acked_seq``.

	Events still ``Pending`` are marked ``Delivered`` in the same call. The caller decides when
	to commit; ``wait_for_events`` commits after calling this.

	Bypasses doctype permissions; the caller must already have authorized the session.
	"""
	acked_seq = frappe.db.get_value(SESSION_DOCTYPE, session, "acked_seq")
	if acked_seq is None:
		raise _missing_session(session)

	rows = frappe.get_all(
		EVENT_DOCTYPE,
		filters={
			"session": session,
			"direction": "to_agent",
			"status": ["in", ["Pending", "Delivered"]],
			"seq": [">", int(acked_seq or 0)],
		},
		fields=EVENT_FIELDS,
		order_by="seq asc",
		limit_page_length=int(limit),
	)

	events = []
	for event in select_deliverable(rows, acked_seq):
		event_dict = _event_dict(event)
		if event_dict["status"] == "Pending":
			frappe.db.set_value(
				EVENT_DOCTYPE, event_dict["name"], "status", "Delivered", update_modified=False
			)
			event_dict["status"] = "Delivered"
		events.append(event_dict)
	return events


def ack(session: str, seq: int) -> int:
	"""Acknowledge every ``to_agent`` event up to and including ``seq``.

	``acked_seq`` never moves backwards. Returns the resulting ``acked_seq``.

	Bypasses doctype permissions; the caller must already have authorized the session.
	"""
	row = frappe.db.get_value(SESSION_DOCTYPE, session, ["acked_seq", "last_seq"], for_update=True)
	if row is None:
		raise _missing_session(session)

	old_acked, last_seq = row
	acked = max(int(old_acked or 0), min(int(seq), int(last_seq or 0)))
	frappe.db.set_value(SESSION_DOCTYPE, session, "acked_seq", acked, update_modified=False)
	frappe.db.sql(
		"""
		UPDATE `tabExternal Agent Event`
		SET `status` = %s
		WHERE `session` = %s
			AND `direction` = %s
			AND `seq` <= %s
			AND `status` <> %s
		""",
		("Acked", session, "to_agent", acked, "Acked"),
	)
	return acked


def wait_for_events(session: str, timeout_seconds: int | None = None) -> list[dict]:
	"""Bounded long-poll for pending ``to_agent`` events.

	Waits up to the clamped timeout (never more than MAX_WAIT_SECONDS) and returns as soon as
	events are available. Returns an empty list when the deadline passes with nothing pending.
	Callers call again on an empty result.

	Bypasses doctype permissions; the caller must already have authorized the session.
	"""
	wait = clamp_wait(timeout_seconds)
	deadline = time.monotonic() + wait
	# Commit earlier writes from this request so they are not discarded by the polling loop.
	frappe.db.commit()
	while True:
		# Commit ends the REPEATABLE READ snapshot so each poll sees rows committed since the last one.
		frappe.db.commit()
		events = fetch_pending(session)
		# Commit the Delivered markings before handing the events to the caller.
		frappe.db.commit()
		if events:
			return events
		remaining = deadline - time.monotonic()
		if remaining <= 0:
			return events
		time.sleep(min(POLL_INTERVAL_SECONDS, remaining))


def _missing_session(session: str) -> frappe.DoesNotExistError:
	return frappe.DoesNotExistError(f"{SESSION_DOCTYPE} {session} does not exist")


def _event_dict(doc_or_row: Any) -> dict:
	"""Convert an event document or row mapping into the public event dict."""

	def _get(key: str) -> Any:
		if isinstance(doc_or_row, Mapping):
			return doc_or_row.get(key)
		return getattr(doc_or_row, key, None)

	raw_payload = _get("payload")
	try:
		payload = json.loads(raw_payload) if raw_payload else {}
	except (TypeError, ValueError):
		payload = {}

	return {
		"name": _get("name"),
		"seq": int(_get("seq") or 0),
		"direction": _get("direction"),
		"event_type": _get("event_type"),
		"payload": payload,
		"status": _get("status"),
		"idempotency_key": _get("idempotency_key"),
	}
