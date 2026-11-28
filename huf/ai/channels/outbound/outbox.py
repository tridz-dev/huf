# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Channel outbox (H-W2-15): a queued flow send, its retry classes and the delivery error shape.

Retry classes (:func:`classify`):

- ``transient``: the message certainly did not reach the channel (connect error, rate limit, error
  answer) and it may accept it later. Retried with exponential backoff up to :data:`MAX_ATTEMPTS`, then
  final as ``permanent`` with ``retry_exhausted``.
- ``ambiguous``: the channel may have accepted it (read timeout, dropped connection, unreadable answer,
  a row left in Sending by a dead worker). Final, never sent again.
- ``permanent``: retrying will not help (bad recipient, template rejected, no authority). Final, no retry.
- ``blocked``: a guard or binder block (G2). Never enqueued; a block found at delivery is final with the
  cap slot already spent. Delivery runs the binder (CONTRACTS.md section 7), the Gateway switch, the live
  gate and the guard chain again, without a second cap claim. A closed send window parks the row.

Delivery error shape (:func:`delivery_error`): ``{"class", "code", "kind"}``. No message text, phone or
value (G4). A row stores token names and the step's references (``recipient_ref``, which may be
``"$member"``, and ``text_ref``); the
recipient, text and token values are resolved again from the run at delivery and handed only to the
transport. The step key (H-W2-13) is the unique row key, so a re-delivered job finds the row and never
posts it twice (G5). WhatsApp does not deduplicate; template sends carry the key as the opaque reference
echoed on status webhooks, for reconciliation only.

A cancelled run, a run a person marked as failed and a removed member send nothing more: :func:`withdraw`
closes their waiting rows, and a row being posted at that moment is not tried again.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from datetime import datetime, timezone

import frappe
from frappe.utils import add_to_date, convert_utc_to_system_timezone, get_datetime, now_datetime

from huf.ai.channels.outbound import button_tokens, guard, guard_steps, recipient_binder, token_binder
from huf.ai.channels.outbound.outbox_errors import (
	AMBIGUOUS,
	BLOCKED,
	MAX_ATTEMPTS,
	NOT_ACCEPTED,
	PERMANENT,
	RETRY_EXHAUSTED,
	TRANSIENT,
	LiteralRecipient,
	backoff_seconds,
	delivery_error,
)
from huf.ai.channels.outbound.outbox_errors import (  # noqa: F401 - re-exported, callers use outbox.<name>
	BACKOFF_BASE_S,
	BACKOFF_MAX_S,
	classify,
)

DOCTYPE = "Channel Outbox"
DELIVERABLE = ("Queued", "Retrying")
STALE_SENDING_MINUTES = 10
STALE_SENDING = "stale_sending"
GATEWAY_DISABLED = "gateway_disabled"
NOT_LIVE = "not_live"
RUN_CANCELLED = "run_cancelled"
RUN_FAILED = "run_failed"
MEMBER_REMOVED = "member_removed"
WITHDRAWN = (RUN_CANCELLED, RUN_FAILED, MEMBER_REMOVED)
FAILED_BY_PERSON = "failed_by_person"  # key in the run's ``waiting`` record
WINDOW_MAX_PARK_DAYS = 7  # a row has no deferral counter, so its age bounds the parking


def enqueue(request: dict, *, deliver_now: bool = True) -> str:
	"""Queue an allowed send; the row name. The same ``step_key`` gives the same row (a re-run queues nothing).

	``request``: ``step_key``, ``run_id``, ``node_id``, ``member_key``, ``gateway``, ``channel``,
	``category``, ``template``, ``language``, ``recipient_ref``, ``text_ref``, ``token_names``, ``header``.
	Only a guard-allowed send comes here: a blocked send is final and never enqueued (G2).
	"""
	step_key = request.get("step_key")
	if not step_key:
		raise ValueError("step_key")
	recipient_ref = recipient_binder.encode_ref(request.get("recipient_ref"))
	if guard_steps.normalise_recipient(recipient_ref):
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
					"text_ref",
				)
			},
			"recipient_ref": recipient_ref,
		}
	)
	try:
		doc.insert(ignore_permissions=True)
	except frappe.UniqueValidationError:
		return frappe.db.get_value(DOCTYPE, {"step_key": step_key}, "name")
	if deliver_now:
		frappe.enqueue(
			"huf.ai.channels.outbound.outbox.deliver",
			queue="short",
			name=doc.name,
			enqueue_after_commit=True,
			job_id=f"outbox:{step_key}",
			deduplicate=True,
		)
	return doc.name


