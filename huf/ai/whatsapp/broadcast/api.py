# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WhatsApp Broadcast: whitelisted API (create, recipients, consent, preview, start, pause, cancel, list).

Guard helpers are shared with ``huf.ai.whatsapp.management``.
"""

from __future__ import annotations

import json
import random
import re
import time
from typing import Any

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from huf.ai.whatsapp.management import (
	_bridge_guard,
	_error,
	_send_authority as _require_send_authority,
	_gateway_write_allowed,
	_gateway_read_allowed,
	_gateway_whatsapp_account,
	_TEMPLATE_RECORD_RE,
	_parse_json_arg,
	_iso,
)
from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.whatsapp.broadcast import params as broadcast_params, policy
from huf.ai.whatsapp.broadcast.checks import start_gate


# --- Broadcast (WP-7) ----------------------------------------------------------------------------
# Thin API over broadcast_recipients / broadcast_limits / broadcast_cost / broadcast_runner. Those
# modules are imported lazily inside each function so that a problem there never breaks this module.
#
# Scheduling and retry (``retry_failed_recipients``: only retryable ``failed`` rows go into a NEW Draft that must be
# attested and started again) live in ``broadcast.schedule``.

_BROADCAST = "WhatsApp Broadcast"
_BROADCAST_RECIPIENT = "WhatsApp Broadcast Recipient"
_BROADCAST_LOG = "huf.whatsapp.broadcast"
_BROADCAST_COUNT_FIELDS = (
	"total", "queued", "sending", "sent", "delivered", "read", "failed", "deferred", "unknown", "skipped",
)
_BROADCAST_FIELDS = (
	"name", "title", "status", "pause_reason", "gateway", "whatsapp_account", "template", "template_name",
	"language_code", "category", "body_params", "header_params", "button_params", "consent_source",
	"consent_attested", "consent_attested_by", "consent_attested_at", "max_recipients", "mps", "send_via",
	"scheduled_at", "started_by", "started_at", "finished_at", "creation", "modified", *_BROADCAST_COUNT_FIELDS,
)


def _broadcast_row(broadcast: Any) -> dict[str, Any] | dict[str, str]:
	"""The Broadcast's fields as a dict, or an error dict when it does not exist."""
	if not broadcast or not frappe.db.exists(_BROADCAST, broadcast):
		return _error("not_found", "Broadcast not found.")
	return frappe.db.get_value(_BROADCAST, broadcast, list(_BROADCAST_FIELDS), as_dict=True) or _error(
		"not_found", "Broadcast not found."
	)


def _require_broadcast_write(broadcast: Any) -> dict[str, Any]:
	"""Broadcast row after proving WRITE authority on ITS gateway (never trust a caller-supplied gateway)."""
	row = _broadcast_row(broadcast)
	if row.get("error"):
		return row
	if not _gateway_write_allowed(row.get("gateway")):
		raise frappe.PermissionError(_("Not permitted to manage broadcasts on this Gateway"))
	return row


def _require_broadcast_read(broadcast: Any) -> dict[str, Any]:
	row = _broadcast_row(broadcast)
	if row.get("error"):
		return row
	if not _gateway_read_allowed(row.get("gateway")):
		raise frappe.PermissionError(_("Not permitted to read broadcasts on this Gateway"))
	return row


def _broadcast_audit(broadcast: str, action: str, **details: Any) -> None:
	"""Audit every mutation: structured log line plus a Comment on the Broadcast."""
	user = getattr(frappe.session, "user", None)
	extra = ", ".join(f"{k}={v}" for k, v in details.items() if v not in (None, ""))
	frappe.logger(_BROADCAST_LOG).info(f"broadcast={broadcast} action={action} user={user} {extra}".strip())
	try:
		frappe.get_doc(_BROADCAST, broadcast).add_comment("Info", f"{action} by {user}" + (f": {extra}" if extra else ""))
	except Exception:
		frappe.logger(_BROADCAST_LOG).warning(f"broadcast={broadcast} action={action}: audit comment failed")


def _broadcast_view(row: dict[str, Any]) -> dict[str, Any]:
	out = {k: row.get(k) for k in _BROADCAST_FIELDS if k not in _BROADCAST_COUNT_FIELDS}
	out["counts"] = {k: int(row.get(k) or 0) for k in _BROADCAST_COUNT_FIELDS}
	for key in ("body_params", "header_params", "button_params"):
		value = out.get(key)
		if isinstance(value, str) and value:
			try:
				out[key] = json.loads(value)
			except ValueError:
				pass
	for key in ("creation", "modified", "scheduled_at", "started_at", "finished_at", "consent_attested_at"):
		out[key] = _iso(out.get(key))
	return out


