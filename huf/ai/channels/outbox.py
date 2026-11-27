# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Channel outbox (H-W2-15): a queued flow send, its retry classes and the delivery error shape.

Retry classes (:func:`classify`):

- ``transient``: the channel may accept it later (rate limit, server error, timeout). Retried with
  exponential backoff up to :data:`MAX_ATTEMPTS`, then final as ``permanent`` with ``retry_exhausted``.
- ``permanent``: retrying will not help (bad recipient, template rejected, no authority). Final, no retry.
- ``blocked``: a guard or binder block (G2). Never enqueued; a block found at delivery (the binder runs
  again there, CONTRACTS.md section 7) is final with the cap slot already spent.

Delivery error shape (:func:`delivery_error`): ``{"class", "code", "kind"}``. No message text, phone or
value (G4). A row stores token names and the step's references (``recipient_ref``, ``text_ref``); the
recipient, text and token values are resolved again from the run at delivery and handed only to the
transport. The step key (H-W2-13) is the unique row key and the transport idempotency token, so a
re-delivered job never makes a second transport effect for a row already sent (G5).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import frappe
from frappe.utils import add_to_date, now_datetime

from huf.ai.channels import guard_steps, token_binder

DOCTYPE = "Channel Outbox"
TRANSIENT, PERMANENT, BLOCKED = "transient", "permanent", "blocked"
MAX_ATTEMPTS = 5
BACKOFF_BASE_S = 30
BACKOFF_MAX_S = 3600
RETRY_EXHAUSTED = "retry_exhausted"
NOT_ACCEPTED = "not_accepted"
DELIVERABLE = ("Queued", "Retrying", "Sending")  # Sending = a worker died mid-delivery


class LiteralRecipient(ValueError):
	"""The step names a phone number itself; the outbox stores references only (G4)."""


def classify(error: Any) -> str:
	"""The retry class of ``error``: a reason code string (guard/binder block), a classification dict, or an exception."""
	if isinstance(error, str) or isinstance(error, token_binder.TokenUnbound):
		return BLOCKED
	classification = error if isinstance(error, dict) else _classify_exception(error)
	return TRANSIENT if classification.get("retryable") else PERMANENT


def delivery_error(error: Any) -> dict:
	"""``{"class", "code", "kind"}`` for ``error``; codes and kinds only, never message text (G4)."""
	if isinstance(error, token_binder.TokenUnbound):
		return {"class": BLOCKED, "code": token_binder.TOKEN_UNBOUND, "kind": "guard"}
	if isinstance(error, str):
		return {"class": BLOCKED, "code": error, "kind": "guard"}
	classification = error if isinstance(error, dict) else _classify_exception(error)
	code = classification.get("code")
	return {
		"class": TRANSIENT if classification.get("retryable") else PERMANENT,
		"code": str(code) if code is not None else str(classification.get("kind") or "unknown"),
		"kind": str(classification.get("kind") or "unknown"),
	}


def backoff_seconds(attempts: int) -> int:
	"""Delay before attempt ``attempts + 1``: 30 s doubling, capped at one hour."""
	return min(BACKOFF_BASE_S * 2 ** max(attempts - 1, 0), BACKOFF_MAX_S)


