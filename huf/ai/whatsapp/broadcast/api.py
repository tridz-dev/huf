# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WhatsApp Broadcast: whitelisted API (create, recipients, consent, preview, start, pause, cancel, list).

Guard helpers are shared with ``huf.ai.whatsapp.management``.
"""

from __future__ import annotations

import json
import random
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
)
from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.whatsapp.broadcast import params as broadcast_params, policy
from huf.ai.whatsapp.broadcast.support import fallback_config


from huf.ai.whatsapp.broadcast.support.api_helpers import (  # noqa: F401 - moved helpers, kept importable from api
	_BROADCAST,
	_BROADCAST_COUNT_FIELDS,
	_BROADCAST_FIELDS,
	_BROADCAST_LOG,
	_BROADCAST_RECIPIENT,
	_LONG_DIGITS_RE,
	_UNSET,
	_broadcast_audit,
	_broadcast_view,
	_carousel_template_problem,
	_json_param,
	_mask_digits,
	_mask_phone,
	_queued_count,
	_reset_attestation,
)

# --- Broadcast (WP-7) ----------------------------------------------------------------------------
# Thin API over broadcast_recipients / broadcast_limits / broadcast_cost / broadcast_runner. Those
# modules are imported lazily inside each function so that a problem there never breaks this module.
#
# Scheduling and retry (``retry_failed_recipients``: only retryable ``failed`` rows go into a NEW Draft that must be
# attested and started again) live in ``broadcast.schedule``.


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
	carousel_params: Any = None,
	fallback_channels: Any = None,
	fallback_body: str | None = None,
	fallback_body_kind: str | None = None,
	fallback_sms_gateway: str | None = None,
	fallback_email_gateway: str | None = None,
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
		return _error("template_not_approved", "Only approved templates can be broadcast. Wait for WhatsApp to approve this one, or pick another.")
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
		carousel = _json_param(carousel_params, "carousel_params")
		problem = broadcast_params.carousel_error(carousel) or _carousel_template_problem(tpl, carousel)
		if problem:
			return _error("invalid_params", problem)
		fallback = fallback_config.clean({
			"fallback_channels": fallback_channels, "fallback_body": fallback_body, "fallback_body_kind": fallback_body_kind,
			"fallback_sms_gateway": fallback_sms_gateway, "fallback_email_gateway": fallback_email_gateway,
		})
		problem = fallback_config.check_complete(fallback.get("fallback_channels"), fallback.get("fallback_body"))
		if problem:
			return _error("invalid_fallback", problem)
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
			"carousel_params": json.dumps(carousel) if carousel is not None else None,
			"consent_source": (consent_source or "").strip() or None,
			"consent_attested": 0,
			"max_recipients": cap,
			"mps": rate,
			"send_via": send_via,
			**fallback,
		}
	).insert(ignore_permissions=True)  # authority was proven by _send_authority above
	_broadcast_audit(doc.name, "created", gateway=gateway, template=tpl.get("name"), category=tpl.get("category"))
	return {"success": True, "broadcast": doc.name, "status": "Draft", "category": tpl.get("category")}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=policy.rate("rate_create_broadcast"), seconds=60)
@_bridge_guard
def update_broadcast(
	broadcast: str | None = None,
	title: str | None = None,
	carousel_params: Any = _UNSET,
	fallback_channels: Any = _UNSET,
	fallback_body: Any = _UNSET,
	fallback_body_kind: Any = _UNSET,
	fallback_sms_gateway: Any = _UNSET,
	fallback_email_gateway: Any = _UNSET,
) -> dict[str, Any]:
	"""Change a Draft broadcast's title, carousel defaults or cross-channel failover. Only the fields you pass change.

	Failover: ``fallback_channels`` an ordered subset of ``["sms","email"]`` (empty list clears it, with the body and
	kind), ``fallback_body`` plain text (required when channels are set), ``fallback_body_kind`` ``marketing`` or
	``transactional``, and the SMS / email Gateways (you need read access to them). Queued recipient rows get the new
	values. Needs write authority on the broadcast's Gateway."""
	row = _require_broadcast_write(broadcast)
	if row.get("error"):
		return row
	if row.get("status") != "Draft":
		return _error("not_draft", "Only a Draft broadcast can be changed.")
	given = {
		"fallback_channels": fallback_channels, "fallback_body": fallback_body, "fallback_body_kind": fallback_body_kind,
		"fallback_sms_gateway": fallback_sms_gateway, "fallback_email_gateway": fallback_email_gateway,
	}
	given = {k: v for k, v in given.items() if v is not _UNSET}
	values: dict[str, Any] = {}
	try:
		if title is not None:
			if not str(title).strip():
				return _error("invalid_title", "A title is required.")
			values["title"] = str(title).strip()[:140]
		if carousel_params is not _UNSET:
			carousel = _json_param(carousel_params, "carousel_params")
			problem = broadcast_params.carousel_error(carousel) or _carousel_template_problem(row.get("template"), carousel)
			if problem:
				return _error("invalid_params", problem)
			values["carousel_params"] = json.dumps(carousel) if carousel is not None else None
		cleaned = fallback_config.clean(given)
		if "fallback_channels" in given and not cleaned.get("fallback_channels"):
			cleaned.update({"fallback_body": None, "fallback_body_kind": None})  # cleared channels clear the config
		values.update(cleaned)
		merged = {**{k: frappe.db.get_value(_BROADCAST, broadcast, k) for k in fallback_config.CONFIG_FIELDS}, **values}
		problem = fallback_config.check_complete(merged.get("fallback_channels"), merged.get("fallback_body"))
		if problem:
			return _error("invalid_fallback", problem)
	except (TypeError, ValueError) as exc:
		return _error("invalid_params", str(exc))
	if not values:
		return _error("nothing_to_update", "Pass at least one field to change.")
	prev = frappe.flags.get("in_broadcast_api")
	frappe.flags.in_broadcast_api = True
	try:
		frappe.db.set_value(_BROADCAST, broadcast, values)
		if any(k in values for k in fallback_config.CONFIG_FIELDS):
			fallback_config.propagate(broadcast)
	finally:
		frappe.flags.in_broadcast_api = prev
	_broadcast_audit(broadcast, "updated", fields=",".join(sorted(values)))
	return {"success": True, "broadcast": broadcast, "updated": sorted(values)}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=policy.rate("rate_add_recipients"), seconds=60)