def _queued_count(broadcast: str) -> int:
	"""Recipients still to send (queued + deferred): same set as broadcast_cost.confirm_token and the runner."""
	return int(frappe.db.count(_BROADCAST_RECIPIENT, {"broadcast": broadcast, "status": ["in", ["queued", "deferred"]]}) or 0)


def _mask_phone(value: Any) -> Any:
	text = str(value or "")
	return ("*" * max(len(text) - 4, 0) + text[-4:]) if text else value


_LONG_DIGITS_RE = re.compile(r"\d{7,}")


def _mask_digits(text: Any) -> Any:
	return _LONG_DIGITS_RE.sub(lambda m: _mask_phone(m.group(0)), text) if isinstance(text, str) else text


def _json_param(value: Any, label: str) -> Any:
	parsed = _parse_json_arg(value, label)
	return parsed if parsed not in ("", None) else None


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=policy.rate("rate_create_broadcast"), seconds=60)
@_bridge_guard
def create_broadcast(
	gateway: str | None = None,
	template: str | None = None,
	title: str | None = None,
	language_code: str | None = None,
	body_params: Any = None,
	header_params: Any = None,
	button_params: Any = None,
	consent_source: str | None = None,
	max_recipients: Any = None,
	mps: Any = None,
	send_via: str | None = None,
) -> dict[str, Any]:
	"""Create a Draft broadcast on a Gateway. The template must be an APPROVED template of the Gateway's own account.

	Category, template name and account are snapshotted here; ``start`` re-checks them. Needs write authority on the Gateway.
	"""
	refused = _require_send_authority(gateway)
	if refused:
		return refused
	account = _gateway_whatsapp_account(gateway)
	if not account:
		return _error("no_account", "This gateway is not linked to a WhatsApp Account.")
	if not template or not _TEMPLATE_RECORD_RE.match(str(template).strip()):
		return _error("invalid_name", "Template must be the Meta name or '<name>-<language_code>'.")
	if not title or not str(title).strip():
		return _error("invalid_title", "A title is required.")
	from huf.ai.whatsapp.broadcast import recipients as br

	docname = bridge._template_docname(account, str(template).strip(), language_code or None)
	tpl = None
	if docname and frappe.db.exists("WhatsApp Templates", docname):
		tpl = frappe.db.get_value(
			"WhatsApp Templates",
			docname,
			["name", "whatsapp_account", "status", "category", "actual_name", "template_name", "language_code"],
			as_dict=True,
		)
	if not tpl or tpl.get("whatsapp_account") != account:
		return _error("template_not_found", "Template not found on this gateway's WhatsApp account.")
	if str(tpl.get("status") or "").upper() != "APPROVED":
		return _error("template_not_approved", f"Template status is {tpl.get('status') or 'unknown'}; only APPROVED templates can be broadcast.")
	send_via = (send_via or "messages").strip()
	if send_via not in ("messages", "marketing_messages"):
		return _error("invalid_send_via", "send_via must be 'messages' or 'marketing_messages'.")
	if send_via == "marketing_messages" and str(tpl.get("category") or "").upper() != "MARKETING":
		return _error("mm_requires_marketing_template", "The Marketing Messages API only accepts MARKETING templates.")
	try:
		body = _json_param(body_params, "body_params")
		header = _json_param(header_params, "header_params")
		buttons = _json_param(button_params, "button_params")
		problem = broadcast_params.header_error(header) or broadcast_params.button_error(buttons)
		if problem:
			return _error("invalid_params", problem)
		cap = int(max_recipients) if max_recipients not in (None, "") else None
		ceiling = policy.get("max_recipients_ceiling")
		if cap is not None and (cap < 1 or (ceiling is not None and cap > ceiling)):
			return _error(
				"invalid_max_recipients",
				f"max_recipients must be between 1 and {ceiling}." if ceiling is not None else "max_recipients must be at least 1.",
			)
		rate = int(mps) if mps not in (None, "") else None
	except (TypeError, ValueError) as exc:
		return _error("invalid_params", str(exc))
	frappe.flags.in_broadcast_api = True
	doc = frappe.get_doc(
		{
			"doctype": _BROADCAST,
			"title": str(title).strip(),
			"status": "Draft",
			"gateway": gateway,
			"whatsapp_account": account,
			"template": tpl.get("name"),
			"template_name": tpl.get("actual_name") or tpl.get("template_name") or tpl.get("name"),
			"language_code": language_code or tpl.get("language_code"),
			"category": tpl.get("category"),
			"body_params": json.dumps(body) if body is not None else None,
			"header_params": json.dumps(header) if header is not None else None,
			"button_params": json.dumps(buttons) if buttons is not None else None,
			"consent_source": (consent_source or "").strip() or None,
			"consent_attested": 0,
			"max_recipients": cap,
			"mps": rate,
			"send_via": send_via,
		}
	).insert(ignore_permissions=True)  # authority was proven by _send_authority above
	_broadcast_audit(doc.name, "created", gateway=gateway, template=tpl.get("name"), category=tpl.get("category"))
	return {"success": True, "broadcast": doc.name, "status": "Draft", "category": tpl.get("category")}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=policy.rate("rate_add_recipients"), seconds=60)
