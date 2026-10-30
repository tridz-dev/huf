# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WhatsApp Broadcast: scheduled start and retry of failed recipients.

Scheduling: ``Draft -> Scheduled`` (``scheduled_at``/``scheduled_by`` set, warnings acknowledged, recipients locked
because edits are Draft-only). The ``*/5`` cron ``start_due`` starts due rows through ``runner._begin`` (the same path
as ``runner.start``: preview checks, consent attestation, one-running, kill switch, allow-list and opt-out at send time),
acting as ``scheduled_by``. The site stop flag ``wa_broadcast_emergency_stop`` (site config) blocks every scheduled
start; the per-Gateway kill switch (``pause_all_broadcasts``) returns that Gateway's Scheduled rows to Draft.

Retry: a NEW Draft broadcast (same template/params/limits) with the retryable failed rows; it must be attested and
started like any other broadcast. The original is never reopened.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import get_datetime, now_datetime

from huf.ai.gateway_adapters import whatsapp_errors as errors
from huf.ai.whatsapp.broadcast import limits as broadcast_limits, policy, runner
from huf.ai.whatsapp.broadcast.api import (
	_bridge_guard,
	_broadcast_audit,
	_is_api_key_caller,
	_queued_count,
	_require_broadcast_write,
)
from huf.ai.whatsapp.broadcast.checks import start_gate
from huf.ai.whatsapp.management import _error

BROADCAST = runner.BROADCAST
RECIPIENT = runner.RECIPIENT
STOP_FLAG = "wa_broadcast_emergency_stop"
# Refusals that describe the moment: the broadcast stays Scheduled and is tried again on the next cron.
_TRANSIENT = frozenset({"another_broadcast_running", "uncommitted_writes"})


def emergency_stop_active() -> bool:
	return bool(frappe.conf.get(STOP_FLAG))


def schedule(broadcast: str, scheduled_at, user: str, override_warnings: list[str] | None = None) -> dict:
	when = get_datetime(scheduled_at)
	if when <= now_datetime():
		raise start_gate.StartRefused("scheduled_in_past", _("Schedule a time in the future (site timezone)."))
	doc = frappe.get_doc(BROADCAST, broadcast)
	if doc.status != "Draft":
		raise start_gate.StartRefused("not_draft", _("Only a Draft broadcast can be scheduled."))
	from huf.ai.whatsapp.broadcast import policy

	if policy.get("require_consent_attestation") and not doc.consent_attested:
		raise start_gate.StartRefused("consent_not_attested", _("Recipient consent must be attested before scheduling"))
	preview = broadcast_limits.preview(broadcast) or {}
	deferred = int(frappe.db.count(RECIPIENT, {"broadcast": broadcast, "status": "deferred"}) or 0)
	acknowledged = start_gate.check_preview(preview, deferred, override_warnings or [])
	start_gate.record_acknowledged(broadcast, acknowledged)
	frappe.db.set_value(BROADCAST, broadcast, {"status": "Scheduled", "scheduled_at": when, "scheduled_by": user})
	return {"broadcast": broadcast, "status": "Scheduled", "scheduled_at": str(when)}


def unschedule(broadcast: str) -> dict:
	if frappe.db.get_value(BROADCAST, broadcast, "status") != "Scheduled":
		raise start_gate.StartRefused("not_scheduled", _("This broadcast is not scheduled."))
	frappe.db.set_value(BROADCAST, broadcast, {"status": "Draft", "scheduled_at": None, "scheduled_by": None})
	return {"broadcast": broadcast, "status": "Draft"}


def hold_scheduled(gateway: str, reason: str = "kill_switch") -> list[str]:
	"""Kill switch: Scheduled broadcasts of the Gateway go back to Draft (they do not start on their own later)."""
	names = frappe.get_all(BROADCAST, filters={"gateway": gateway, "status": "Scheduled"}, pluck="name")
	for name in names:
		frappe.db.set_value(
			BROADCAST, name, {"status": "Draft", "scheduled_at": None, "scheduled_by": None, "pause_reason": reason}
		)
	return names


def start_due() -> dict:
	"""Cron */5: start every Scheduled broadcast whose time has come. Nothing starts while the stop flag is set."""
	if emergency_stop_active():
		frappe.logger("huf.whatsapp.broadcast").info({"event": "scheduled_start_blocked", "reason": "emergency_stop"})
		return {"started": [], "blocked": "emergency_stop"}
	due = frappe.get_all(
		BROADCAST,
		filters={"status": "Scheduled", "scheduled_at": ["<=", now_datetime()]},
		fields=["name", "scheduled_by"],
		order_by="scheduled_at asc",
	)
	started: list[str] = []
	for row in due:
		name = row.name
		try:
			runner._begin(
				name,
				row.scheduled_by,
				allowed_from=("Scheduled",),
				override_warnings=sorted(start_gate.stored_acknowledged(name)),
			)
			started.append(name)
		except Exception as exc:
			code = getattr(exc, "code", None)
			frappe.db.rollback()
			if code in _TRANSIENT:
				continue
			frappe.db.set_value(
				BROADCAST, name,
				{"status": "Draft", "scheduled_at": None, "scheduled_by": None, "pause_reason": str(code or "scheduled_start_refused")[:140]},
			)
			frappe.db.commit()
			frappe.logger("huf.whatsapp.broadcast").info({"event": "scheduled_start_refused", "broadcast": name, "code": code})
	return {"started": started}


