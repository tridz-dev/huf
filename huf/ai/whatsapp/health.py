# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Health, checklist and next-step evaluation for ONE WhatsApp Gateway.

Two layers:

* :func:`evaluate` is pure. It takes a ``facts`` dict and returns the health payload, so every
  state is unit-testable without a database.
* :func:`read_events`, :func:`read_fallback_template` and :func:`read_unrouted_phone_ids` are the
  DB reads that feed it. Nothing here makes a network call, and nothing here returns a secret.

``action_url`` convention: an absolute ``https://`` URL opens in Meta; a value starting with ``#``
is an in-app anchor for the Settings tab (``#credentials``, ``#app-secret``, ``#enabled``,
``#fallback-template``, ``#test-message``) that the frontend resolves.

Inferences (Meta offers no read API here, so the checklist is inferred from what Huf has seen):

* ``meta_app``: done when an app id is known or an access token exists (a token implies an app).
* ``webhook``: done when ``Gateway.last_verify_ok_at`` is set (Meta's GET verification passed),
  ``Gateway.last_event_at`` is set, or any Gateway Event exists.
* ``signature_failed`` (error): the webhook recorded a failed POST signature or GET verify token
  (``last_signature_failure_at``, a bare timestamp written at most once a minute) within the last
  24 hours and no valid event has arrived since. Trade-off: the callers are unauthenticated, so
  anyone who knows the callback URL can make a gateway read "blocked" by sending a bad signature;
  this is bounded (one write a minute, expires after 24 hours, cleared by the next valid event)
  and is preferred over hiding a wrong App Secret behind "Meta never called us".
* ``subscribed``: done when at least one Gateway Event exists (events are created only for inbound
  messages, so the ``messages`` field must be subscribed).
* ``test_message``: done when any event ever got a reply with ``reply_status`` sent/delivered/read.
* ``unrouted_phone_ids``: Huf only logs unknown phone ids (no row). We derive them from recent
  Rejected/Unrouted Gateway Events whose payload ``metadata.phone_number_id`` differs from this
  gateway's phone number id; otherwise the list is empty.
* "recent error": ``Gateway.last_error`` is non-empty and ``last_event_at`` is within 24 hours
  (or unset); the doc stores no error timestamp.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

import frappe

WINDOW = timedelta(hours=24)
APP_DASHBOARD = "https://developers.facebook.com/apps/"
WHATSAPP_MANAGER = "https://business.facebook.com/latest/whatsapp_manager/message_templates"
_APP_ID_RE = re.compile(r"^\d{5,30}$")
_BAD_TEMPLATE_STATES = frozenset({"REJECTED", "PAUSED", "DISABLED"})
_REPLIED = ("sent", "delivered", "read")
_SECRET_RE = re.compile(r"(?i)((?:access_)?token=)[^&\s\"'<>]+|EAA[A-Za-z0-9]{12,}")
_MAX_EVENTS = 5000
_AFTER_APP_SECRET = frozenset({"configure_webhook", "subscribe_messages", "approve_sender", "send_test_message"})

# next-step priority, then (code, label, action anchor)
_STEPS = (
	("meta_app", "create_meta_app", "Create a Meta app", APP_DASHBOARD),
	("credentials", "add_credentials", "Add the access token and phone number ID", "#credentials"),
	("app_secret", "add_app_secret", "Add the app secret", "#app-secret"),
	("enabled", "enable_gateway", "Turn the gateway on", "#enabled"),
	("webhook", "configure_webhook", "Set the callback URL in Meta", None),
	("subscribed", "subscribe_messages", "Subscribe to the messages field in Meta", None),
	("approve_sender", "approve_sender", "Approve the people waiting to talk to your agent", "#access"),
	("test_message", "send_test_message", "Send a test message to this number", "#test-message"),
)


def redact(text: Any) -> str:
	"""Strip tokens from text before it is shown (gateway service redactor, then a local pass)."""
	out = str(text or "")
	try:
		from huf.ai.gateway_service import _redact_error_text

		out = str(_redact_error_text(out))
	except Exception:
		pass
	return _SECRET_RE.sub(lambda m: (m.group(1) + "[redacted]") if m.group(1) else "[redacted]", out)


def mask_id(value: Any) -> str:
	text = str(value or "")
	return f"...{text[-4:]}" if len(text) > 6 else text


def _iso(value: Any) -> str | None:
	return str(value) if value else None


def meta_links(app_id: str | None) -> dict[str, str | None]:
	app = str(app_id or "").strip()
	known = bool(_APP_ID_RE.match(app))
	return {
		"app_dashboard": f"{APP_DASHBOARD}{app}/" if known else None,
		"whatsapp_manager": WHATSAPP_MANAGER,  # list page; Meta documents no deep links
		# best-effort path, not documented by Meta
		"webhook_config": f"{APP_DASHBOARD}{app}/whatsapp-business/wa-settings/" if known else None,
	}


def _reason(code: str, severity: str, message: str) -> dict[str, str]:
	return {"code": code, "severity": severity, "message": message}


def _count_text(count: int) -> str:
	return f"{count} in the last 24 hours"


def evaluate(facts: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
	"""Pure: facts -> health, reasons, next_step, checklist.

	``facts`` keys: enabled, has_integration, access_token_present, phone_number_id_present,
	verify_token_present, app_secret_present, app_id_present, account_phone_mismatch, token_valid (bool|None, last live check),
	last_event_at, signature_failure_at, verify_ok_at, last_error, events_ever (int), replied_ever (bool), events_24h (dict),
	fallback_template (str), fallback_template_approved (bool|None), fallback_template_status.
	"""
	now = now or frappe.utils.now_datetime()
	enabled = bool(facts.get("enabled"))
	token = bool(facts.get("access_token_present"))
	phone = bool(facts.get("phone_number_id_present"))
	verify = bool(facts.get("verify_token_present"))
	secret = bool(facts.get("app_secret_present"))
	app_id = bool(facts.get("app_id_present"))
	mismatch = bool(facts.get("account_phone_mismatch"))
	# Meta said the stored token is expired or revoked (last cached live check); None = never checked.
	token_invalid = token and facts.get("token_valid") is False
	conn_state = str(facts.get("connection_state") or "Connected")
	conn_reason = str(facts.get("connection_reason") or "").strip()
	last_event_at = facts.get("last_event_at")
	last_error = str(facts.get("last_error") or "").strip()
	events_ever = int(facts.get("events_ever") or 0)
	agent_failed = int((facts.get("events_24h") or {}).get("agent_failed") or 0)
	failed = max(int((facts.get("events_24h") or {}).get("failed") or 0) - agent_failed, 0)
	replied = bool(facts.get("replied_ever"))
	pending_senders = int(facts.get("pending_senders") or 0)
	approved_senders = int(facts.get("approved_senders") or 0)
	pairing = facts.get("direct_policy") == "Pairing"
	never_seen = not last_event_at and events_ever == 0
	sig_at = facts.get("signature_failure_at")
	verify_ok_at = facts.get("verify_ok_at")
	sig_failed = bool(
		secret and sig_at and (now - sig_at) <= WINDOW and (not last_event_at or last_event_at < sig_at)
	)

	reasons: list[dict[str, str]] = []
	if not token:
		reasons.append(_reason("access_token_missing", "error", "The access token is missing."))
	if token_invalid:
		reasons.append(
			_reason(
				"access_token_invalid",
				"error",
				"Meta rejected the access token. It may have expired; replace it in Settings.",
			)
		)
	if not phone:
		reasons.append(_reason("phone_number_id_missing", "error", "The phone number ID is missing."))
	if not verify:
		reasons.append(_reason("verify_token_missing", "error", "The webhook verify token is missing."))
	if not secret:
		reasons.append(
			_reason(
				"app_secret_missing",
				"error",
				"Add the app secret so we can confirm messages really come from Meta.",
			)
		)
	if mismatch:
		reasons.append(
			_reason(
				"account_phone_mismatch",
				"error",
				"This number belongs to a different WhatsApp account than the one linked.",
			)
		)
	unauthorized = int(facts.get("execution_unauthorized") or 0)
	if unauthorized > 0:
		reasons.append(
			_reason(
				"execution_user_not_authorized",
				"error",
				f"The gateway's Run-as user is not allowed to run the agent ({_count_text(unauthorized)}). "
				"Give that user the Huf Gateway User role.",
			)
		)
	if failed > 0:
		reasons.append(_reason("delivery_failures", "warning", f"Replies are failing: {_count_text(failed)}."))
	if agent_failed > 0:
		kind = str(facts.get("agent_error_kind") or "unknown")
		reasons.append(
			_reason(
				"agent_failing",
				"warning",
				f"The AI model returned an error ({kind}); customers got no reply: {_count_text(agent_failed)}.",
			)
		)
	recent_error = False
	if last_error:
		recent_error = not last_event_at or (now - last_event_at) <= WINDOW
		if recent_error and failed == 0 and agent_failed == 0:
			reasons.append(_reason("recent_error", "warning", f"The last problem was: {last_error}"))
	if facts.get("fallback_template_approved") is False:
		status = str(facts.get("fallback_template_status") or "").upper()
		if status in _BAD_TEMPLATE_STATES:
			word = {"REJECTED": "rejected", "PAUSED": "paused", "DISABLED": "disabled"}[status]
			reasons.append(
				_reason(
					"fallback_template_unavailable",
					"warning",
					f"The fallback template was {word} by Meta, so replies outside the 24-hour window will fail.",
				)
			)
	if sig_failed:
		reasons.append(
			_reason(
				"signature_failed",
				"error",
				"Meta is calling us, but the signature check failed. Check the app secret.",
			)
		)
	if never_seen and not sig_failed:
		reasons.append(
			_reason(
				"no_events_yet",
				"warning",
				"Meta hasn't sent us anything yet. Check the callback URL and that the messages field is subscribed.",
			)
		)

	if conn_state == "Disconnected":
		reasons.append(_reason("gateway_disconnected", "error", conn_reason or "This WhatsApp account is disconnected. Sends are refused until it is reconnected."))
	elif conn_state == "Degraded":
		reasons.append(_reason("gateway_degraded", "warning", conn_reason or "Meta restricted this WhatsApp account. Sends are allowed but may fail."))

	if pending_senders and pairing:
		reasons.append(
			_reason(
				"senders_waiting",
				"warning",
				f"{pending_senders} {'person is' if pending_senders == 1 else 'people are'} waiting for approval. "
				"Your agent won't reply to them until you approve them.",
			)
		)

	configured_nothing = not (facts.get("has_integration") or token or phone or verify or secret)
	errors = [r for r in reasons if r["severity"] == "error"]
	warnings = [r for r in reasons if r["severity"] == "warning" and r["code"] != "no_events_yet"]
	if not enabled:
		health = "disabled"
	elif configured_nothing and never_seen:
		health = "not_set_up"
	elif errors:
		health = "blocked"
	elif never_seen:
		health = "not_set_up"
	elif warnings:
		health = "degraded"
	else:
		health = "healthy"

	credentials_ok = token and phone and verify
	steps_state = {
		"meta_app": "done" if (app_id or token) else "todo",
		"credentials": "blocked" if (mismatch or token_invalid) else ("done" if credentials_ok else "todo"),
		"webhook": "done" if (verify_ok_at or last_event_at or events_ever) else ("blocked" if not verify else "todo"),
		"subscribed": "done" if events_ever else ("blocked" if not verify else "todo"),
		"app_secret": "done" if secret else "todo",
		"enabled": "done" if enabled else "todo",
		# Pairing: nobody reaches the agent until an admin approves them, so this is a real setup step.
		"approve_sender": "done"
		if (approved_senders or replied or not pairing)
		else ("todo" if pending_senders else "blocked"),
		"test_message": "done" if replied else ("todo" if credentials_ok and enabled else "blocked"),
	}
	checklist_urls = {
		"meta_app": APP_DASHBOARD,
		"credentials": "#credentials",
		"webhook": None,
		"subscribed": None,
		"app_secret": "#app-secret",
		"enabled": "#enabled",
		"approve_sender": "#access",
		"test_message": "#test-message",
	}
	checklist = [
		{"code": code, "state": steps_state[code], "action_url": checklist_urls[code]}
		for code in (
			"meta_app", "credentials", "webhook", "subscribed", "app_secret", "enabled", "approve_sender", "test_message"
		)
	]

	next_step = None
	if mismatch:
		next_step = {"code": "fix_account_link", "label": "Link the WhatsApp account that owns this number", "action_url": "#credentials"}
	elif token_invalid:
		next_step = {"code": "fix_access_token", "label": "Replace access token", "action_url": "#credentials"}
	else:
		for key, code, label, url in _STEPS:
			if steps_state[key] != "done":
				next_step = {"code": code, "label": label, "action_url": url}
				break
	if sig_failed and not mismatch and (next_step is None or next_step["code"] in _AFTER_APP_SECRET):
		next_step = {"code": "fix_app_secret", "label": "Check the app secret", "action_url": "#app-secret"}
	if pending_senders and pairing and next_step is not None and next_step["code"] in ("approve_sender", "send_test_message"):
		next_step = {
			"code": "approve_sender",
			"label": f"Approve the {pending_senders} {'person' if pending_senders == 1 else 'people'} waiting to talk to your agent",
			"action_url": "#access",
		}
	if health == "not_set_up" and not errors and never_seen and credentials_ok and secret and enabled:
		next_step = {"code": "send_test_message", "label": "Send a test message to this number", "action_url": "#test-message"}
	return {"health": health, "reasons": reasons, "next_step": next_step, "checklist": checklist}


# --- DB reads (feed evaluate) ---------------------------------------------------


def _is_failed(row: dict[str, Any]) -> bool:
	err = (row.get("delivery_error") or "").strip()
	if err and re.search(r"\b(131060|2593109)\b", err):
		return False  # informational codes never count as failures
	return str(row.get("status") or "") == "Failed" or str(row.get("reply_status") or "").lower() == "failed" or bool(err)


_AGENT_ERROR_RE = re.compile(r"^(?:provider_([a-z_]+)|agent_run_failed):")


def _agent_error_kind(row: dict[str, Any]) -> str | None:
	"""Kind of a failed-agent-run event (``unknown`` for a plain agent_run_failed), else None."""
	if str(row.get("status") or "") != "Failed":
		return None
	match = _AGENT_ERROR_RE.match(str(row.get("error_message") or ""))
	if not match:
		return None
	return match.group(1) or "unknown"


def count_events(rows: list[dict[str, Any]]) -> dict[str, int]:
	"""Pure: events_24h counters from event rows already limited to the last 24 hours."""
	return {
		"received": len(rows),
		"failed": sum(1 for r in rows if _is_failed(r)),
		"agent_failed": sum(1 for r in rows if _agent_error_kind(r) is not None),
		"unrouted": sum(1 for r in rows if str(r.get("status") or "") == "Unrouted"),
		"rejected": sum(1 for r in rows if str(r.get("status") or "") == "Rejected"),
	}


def read_events(gateway_name: str, now: datetime) -> dict[str, Any]:
	since = now - WINDOW
	rows = frappe.get_all(
		"Gateway Event",
		filters={"gateway": gateway_name, "received_at": [">=", since]},
		fields=["name", "status", "reply_status", "delivery_error", "error_message"],
		limit_page_length=_MAX_EVENTS,
	)
	events_ever = frappe.db.count("Gateway Event", {"gateway": gateway_name})
	replied = bool(
		frappe.db.exists("Gateway Event", {"gateway": gateway_name, "reply_status": ["in", list(_REPLIED)]})
	)
	unauthorized = frappe.db.count(
		"Gateway Event",
		{
			"gateway": gateway_name,
			"received_at": [">=", since],
			"error_message": ["like", "%not authorized to use this agent%"],
		},
	) + frappe.db.count(
		"Gateway Event",
		{
			"gateway": gateway_name,
			"received_at": [">=", since],
			"error_message": ["like", "%Not permitted to create%"],
		},
	)
	last_failed = None
	failed_rows = frappe.get_all(
		"Gateway Event",
		filters={"gateway": gateway_name},
		or_filters=[["status", "=", "Failed"], ["reply_status", "=", "failed"], ["delivery_error", "!=", ""]],
		fields=["name", "received_at", "delivery_error", "error_message"],
		order_by="received_at desc",
		limit_page_length=1,
	)
	if failed_rows:
		row = failed_rows[0]
		last_failed = {
			"name": row.get("name"),
			"at": _iso(row.get("received_at")),
			"error": redact(row.get("delivery_error") or row.get("error_message") or ""),
		}
	event_rows = [dict(r) for r in rows or []]
	agent_error_kind = next((k for k in (_agent_error_kind(r) for r in event_rows) if k), "")
	return {
		"agent_error_kind": agent_error_kind,
		"events_24h": count_events(event_rows),
		"events_ever": int(events_ever or 0),
		"replied_ever": replied,
		"execution_unauthorized": int(unauthorized or 0),
		"last_failed_event": last_failed,
	}


def read_unrouted_phone_ids(gateway_name: str, own_phone_id: str, now: datetime) -> list[str]:
	"""Phone ids seen on recent Rejected/Unrouted events that are not this gateway's own."""
	rows = frappe.get_all(
		"Gateway Event",
		filters={
			"gateway": gateway_name,
			"status": ["in", ["Rejected", "Unrouted"]],
			"received_at": [">=", now - WINDOW],
		},
		fields=["raw_payload"],
		order_by="received_at desc",
		limit_page_length=50,
	)
	seen: list[str] = []
	for row in rows or []:
		payload = row.get("raw_payload")
		if isinstance(payload, str):
			try:
				import json

				payload = json.loads(payload)
			except Exception:
				payload = None
		pid = str(((payload or {}).get("metadata") or {}).get("phone_number_id") or "") if isinstance(payload, dict) else ""
		if pid and pid != (own_phone_id or "") and pid not in seen:
			seen.append(pid)
	return seen


def read_fallback_template(
	account: str | None, template: str, language: str, connector_available: bool
) -> dict[str, Any]:
	"""Account-scoped status of the fallback template; approved is None when unknown."""
	out: dict[str, Any] = {"approved": None, "status": ""}
	if not (connector_available and account and template):
		return out
	try:
		filters: dict[str, Any] = {"whatsapp_account": account}
		if language:
			filters["language_code"] = language
		rows = frappe.get_all(
			"WhatsApp Templates",
			filters=filters,
			or_filters=[["name", "=", template], ["actual_name", "=", template], ["template_name", "=", template]],
			fields=["status"],
			limit_page_length=1,
		)
	except Exception:
		return out
	if rows:
		status = str(rows[0].get("status") or "")
		out["status"] = status
		out["approved"] = status.upper() == "APPROVED"
	return out


def _gateway_stamp(gateway: dict[str, Any], field: str) -> datetime | None:
	"""A Gateway timestamp from the payload dict, else straight from the DB (never raises)."""
	try:
		value = gateway[field] if field in gateway else frappe.db.get_value("Gateway", gateway["name"], field)
		return frappe.utils.get_datetime(value) if value else None
	except Exception:
		return None


def _cached_token_check(gateway_name: str) -> dict[str, Any] | None:
	"""The last live token check, from cache only (no network, no secrets). None when never checked."""
	try:
		from huf.ai.whatsapp.token_check import _result_key

		cached = frappe.cache().get_value(_result_key(gateway_name))
	except Exception:
		return None
	if isinstance(cached, dict) and cached.get("valid") in (True, False):
		return {k: v for k, v in cached.items() if k not in ("cached", "success")}
	return None


def read_sender_counts(gateway_name: str) -> dict[str, int]:
	"""Pending and approved direct-message senders (pairing requests) of one gateway."""
	base = {"gateway": gateway_name, "entry_type": "Sender"}
	now = frappe.utils.now_datetime()
	pending = frappe.db.count(
		"Gateway Access Entry", {**base, "state": "Pending", "expires_at": [">=", now]}
	) + frappe.db.count("Gateway Access Entry", {**base, "state": "Pending", "expires_at": ["is", "not set"]})
	approved = frappe.db.count("Gateway Access Entry", {**base, "state": "Approved"})
	return {"pending_senders": int(pending or 0), "approved_senders": int(approved or 0)}


def build_health(
	gateway: dict[str, Any],
	presence: dict[str, bool],
	*,
	connector_available: bool,
	mismatch: bool,
	app_id: str,
	now: datetime | None = None,
) -> dict[str, Any]:
	"""All health-related payload fields for one gateway (DB reads, no network, no secrets)."""
	now = now or frappe.utils.now_datetime()
	name = gateway["name"]
	events = read_events(name, now)
	template = (gateway.get("fallback_template") or "").strip()
	language = (gateway.get("fallback_template_language") or "").strip()
	tpl = read_fallback_template(gateway.get("whatsapp_account"), template, language, connector_available)
	own_phone = (gateway.get("phone_number_id") or "").strip()
	last_event_at = gateway.get("last_event_at")
	# not in every caller's field list: read the two webhook timestamps when the dict lacks them
	sig_at = _gateway_stamp(gateway, "last_signature_failure_at")
	verify_ok_at = _gateway_stamp(gateway, "last_verify_ok_at")
	last_error = redact(gateway.get("last_error") or "")
	phone_present = bool(presence.get("phone_number_id") or own_phone)
	token_check = _cached_token_check(name)
	if "connection_state" not in gateway:  # not in every caller's field list
		try:
			stored = frappe.db.get_value("Gateway", name, ["connection_state", "connection_reason"], as_dict=True) or {}
		except Exception:
			stored = {}
		gateway = {**gateway, **stored}
	facts = {
		"token_valid": token_check["valid"] if token_check else None,
		"enabled": gateway.get("is_enabled"),
		"has_integration": bool(gateway.get("integration_settings")),
		"access_token_present": presence.get("access_token"),
		"phone_number_id_present": phone_present,
		"verify_token_present": presence.get("webhook_verify_token"),
		"app_secret_present": presence.get("app_secret"),
		"app_id_present": bool(app_id),
		"account_phone_mismatch": mismatch,
		"last_event_at": last_event_at,
		"signature_failure_at": sig_at,
		"verify_ok_at": verify_ok_at,
		"last_error": last_error,
		"connection_state": gateway.get("connection_state") or "Connected",
		"connection_reason": gateway.get("connection_reason") or "",
		"events_ever": events["events_ever"],
		"replied_ever": events["replied_ever"],
		"events_24h": events["events_24h"],
		"agent_error_kind": events.get("agent_error_kind", ""),
		"execution_unauthorized": events.get("execution_unauthorized", 0),
		"fallback_template_approved": tpl["approved"],
		"fallback_template_status": tpl["status"],
		"direct_policy": gateway.get("direct_policy") or "",
		**read_sender_counts(name),
	}
	mode = gateway.get("voice_reply_mode")
	if mode is None:
		try:
			mode = frappe.db.get_value("Gateway", name, "voice_reply_mode")
		except Exception:
			mode = None
	facts["voice_reply_mode"] = mode or "Off"
	result = evaluate(facts, now)
	result.update(
		{
			"fallback_template": template,
			"fallback_template_language": language,
			"fallback_template_approved": tpl["approved"],
			"last_event_at": _iso(last_event_at),
			"last_signature_failure_at": _iso(sig_at),
			"last_verify_ok_at": _iso(verify_ok_at),
			"last_error": last_error,
			"access_token_present": bool(presence.get("access_token")),
			"app_id_present": bool(app_id),
			"app_secret_present": bool(presence.get("app_secret")),
			"verify_token_present": bool(presence.get("webhook_verify_token")),
			"token_check": token_check,
			"events_24h": events["events_24h"],
			"last_failed_event": events["last_failed_event"],
			"unrouted_phone_ids": read_unrouted_phone_ids(name, own_phone, now),
			"policy": {
				"direct_policy": gateway.get("direct_policy") or "",
				"room_policy": gateway.get("room_policy") or "",
				"room_sender_policy": gateway.get("room_sender_policy") or "",
				"mention_required": bool(gateway.get("mention_required")),
				"pairing_enabled": (gateway.get("direct_policy") or "") == "Pairing",
				"default_target": _default_target(gateway),
			},
			"meta_links": meta_links(app_id),
		}
	)
	return result


def _default_target(gateway: dict[str, Any]) -> dict[str, str] | None:
	kind = gateway.get("default_target_type") or ""
	if kind == "Agent" and gateway.get("default_agent"):
		return {"type": "Agent", "name": gateway["default_agent"]}
	if kind == "Flow" and gateway.get("default_flow"):
		return {"type": "Flow", "name": gateway["default_flow"]}
	return None