@_bridge_guard
def add_broadcast_recipients(broadcast: str | None = None, recipients: Any = None, csv_text: str | None = None) -> dict[str, Any]:
	"""Add recipients to a Draft broadcast, from a list (``["+1555..", {"recipient":..,"params":..}]``) or CSV text."""
	row = _require_broadcast_write(broadcast)
	if row.get("error"):
		return row
	if row.get("status") != "Draft":
		return _error("not_draft", "Recipients can only be added while the broadcast is a Draft.")
	from huf.ai.whatsapp.broadcast import recipients as br

	csv_mb = policy.get("max_csv_mb")
	if csv_text and len(str(csv_text).encode("utf-8")) > csv_mb * 1024 * 1024:
		return _error("csv_too_large", f"csv_text is limited to {csv_mb} MB.")
	per_request = policy.get("max_rows_per_request")
	try:
		items = _parse_json_arg(recipients, "recipients") or []
		if isinstance(items, list) and len(items) > per_request:
			return _error("too_many_recipients", f"At most {per_request} recipients per request.")
		if csv_text and str(csv_text).strip():
			items = list(items) + list(br.parse_csv(str(csv_text)))
	except ValueError as exc:
		return _error("invalid_params", str(exc))
	if not isinstance(items, list) or not items:
		return _error("no_recipients", "Provide recipients or csv_text.")
	if len(items) > per_request:
		return _error("too_many_recipients", f"At most {per_request} recipients per request.")
	rows = [{"recipient": str(i)} if not isinstance(i, dict) else i for i in items]
	prev = frappe.flags.get("in_broadcast_api")
	frappe.flags.in_broadcast_api = True  # recipient rows are insert-guarded; prepare() is the only writer
	result = None
	try:
		for attempt in range(policy.get("prepare_retries")):
			try:
				result = br.prepare(broadcast, rows)
				break
			except frappe.QueryDeadlockError:
				frappe.db.rollback()  # the whole prepare is idempotent (duplicates are skipped), so redo it
				if attempt < policy.get("prepare_retries") - 1:
					time.sleep(random.uniform(0.05, 0.25))
	finally:
		frappe.flags.in_broadcast_api = prev
	if result is None:
		return _error("busy_retry", "Another request is updating this broadcast; retry in a moment.")
	if row.get("consent_attested"):
		# the attestation covered a different list; the owner must re-attest
		frappe.flags.in_broadcast_api = True
		try:
			frappe.db.set_value(_BROADCAST, broadcast, {
				"consent_attested": 0, "consent_attested_by": None, "consent_attested_at": None,
			})
		finally:
			frappe.flags.in_broadcast_api = prev
		frappe.get_doc(_BROADCAST, broadcast).add_comment("Info", "attestation reset: recipients changed")
	_broadcast_audit(
		broadcast, "recipients_added",
		added=result.get("added"), skipped=result.get("skipped_total"), invalid=result.get("invalid_total"),
	)
	return {"success": True, **result}