def deliver(name: str, *, transport: Callable | None = None, resolver: Callable | None = None) -> str | None:
	"""Deliver one row once; its new status, or None when there was nothing to do.

	The guard is checked again here: the row may have been queued long before.

	``transport(row, recipient, text, values)`` answers ``{"message_id": ...}`` or raises; ``resolver(row)``
	answers ``(recipient, text)``. Both default to the WhatsApp transport and the run's context.
	"""
	row = _claim(name)
	if row is None:
		return None
	if row.status != "Sending":  # closed by the claim
		return row.status
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
	except recipient_binder.RecipientUnbound as exc:
		values = {}
		return _finish(row, "Blocked", delivery_error(exc))
	except Exception as exc:  # noqa: BLE001 - classified like a transport error
		values = {}
		return _failed_attempt(row, delivery_error(exc, posting=False))
	verdict = _blocked_now(row, recipient)
	if isinstance(verdict, datetime):
		return _park(row, verdict)
	if verdict:
		values = {}
		return _finish(row, "Blocked", delivery_error(verdict))
	try:
		answer = (transport or whatsapp_transport)(row, recipient, text, values)
	except Exception as exc:  # noqa: BLE001 - every transport error is classified
		return _failed_attempt(row, delivery_error(exc))
	finally:
		values = {}
	message_id = (answer or {}).get("message_id") if isinstance(answer, dict) else None
	if isinstance(answer, dict) and answer.get("success") is False:
		return _failed_attempt(row, {"class": PERMANENT, "code": NOT_ACCEPTED, "kind": "unknown"})
	return _finish(row, "Sent", None, provider_message_id=message_id)


def withdraw(run_ids: list[str], code: str) -> None:
	"""Close the waiting rows of these runs as Blocked with ``code``. The caller commits.

	A row being posted now is only marked: if that post would be tried again, it is closed instead.
	"""
	if not run_ids:
		return
	names = frappe.get_all(
		DOCTYPE,
		filters={"run_id": ["in", run_ids], "status": ["in", [*DELIVERABLE, "Sending"]]},
		pluck="name",
		limit_page_length=0,
	)
	for name in names:
		status = frappe.db.get_value(DOCTYPE, name, "status", for_update=True)
		if status in DELIVERABLE:
			values = {
				"status": "Blocked",
				"next_attempt_at": None,
				"error_class": BLOCKED,
				"error_code": code,
			}
			frappe.db.set_value(DOCTYPE, name, values)
		elif status == "Sending":
			# ``modified`` stays: it dates the claim, which closes a dead worker's row
			frappe.db.set_value(DOCTYPE, name, "error_code", code, update_modified=False)


def retry_due(limit: int = 500) -> int:
	"""Enqueue rows whose backoff has passed, and rows left in Sending so :func:`deliver` closes them. Scheduler job."""
	stale = add_to_date(now_datetime(), minutes=-STALE_SENDING_MINUTES)
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
			"huf.ai.channels.outbound.outbox.deliver",
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
		row = frappe.db.get_value(
			DOCTYPE,
			{"provider_message_id": provider_message_id},
			["name", "delivery_status", "error_code"],
			as_dict=True,
		)
		if not row:
			return
		values = {"delivery_status": str(status)[:40]}
		if error_code:
			values["error_code"] = str(error_code)[:80]
		# a duplicate webhook writes nothing, so ``modified`` moves only for a change reports must pick up
		if any(row[key] != value for key, value in values.items()):
			frappe.db.set_value(DOCTYPE, row.name, values)
	except Exception as exc:  # noqa: BLE001 - a status hook never raises
		frappe.logger("huf.outbox").warning("delivery status: %s", type(exc).__name__)


def resolve_from_run(row) -> tuple[str | None, str | None]:
	"""The recipient and text of ``row`` resolved from its run's context, at delivery only."""
	from huf.ai.flow.engine import _context_of

	flow_run = frappe.get_doc("Agent Flow Run", row.run_id)
	ctx = _context_of(flow_run, None)
	if recipient_binder.is_member_ref(row.recipient_ref):
		raw = recipient_binder.resolve(row.gateway, row.member_key, _refs(row, flow_run))
	else:
		raw = ctx.resolve(recipient_binder.decode_ref(row.recipient_ref))
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
		buttons = button_tokens.required_buttons(row.gateway, row.template)
		body_names, button_params = button_tokens.split(token_names, buttons, values)
		return bridge.send_template(
			account,
			phone,
			row.template,
			_body_params(body_names, values, named=template_is_named(row.template)) if body_names else [],
			[header] if header else [],
			button_params=button_params or None,
			language_code=row.language or None,
			gateway_name=row.gateway,
			run_id=row.run_id,
			force_graph=True,
			redact_params=True,
			opaque_ref=row.step_key,
		)
	return bridge.send_text(account, phone, str(text), gateway_name=row.gateway)


def _blocked_now(row, recipient) -> str | datetime | None:
	"""None to send, a block code, or the moment the send window opens. Never raises: an error blocks."""
	try:
		if not frappe.db.get_value("Gateway", row.gateway, "is_enabled"):
			return GATEWAY_DISABLED
		from huf.ai.flow.testrun import gate

		flow_run = frappe.get_doc("Agent Flow Run", row.run_id)
		ended = _ended_by_person(flow_run)
		if ended:
			return ended
		if not gate.is_live(flow_run):
			return NOT_LIVE
		request = {
			"member_key": row.member_key,
			"gateway": row.gateway,
			"channel": row.channel,
			"category": row.category,
			"recipient": recipient,
			"template": row.template or None,
			"token_names": json.loads(row.token_names or "[]"),
			**_refs(row, flow_run),
			"step_key": row.step_key,
			"live": True,
		}
		return _recheck(request, json.loads(row.header) if row.header else None)
	except Exception as exc:  # noqa: BLE001 - fail closed
		frappe.logger("huf.outbox").warning("delivery guard: %s", type(exc).__name__)
		return guard.HOOK_ERROR