def enqueue(request: dict, *, deliver_now: bool = True) -> str:
	"""Queue an allowed send; the row name. The same ``step_key`` gives the same row (a re-run queues nothing).

	``request``: ``step_key``, ``run_id``, ``node_id``, ``member_key``, ``gateway``, ``channel``,
	``category``, ``template``, ``language``, ``recipient_ref``, ``text_ref``, ``token_names``, ``header``.
	Only a guard-allowed send comes here: a blocked send is final and never enqueued (G2).
	"""
	step_key = request.get("step_key")
	if not step_key:
		raise ValueError("step_key")
	if guard_steps.normalise_recipient(request.get("recipient_ref")):
		raise LiteralRecipient("recipient_ref")
	existing = frappe.db.get_value(DOCTYPE, {"step_key": step_key}, "name")
	if existing:
		return existing
	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"status": "Queued",
			"attempts": 0,
			"token_names": json.dumps(list(request.get("token_names") or [])),
			"header": json.dumps(request["header"]) if request.get("header") else None,
			**{
				key: request.get(key)
				for key in (
					"step_key",
					"run_id",
					"node_id",
					"member_key",
					"gateway",
					"channel",
					"category",
					"template",
					"language",
					"recipient_ref",
					"text_ref",
				)
			},
		}
	)
	try:
		doc.insert(ignore_permissions=True)
	except frappe.UniqueValidationError:
		return frappe.db.get_value(DOCTYPE, {"step_key": step_key}, "name")
	if deliver_now:
		frappe.enqueue(
			"huf.ai.channels.outbox.deliver",
			queue="short",
			name=doc.name,
			enqueue_after_commit=True,
			job_id=f"outbox:{step_key}",
			deduplicate=True,
		)
	return doc.name


def deliver(name: str, *, transport: Callable | None = None, resolver: Callable | None = None) -> str | None:
	"""Deliver one row once; its new status, or None when there was nothing to do.

	``transport(row, recipient, text, values)`` answers ``{"message_id": ...}`` or raises; ``resolver(row)``
	answers ``(recipient, text)``. Both default to the WhatsApp transport and the run's context.
	"""
	row = _claim(name)
	if row is None:
		return None
	token_names = json.loads(row.token_names or "[]")
	values: dict = {}
	if token_names:
		try:
			if not row.member_key:
				raise token_binder.TokenUnbound(token_names)  # noqa: TRY301
			values = token_binder.bind(row.template or "", token_names, row.member_key, _refs(row))
		except token_binder.TokenUnbound as exc:
			return _finish(row, "Blocked", delivery_error(exc))
	try:
		recipient, text = (resolver or resolve_from_run)(row)
		answer = (transport or whatsapp_transport)(row, recipient, text, values)
	except Exception as exc:  # noqa: BLE001 - every transport error is classified
		return _failed_attempt(row, delivery_error(exc))
	finally:
		values = {}
	message_id = (answer or {}).get("message_id") if isinstance(answer, dict) else None
	if isinstance(answer, dict) and answer.get("success") is False:
		return _failed_attempt(row, {"class": PERMANENT, "code": NOT_ACCEPTED, "kind": "unknown"})
	return _finish(row, "Sent", None, provider_message_id=message_id)


def retry_due(limit: int = 500) -> int:
	"""Enqueue delivery of rows whose backoff has passed and of rows left in Sending by a dead worker. Scheduler job."""
	stale = add_to_date(now_datetime(), minutes=-10)
	names = frappe.get_all(
		DOCTYPE,
		filters=[["status", "=", "Retrying"], ["next_attempt_at", "<=", now_datetime()]],
		pluck="name",
		limit=limit,
	) + frappe.get_all(
		DOCTYPE, filters=[["status", "=", "Sending"], ["modified", "<", stale]], pluck="name", limit=limit
	)
	for row_name in names:
		step_key = frappe.db.get_value(DOCTYPE, row_name, "step_key")
		frappe.enqueue(
			"huf.ai.channels.outbox.deliver",
			queue="short",
			name=row_name,
			job_id=f"outbox:{step_key}",
			deduplicate=True,
		)
	return len(names)


def on_delivery_status(gateway=None, provider_message_id=None, status=None, error_code=None, **_):
	"""``huf_gateway_delivery_status`` handler: mirror the provider status onto the row. Never raises."""
	try:
		if not provider_message_id or not status:
			return
		name = frappe.db.get_value(DOCTYPE, {"provider_message_id": provider_message_id}, "name")
		if name:
			frappe.db.set_value(
				DOCTYPE,
				name,
				{
					"delivery_status": str(status)[:40],
					**({"error_code": str(error_code)[:80]} if error_code else {}),
				},
				update_modified=False,
			)
	except Exception as exc:  # noqa: BLE001 - a status hook never raises
		frappe.logger("huf.outbox").warning("delivery status: %s", type(exc).__name__)


