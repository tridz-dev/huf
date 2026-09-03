# Copyright (c) 2026, Huf and Contributors
# For license information, please see license.txt

"""HTTP route firing an Automation Trigger of type "Webhook".

Net-new runtime: a grep across the whole ``huf/`` tree found no live HTTP
route resolving the legacy "Agent Trigger" doctype's Webhook type either --
``webhook_slug`` was schema-only before this file. There is therefore no
legacy behavior to preserve or fall back to; the
``automation_trigger_runtime`` flag (see ``automation_runtime_flag.py``)
being ``"legacy"`` just means this endpoint is disabled.

Follows the same allow_guest whitelisted-webhook convention already used by
``huf.ai.gateway_webhook.handle_gateway_webhook``: the routing key (here,
the Automation Trigger's ``webhook_slug``) is read directly off the query
string via ``frappe.request.args`` rather than taken as a function kwarg,
because ``frappe.app.make_form_dict`` replaces ``frappe.form_dict`` wholesale
with the parsed JSON body whenever ``Content-Type`` is ``application/json``
-- every real webhook caller posts JSON, so a query-string kwarg named
``slug`` would never actually reach this function on a live call. The
response shape (``{"success": bool, "error": str}`` on failure) also mirrors
``gateway_webhook.py``.

Auth follows the plan's explicit V1 scope ("preserve existing key/slug and
migrate later" -- advanced ``auth_mode``/``signature_header``/
``payload_mapping`` fields are out of scope): the secret stored on the
trigger's ``webhook_key`` field must be supplied via an ``X-Webhook-Key``
request header. Headers, not the query string or body, are the convention
here specifically so the secret never lands in access logs or inside the
``trigger_context`` payload handed to the automation.

Routing safety: the URL's ``slug`` is the *only* input that selects which
Automation Trigger (and therefore which Automation) runs. The request body
is parsed only after routing + auth have both succeeded, and is passed to
``run_automation`` purely as inert ``trigger_context`` data -- nothing in
the payload is ever read to choose a doctype, trigger, or automation name.
"""

from __future__ import annotations

import hmac
import json

import frappe
from frappe import _

# Headers never forwarded into trigger_context: credentials that must not be
# echoed back into automation prompts, logs, or (eventually) chat history.
_EXCLUDED_HEADERS = frozenset({"authorization", "cookie", "x-webhook-key"})

# Generic messages for the two failure modes that must not leak details:
# unknown/disabled/wrong-type slugs, and slugs that resolve but whose key
# check fails. Neither message names the automation, the trigger, or why a
# slug didn't resolve (unknown vs. disabled vs. wrong trigger_type all look
# identical from the outside).
_NOT_FOUND = {"success": False, "error": "Not found."}
_INVALID_KEY = {"success": False, "error": "Invalid webhook key."}


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def handle_automation_webhook():
	"""Resolve `?slug=...` to an Automation Trigger and run its Automation."""
	from huf.ai.automation_runner import run_automation
	from huf.ai.automation_runtime_flag import automation_runtime_is_new

	if not automation_runtime_is_new():
		frappe.local.response["http_status_code"] = 503
		return {"success": False, "error": "Automation webhooks are disabled."}

	slug = frappe.request.args.get("slug") if frappe.request is not None else None
	if not slug:
		frappe.local.response["http_status_code"] = 404
		return dict(_NOT_FOUND)

	trigger_name = frappe.db.get_value(
		"Automation Trigger",
		{"trigger_type": "Webhook", "webhook_slug": slug, "disabled": 0},
		"name",
	)
	if not trigger_name:
		frappe.local.response["http_status_code"] = 404
		return dict(_NOT_FOUND)

	trigger = frappe.get_doc("Automation Trigger", trigger_name)

	supplied_key = frappe.get_request_header("X-Webhook-Key") or ""
	expected_key = trigger.get_password("webhook_key") or ""
	if not expected_key or not hmac.compare_digest(supplied_key, expected_key):
		frappe.local.response["http_status_code"] = 401
		return dict(_INVALID_KEY)

	if not trigger.automation:
		# Configured but incomplete (no Automation linked yet) -- same
		# externally-observable outcome as a slug that never resolved.
		frappe.local.response["http_status_code"] = 404
		return dict(_NOT_FOUND)

	raw_body = frappe.request.get_data(as_text=False) if frappe.request is not None else b""
	trigger_context = {
		"type": "webhook",
		"payload": _parse_payload(raw_body),
		"headers": _safe_headers(frappe.request.headers if frappe.request is not None else {}),
	}

	try:
		result = run_automation(trigger.automation, trigger.name, trigger_context=trigger_context)
	except Exception:
		frappe.log_error(
			title=f"Automation webhook run failed: {trigger.automation}",
			message=frappe.get_traceback(),
		)
		frappe.local.response["http_status_code"] = 500
		return {"success": False, "error": _("Automation run failed.")}

	return {"success": True, "result": result}


def _safe_headers(headers) -> dict:
	"""Drop credential-bearing headers before they become trigger_context data."""
	return {
		key: value
		for key, value in dict(headers or {}).items()
		if key.lower() not in _EXCLUDED_HEADERS
	}


def _parse_payload(raw_body: bytes):
	"""Best-effort JSON decode of the request body; never raises."""
	if not raw_body:
		return {}
	try:
		return json.loads(raw_body.decode("utf-8"))
	except (UnicodeDecodeError, json.JSONDecodeError):
		return {"raw": raw_body.decode("utf-8", errors="replace")}
