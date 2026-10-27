"""WhatsApp Broadcast: send one recipient, crash-safe (WP-4).

The WhatsApp Broadcast Recipient row is the duplicate-send guard:

	queued|deferred --claim (atomic conditional UPDATE + COMMIT, before any POST)--> sending
	sending --> sent | failed | deferred | unknown | skipped

Rules that make a crash or a double call harmless:

* The claim is ``UPDATE ... SET status='sending' WHERE name=%s AND status IN ('queued','deferred')``
  followed by a commit; rowcount 0 means someone else owns the row (``lost_claim``).
* Anything that fails BEFORE the Graph POST is attempted leaves the row in ``sending`` (the runner's
  ``resume_stale`` turns a stale ``sending`` row into ``unknown``). Nothing here ever moves a row back to
  ``queued`` after the POST was attempted.
* Once ``bridge.send_template`` has been called, an ambiguous outcome (timeout, connection error, a non-Graph
  exception, an unparseable response) is ``unknown`` and is NEVER resent. Only an error that carries a Graph
  error code (Meta answered and refused) is classified as failed / deferred.
* If the result cannot be written after a successful POST, the row is forced to ``unknown`` (with the wamid
  when known); it is never left ``queued``/``deferred``.
* This module never imports ``huf.ai.tools.whatsapp`` (its legacy direct-Graph fallback bypasses policy).
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe.utils import add_to_date, now_datetime

from huf.ai.gateway_adapters import whatsapp_errors as errors

RECIPIENT = "WhatsApp Broadcast Recipient"
BROADCAST = "WhatsApp Broadcast"
MAX_ATTEMPTS = 5
DEFER_24H_SECONDS = 86400
GATEWAY_DOWN_DEFER_SECONDS = 300

OUTCOMES = ("sent", "failed", "deferred", "unknown", "skipped", "lost_claim")
# pre-POST refusals (policy / validation) from the bridge that mean "do not message this contact"
_SKIP_CODES = {"opted_out", "marketing_opted_out", "bsuid_recipient"}
_STARTED = ("sending", "sent", "delivered", "read", "unknown", "failed")


# ---------------------------------------------------------------- db helpers (small so tests can fake them)


def _claim(name: str) -> bool:
	"""Atomically queued|deferred -> sending (attempts+1), committed before returning. True when we own it."""
	frappe.db.sql(
		f"update `tab{RECIPIENT}` set status='sending', attempts=ifnull(attempts,0)+1, modified=%s "
		"where name=%s and status in ('queued','deferred') and ifnull(attempts,0) < %s",
		(now_datetime(), name, MAX_ATTEMPTS),
	)
	owned = frappe.db.sql("select row_count()")[0][0] == 1
	frappe.db.commit()
	return owned


def _release(name: str) -> None:
	"""sending -> queued, giving back the attempt. Only used before the POST was attempted."""
	frappe.db.sql(
		f"update `tab{RECIPIENT}` set status='queued', attempts=greatest(ifnull(attempts,0)-1,0) "
		"where name=%s and status='sending'",
		(name,),
	)
	frappe.db.commit()


def _load(name: str) -> dict[str, Any] | None:
	return frappe.db.get_value(RECIPIENT, name, "*", as_dict=True)


def _load_broadcast(name: str) -> dict[str, Any] | None:
	return frappe.db.get_value(BROADCAST, name, "*", as_dict=True)


def _write(name: str, **fields: Any) -> None:
	"""Update a row that this call owns (status still ``sending``) and commit."""
	sets = ", ".join(f"`{k}`=%s" for k in fields)
	frappe.db.sql(
		f"update `tab{RECIPIENT}` set {sets}, modified=%s where name=%s and status='sending'",
		(*fields.values(), now_datetime(), name),
	)
	frappe.db.commit()


def _started_count(broadcast: str) -> int:
	return int(
		frappe.db.sql(
			f"select count(*) from `tab{RECIPIENT}` where broadcast=%s and status in %s",
			(broadcast, _STARTED),
		)[0][0]
	)


# ---------------------------------------------------------------- helpers


def _json(value: Any) -> Any:
	if isinstance(value, str):
		value = value.strip()
		if not value:
			return None
		try:
			return json.loads(value)
		except ValueError:
			return value
	return value or None


def _merge_params(broadcast: dict[str, Any], row: dict[str, Any]) -> tuple[Any, Any, Any]:
	"""(body, header, button): the recipient's ``params`` override the broadcast defaults, per part."""
	own = _json(row.get("params"))
	own = own if isinstance(own, dict) else {}
	out = []
	for part in ("body", "header", "button"):
		default = _json(broadcast.get(f"{part}_params"))
		mine = own.get(part, own.get(f"{part}_params"))
		if mine is None:
			out.append(default)
		elif isinstance(default, dict) and isinstance(mine, dict):
			out.append({**default, **mine})
		else:
			out.append(mine)
	return tuple(out)


def _classify(payload: dict[str, Any]) -> dict[str, Any]:
	"""Classification of a BridgeError payload that carries a Graph code."""
	return errors.classify(
		{"error": {"code": payload.get("graph_code"), "error_subcode": payload.get("subcode"), "message": payload.get("message")}}
	)


def _later(seconds: float):
	return add_to_date(now_datetime(), seconds=int(seconds))


# ---------------------------------------------------------------- public