@_bridge_guard
def add_broadcast_recipients(
	broadcast: str | None = None,
	recipients: Any = None,
	csv_text: str | None = None,
	fallback_channels: Any = None,
	fallback_body: str | None = None,
	fallback_body_kind: str | None = None,
	fallback_sms_gateway: str | None = None,
	fallback_email_gateway: str | None = None,
) -> dict[str, Any]:
	"""Add recipients to a Draft broadcast, from a list (``["+1555..", {"recipient":..,"params":..,"fallback_email":..}]``)
	or CSV text. The ``fallback_*`` arguments (validated like ``update_broadcast``) override the broadcast's failover for
	every row of this call; a row may also carry its own ``fallback_*`` keys and a ``fallback_email``."""
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
	batch = {k: v for k, v in {
		"fallback_channels": fallback_channels, "fallback_body": fallback_body, "fallback_body_kind": fallback_body_kind,
		"fallback_sms_gateway": fallback_sms_gateway, "fallback_email_gateway": fallback_email_gateway,
	}.items() if v not in (None, "")}
	if batch:
		try:
			batch = fallback_config.clean(batch)
		except ValueError as exc:
			return _error("invalid_fallback", str(exc))
		rows = [{**batch, **r} for r in rows]
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
	from huf.ai.whatsapp.broadcast import limits as broadcast_limits
	from huf.ai.whatsapp.broadcast.support import cost as broadcast_cost

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


from huf.ai.whatsapp.broadcast.support.api_controls import (  # noqa: E402,F401 - whitelisted endpoints, re-exported
	_is_api_key_caller,
	cancel_broadcast,
	pause_all_broadcasts,
	pause_broadcast,
	resume_broadcast,
	start_broadcast,
)