def _reset_attestation(broadcast: str, why: str) -> None:
	"""The attestation covered a different recipient list; the owner must attest again."""
	prev = frappe.flags.get("in_broadcast_api")
	frappe.flags.in_broadcast_api = True
	try:
		frappe.db.set_value(_BROADCAST, broadcast, {
			"consent_attested": 0, "consent_attested_by": None, "consent_attested_at": None,
		})
	finally:
		frappe.flags.in_broadcast_api = prev
	frappe.get_doc(_BROADCAST, broadcast).add_comment("Info", f"attestation reset: {why}")


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=policy.rate("rate_remove_recipient"), seconds=60)
@_bridge_guard
def remove_broadcast_recipient(broadcast: str | None = None, recipient: str | None = None) -> dict[str, Any]:
	"""Remove one recipient (by number or row name) from a Draft broadcast. Started rows are the send record and stay."""
	row = _require_broadcast_write(broadcast)
	if row.get("error"):
		return row
	if row.get("status") != "Draft":
		return _error("not_draft", "Recipients can only be removed while the broadcast is a Draft.")
	if not recipient or not str(recipient).strip():
		return _error("invalid_recipient", "Name the recipient to remove.")
	from huf.ai.whatsapp.broadcast import recipients as br

	key = str(recipient).strip()
	normalized = br.normalize_recipient(key)
	candidates = ([f"{broadcast}-{normalized}"] if normalized else []) + [f"{broadcast}-{key}", key]
	name = next((c for c in candidates if frappe.db.exists(_BROADCAST_RECIPIENT, {"name": c, "broadcast": broadcast})), None)
	if not name:
		return _error("not_found", "That recipient is not on this broadcast.")
	prev = frappe.flags.get("in_broadcast_api")
	frappe.flags.in_broadcast_api = True
	try:
		frappe.delete_doc(_BROADCAST_RECIPIENT, name, force=True, ignore_permissions=True)
	finally:
		frappe.flags.in_broadcast_api = prev
	frappe.get_doc(_BROADCAST, broadcast).recount()
	if row.get("consent_attested"):
		_reset_attestation(broadcast, "recipients changed")
	_broadcast_audit(broadcast, "recipient_removed", recipient=_mask_phone(key))
	return {"success": True, "broadcast": broadcast, "removed": 1, "queued": _queued_count(broadcast)}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=policy.rate("rate_delete_broadcast"), seconds=60)
@_bridge_guard
def delete_broadcast(broadcast: str | None = None) -> dict[str, Any]:
	"""Delete a Draft broadcast and its recipient rows. Anything that ever started is kept as the send record."""
	row = _require_broadcast_write(broadcast)
	if row.get("error"):
		return row
	if row.get("status") != "Draft":
		return _error("not_draft", "Only a Draft broadcast can be deleted. Cancel a running one instead.")
	_broadcast_audit(broadcast, "deleted")  # the Comment goes with the doc; the log line stays
	try:
		frappe.delete_doc(_BROADCAST, broadcast, ignore_permissions=True)
	except frappe.PermissionError as exc:
		return _error("not_deletable", str(exc))
	return {"success": True, "broadcast": broadcast, "deleted": True}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=policy.rate("rate_attest_consent"), seconds=60)
@_bridge_guard
def attest_broadcast_consent(broadcast: str | None = None, consent_source: str | None = None) -> dict[str, Any]:
	"""Record that the caller attests recipients opted in to this kind of message (source of the opt-in is required)."""
	row = _require_broadcast_write(broadcast)
	if row.get("error"):
		return row
	if row.get("status") not in ("Draft", "Paused"):
		return _error("invalid_state", "Consent can only be attested on a Draft or Paused broadcast.")
	source = (consent_source or "").strip()
	if not source:
		return _error("consent_source_required", "State where the recipients' opt-in was collected.")
	now = frappe.utils.now_datetime()
	frappe.flags.in_broadcast_api = True
	frappe.db.set_value(
		_BROADCAST,
		broadcast,
		{
			"consent_attested": 1,
			"consent_attested_by": frappe.session.user,
			"consent_attested_at": now,
			"consent_source": source,
		},
	)
	_broadcast_audit(broadcast, "consent_attested", consent_source=source)
	return {"success": True, "broadcast": broadcast, "consent_attested": True, "consent_source": source}


@frappe.whitelist(methods=["POST"])
@_bridge_guard
def preview_broadcast(broadcast: str | None = None) -> dict[str, Any]:
	"""Pre-flight: limits and warnings, cost estimate and the count the operator must type to start. Read-only."""
	row = _require_broadcast_write(broadcast)  # preview feeds the start decision, so it needs write authority too
	if row.get("error"):
		return row
	from huf.ai.whatsapp.broadcast import cost as broadcast_cost, limits as broadcast_limits

	limits = broadcast_limits.preview(broadcast)
	cost = broadcast_cost.estimate(broadcast)
	token = broadcast_cost.confirm_token(broadcast)
	frappe.db.set_value(_BROADCAST, broadcast, "cost_estimate", json.dumps(cost, default=str), update_modified=False)
	return {
		"success": True,
		"broadcast": broadcast,
		"status": row.get("status"),
		"consent_attested": bool(row.get("consent_attested")),
		"limits": limits,
		"limits_in_effect": list((limits or {}).get("limits_in_effect") or []),
		"cost": cost,
		"confirm_required": bool(policy.get("require_typed_count")) and int(token or 0) > 0,
		"queued": _queued_count(broadcast),
	}


