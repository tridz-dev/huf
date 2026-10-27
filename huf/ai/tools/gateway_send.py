"""``gateway_send``: proactive (no inbound event) message through a Gateway.

Recipients are resolved server-side by ``huf.ai.gateways.recipients`` (see its grammar). The
LLM can never address an arbitrary Slack channel or user id. Text is mrkdwn-escaped so no
``<!channel>`` / ``<@U..>`` pings unless ``allow_mentions`` is set by a trusted caller (it is
not part of the tool schema). Quiet hours and digests are deferred.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

import frappe

from huf.ai.gateways import recipients as rcp
from huf.ai.gateways.slack_context import get_slack_api

MAX_TEXT_CHARS = 3000
DEFAULT_DEDUPE_TTL_SECONDS = 24 * 3600
SEND_INTERVAL_SECONDS = 1.1
_TRUNCATION_MARK = "..."
_KEY_PREFIX = "huf_gateway_send:"
_sleep = time.sleep

GATEWAY_SEND_TOOLS = [
	{
		"tool_name": "gateway_send",
		"description": (
			"Proactively send a text message through a configured Gateway (e.g. Slack) to people, a role, "
			"a user field on a document, a named recipient, or an approved channel. Recipient is JSON, one "
			"of: {\"user\": \"a@b.com\"}, {\"role\": \"Sales Manager\"}, "
			"{\"doc_field\": {\"doctype\": \"Task\", \"name\": \"TASK-1\", \"field\": \"owner\"}}, "
			"{\"recipient_name\": \"Sales Alerts\"}, {\"channel\": \"C123\"} (approved channels only). "
			"People must have linked their Slack account. Use dedupe_key to avoid double sends on retries."
		),
		"function_path": "huf.ai.tools.gateway_send.handle_gateway_send",
		"category": "Communication Tools",
		"parameters": [
			{"label": "Gateway", "fieldname": "gateway", "type": "string", "required": 1,
				"description": "Name of the Gateway to send through"},
			{"label": "Recipient", "fieldname": "recipient", "type": "string", "required": 1,
				"description": "JSON recipient spec (user, role, doc_field, recipient_name or channel)"},
			{"label": "Text", "fieldname": "text", "type": "string", "required": 1,
				"description": f"Message text (plain text, max {MAX_TEXT_CHARS} characters)"},
			{"label": "Dedupe Key", "fieldname": "dedupe_key", "type": "string", "required": 0,
				"description": "Optional key; the same key + recipient is sent at most once per window"},
			{"label": "Dedupe Hours", "fieldname": "dedupe_hours", "type": "number", "required": 0,
				"description": "Dedupe window in hours (default 24)"},
		],
	},
]


def safe_text(text: Any, limit: int = MAX_TEXT_CHARS, allow_mentions: bool = False) -> str:
	value = "" if text is None else str(text)
	if not allow_mentions:
		value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
	value = value.strip()
	if len(value) > limit:
		value = value[: limit - len(_TRUNCATION_MARK)] + _TRUNCATION_MARK
	return value


def _result(ok: bool, **extra) -> str:
	return json.dumps({"success": ok, **extra})


def _cache():
	cache = frappe.cache
	return cache() if callable(cache) and not hasattr(cache, "get_value") else cache


def _claim(key: str, ttl: int) -> bool:
	"""Atomically claim ``key``; False if already claimed."""
	cache = _cache()
	try:
		return bool(cache.set(cache.make_key(key), 1, nx=True, ex=ttl))
	except (AttributeError, TypeError):
		if cache.get_value(key):
			return False
		cache.set_value(key, 1, expires_in_sec=ttl)
		return True


def _release(key: str) -> None:
	cache = _cache()
	try:
		cache.delete_value(key)
	except Exception:
		pass


def _dedupe_key(gateway: str, dedupe_key: str, target: dict) -> str:
	dest = f"{target['slack_user'] or ''}|{target['channel'] or ''}"
	digest = hashlib.sha256(f"{gateway}|{dedupe_key}|{dest}".encode()).hexdigest()[:32]
	return _KEY_PREFIX + digest


def handle_gateway_send(
	gateway: str = "",
	recipient: Any = None,
	text: str = "",
	dedupe_key: str | None = None,
	dedupe_hours: float | None = None,
	allow_mentions: bool = False,
	**_ignored,
) -> str:
	"""Tool handler. Returns a JSON string; never raises, never includes tokens."""
	try:
		body = safe_text(text, allow_mentions=bool(allow_mentions))
		if not body:
			return _result(False, error="Message text is empty.")
		if not gateway or not frappe.db.exists("Gateway", gateway):
			return _result(False, error="Unknown gateway.")
		gw = frappe.get_doc("Gateway", gateway)
		if not getattr(gw, "is_enabled", 0):
			return _result(False, error="Gateway is disabled.")
		if str(getattr(gw, "provider", "")).lower() != "slack":
			return _result(False, error="Proactive send supports Slack gateways only.")
		try:
			specs = rcp.parse_specs(recipient)
		except ValueError as exc:
			return _result(False, error=str(exc))
		targets, skipped = rcp.resolve(gw.name, specs, caller=frappe.session.user)
		ttl = int(float(dedupe_hours) * 3600) if dedupe_hours else DEFAULT_DEDUPE_TTL_SECONDS
		try:
			api = get_slack_api(gw)
		except ValueError:
			return _result(False, error="Gateway has no bot token configured.")

		sent, deduped = [], []
		for index, target in enumerate(targets):
			claimed = None
			if dedupe_key:
				claimed = _dedupe_key(gw.name, str(dedupe_key), target)
				if not _claim(claimed, ttl):
					deduped.append(target["label"])
					continue
			if index and SEND_INTERVAL_SECONDS:
				_sleep(SEND_INTERVAL_SECONDS)
			try:
				channel = target["channel"] or api.conversations_open([target["slack_user"]])
				if not channel:
					raise RuntimeError("no channel")
				api.post_message(channel, body)
				sent.append(target["label"])
			except Exception as exc:
				if claimed:
					_release(claimed)
				code = getattr(exc, "error_code", None)
				skipped.append({"recipient": target["label"], "reason": f"send failed{': ' + code if code else ''}"})
		return _result(bool(sent) or bool(deduped), sent=sent, skipped=skipped, deduped=deduped)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "gateway_send tool failed")
		return _result(False, error="Could not send the message.")