def send_one(recipient_name: str) -> str:
	"""Send the broadcast template to one recipient row. Returns one of :data:`OUTCOMES`."""
	if not _claim(recipient_name):
		row = _load(recipient_name)
		if row and row.get("status") in ("queued", "deferred") and int(row.get("attempts") or 0) >= MAX_ATTEMPTS:
			frappe.db.sql(
				f"update `tab{RECIPIENT}` set status='failed', failed_at=%s, error_message=%s "
				"where name=%s and status in ('queued','deferred')",
				(now_datetime(), "Gave up after the maximum number of attempts.", recipient_name),
			)
			frappe.db.commit()
			return "failed"
		return "lost_claim"

	row = _load(recipient_name)
	bc = _load_broadcast(row["broadcast"]) if row else None
	if not row or not bc:
		_write(recipient_name, status="failed", failed_at=now_datetime(), error_message="Broadcast or recipient missing.")
		return "failed"

	# kill switch: only a Running broadcast sends; nothing was posted, so hand the row back
	if bc.get("status") != "Running":
		_release(recipient_name)
		return "lost_claim"

	# per-broadcast cap (rows already started, excluding this one)
	max_recipients = int(bc.get("max_recipients") or 0)
	if max_recipients and _started_count(bc["name"]) > max_recipients:
		_write(recipient_name, status="skipped", skip_reason="max_recipients")
		return "skipped"

	# STOP / BSUID re-check immediately before sending
	from huf.ai.whatsapp import outbound_policy as policy

	to = row["recipient"]
	try:
		policy.check_recipient(bc.get("gateway"), to)
	except policy.OutboundRefused as exc:
		_write(recipient_name, status="skipped", skip_reason=exc.code)
		return "skipped"

	body, header, button = _merge_params(bc, row)
	opaque = row.get("opaque_ref") or recipient_name

	from huf.ai.gateway_adapters import whatsapp_bridge as bridge

	# ---- POST is attempted from here: nothing below may ever return the row to queued
	try:
		result = bridge.send_template(
			bc.get("whatsapp_account"),
			to,
			bc.get("template"),
			body,
			header,
			button_params=button,
			trusted=True,  # D8: the runner verified Gateway write permission at start and on each tick
			language_code=bc.get("language_code") or None,
			gateway_name=bc.get("gateway"),
			force_graph=True,
			opaque_ref=opaque,
		)
	except bridge.BridgeError as exc:
		return _after_bridge_error(recipient_name, int(row.get("attempts") or 0) + 1, exc.payload or {})
	except Exception as exc:  # timeout / driver error / anything after the POST was attempted: ambiguous
		return _mark_unknown(recipient_name, f"Outcome unknown: {type(exc).__name__}")

	wamid = str((result or {}).get("wamid") or (result or {}).get("message_id") or "")
	if not wamid:
		return _mark_unknown(recipient_name, "Sent but no message id was returned.")
	try:
		_write(
			recipient_name,
			status="sent",
			wamid=wamid,
			message_status=(result or {}).get("message_status") or None,
			sent_at=now_datetime(),
			error_code=None,
			error_message=None,
		)
	except Exception:
		# the message is out; never leave the row claimable. Roll back and force unknown (+wamid) once more.
		return _mark_unknown(recipient_name, "Sent, but the result could not be recorded.", wamid=wamid)
	return "sent"


def _mark_unknown(name: str, message: str, wamid: str | None = None) -> str:
	fields: dict[str, Any] = {"status": "unknown", "error_message": message[:500]}
	if wamid:
		fields["wamid"] = wamid
	try:
		frappe.db.rollback()
	except Exception:
		pass
	_write(name, **fields)  # if this also raises the row stays `sending`; resume_stale turns it into unknown
	return "unknown"


def _after_bridge_error(name: str, attempts: int, payload: dict[str, Any]) -> str:
	code = str(payload.get("error") or "")
	graph_code = payload.get("graph_code")
	message = str(payload.get("message") or code or "Send failed.")[:500]

	if graph_code is None:
		if code in _SKIP_CODES:
			_write(name, status="skipped", skip_reason=code)
			return "skipped"
		if code == "gateway_disconnected":
			frappe.flags.broadcast_pause = "gateway_disconnected"
			_write(name, status="deferred", next_attempt_at=_later(GATEWAY_DOWN_DEFER_SECONDS), error_message=message)
			return "deferred"
		if code == "send_failed":
			# no Graph answer: timeout, dropped connection or an unreadable response. It may have been delivered.
			return _mark_unknown(name, message)
		# policy / validation refusal raised before any POST
		if code == "template_not_approved":
			frappe.flags.broadcast_pause = "template_not_approved"
		_write(name, status="failed", failed_at=now_datetime(), error_message=message)
		return "failed"

	cls = _classify(payload)
	ecode = cls.get("code")
	common = {"error_code": ecode, "error_message": message}

	if errors.should_defer_24h(ecode):
		_write(name, status="deferred", next_attempt_at=_later(DEFER_24H_SECONDS), **common)
		return "deferred"

	if errors.is_pause_signal(ecode):
		frappe.flags.broadcast_pause = f"meta_error_{ecode}"

	if cls.get("retryable") and attempts < MAX_ATTEMPTS:
		delay = errors.backoff_seconds(cls, attempts) or 60
		_write(name, status="deferred", next_attempt_at=_later(delay), **common)
		return "deferred"

	_write(name, status="failed", failed_at=now_datetime(), **common)
	return "failed"