def _is_api_key_caller() -> bool:
	"""True when the request is authenticated with an API key/secret (``Authorization: token key:secret``)."""
	header = frappe.get_request_header("Authorization")
	return isinstance(header, str) and header.strip().lower().startswith("token ")


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=policy.rate("rate_start_broadcast"), seconds=60)
@_bridge_guard
def start_broadcast(
	broadcast: str | None = None, confirm_count: Any = None, override_warnings: Any = None
) -> dict[str, Any]:
	"""Start (or restart a Draft) broadcast.

	The typed count must equal the queued recipients (when ``require_typed_count`` is on; API-key callers skip it).
	``override_warnings``: acknowledged warning codes; the runner refuses with ``warnings_changed`` (plus the
	current warnings) when they differ, and enforces consent and one-running under a lock."""
	row = _require_broadcast_write(broadcast)
	if row.get("error"):
		return row
	acknowledged = start_gate.parse_override_warnings(override_warnings)
	if acknowledged is None:
		return _error("invalid_override_warnings", "override_warnings must be a JSON list of warning codes.")
	queued = _queued_count(broadcast)
	if queued <= 0:
		return _error("no_recipients", "There are no queued recipients.")
	if policy.get("require_typed_count") and not _is_api_key_caller():
		if str(confirm_count if confirm_count is not None else "").strip() != str(queued):
			return _error("confirm_mismatch", f"Type the number of queued recipients ({queued}) to confirm.")
	from huf.ai.whatsapp.broadcast import runner as broadcast_runner

	try:
		result = broadcast_runner.start(broadcast, user=frappe.session.user, override_warnings=acknowledged, expected_count=queued)
	except broadcast_runner.StartRefused as exc:
		return {"success": False, "error": exc.code, "message": str(exc), **exc.extra}
	_broadcast_audit(broadcast, "started", queued=queued, override_warnings=acknowledged)
	return {"success": True, "broadcast": broadcast, "queued": queued, **(result if isinstance(result, dict) else {})}


def _runner_action(broadcast: str | None, action: str, **kwargs: Any) -> dict[str, Any]:
	row = _require_broadcast_write(broadcast)
	if row.get("error"):
		return row
	from huf.ai.whatsapp.broadcast import runner as broadcast_runner

	result = getattr(broadcast_runner, action)(broadcast, **kwargs)
	_broadcast_audit(broadcast, action, **kwargs)
	status = frappe.db.get_value(_BROADCAST, broadcast, "status")
	return {"success": True, "broadcast": broadcast, "status": status, **(result if isinstance(result, dict) else {})}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=policy.rate("rate_pause_broadcast"), seconds=60)
@_bridge_guard
def pause_broadcast(broadcast: str | None = None) -> dict[str, Any]:
	"""Pause a running broadcast; queued rows stay queued."""
	return _runner_action(broadcast, "pause", reason="manual")


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=policy.rate("rate_resume_broadcast"), seconds=60)
@_bridge_guard
def resume_broadcast(broadcast: str | None = None) -> dict[str, Any]:
	"""Resume a paused broadcast."""
	return _runner_action(broadcast, "resume")


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=policy.rate("rate_cancel_broadcast"), seconds=60)
@_bridge_guard
def cancel_broadcast(broadcast: str | None = None) -> dict[str, Any]:
	"""Cancel a broadcast: queued rows become skipped (cancelled); already sent messages are unaffected."""
	return _runner_action(broadcast, "cancel")


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=policy.rate("rate_pause_all"), seconds=60)
@_bridge_guard
def pause_all_broadcasts(gateway: str | None = None) -> dict[str, Any]:
	"""Kill switch: pause every running broadcast of a Gateway."""
	refused = _require_send_authority(gateway)
	if refused:
		return refused
	running = frappe.get_all(_BROADCAST, filters={"gateway": gateway, "status": "Running"}, pluck="name") or []
	from huf.ai.whatsapp.broadcast import runner as broadcast_runner

	result = broadcast_runner.pause_all(gateway, "kill_switch")
	broadcast_runner.hold_scheduled(gateway)
	for name in running:
		_broadcast_audit(name, "pause_all", gateway=gateway)
	frappe.logger(_BROADCAST_LOG).info(f"gateway={gateway} action=pause_all user={frappe.session.user} paused={len(running)}")
	return {"success": True, "gateway": gateway, "paused": running, **(result if isinstance(result, dict) else {})}