def resolve_from_run(row) -> tuple[str | None, str | None]:
	"""The recipient and text of ``row`` resolved from its run's context, at delivery only."""
	from huf.ai.flow.engine import _context_of

	flow_run = frappe.get_doc("Agent Flow Run", row.run_id)
	ctx = _context_of(flow_run, None)
	raw = ctx.resolve(row.recipient_ref)
	recipient = guard_steps.normalise_recipient(raw) or (raw if isinstance(raw, str) else None)
	text = ctx.resolve(row.text_ref) if row.text_ref else None
	return recipient, (str(text) if text is not None else None)


def whatsapp_transport(row, recipient, text, values) -> dict:
	"""Send ``row`` on WhatsApp; ``{"message_id"}`` or raise (classified by :func:`delivery_error`)."""
	from huf.ai.flow.nodes.send import _body_params
	from huf.ai.gateway_adapters import whatsapp_bridge as bridge
	from huf.ai.whatsapp import management

	if row.channel != "whatsapp":
		raise ValueError("channel")
	if management._send_authority(row.gateway):
		raise frappe.PermissionError("send_authority")
	account = frappe.db.get_value("Gateway", row.gateway, "whatsapp_account")
	phone = bridge.normalize_phone(recipient)
	if row.template:
		token_names = json.loads(row.token_names or "[]")
		header = json.loads(row.header) if row.header else None
		return bridge.send_template(
			account,
			phone,
			row.template,
			_body_params(token_names, values) if token_names else [],
			[header] if header else [],
			language_code=row.language or None,
			gateway_name=row.gateway,
			run_id=row.run_id,
			force_graph=True,
			redact_params=True,
		)
	return bridge.send_text(account, phone, str(text), gateway_name=row.gateway)


def _claim(name: str):
	"""Lock the row and mark it Sending, committing so a crash leaves it re-deliverable; None when not due."""
	frappe.db.sql("select name from `tabChannel Outbox` where name=%s for update", name)
	row = frappe.get_doc(DOCTYPE, name)
	if row.status not in DELIVERABLE:
		return None
	if row.status == "Retrying" and row.next_attempt_at and row.next_attempt_at > now_datetime():
		return None
	row.db_set({"status": "Sending", "attempts": (row.attempts or 0) + 1}, commit=True)
	return row


def _failed_attempt(row, error: dict) -> str:
	if error["class"] == TRANSIENT and row.attempts < MAX_ATTEMPTS:
		row.db_set(
			{
				"status": "Retrying",
				"error_class": TRANSIENT,
				"error_code": error["code"][:80],
				"next_attempt_at": add_to_date(now_datetime(), seconds=backoff_seconds(row.attempts)),
			},
			commit=True,
		)
		return "Retrying"
	if error["class"] == TRANSIENT:
		error = {"class": PERMANENT, "code": RETRY_EXHAUSTED, "kind": error["kind"]}
	return _finish(row, "Failed", error)


def _finish(row, status: str, error: dict | None, provider_message_id: str | None = None) -> str:
	values = {"status": status, "next_attempt_at": None}
	if error:
		values.update(error_class=error["class"], error_code=error["code"][:80])
	if provider_message_id:
		values["provider_message_id"] = str(provider_message_id)[:255]
	row.db_set(values, commit=True)
	return status


def _refs(row) -> dict:
	return {"flow_id": None, "flow_version": "", "run_id": row.run_id, "node_id": row.node_id}


def _classify_exception(exc: BaseException) -> dict:
	from huf.ai.gateway_adapters.whatsapp_parts.send_errors import classify_send_exception

	if isinstance(exc, frappe.PermissionError):
		return {"kind": "permission", "retryable": False, "code": "no_send_authority"}
	try:
		return classify_send_exception(exc)
	except Exception:  # noqa: BLE001 - unclassifiable is permanent
		return {"kind": "unknown", "retryable": False}