def is_retryable(row: dict) -> bool:
	"""A failed row with a Graph error code that the error taxonomy marks retryable.

	No code (policy/validation refusals raised before any send), permanent codes, and skipped rows
	(opted out, allow-list, per-user limit, ...) are never retried; ``unknown`` rows may have been delivered."""
	if row.get("status") != "failed":
		return False
	code = int(row.get("error_code") or 0)
	if not code:
		return False
	return bool(errors.classify({"error": {"code": code}}).get("retryable"))


def retry_failed(broadcast: str) -> dict:
	"""Create a Draft broadcast holding the retryable failed rows of ``broadcast``."""
	from huf.ai.whatsapp.broadcast import recipients as br

	src = frappe.get_doc(BROADCAST, broadcast)
	if src.status not in ("Completed", "Cancelled", "Paused", "Failed"):
		raise start_gate.StartRefused("not_finished", _("Retry is available once the broadcast has stopped."))
	failed = frappe.get_all(
		RECIPIENT, filters={"broadcast": broadcast, "status": "failed"},
		fields=["recipient", "params", "error_code", "status", "consent_source", "consent_at", "audience"],
	)
	rows = []
	for r in failed:
		if not is_retryable(r):
			continue
		params = None
		if r.params:
			try:
				params = json.loads(r.params)
			except ValueError:
				params = None
		rows.append({
			"recipient": r.recipient, "params": params if isinstance(params, dict) else None,
			"consent_source": r.consent_source, "consent_at": r.consent_at,
		})
	if not rows:
		raise start_gate.StartRefused("nothing_to_retry", _("No retryable failed recipients."))
	prev = frappe.flags.get("in_broadcast_api")
	frappe.flags.in_broadcast_api = True
	try:
		new = frappe.get_doc({
			"doctype": BROADCAST, "title": f"{src.title} (retry)"[:140], "status": "Draft", "gateway": src.gateway,
			"whatsapp_account": src.whatsapp_account, "template": src.template, "template_name": src.template_name,
			"language_code": src.language_code, "category": src.category, "send_via": src.send_via,
			"body_params": src.body_params, "header_params": src.header_params, "button_params": src.button_params,
			"consent_source": src.consent_source, "consent_attested": 0,
			"max_recipients": src.max_recipients, "mps": src.mps,
		}).insert(ignore_permissions=True, ignore_links=True)
		result = br.prepare(new.name, rows)  # re-applies opt-out / allow-list / marketing policy
	finally:
		frappe.flags.in_broadcast_api = prev
	return {"broadcast": new.name, "retried_from": broadcast, "added": result.get("added"), "skipped_total": result.get("skipped_total")}


# --- API (whitelisted) ----------------------------------------------------------------------------

@frappe.whitelist(methods=["POST"])
@rate_limit(limit=policy.rate("rate_start_broadcast"), seconds=60)
@_bridge_guard
def schedule_broadcast(
	broadcast: str | None = None, scheduled_at: Any = None, confirm_count: Any = None, override_warnings: Any = None
) -> dict[str, Any]:
	"""Schedule a Draft broadcast to start at ``scheduled_at`` (site timezone). Same gate and confirmation as ``start_broadcast``."""
	row = _require_broadcast_write(broadcast)
	if row.get("error"):
		return row
	acknowledged = start_gate.parse_override_warnings(override_warnings)
	if acknowledged is None:
		return _error("invalid_override_warnings", "override_warnings must be a JSON list of warning codes.")
	try:
		frappe.utils.get_datetime(scheduled_at)
	except Exception:
		return _error("invalid_scheduled_at", "scheduled_at must be a date and time.")
	queued = _queued_count(broadcast)
	if queued <= 0:
		return _error("no_recipients", "There are no queued recipients.")
	if policy.get("require_typed_count") and not _is_api_key_caller():
		if str(confirm_count if confirm_count is not None else "").strip() != str(queued):
			return _error("confirm_mismatch", f"Type the number of queued recipients ({queued}) to confirm.")
	try:
		result = schedule(broadcast, scheduled_at, frappe.session.user, acknowledged)
	except start_gate.StartRefused as exc:
		return {"success": False, "error": exc.code, "message": str(exc), **exc.extra}
	_broadcast_audit(broadcast, "scheduled", scheduled_at=result.get("scheduled_at"))
	return {"success": True, **result}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=policy.rate("rate_cancel_broadcast"), seconds=60)
@_bridge_guard
def unschedule_broadcast(broadcast: str | None = None) -> dict[str, Any]:
	"""Return a Scheduled broadcast to Draft."""
	row = _require_broadcast_write(broadcast)
	if row.get("error"):
		return row
	try:
		result = unschedule(broadcast)
	except start_gate.StartRefused as exc:
		return {"success": False, "error": exc.code, "message": str(exc), **exc.extra}
	_broadcast_audit(broadcast, "unscheduled")
	return {"success": True, **result}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=policy.rate("rate_create_broadcast"), seconds=60)
@_bridge_guard
def retry_failed_recipients(broadcast: str | None = None) -> dict[str, Any]:
	"""New Draft broadcast with the retryable failed recipients (never opted-out, allow-list or policy refusals)."""
	row = _require_broadcast_write(broadcast)
	if row.get("error"):
		return row
	try:
		result = retry_failed(broadcast)
	except start_gate.StartRefused as exc:
		return {"success": False, "error": exc.code, "message": str(exc), **exc.extra}
	_broadcast_audit(result["broadcast"], "retry_created", retried_from=broadcast, added=result.get("added"))
	return {"success": True, **result}