def _ended_by_person(flow_run) -> str | None:
	"""The block code of a run that was cancelled or marked as failed; a finished or crashed run still delivers."""
	from huf.ai.flow.runs.park import _waiting

	status = getattr(flow_run, "status", None)
	if status == "Cancelled":
		return RUN_CANCELLED
	if status == "Failed" and _waiting(flow_run).get(FAILED_BY_PERSON):
		return RUN_FAILED
	return None


def _close_if_withdrawn(row) -> str | None:
	"""Close a row :func:`withdraw` marked while it was being posted, instead of trying it again."""
	code = frappe.db.get_value(DOCTYPE, row.name, "error_code", for_update=True)
	return _finish(row, "Blocked", delivery_error(code)) if code in WITHDRAWN else None


def _recheck(request: dict, header: dict | None) -> str | datetime | None:
	"""``guard.evaluate`` without its last step: the cap slot was claimed at enqueue.

	``evaluate`` has no way to leave the cap out (a claim would count twice, a look would see this send's own
	slot), so this walks the same steps in the same order with the same runner.
	"""
	seconds = guard._timeout(None)
	consent_hooks = guard._consent_hook_paths()
	hooks = guard._hook_paths()
	resolvers = guard_steps.window_resolvers()
	for name, step, args in guard._leading_steps(request, header, consent_hooks):
		reason = guard._run_step(name, step or frappe.get_attr(name), copy.deepcopy(args), seconds)
		if reason:
			return reason
	if resolvers:
		reason, defer_until = guard._window_step(copy.deepcopy(request), resolvers, seconds)
		if reason or defer_until:
			return reason or defer_until
	for path in hooks:
		reason = guard._run_step(path, frappe.get_attr(path), copy.deepcopy(request), seconds)
		if reason:
			return reason
	return None


def _park(row, defer_until: datetime) -> str:
	"""Outside the send window: try again when it opens. Nothing was posted, so no attempt is spent."""
	if get_datetime(row.creation) < add_to_date(now_datetime(), days=-WINDOW_MAX_PARK_DAYS):
		return _finish(row, "Blocked", delivery_error("window_defer_exhausted"))
	if withdrawn := _close_if_withdrawn(row):
		return withdrawn
	utc = defer_until.astimezone(timezone.utc).replace(tzinfo=None)
	row.db_set(
		{
			"status": "Retrying",
			"attempts": row.attempts - 1,
			"next_attempt_at": convert_utc_to_system_timezone(utc).replace(tzinfo=None),
		},
		commit=True,
	)
	return "Retrying"


def _claim(name: str):
	"""Lock the row and mark it Sending, committing before anything is posted; None when not due.

	A row left in Sending by a dead worker may already have been posted: it is closed as ambiguous.
	"""
	frappe.db.sql("select name from `tabChannel Outbox` where name=%s for update", name)
	row = frappe.get_doc(DOCTYPE, name)
	if row.status == "Sending" and get_datetime(row.modified) < add_to_date(
		now_datetime(), minutes=-STALE_SENDING_MINUTES
	):
		_finish(row, "Failed", {"class": AMBIGUOUS, "code": STALE_SENDING, "kind": "unknown"})
		return row
	if row.status not in DELIVERABLE:
		return None
	if row.status == "Retrying" and row.next_attempt_at and row.next_attempt_at > now_datetime():
		return None
	row.db_set({"status": "Sending", "attempts": (row.attempts or 0) + 1}, commit=True)
	return row


def _failed_attempt(row, error: dict) -> str:
	if error["class"] == TRANSIENT and row.attempts < MAX_ATTEMPTS:
		if withdrawn := _close_if_withdrawn(row):
			return withdrawn
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


def template_is_named(template: str | None) -> bool:
	"""Whether the WhatsApp template takes NAMED parameters; positional (a list) when unknown."""
	from huf.ai.gateway_adapters import whatsapp_bridge as bridge

	if not template:
		return False
	row = bridge._template_row(template) or {}
	return str(row.get("parameter_format") or "").upper() == "NAMED"


def _refs(row, flow_run=None) -> dict:
	"""All four binder context keys of ``row`` (CONTRACTS.md section 7), read from its run."""
	if flow_run is None and row.run_id:
		flow = frappe.db.get_value("Agent Flow Run", row.run_id, ["flow_id", "flow_version"], as_dict=True)
	else:
		flow = flow_run
	return {
		"flow_id": getattr(flow, "flow_id", None) if flow else None,
		"flow_version": str((getattr(flow, "flow_version", "") if flow else "") or ""),
		"run_id": row.run_id,
		"node_id": row.node_id,
	}


