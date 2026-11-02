# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Optional bridge between the Huf WhatsApp gateway and ``frappe_whatsapp``.

This is the only Huf module that touches frappe_whatsapp doctypes. They are
addressed by DocType name behind :func:`is_available`; frappe_whatsapp is
never imported at module import time (only lazily, inside :func:`forward_status`).

Structured errors: functions that can fail for expected reasons return or
raise a dict-shaped error ``{"success": False, "error": "<code>", ...}``.
``resolve_account`` returns ``{"error": "no_account"}`` when the named account does not exist
or no name is given: there is no default-account guess on gateway paths.
"""

from __future__ import annotations

import contextvars
import copy
import hashlib
import importlib
import json
import mimetypes
import os
import re
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urljoin, urlparse

import frappe
import frappe.utils

from huf.ai.whatsapp import outbound_policy as policy, template_plain
from huf.ai.gateway_adapters import whatsapp_messages as wm
from huf.ai.gateway_adapters import whatsapp_templates as wt

GRAPH_HOST = "https://graph.facebook.com"
# Newest Graph version that is >= ~3 months old (v25.0 released 2026-02-18; v26.0 is too new).
GRAPH_DEFAULT_VERSION = "v25.0"
WINDOW_HOURS = 24
_MB = 1024 * 1024
# Meta's inbound limits: documents 100 MB, images 5 MB, audio/video 16 MB, stickers 500 KB.
MEDIA_LIMITS_BY_KIND = {
	"document": 100 * _MB,
	"image": 5 * _MB,
	"audio": 16 * _MB,
	"video": 16 * _MB,
	"sticker": 500 * 1024,
}
DEFAULT_MAX_MEDIA_BYTES = MEDIA_LIMITS_BY_KIND["document"]  # absolute ceiling; per-kind limits apply
DEFAULT_MIME_PREFIXES = (
	"image/",
	"audio/",
	"video/",
	"application/pdf",
	"text/plain",
	"application/msword",
	"application/vnd.openxmlformats-officedocument.",
	"application/vnd.ms-excel",
	"application/vnd.ms-powerpoint",
)
# Never allowed even though a prefix above would match (active content).
_BLOCKED_MIME_PREFIXES = ("image/svg", "text/html", "application/xhtml")
# AUTHENTICATION is intentionally unsupported: Meta requires OTP button components.
TEMPLATE_CATEGORIES = ("MARKETING", "UTILITY")
FORWARD_RETRY_DELAY_SECONDS = 5
_TEMPLATE_NAME_RE = re.compile(r"^[a-z0-9_]+$")
_HTTP_TIMEOUT = 15
_MEDIA_HOST_SUFFIXES = ("fbcdn.net", "facebook.com", "whatsapp.net", "fbsbx.com")
_SECRET_QS_RE = re.compile(r"(?i)((?:access_)?token=)[^&\s\"'<>]+")
_URL_RE = re.compile(r"https?://[^\s\"'<>]+")
# Frappe ``Data`` columns default to varchar(140); Meta example/CDN URLs can exceed it.
_DATA_COLUMN_LEN = 140
_TEMPLATE_DATA_FIELDS = ("template_name", "actual_name", "language_code", "header", "footer", "id", "status", "category")
_BUTTON_DATA_FIELDS = ("button_label", "phone_number", "website_url")


def _redact(text: Any) -> str:
	"""Strip access tokens and full URLs from text destined for errors/logs."""
	out = _SECRET_QS_RE.sub(r"\1[redacted]", str(text))
	return _URL_RE.sub("[url]", out)


def _test_hosts() -> set[str]:
	"""Extra ``host:port`` entries, honoured ONLY while running tests.

	``frappe.flags.whatsapp_test_media_hosts`` lets integration tests point media
	downloads at a local fake Graph server. It is ignored unless
	``frappe.flags.in_test`` is set, so production allowlists cannot be widened
	through it.
	"""
	if not getattr(frappe.flags, "in_test", False):
		return set()
	return {str(h).lower() for h in (getattr(frappe.flags, "whatsapp_test_media_hosts", None) or ())}


def graph_base_url(override: str | None = None) -> str:
	"""Graph API host; ``override`` (a credential) is honoured only while running tests."""
	if override and getattr(frappe.flags, "in_test", False):
		return str(override).strip().rstrip("/")
	return GRAPH_HOST


def _is_media_host(url: str) -> bool:
	parsed = urlparse(url)
	host = (parsed.hostname or "").lower()
	if host and parsed.netloc.lower() in _test_hosts():
		return parsed.scheme in ("http", "https")
	if parsed.scheme != "https" or not host:
		return False
	return any(host == suf or host.endswith("." + suf) for suf in _MEDIA_HOST_SUFFIXES)


class BridgeError(Exception):
	"""Structured bridge failure; ``payload`` is the error dict."""

	def __init__(self, payload: dict[str, Any]):
		super().__init__(payload.get("error") or "bridge_error")
		self.payload = payload


def _err(code: str, **extra: Any) -> dict[str, Any]:
	return {"success": False, "error": code, **extra}


def _gateway_required() -> dict[str, Any]:
	return _err(
		"gateway_required",
		message="Choose a WhatsApp gateway (or an account you may access); data is never listed across accounts.",
	)


def _default_get(*args: Any, **kwargs: Any) -> Any:
	import requests

	kwargs.setdefault("timeout", _HTTP_TIMEOUT)
	return requests.get(*args, **kwargs)


def is_available() -> bool:
	"""Return True when frappe_whatsapp's required DocTypes are installed."""
	try:
		return all(
			frappe.db.exists("DocType", dt)
			for dt in ("WhatsApp Message", "WhatsApp Templates", "WhatsApp Account")
		)
	except Exception:
		return False


def is_bsuid(raw: Any) -> bool:
	"""True for a business-scoped user id (``IN.4608...``): country-prefix dot form (``IN.123``, ``US.ENT.123``)."""
	text = str(raw or "").strip()
	return bool(re.match(r"^[A-Za-z]{2}\.[A-Za-z0-9.]+$", text))


def normalize_phone(raw: Any) -> str:
	"""Return digits only (no +, spaces, dashes, parens, leading ``00``); a BSUID is returned verbatim."""
	if is_bsuid(raw):
		return str(raw).strip()
	digits = re.sub(r"\D", "", str(raw or ""))
	if digits.startswith("00"):
		digits = digits[2:]
	return digits


def resolve_account(name: str | None = None) -> dict[str, Any] | None:
	"""Resolve a named WhatsApp Account to a plain dict.

	There is deliberately no default: an empty ``name`` is ``{"error": "no_account"}``.
	Gateway paths derive the account from ``Gateway.whatsapp_account`` and never guess;
	only non-gateway agent tools may use :func:`resolve_default_account`. Returns ``None``
	when the bridge is unavailable and ``{"error": "no_account"}`` when the account does
	not exist. Never raises for a missing account.
	"""
	if not is_available():
		return None
	if not name or not frappe.db.exists("WhatsApp Account", name):
		return {"error": "no_account"}
	doc = frappe.get_doc("WhatsApp Account", name)
	return {
		"name": doc.name,
		"phone_id": doc.get("phone_id"),
		"business_id": doc.get("business_id"),
		"app_id": doc.get("app_id"),
		"token": doc.get_password("token"),
		"url": (doc.get("url") or "https://graph.facebook.com").rstrip("/"),
		"version": doc.get("version") or GRAPH_DEFAULT_VERSION,
		"webhook_verify_token": doc.get("webhook_verify_token"),
		"status": doc.get("status"),
	}


def resolve_default_account() -> dict[str, Any] | None:
	"""The default outgoing (else first Active) account, for NON-gateway agent tools only.

	Gateway, webhook and management code must never call this: they resolve through
	``Gateway.whatsapp_account`` so one gateway can never act as another's account.
	"""
	if not is_available():
		return None
	name = frappe.db.get_value("WhatsApp Account", {"is_default_outgoing": 1}, "name")
	if not name:
		name = frappe.db.get_value("WhatsApp Account", {"status": "Active"}, "name")
	return resolve_account(name)


def gateway_account(gateway_name: str) -> str:
	"""``Gateway.whatsapp_account`` ('' when unlinked or the gateway is unknown)."""
	try:
		return str(frappe.db.get_value("Gateway", gateway_name, "whatsapp_account") or "").strip()
	except Exception:
		return ""


def account_business_id(account_name: Any) -> str:
	"""``WhatsApp Account.business_id`` ('' when unlinked, unknown or the bridge is unavailable)."""
	name = str(account_name or "").strip()
	if not name or not is_available():
		return ""
	try:
		return str(frappe.db.get_value("WhatsApp Account", name, "business_id") or "").strip()
	except Exception:
		return ""


def accounts_for_waba(waba_id: Any) -> list[str]:
	"""WhatsApp Accounts whose ``business_id`` is the given WABA id (payload ``entry[].id``)."""
	waba = str(waba_id or "").strip()
	if not waba or not is_available():
		return []
	try:
		return list(frappe.get_all("WhatsApp Account", filters={"business_id": waba}, pluck="name") or [])
	except Exception:
		return []


_run_bound: contextvars.ContextVar = contextvars.ContextVar("huf_whatsapp_run_bound_send", default=False)


@contextmanager
def run_bound_send():
	"""Server-side scope for the agent tool: the run's own gateway authorised the send, so the run user
	needs no WhatsApp Message create permission. Skips permission checks only (``trusted`` also commits)."""
	token = _run_bound.set(True)
	try:
		yield
	finally:
		_run_bound.reset(token)


def _may_bypass(trusted: bool) -> bool:
	return bool(trusted) or _run_bound.get()


def _refuse_if_disconnected(acct: dict[str, Any]) -> None:
	from huf.ai.whatsapp import account_events as _ae

	if (refusal := _ae.send_refusal(acct.get("phone_id"))):
		raise BridgeError(refusal)


def _account_or_error(account_name: str | None) -> dict[str, Any]:
	if not is_available():
		raise BridgeError(_err("bridge_unavailable"))
	acct = resolve_account(account_name)
	if not acct or acct.get("error"):
		raise BridgeError(_err("no_account"))
	return acct


def account_matches_phone_id(account_name: str, phone_number_id: str) -> bool:
	"""True iff the account's phone_id equals the payload phone_number_id (A11)."""
	if not account_name or not phone_number_id or not is_available():
		return False
	try:
		phone_id = frappe.db.get_value("WhatsApp Account", account_name, "phone_id")
	except Exception:
		return False
	return bool(phone_id) and str(phone_id) == str(phone_number_id)


def message_time(raw_payload: Any) -> datetime | None:
	"""Return the provider's own message timestamp as a naive system-time datetime.

	Meta stamps ``messages[].timestamp`` in epoch seconds (UTC). ``received_at``
	is stored with ``now_datetime()`` (naive, system timezone), so the epoch is
	converted into the system timezone and made naive to be comparable.
	"""
	if isinstance(raw_payload, (str, bytes)):
		try:
			raw_payload = json.loads(raw_payload)
		except ValueError:
			return None
	message = raw_payload.get("message") if isinstance(raw_payload, dict) else None
	if not isinstance(message, dict):
		return None
	try:
		epoch = int(str(message.get("timestamp")).strip())
		utc = datetime.fromtimestamp(epoch, tz=timezone.utc)
	except (TypeError, ValueError, OverflowError, OSError):
		return None
	return frappe.utils.convert_utc_to_system_timezone(utc).replace(tzinfo=None)


def is_reaction_payload(raw_payload: Any) -> bool:
	"""True when a stored Gateway Event ``raw_payload`` describes an inbound reaction."""
	if isinstance(raw_payload, (str, bytes)):
		try:
			raw_payload = json.loads(raw_payload)
		except ValueError:
			return False
	if not isinstance(raw_payload, dict):
		return False
	if raw_payload.get("kind") == "reaction":
		return True
	message = raw_payload.get("message")
	return isinstance(message, dict) and message.get("type") == "reaction"


def payload_kind(raw_payload: Any) -> str:
	"""``kind`` of a stored Gateway Event ``raw_payload`` ("" when absent or unparsable)."""
	if isinstance(raw_payload, (str, bytes)):
		try:
			raw_payload = json.loads(raw_payload)
		except ValueError:
			return ""
	return str(raw_payload.get("kind") or "") if isinstance(raw_payload, dict) else ""


def fallback_template_info(account_name: str, template_name: str, language: str | None = None) -> dict[str, Any] | None:
	"""``{"status", "variables"}`` of the account's template row (None when unknown or unavailable).

	``variables`` are the body variable tokens in order (``"1"`` or a NAMED token).
	"""
	if not is_available():
		return None
	try:
		row = _template_row(_template_docname(account_name, template_name, language))
	except Exception:
		return None
	if not row or (row.get("whatsapp_account") or "") != (account_name or ""):
		return None
	return {"status": str(row.get("status") or ""), "variables": wt.variables(row.get("template") or "")}


def window_state(gateway_name: str, phone: str, now: datetime | None = None) -> dict[str, Any]:
	"""Compute the 24h customer-service window from signed Gateway Events only (A3).

	Only inbound events with ``verified_sender=1`` for the same gateway and
	normalised sender count. WhatsApp Message rows are never consulted.

	The window anchors on the customer's own message time (Meta redelivers old
	webhooks for days, so ``received_at`` alone would reopen a closed window),
	falling back to ``received_at`` when the payload carries no timestamp. The
	message time is capped at ``received_at`` so clock skew cannot extend it.
	"""
	now = now or frappe.utils.now_datetime()
	sender = normalize_phone(phone)
	rows = frappe.get_all(
		"Gateway Event",
		filters={
			"gateway": gateway_name,
			"sender_id": sender,
			"verified_sender": 1,
			"received_at": [">=", now - timedelta(hours=WINDOW_HOURS)],
		},
		fields=["received_at", "verified_sender", "sender_id", "raw_payload"],
		order_by="received_at desc",
		limit_page_length=50,
	)
	from huf.ai.gateway_adapters import whatsapp_inbound as inbound

	last = None
	for row in rows or []:
		if not row.get("verified_sender"):
			continue
		if payload_kind(row.get("raw_payload")) in inbound.RECORD_ONLY_KINDS:
			continue  # recorded edit/revoke/system/unknown events never open or extend the window
		if is_reaction_payload(row.get("raw_payload")):
			continue  # a reaction never opens or extends the customer-service window
		ts = row.get("received_at")
		if not ts:
			continue
		sent = message_time(row.get("raw_payload"))
		if sent is not None:
			ts = min(sent, ts)
		if last is None or ts > last:
			last = ts
	if last is None:
		return {"open": False, "last_inbound_at": None, "expires_at": None}
	expires = last + timedelta(hours=WINDOW_HOURS)
	return {"open": now < expires and last <= now, "last_inbound_at": last, "expires_at": expires}


def record_incoming(account_name: str, message: dict[str, Any], profile_name: str | None = None) -> str | None:
	"""Idempotently mirror a signed inbound message into ``WhatsApp Message``.

	Returns the doc name, or None when unavailable / no message id. Does not
	trigger an outgoing send (type Incoming).
	"""
	if not is_available():
		return None
	message_id = (message or {}).get("id") or (message or {}).get("message_id")
	if not message_id:
		return None
	existing = frappe.db.get_value("WhatsApp Message", {"message_id": message_id}, "name")
	if existing:
		return existing
	from huf.ai.gateway_adapters import whatsapp_inbound as inbound

	raw_type = message.get("type") or message.get("content_type") or "text"
	if raw_type == "reaction":
		return None  # reactions are kept on the Gateway Event only, never mirrored
	content_type = inbound.CONTENT_TYPES.get(raw_type, "text")
	body = inbound.render_message_text({**message, "type": raw_type})
	if not body:
		body = message.get("body") or message.get("message") or ""
	doc = frappe.get_doc(
		{
			"doctype": "WhatsApp Message",
			"type": "Incoming",
			"from": normalize_phone(message.get("from")),
			"message": body,
			"message_id": message_id,
			"content_type": content_type,
			"profile_name": profile_name,
			"whatsapp_account": account_name,
		}
	)
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)  # signed ingress mirror, internal
	return doc.name


def _readback(doc: Any) -> dict[str, Any]:
	return {
		"success": True,
		"name": doc.name,
		"message_id": doc.get("message_id"),
		"status": doc.get("status"),
	}


def send_text(
	account_name: str,
	to: str,
	text: str,
	reply_to: str | None = None,
	trusted: bool = False,
	preview_url: bool | None = None,
	http_post: Callable[..., Any] | None = None,
) -> dict[str, Any]:
	"""Send a free-form text via ``WhatsApp Message`` (it performs the one send, A1).

	``preview_url`` (gateway reply path, ``trusted`` only): when not None the text is posted to Graph
	directly with the account credentials (frappe_whatsapp hardcodes ``preview_url: true``) and the
	outgoing row is mirrored afterwards without a second send. Management sends leave it None.

	``trusted=True`` is only for the gateway-internal reply path and skips
	permission checks; user-initiated calls must leave it False. Raises
	:class:`BridgeError` (``.payload`` is the error dict) on failure.
	"""
	acct = _account_or_error(account_name)
	_refuse_if_disconnected(acct)
	if preview_url is not None and trusted:
		return _send_text_direct(acct, to, text, reply_to, bool(preview_url), http_post)
	values = {
		"doctype": "WhatsApp Message",
		"type": "Outgoing",
		"to": normalize_phone(to),
		"message": text,
		"content_type": "text",
		"whatsapp_account": account_name,
	}
	if reply_to:
		values["is_reply"] = 1
		values["reply_to_message_id"] = reply_to
	try:
		doc = frappe.get_doc(values)
		doc.insert(ignore_permissions=_may_bypass(trusted))
		if trusted:
			# Gateway reply path runs in a background job: persist the outgoing row
			# now so Meta's status webhook can match its wamid straight away.
			frappe.db.commit()
	except frappe.PermissionError:
		raise
	except Exception as exc:
		raise BridgeError(_err("send_failed", message=_redact(exc))) from exc
	return _readback(doc)


def _text_payload(to: str, text: str, reply_to: str | None, preview_url: bool) -> dict[str, Any]:
	data: dict[str, Any] = {
		"messaging_product": "whatsapp",
		"recipient_type": "individual",
		"to": normalize_phone(to),
		"type": "text",
		"text": {"preview_url": bool(preview_url), "body": text},
	}
	if reply_to:
		data["context"] = {"message_id": reply_to}
	return data


def _send_text_direct(
	acct: dict[str, Any], to: str, text: str, reply_to: str | None, preview_url: bool, http_post: Callable[..., Any] | None
) -> dict[str, Any]:
	"""Post a text straight to Graph, then mirror the Outgoing row with the wamid preset (no second send)."""
	wamid = _graph_post_message(acct, _text_payload(to, text, reply_to, preview_url), http_post)
	values = {
		"doctype": "WhatsApp Message",
		"type": "Outgoing",
		"to": normalize_phone(to),
		"message": text,
		"content_type": "text",
		"whatsapp_account": acct["name"],
		"message_id": wamid,
		"status": "Success",
		# frappe_whatsapp sends every non-template Outgoing row from before_insert; "Template" is its own
		# "already delivered" path and, with the preset message_id, makes the row audit-only (no second send).
		"message_type": "Template",
	}
	if reply_to:
		values["is_reply"] = 1
		values["reply_to_message_id"] = reply_to
	try:
		doc = frappe.get_doc(values)
		doc.insert(ignore_permissions=True)
		frappe.db.commit()
		return {"success": True, "name": doc.name, "message_id": wamid, "status": doc.get("status")}
	except Exception:
		# Already delivered: a failed audit row must never fail (or retry) the send.
		return {"success": True, "name": None, "message_id": wamid, "status": "Success", "mirrored": False}


READ_TYPING_TIMEOUT = 5


def mark_read_typing(account_name: str, message_id: str, http_post: Callable[..., Any] | None = None) -> bool:
	"""Best effort ``status: read`` + typing indicator for an inbound wamid. Never raises, no retry."""
	try:
		if not message_id:
			return False
		acct = _account_or_error(account_name)
		http_post = http_post or _default_post
		resp = http_post(
			f"{acct['url']}/{acct['version']}/{acct['phone_id']}/messages",
			json=read_typing_payload(message_id),
			headers={"Authorization": f"Bearer {acct['token']}", "Content-Type": "application/json"},
			timeout=READ_TYPING_TIMEOUT,
		)
		status = getattr(resp, "status_code", 200)
		return not (isinstance(status, int) and status >= 400)
	except Exception:
		return False


def read_typing_payload(message_id: str) -> dict[str, Any]:
	return {
		"messaging_product": "whatsapp",
		"status": "read",
		"message_id": str(message_id),
		"typing_indicator": {"type": "text"},
	}


def _template_docname(account_name: str, template_name: str, language_code: str | None = None) -> str:
	"""Map a Meta template name to the ``WhatsApp Templates`` document name, within one account.

	``WhatsApp Message.template`` is a Link to the document, whose name is
	``<template_name>-<language_code>`` and not the bare Meta name. With several
	languages for one template, ``language_code`` picks the matching row. Every lookup
	is filtered by ``whatsapp_account``: another account's template of the same name is
	never returned (an unmatched name is returned unchanged for the caller to reject).
	"""
	scoped = frappe.db.get_value(
		"WhatsApp Templates", {"name": template_name, "whatsapp_account": account_name}, "name"
	)
	if scoped:
		return scoped
	for field in ("actual_name", "template_name"):
		filters = {"whatsapp_account": account_name, field: template_name}
		if language_code:
			name = frappe.db.get_value("WhatsApp Templates", {**filters, "language_code": language_code}, "name")
			if name:
				return name
		if not language_code:
			rows = frappe.get_all("WhatsApp Templates", filters=filters, fields=["name", "language_code"], limit_page_length=50)
			if len(rows) > 1:
				langs = sorted({r.get("language_code") or "" for r in rows if r.get("language_code")})
				raise BridgeError(
					_err(
						"language_required",
						message=f"Template '{template_name}' exists in several languages; pass language_code.",
						languages=langs,
					)
				)
		name = frappe.db.get_value("WhatsApp Templates", filters, "name")
		if name:
			return name
	return template_name


def template_language(account_name: str, template_name: str, preferred: str | None = None) -> str | None:
	"""Language code of the account's WhatsApp Templates row for ``template_name`` (None if not found)."""
	if not is_available():
		return None
	try:
		scoped = frappe.db.get_value(
			"WhatsApp Templates", {"name": template_name, "whatsapp_account": account_name}, "language_code"
		)
		if scoped:
			return scoped
		for field in ("actual_name", "template_name"):
			filters = {"whatsapp_account": account_name, field: template_name}
			if preferred:
				found = frappe.db.get_value("WhatsApp Templates", {**filters, "language_code": preferred}, "language_code")
				if found:
					return found
			found = frappe.db.get_value("WhatsApp Templates", filters, "language_code")
			if found:
				return found
	except Exception:
		return None
	return None


def _default_post(*args: Any, **kwargs: Any) -> Any:
	import requests

	kwargs.setdefault("timeout", _HTTP_TIMEOUT)
	return requests.post(*args, **kwargs)


def graph_error_message(resp: Any) -> str:
	"""Readable, token-free message from a Meta Graph error response."""
	try:
		err = (resp.json() or {}).get("error") or {}
	except Exception:
		err = {}
	if err:
		details = (err.get("error_data") or {}).get("details")
		parts = [f"({err.get('code')})" if err.get("code") is not None else "", str(err.get("message") or "")]
		if details:
			parts.append(str(details))
		return _redact(" ".join(p for p in parts if p).strip())
	return _redact(getattr(resp, "text", "") or f"HTTP {getattr(resp, 'status_code', '?')}")


EDIT_BLOCKED_SUBCODE = 2388039
EDIT_BLOCKED_TEXT = (
	"Meta won't let this template be edited right now (it may still be in review, or was just "
	"approved/reclassified). Try again later or create a new version."
)
EDIT_BLOCKED_SECONDS = 3600


def graph_error_detail(resp_or_exc: Any) -> dict[str, Any]:
	"""Structured, always-redacted detail of a Graph error response or exception. Never raises.

	Keys: ``message`` (best human text: Meta user message, else Meta message plus the classifier advice), ``user_title``,
	``user_msg`` (Meta's ``error_user_title`` / ``error_user_msg``), ``code``, ``subcode``, ``kind``
	(from ``whatsapp_errors.classify``), ``retryable``, ``operator_text``, ``trace_id`` (``fbtrace_id``).
	Subcode 2388039 ("status can't be changed") gets a plain explanation as ``operator_text``/``message``.
	"""
	from huf.ai.gateway_adapters import whatsapp_errors as we

	def clean(value: Any) -> str:
		return _redact(we.redact(value)).strip() if value not in (None, "") else ""

	try:
		cls = we.classify(resp_or_exc)
		try:
			inner = we._unpack(resp_or_exc)[1] or {}
		except Exception:
			inner = {}
		title, user_msg = clean(inner.get("error_user_title")), clean(inner.get("error_user_msg"))
		trace = clean(inner.get("fbtrace_id"))
		code, subcode, kind = cls.get("code"), cls.get("subcode"), cls.get("kind") or "unknown"
		operator_text = clean(cls.get("operator_text"))
		meta_message = clean(cls.get("message")) or clean(resp_or_exc)
		blocked = subcode == EDIT_BLOCKED_SUBCODE or "can't be changed" in f"{title} {user_msg}".lower()
		if blocked:
			kind, operator_text = "edit_blocked", EDIT_BLOCKED_TEXT
			message = EDIT_BLOCKED_TEXT + (f" Meta says: {user_msg}" if user_msg else "")
		else:
			# Meta's own user message first; else its message, plus the classifier's advice when that adds something
			message = user_msg or meta_message or operator_text
			if not user_msg and operator_text and kind not in ("unknown", "param") and operator_text not in message:
				message = f"{message} {operator_text}".strip()
		return {
			"message": message, "user_title": title, "user_msg": user_msg, "code": code, "subcode": subcode,
			"kind": kind, "retryable": bool(cls.get("retryable")) and not blocked, "operator_text": operator_text,
			"trace_id": trace,
		}
	except Exception:
		return {
			"message": clean(resp_or_exc) or "Meta request failed.", "user_title": "", "user_msg": "", "code": None,
			"subcode": None, "kind": "unknown", "retryable": False, "operator_text": "", "trace_id": "",
		}


def _graph_err(error: str, resp_or_exc: Any, **extra: Any) -> dict[str, Any]:
	"""Error dict carrying the structured Graph detail (the numeric Graph code is ``graph_code``)."""
	d = graph_error_detail(resp_or_exc)
	return _err(
		error, message=d["message"], user_title=d["user_title"], user_msg=d["user_msg"],
		graph_code=d["code"], subcode=d["subcode"], kind=d["kind"], retryable=d["retryable"],
		operator_text=d["operator_text"], trace_id=d["trace_id"], **extra,
	)


def _graph_post(
	acct: dict[str, Any], data: dict[str, Any], http_post: Callable[..., Any] | None = None, marketing_api: bool = False
) -> dict[str, Any]:
	"""POST to ``/messages`` (``/marketing_messages`` if ``marketing_api``); returns ``{"wamid", "message_status"}`` or raises BridgeError."""
	from huf.ai.whatsapp import account_events as _ae

	if (refusal := _ae.send_refusal(acct.get("phone_id"))):
		raise BridgeError(refusal)
	http_post = http_post or _default_post
	url = f"{acct['url']}/{acct['version']}/{acct['phone_id']}/{'marketing_messages' if marketing_api else 'messages'}"
	try:
		resp = http_post(
			url,
			json=data,
			headers={"Authorization": f"Bearer {acct['token']}", "Content-Type": "application/json"},
			timeout=_HTTP_TIMEOUT,
		)
	except Exception as exc:
		raise BridgeError({**_graph_err("send_failed", exc), "message": _redact(exc)}) from exc
	status = getattr(resp, "status_code", 200)
	if isinstance(status, int) and status >= 400:
		raise BridgeError({**_graph_err("send_failed", resp), "message": graph_error_message(resp)})
	try:
		first = resp.json()["messages"][0]
		wamid = str(first["id"])
	except Exception as exc:
		raise BridgeError(_err("send_failed", message="Unexpected response from WhatsApp.")) from exc
	ms = first.get("message_status") if isinstance(first, dict) else None
	return {"wamid": wamid, "message_status": str(ms) if ms else None}


def _graph_post_message(acct: dict[str, Any], data: dict[str, Any], http_post: Callable[..., Any] | None = None) -> str:
	"""POST a ``/messages`` body with the account credentials; returns the wamid or raises BridgeError."""
	return _graph_post(acct, data, http_post)["wamid"]


OPAQUE_REF_MAX = 256


def _clean_opaque_ref(ref: Any) -> str | None:
	"""``biz_opaque_callback_data``: stripped, at most 256 chars; None if empty."""
	if ref is None:
		return None
	text = str(ref).strip()[:OPAQUE_REF_MAX]
	return text or None


def _template_row(docname: str) -> dict[str, Any] | None:
	"""Header/body/button definition of a WhatsApp Templates document (None if unknown).

	``parameter_format`` / ``header_format`` come from the Template Extra when Huf holds one
	(NAMED variables, VIDEO / LOCATION headers); empty otherwise.
	"""
	if not frappe.db.exists("WhatsApp Templates", docname):
		return None
	row = frappe.db.get_value(
		"WhatsApp Templates",
		docname,
		[
			"template", "header_type", "header", "sample", "actual_name", "template_name", "language_code", "status",
			"whatsapp_account", "category",
		],
		as_dict=True,
	)
	row["buttons"] = frappe.get_all(
		"WhatsApp Button",
		filters={"parent": docname, "parenttype": "WhatsApp Templates"},
		fields=["button_type", "button_label", "url_type", "website_url"],
		order_by="idx asc",
	)
	extra = _get_extra(row.get("whatsapp_account"), docname) or {}
	row["parameter_format"] = extra.get("parameter_format") or ""
	row["header_format"] = extra.get("header_format") or ""
	return row


def _get_extra(account: str | None, template: str) -> dict[str, Any] | None:
	"""Template Extra (``whatsapp_template_guard.get_extra``), None when unavailable."""
	try:
		from huf.ai.gateway_adapters import whatsapp_template_guard as guard

		return guard.get_extra(account, template)
	except Exception:
		return None


def _mirror_template_send(acct: dict[str, Any], docname: str, to: str, wamid: str, values: dict[str, Any], trusted: bool) -> dict[str, Any]:
	"""Record a Graph-sent template as an Outgoing ``WhatsApp Message`` without sending again.

	``message_id`` is preset, which makes frappe_whatsapp skip its own send.
	"""
	doc_values = {
		"doctype": "WhatsApp Message",
		"type": "Outgoing",
		"to": normalize_phone(to),
		"use_template": 1,
		"template": docname,
		"whatsapp_account": acct["name"],
		"content_type": "text",
		"message_id": wamid,
		"status": "Success",
		**values,
	}
	try:
		doc = frappe.get_doc(doc_values)
		doc.insert(ignore_permissions=_may_bypass(trusted))
		if trusted:
			frappe.db.commit()
		return {"success": True, "name": doc.name, "message_id": wamid, "status": doc.get("status")}
	except Exception:
		# The template is already delivered; a failed audit row must not fail the send.
		return {"success": True, "name": None, "message_id": wamid, "status": "Success", "mirrored": False}


def _named_names(raw: Any) -> list[str]:
	"""Variable names carried by a NAMED parameter value (``{name: v}`` or ``[{name, value}]``)."""
	if isinstance(raw, dict):
		return [str(k) for k in raw]
	if isinstance(raw, (list, tuple)) and raw and all(isinstance(x, dict) for x in raw):
		return [str(x.get("name") or x.get("parameter_name") or "") for x in raw]
	return []


def _params_template_view(body_params: Any, header_params: Any) -> dict[str, Any]:
	"""Stand-in template for a send with no known template: NAMED when the params are named."""
	body_names = _named_names(body_params)
	header_names = _named_names(header_params) if isinstance(header_params, dict) and "type" not in header_params else []
	if not body_names and not header_names:
		return {}
	return {
		"parameter_format": "NAMED",
		"body": " ".join("{{%s}}" % n for n in body_names),
		"header_type": "TEXT" if header_names else "",
		"header_text": "{{%s}}" % header_names[0] if header_names else "",
	}


def split_copy_code_params(button_params: Any) -> tuple[list[Any], list[dict[str, Any]], list[dict[str, str]]]:
	"""Split COPY_CODE button params (``{"index", "sub_type": "copy_code", "code"|"text"}``) off ``button_params``.

	Returns ``(other_params, copy_code_components, errors)``; the copy-code components are ready
	Graph ``button`` components.
	"""
	rest: list[Any] = []
	comps: list[dict[str, Any]] = []
	errors: list[dict[str, str]] = []
	for i, item in enumerate(button_params or []):
		if isinstance(item, dict) and str(item.get("sub_type") or item.get("type") or "").lower() == "copy_code":
			code = str(item.get("code") if item.get("code") is not None else item.get("text") or "").strip()
			try:
				index = int(item.get("index", i))
			except (TypeError, ValueError):
				index = -1
			if not 0 <= index <= 9:
				errors.append(wt._e(f"button_params[{i}].index", "invalid_index", "Button index must be an integer 0-9."))
			elif not code or len(code) > 15:
				errors.append(wt._e(f"button_params[{i}]", "invalid_code", "A copy-code parameter needs a code of at most 15 characters."))
			else:
				comps.append({
					"type": "button", "sub_type": "copy_code", "index": str(index),
					"parameters": [{"type": "coupon_code", "coupon_code": code}],
				})
		else:
			rest.append(item)
	return rest, comps, errors


def _header_list(header_params: Any, has_template: bool) -> Any:
	"""Raw header params as ``build_send_components`` expects them (media URL strings get a default kind
	only when no template says which)."""
	if isinstance(header_params, dict):
		return header_params
	items = list(header_params or [])
	if not has_template:
		items = [{"type": "image", "link": h.strip()} if isinstance(h, str) and wt.is_http_url(h.strip()) else h for h in items]
	return items


def send_error(errors: list[dict[str, str]]) -> dict[str, Any]:
	"""Structured send error; missing/unknown NAMED parameters surface as the top-level ``error`` code."""
	out = wt.validation_error(errors)
	if errors and errors[0].get("code") in ("param_missing", "param_unknown"):
		out["error"] = errors[0]["code"]
	return out


def direct_send_components(
	body_params: Any = None, header_params: Any = None, button_params: Any = None, template: Any = None
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
	"""Graph ``template.components`` for a send that bypasses the local template row (direct mode).

	``template`` (spec or Meta components) is optional: without it NAMED params are recognised from their
	shape (a ``{name: value}`` dict). Media header objects must carry their kind here.
	"""
	rest, copy_comps, cerr = split_copy_code_params(button_params)
	view = template if template else _params_template_view(body_params, header_params)
	components, errors = wt.build_send_components(view, body_params, _header_list(header_params, False), rest)
	if isinstance(header_params, dict):
		header_items = [header_params] if "type" in header_params else []
	else:
		header_items = list(header_params or [])
	if any(isinstance(h, dict) and not h.get("type") for h in header_items):
		errors.append(wt._e("header_params", "invalid_type", "Media header needs a type (image, document or video)."))
	return components + copy_comps, cerr + errors


def _send_view(tpl: dict[str, Any]) -> dict[str, Any]:
	"""Template definition in the shape ``build_send_components`` reads."""
	htype = str(tpl.get("header_format") or tpl.get("header_type") or "").upper()
	return {
		"body": tpl.get("template") or "",
		"header_type": htype,
		"header_text": (tpl.get("header") or "") if htype == "TEXT" else "",
		"parameter_format": tpl.get("parameter_format") or "",
	}


def send_template(
	account_name: str,
	to: str,
	template_name: str,
	body_params: Any = None,
	header_params: Any = None,
	trusted: bool = False,
	language_code: str | None = None,
	button_params: list | None = None,
	http_post: Callable[..., Any] | None = None,
	gateway_name: str | None = None,
	run_id: str | None = None,
	solution: str | None = None,
	force_graph: bool = False,
	opaque_ref: str | None = None,
	marketing_api: bool = False,
) -> dict[str, Any]:
	"""Send an approved template. ``force_graph`` always posts to Graph (returns ``wamid`` and ``message_status``),
	``opaque_ref`` is echoed on status webhooks, ``marketing_api`` uses the Marketing Messages endpoint.

	``run_id`` / ``solution`` (optional) attribute the send to a Solution for template usage tracking.

	Goes through :mod:`huf.ai.whatsapp.outbound_policy` first: a STOPped contact, a BSUID recipient, a
	template that is not APPROVED and marketing to a contact who stopped marketing are refused with a
	``BridgeError`` whose ``error`` is the policy code. ``gateway_name`` scopes the checks; without it
	every Gateway linked to the account is checked.

	Plain body-only sends of POSITIONAL templates use an Outgoing ``WhatsApp Message``
	(use_template=1), which frappe_whatsapp sends. Everything else (header or button parameters,
	NAMED variables, LOCATION / VIDEO headers) needs components frappe_whatsapp cannot build, so
	it is posted to Graph with the account credentials and mirrored into ``WhatsApp Message``
	without a second send.

	``body_params``: an ordered list; for NAMED templates also a ``{name: value}`` dict or a list of
	``{name, value}`` (every body / text-header parameter then carries ``parameter_name``).
	``header_params``: one text string, one ``{"type": image|document|video, "link": ...,
	"filename"?: ...}``, or ``{"type": "location", "latitude", "longitude", "name"?, "address"?}``;
	for a NAMED text header a one-entry ``{name: value}`` dict. ``button_params``: ``[{"index": 0,
	"sub_type": "url", "text": "<suffix>"}]`` (a bare string is the URL suffix at its list
	position) and ``{"index": n, "sub_type": "copy_code", "code": "..."}``. Permission-checked
	unless ``trusted=True`` (gateway-internal reply path). Raises :class:`BridgeError` (``.payload``
	is the error dict; ``error`` is ``validation_failed``, or ``param_missing`` / ``param_unknown``
	for NAMED mismatches, with the full ``errors`` list).
	"""
	acct = _account_or_error(account_name)
	_refuse_if_disconnected(acct)
	docname = _template_docname(account_name, template_name, language_code)
	tpl = _template_row(docname)
	if tpl and (tpl.get("whatsapp_account") or "") != (account_name or ""):
		# the docname resolves to another account's template: never send it from this account
		raise BridgeError(_err("template_not_found", message="That template does not belong to this WhatsApp account."))

	try:
		policy.enforce_template(account_name, to, tpl, gateway_name)
	except policy.OutboundRefused as exc:
		raise BridgeError(_err(exc.code, message=str(exc))) from exc

	other_buttons, copy_comps, errors = split_copy_code_params(button_params)
	view = _send_view(tpl) if tpl else _params_template_view(body_params, header_params)
	header_raw = _header_list(header_params, bool(tpl))
	components, build_errors = wt.build_send_components(view, body_params, header_raw, other_buttons)
	errors += build_errors
	if tpl:
		seen = {(e["field"], e["code"]) for e in errors}
		errors += [
			e for e in _check_send_against_template(tpl, view, body_params, header_raw, other_buttons, copy_comps)
			if (e["field"], e["code"]) not in seen
		]
	if errors:
		raise BridgeError(send_error(errors))
	components += copy_comps

	header_type = view.get("header_type") or ""
	header_given = any(c.get("type") == "header" for c in components)
	if tpl and header_type in wt.MEDIA_HEADER_TYPES and not header_given:
		if not (header_type == "IMAGE" and wt.is_http_url(str(tpl.get("sample") or ""))):
			raise BridgeError(
				wt.validation_error(
					[wt._e("header_params", "required", f"This template has an {header_type} header; provide a media link.")]
				)
			)
	named = wt._template_view(view)["fmt"] == "NAMED"
	body_comp = next((c for c in components if c.get("type") == "body"), None)
	body_items = (body_comp or {}).get("parameters") or []
	params = [str(p.get("text")) for p in body_items]
	if named:
		body_map = {p["parameter_name"]: p["text"] for p in body_items if p.get("parameter_name")}
	else:
		body_map = {str(i + 1): p for i, p in enumerate(params)}

	if marketing_api and not force_graph:
		raise BridgeError(_err("invalid_request", message="marketing_api requires force_graph."))
	if force_graph or named or any(c.get("type") in ("header", "button") for c in components) or (tpl and _has_dynamic_url(tpl)):
		if not _may_bypass(trusted) and not frappe.has_permission("WhatsApp Message", "create"):
			raise frappe.PermissionError("Not permitted to send WhatsApp messages")
		template_payload: dict[str, Any] = {
			"name": (tpl or {}).get("actual_name") or (tpl or {}).get("template_name") or template_name,
			"language": {"code": (tpl or {}).get("language_code") or language_code or "en_US"},
		}
		if components:
			template_payload["components"] = components
		payload: dict[str, Any] = {
			"messaging_product": "whatsapp",
			"recipient_type": "individual",
			"to": normalize_phone(to),
			"type": "template",
			"template": template_payload,
		}
		if (ref := _clean_opaque_ref(opaque_ref)):
			payload["biz_opaque_callback_data"] = ref
		if force_graph:
			posted = _graph_post(acct, payload, http_post, marketing_api=marketing_api)
		else:
			posted = {"wamid": _graph_post_message(acct, payload, http_post), "message_status": None}
		wamid = posted["wamid"]
		mirror: dict[str, Any] = {"template_parameters": ",".join(params)}
		if body_map:
			mirror["body_param"] = json.dumps(body_map)
		header_comp = next((c for c in components if c.get("type") == "header"), None)
		if header_comp:
			hp = header_comp["parameters"][0]
			if hp.get("type") == "text":
				mirror["template_header_parameters"] = str(hp.get("text"))
			elif hp.get("type") in ("image", "video", "document"):
				mirror["attach"] = (hp.get(hp["type"]) or {}).get("link")
		result = _mirror_template_send(acct, docname, to, wamid, mirror, trusted)
		result["wamid"] = wamid
		result["message_status"] = posted["message_status"]
		policy.note_template_sent(account_name, to, gateway_name, *_usage_args(tpl, template_name, language_code, run_id, solution))
		return result

	values: dict[str, Any] = {
		"doctype": "WhatsApp Message",
		"type": "Outgoing",
		"to": normalize_phone(to),
		"use_template": 1,
		"template": docname,
		"whatsapp_account": account_name,
		"content_type": "text",
		"template_parameters": ",".join(params),
		# frappe_whatsapp builds the Meta payload from body_param (JSON dict values)
		"body_param": json.dumps(body_map),
	}
	try:
		doc = frappe.get_doc(values)
		doc.insert(ignore_permissions=_may_bypass(trusted))
		if trusted:
			# Gateway reply path runs in a background job: persist the outgoing row
			# now so Meta's status webhook can match its wamid straight away.
			frappe.db.commit()
	except frappe.PermissionError:
		raise
	except Exception as exc:
		raise BridgeError(_err("send_failed", message=_redact(exc))) from exc
	policy.note_template_sent(account_name, to, gateway_name, *_usage_args(tpl, template_name, language_code, run_id, solution))
	return _readback(doc)


def _usage_args(
	tpl: dict[str, Any] | None, template_name: str, language_code: str | None, run_id: str | None, solution: str | None
) -> tuple[str | None, str | None, str | None]:
	"""``(Meta template name, language, solution)`` for template usage; the solution comes from the Agent Run when not given."""
	try:
		sol = solution
		if not sol and run_id:
			from huf.ai.solutions.template_usage import solution_for_run

			sol = solution_for_run(run_id)
		name = (tpl or {}).get("actual_name") or (tpl or {}).get("template_name") or template_name
		return name, (tpl or {}).get("language_code") or language_code, sol or None
	except Exception:
		return None, None, None


def _has_dynamic_url(tpl: dict[str, Any]) -> bool:
	return any(b.get("button_type") == "Visit Website" and b.get("url_type") == "Dynamic" for b in tpl.get("buttons") or [])


def _check_send_against_template(
	tpl: dict[str, Any],
	view: dict[str, Any],
	body_params: Any,
	header_raw: Any,
	button_params: list[Any],
	copy_comps: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
	"""Compare raw send params with the template definition (counts, header kind, button kinds)."""
	errors: list[dict[str, str]] = []
	tv = wt._template_view(view)
	if tv["fmt"] != "NAMED":  # NAMED mismatches (param_missing / param_unknown) come from build_send_components
		given = list(body_params.values()) if isinstance(body_params, dict) else list(body_params or [])
		expected = len(tv["body_vars"])
		if expected != len(given):
			errors.append(wt._e("body_params", "param_count_mismatch", f"This template takes {expected} body parameter(s); got {len(given)}."))
	header_type = tv["header_type"]
	if isinstance(header_raw, dict):
		items = [header_raw] if "type" in header_raw else list(header_raw.values())
	else:
		items = list(header_raw or [])
	first = items[0] if items else None
	first_kind = str(first.get("type") or "").lower() if isinstance(first, dict) else ""
	if header_type == "TEXT":
		header_vars = len(tv["header_vars"])
		if header_vars and not items:
			errors.append(wt._e("header_params", "required", "This template header has a variable; provide one header parameter."))
		elif not header_vars and items:
			errors.append(wt._e("header_params", "not_expected", "This template header takes no parameter."))
		elif isinstance(first, dict):
			errors.append(wt._e("header_params", "invalid_type", "This template header needs text, not media."))
	elif header_type in wt.MEDIA_HEADER_TYPES:
		if items and not isinstance(first, (dict, str)):
			errors.append(wt._e("header_params", "invalid_type", f"This template has an {header_type} header; provide a media link."))
		elif items and not isinstance(first, dict):
			pass  # a bare link: the kind is the template's
		elif first_kind and first_kind != header_type.lower():
			errors.append(wt._e("header_params", "invalid_type", f"This template has an {header_type} header."))
	elif header_type == "LOCATION":
		if not items:
			errors.append(wt._e("header_params", "required", "This template has a LOCATION header; provide latitude and longitude."))
		elif first_kind != "location":
			errors.append(wt._e("header_params", "invalid_type", "This template has a LOCATION header; provide a location."))
	elif items:
		errors.append(wt._e("header_params", "not_expected", "This template has no header."))
	buttons_n, _ = wt.normalize_button_params(button_params)
	buttons = tpl.get("buttons") or []
	dynamic = {i for i, b in enumerate(buttons) if b.get("button_type") == "Visit Website" and b.get("url_type") == "Dynamic"}
	copy_idx = {i for i, b in enumerate(buttons) if b.get("button_type") == wt.DOCTYPE_BUTTON_TYPE["COPY_CODE"]}
	given_idx = set()
	for bp in buttons_n:
		idx = bp["index"]
		if bp["sub_type"] == "url":
			if idx not in dynamic:
				errors.append(wt._e("button_params", "unexpected", f"Button {idx} is not a dynamic URL button."))
			given_idx.add(idx)
		elif idx >= len(buttons) or buttons[idx].get("button_type") != "Quick Reply":
			errors.append(wt._e("button_params", "unexpected", f"Button {idx} is not a quick-reply button."))
	for idx in sorted(dynamic - given_idx):
		errors.append(wt._e("button_params", "required", f"Button {idx} is a dynamic URL button and needs its URL suffix."))
	copy_given = {int(c["index"]) for c in copy_comps or []}
	for idx in sorted(copy_given - copy_idx):
		errors.append(wt._e("button_params", "unexpected", f"Button {idx} is not a copy-code button."))
	for idx in sorted(copy_idx - copy_given):
		errors.append(wt._e("button_params", "required", f"Button {idx} is a copy-code button and needs its code."))
	return errors


def send_media(
	account_name: str,
	to: str,
	kind: str,
	link: str | None = None,
	media_id: str | None = None,
	caption: str | None = None,
	filename: str | None = None,
	reply_to: str | None = None,
	trusted: bool = False,
	voice: bool | None = None,
	http_post: Callable[..., Any] | None = None,
	http_get: Callable[..., Any] | None = None,
) -> dict[str, Any]:
	"""Send an image/document/audio/video/sticker; exactly one Graph call.

	A ``link`` is preflighted first (:func:`preflight_media_link`): Meta fetches links asynchronously, so a
	dead or hotlink-protected URL would otherwise return a message id and never be delivered.

	A plain image/document/audio/video by public ``link`` is an Outgoing ``WhatsApp Message`` (frappe_whatsapp
	reads ``attach``/``message`` and performs the send). It cannot send an uploaded ``media_id``, a sticker, a
	voice note or a document filename, so those are posted to Graph directly with the account credentials and
	mirrored into ``WhatsApp Message`` with ``message_id`` preset (no second send), like template sends.
	The caller is responsible for the 24h window and opt-out checks; free-form media is subject to both.
	"""
	_account_or_error(account_name)
	media, errors = wt.validate_media_request(kind, link, media_id, caption, filename, voice)
	if errors:
		raise BridgeError(wt.validation_error(errors))
	if not media["media_id"]:
		_preflight_link(media["kind"], media["link"], http_get)
	if media["media_id"] or media["kind"] == "sticker" or media["voice"] or media["filename"]:
		payload = wt.build_media_payload(normalize_phone(to), media, reply_to)
		return _send_payload(account_name, payload, trusted, http_post)
	values = {
		"doctype": "WhatsApp Message",
		"type": "Outgoing",
		"to": normalize_phone(to),
		"message": media["caption"],
		"content_type": media["kind"],
		"attach": media["link"],
		"whatsapp_account": account_name,
	}
	if reply_to:
		values["is_reply"] = 1
		values["reply_to_message_id"] = reply_to
	try:
		doc = frappe.get_doc(values)
		doc.insert(ignore_permissions=_may_bypass(trusted))
		if trusted:
			frappe.db.commit()
	except frappe.PermissionError:
		raise
	except Exception as exc:
		raise BridgeError(_err("send_failed", message=_redact(exc))) from exc
	return _readback(doc)


# ---------------------------------------------------------------------------
# Non-text outbound types (T5). Each is validated by whatsapp_messages, posted to Graph directly with the
# account credentials (frappe_whatsapp cannot build these bodies) and mirrored without a second send.
# ---------------------------------------------------------------------------
def _post_typed_message(acct: dict[str, Any], data: dict[str, Any], http_post: Callable[..., Any] | None = None) -> str:
	"""POST a ``/messages`` body; returns the wamid or raises BridgeError carrying the structured Graph error."""
	from huf.ai.whatsapp import account_events as _ae

	if (refusal := _ae.send_refusal(acct.get("phone_id"))):
		raise BridgeError(refusal)
	http_post = http_post or _default_post
	url = f"{acct['url']}/{acct['version']}/{acct['phone_id']}/messages"
	try:
		resp = http_post(
			url,
			json=data,
			headers={"Authorization": f"Bearer {acct['token']}", "Content-Type": "application/json"},
			timeout=_HTTP_TIMEOUT,
		)
	except Exception as exc:
		raise BridgeError(_err("send_failed", message=_redact(exc))) from exc
	status = getattr(resp, "status_code", 200)
	if isinstance(status, int) and status >= 400:
		raise BridgeError(_graph_err("send_failed", resp))
	try:
		return str(resp.json()["messages"][0]["id"])
	except Exception as exc:
		raise BridgeError(_err("send_failed", message="Unexpected response from WhatsApp.")) from exc


def _mirror_direct_send(acct: dict[str, Any], payload: dict[str, Any], wamid: str, trusted: bool) -> dict[str, Any]:
	"""Record a Graph-sent message as an Outgoing ``WhatsApp Message`` without sending again.

	frappe_whatsapp sends every non-template Outgoing row from ``before_insert``. ``message_type = "Template"``
	(its own flag for "already delivered / template path") together with the preset ``message_id`` makes it skip
	that send; the row is audit only. Verified against frappe_whatsapp by the single-send fake-Graph test.
	"""
	content_type, text = wm.mirror_summary(payload)
	mtype = payload.get("type")
	obj = payload.get(mtype) if isinstance(payload.get(mtype), dict) else {}
	values: dict[str, Any] = {
		"doctype": "WhatsApp Message",
		"type": "Outgoing",
		"to": payload.get("to"),
		"message": text,
		"content_type": content_type,
		"message_id": wamid,
		"status": "Success",
		"message_type": "Template",
		"whatsapp_account": acct["name"],
	}
	if mtype in ("image", "video", "audio", "document", "sticker") and obj.get("link"):
		values["attach"] = obj["link"]
	if mtype == "reaction":
		values["reply_to_message_id"] = obj.get("message_id")
	elif (payload.get("context") or {}).get("message_id"):
		values["is_reply"] = 1
		values["reply_to_message_id"] = payload["context"]["message_id"]
	try:
		doc = frappe.get_doc(values)
		doc.insert(ignore_permissions=_may_bypass(trusted))
		if trusted:
			frappe.db.commit()
		return {"success": True, "name": doc.name, "message_id": wamid, "status": doc.get("status")}
	except Exception:
		# already delivered: a failed audit row must not fail the send
		return {"success": True, "name": None, "message_id": wamid, "status": "Success", "mirrored": False}


def _send_payload(
	account_name: str, payload: dict[str, Any], trusted: bool = False, http_post: Callable[..., Any] | None = None
) -> dict[str, Any]:
	acct = _account_or_error(account_name)
	if not _may_bypass(trusted) and not frappe.has_permission("WhatsApp Message", "create"):
		raise frappe.PermissionError("Not permitted to send WhatsApp messages")
	wamid = _post_typed_message(acct, payload, http_post)
	return _mirror_direct_send(acct, payload, wamid, trusted)


def _built(result: tuple[dict[str, Any] | None, list[dict[str, str]]]) -> dict[str, Any]:
	payload, errors = result
	if errors or payload is None:
		raise BridgeError(wt.validation_error(errors))
	return payload


def send_interactive(
	account_name: str, to: str, kind: str, spec: dict[str, Any], reply_to: str | None = None,
	trusted: bool = False, http_post: Callable[..., Any] | None = None,
) -> dict[str, Any]:
	"""Send reply buttons / list / CTA URL / flow / location request (``kind``: buttons|list|cta_url|flow|location_request)."""
	_account_or_error(account_name)
	payload = _built(wm.build_interactive_payload(normalize_phone(to), kind, spec or {}, reply_to))
	return _send_payload(account_name, payload, trusted, http_post)


def send_location(
	account_name: str, to: str, latitude: Any, longitude: Any, name: str | None = None, address: str | None = None,
	reply_to: str | None = None, trusted: bool = False, http_post: Callable[..., Any] | None = None,
) -> dict[str, Any]:
	_account_or_error(account_name)
	payload = _built(wm.build_location_payload(normalize_phone(to), latitude, longitude, name, address, reply_to))
	return _send_payload(account_name, payload, trusted, http_post)


def send_contacts(
	account_name: str, to: str, contacts: Any, reply_to: str | None = None, trusted: bool = False,
	http_post: Callable[..., Any] | None = None,
) -> dict[str, Any]:
	_account_or_error(account_name)
	payload = _built(wm.build_contacts_payload(normalize_phone(to), contacts, reply_to))
	return _send_payload(account_name, payload, trusted, http_post)


def send_reaction(
	account_name: str, to: str, message_id: str, emoji: str = "", remove: bool = False, trusted: bool = False,
	http_post: Callable[..., Any] | None = None,
) -> dict[str, Any]:
	"""React to (``emoji``) or un-react (empty emoji / ``remove``) an inbound message (target <= 30 days old)."""
	_account_or_error(account_name)
	payload = _built(wm.build_reaction_payload(normalize_phone(to), message_id, emoji, remove))
	return _send_payload(account_name, payload, trusted, http_post)


def send_sticker(
	account_name: str, to: str, link: str | None = None, media_id: str | None = None, reply_to: str | None = None,
	trusted: bool = False, http_post: Callable[..., Any] | None = None, http_get: Callable[..., Any] | None = None,
) -> dict[str, Any]:
	_account_or_error(account_name)
	payload = _built(wm.build_sticker_payload(normalize_phone(to), link, media_id, reply_to))
	if not media_id:
		_preflight_link("sticker", link, http_get)
	return _send_payload(account_name, payload, trusted, http_post)


def post_media_upload(
	graph_url: str, phone_id: str, token: str, content: bytes, mime_type: str, filename: str = "",
	http_post: Callable[..., Any] | None = None,
) -> str:
	"""``POST {graph_url}/{phone_id}/media`` (multipart: messaging_product, type, file); returns the media id.

	``graph_url`` is the versioned Graph root (``https://graph.facebook.com/v25.0``). Media ids live 30 days.
	"""
	http_post = http_post or _default_post
	name = filename or f"upload{mimetypes.guess_extension(mime_type) or ''}"
	try:
		resp = http_post(
			f"{graph_url}/{phone_id}/media",
			data={"messaging_product": "whatsapp", "type": mime_type},
			files={"file": (name, content, mime_type)},
			headers={"Authorization": f"Bearer {token}"},
			timeout=60,
		)
	except Exception as exc:
		raise BridgeError(_err("upload_failed", message=_redact(exc))) from exc
	status = getattr(resp, "status_code", 200)
	if isinstance(status, int) and status >= 400:
		raise BridgeError(_graph_err("upload_failed", resp))
	try:
		return str(resp.json()["id"])
	except Exception as exc:
		raise BridgeError(_err("upload_failed", message="Unexpected response from WhatsApp.")) from exc


def send_voice_note(
	account_name: str,
	to: str,
	link: str | None = None,
	media_id: str | None = None,
	reply_to: str | None = None,
	trusted: bool = False,
	http_post: Callable[..., Any] | None = None,
) -> dict[str, Any]:
	"""Send audio as a voice note (``audio.voice: true``); rejects anything that is not Ogg/Opus before any call."""
	if link and not media_id:
		errors = wm.validate_voice_link(link)
		if errors:
			raise BridgeError(wt.validation_error(errors))
	return send_media(
		account_name, to, "audio", link=link, media_id=media_id, reply_to=reply_to, trusted=trusted,
		voice=True, http_post=http_post,
	)


def upload_media(
	account_name: str, content: bytes, mime_type: str, filename: str = "", kind: str | None = None,
	voice: bool = False, trusted: bool = False, http_post: Callable[..., Any] | None = None,
) -> dict[str, Any]:
	"""Upload bytes to Meta and return ``{"success": True, "media_id", "kind", "mime_type", "size"}``.

	Mime type and size are checked against the per-kind caps first (image 5 MB jpeg/png, video 16 MB mp4/3gp, audio
	16 MB, document 100 MB, sticker webp 100 KB static / 500 KB animated); a failing file never reaches Meta.
	"""
	acct = _account_or_error(account_name)
	if not _may_bypass(trusted) and not frappe.has_permission("WhatsApp Message", "create"):
		raise frappe.PermissionError("Not permitted to send WhatsApp messages")
	mime = wm.normalize_mime(mime_type)
	kind, errors = wm.validate_upload(mime_type, content, kind, bool(voice))
	if errors:
		raise BridgeError(wt.validation_error(errors))
	media_id = post_media_upload(f"{acct['url']}/{acct['version']}", acct["phone_id"], acct["token"], content, mime, filename, http_post)
	return {"success": True, "media_id": media_id, "kind": kind, "mime_type": mime, "size": len(content)}


def list_templates(account_name: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
	"""List one account's WhatsApp Templates (empty list when the bridge is unavailable).

	An account is required: without one this raises ``gateway_required`` instead of
	returning every account's templates.
	"""
	if not is_available():
		return []
	if not account_name:
		raise BridgeError(_gateway_required())
	filters: dict[str, Any] = {"whatsapp_account": account_name}
	if status:
		filters["status"] = status
	rows = frappe.get_list(
		"WhatsApp Templates",
		filters=filters,
		fields=[
			"name", "template_name", "actual_name", "category", "language_code", "status", "id",
			"whatsapp_account", "template", "header_type", "header", "footer", "sample_values",
		],
		order_by="modified desc",
		limit_page_length=500,
	)
	_attach_state(rows)
	for row in rows:
		extra = _get_extra(row.get("whatsapp_account"), row["name"]) or {}
		row["header_format"] = str(extra.get("header_format") or row.get("header_type") or "").upper()
	return rows


def _attach_state(rows: list[dict[str, Any]]) -> None:
	"""Add review/quality state columns to listed template rows (best effort), matched per account."""
	try:
		states = {
			(r.get("whatsapp_account") or "", r["template"]): r
			for r in frappe.get_all(
				STATE_DOCTYPE,
				filters={"template": ["in", [r["name"] for r in rows] or [""]]},
				fields=["template", "whatsapp_account", "rejected_reason", "quality_score", "correct_category", "last_meta_update"],
			)
		}
	except Exception:
		states = {}
	for row in rows:
		st = states.get((row.get("whatsapp_account") or "", row["name"])) or {}
		row["rejected_reason"] = st.get("rejected_reason") or ""
		row["quality_score"] = st.get("quality_score") or "UNKNOWN"
		row["correct_category"] = st.get("correct_category") or ""
		row["category_change_pending"] = bool(row["correct_category"] and row["correct_category"] != row.get("category"))
		row["last_meta_update"] = str(st["last_meta_update"]) if st.get("last_meta_update") else None


def _check_sample_reference(sample: str) -> dict[str, str] | None:
	"""Media header sample must be fetchable by frappe_whatsapp: public http(s) URL or an existing File."""
	if wt.is_http_url(sample):
		parsed = urlparse(sample)
		if getattr(frappe.flags, "in_test", False):
			return None
		if parsed.scheme != "https" or _is_private_host(parsed.hostname or ""):
			return wt._e("sample", "invalid_sample", "Sample URL must be a public https URL.")
		return None
	if not frappe.db.exists("File", {"file_url": sample}):
		return wt._e("sample", "sample_not_found", "No uploaded file matches this sample path.")
	return None


def _is_private_host(host: str) -> bool:
	import ipaddress
	import socket

	host = host.strip("[]").lower()
	if host in ("localhost", "") or host.endswith(".localhost") or host.endswith(".local"):
		return True
	try:
		addrs = {ai[4][0] for ai in socket.getaddrinfo(host, None)}
	except OSError:
		return False  # unresolved here; the fetch will fail and be reported by frappe_whatsapp
	for addr in addrs:
		ip = ipaddress.ip_address(addr)
		if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
			return True
	return False


def _language_link(language_code: str, given: Any) -> str | None:
	"""``WhatsApp Templates.language`` (Link to Language) for a Meta language code."""
	if given:
		return str(given)
	for candidate in (language_code.replace("_", "-"), language_code, language_code.split("_")[0]):
		if frappe.db.exists("Language", candidate):
			return candidate
	return None


_TEMPLATE_PASSTHROUGH = ("field_names", "for_doctype")


def template_buttons(names: list[str]) -> dict[str, list[dict[str, Any]]]:
	"""Button rows (``WhatsApp Button``) of the given templates, keyed by template name."""
	if not names or not is_available():
		return {}
	rows = frappe.get_all(
		"WhatsApp Button",
		filters={"parent": ["in", list(names)], "parenttype": "WhatsApp Templates"},
		fields=["parent", "button_type", "button_label", "url_type", "website_url", "phone_number"],
		order_by="idx asc",
	)
	out: dict[str, list[dict[str, Any]]] = {}
	for row in rows:
		out.setdefault(row.pop("parent"), []).append(row)
	return out


def validate_create_payload(payload: dict[str, Any]) -> dict[str, Any]:
	"""Validate a template create payload without touching Meta or frappe_whatsapp.

	Returns ``{"error": <error dict>}`` on failure, else
	``{"name", "category", "language_code", "language", "spec"}``.
	"""
	name = str(payload.get("template_name") or payload.get("name") or "")
	category = str(payload.get("category") or "").upper()
	language_code = str(payload.get("language_code") or "")
	if not _TEMPLATE_NAME_RE.match(name):
		return {"error": _err("invalid_name", message="Name must match ^[a-z0-9_]+$")}
	if category not in TEMPLATE_CATEGORIES:
		return {"error": _err("invalid_category", message="Category must be one of " + ", ".join(TEMPLATE_CATEGORIES))}
	if not language_code:
		return {"error": _err("invalid_language", message="language_code is required")}
	if len(name) > 512:
		return {"error": wt.validation_error([wt._e("template_name", "too_long", "Template name is longer than 512 characters.")])}
	spec, errors = wt.validate_template_spec(payload)
	if spec["header_type"] in wt.MEDIA_HEADER_TYPES and spec["header_sample"] and not errors:
		problem = _check_sample_reference(spec["header_sample"])
		if problem:
			errors.append(problem)
	language = _language_link(language_code, payload.get("language"))
	if not language:
		errors.append(wt._e("language_code", "unknown_language", f"Language {language_code} is not installed on this site."))
	if errors:
		return {"error": wt.validation_error(errors)}
	return {"name": name, "category": category, "language_code": language_code, "language": language, "spec": spec}


def _docname_taken_by_other_account(account_name: str, docname: str) -> dict[str, Any] | None:
	"""Error dict when ``docname`` (``<name>-<lang>``, unique site-wide upstream) belongs to another account."""
	if not frappe.db.exists("WhatsApp Templates", docname):
		return None
	owner = frappe.db.get_value("WhatsApp Templates", docname, "whatsapp_account")
	if (owner or "") != (account_name or ""):
		return _err(
			"template_name_taken_by_other_account",
			message=(
				f"The template document {docname} already belongs to another WhatsApp account. "
				"frappe_whatsapp names templates <name>-<language> site-wide, so pick a different template name."
			),
		)
	return None


_MEDIA_MIME_PREFIXES = {"IMAGE": ("image/",), "VIDEO": ("video/",), "DOCUMENT": ("application/", "text/")}
_HEADER_SAMPLE_LIMITS = {"IMAGE": 5 * _MB, "VIDEO": 16 * _MB, "DOCUMENT": 100 * _MB}


def _sample_problem(code: str, message: str) -> BridgeError:
	return BridgeError(wt.validation_error([wt._e("sample", code, message)]))


_SAMPLE_MAX_REDIRECTS = 3
_REDIRECT_STATUSES = (301, 302, 303, 307, 308)


def _check_hop(url: str, fail: Callable[[str, str], Any], label: str) -> None:
	"""SSRF guard for ONE hop of a fetch: https only, no private/loopback/link-local host. ``fail(code, msg)`` raises."""
	parsed = urlparse(url)
	host = parsed.hostname or ""
	if host and parsed.netloc.lower() in _test_hosts():  # tests only (see _test_hosts)
		return
	if parsed.scheme != "https":
		fail(f"{label}_not_https", f"The {label} URL must be https (a redirect to a non-https URL was refused).")
	if not host or _is_private_host(host):
		fail(f"{label}_private_host", f"The {label} URL (or a redirect target) points to a private or local address.")


def _check_sample_hop(url: str) -> None:
	def fail(code: str, message: str) -> None:
		raise _sample_problem(code, message)

	_check_hop(url, fail, "sample")


def _follow_redirects(
	url: str, get: Callable[..., Any], fail: Callable[[str, str], Any], label: str, **get_kwargs: Any
) -> tuple[Any, int]:
	"""GET ``url`` following up to 3 redirects by hand, checking EVERY hop (SSRF). Returns ``(response, hops)``.

	Non-2xx answers, loops and too many redirects go through ``fail(code, message)`` (which raises);
	``"<label>_unreachable"`` is the code used for them. A 3xx without a ``Location`` also fails.
	"""
	unreachable = f"{label}_unreachable"
	seen = []
	code: Any = None
	for hop in range(_SAMPLE_MAX_REDIRECTS + 1):
		_check_hop(url, fail, label)
		seen.append(url)
		try:
			resp = get(url, allow_redirects=False, **get_kwargs)
		except Exception as exc:
			fail(unreachable, f"Could not fetch the {label}: {_redact(exc)}")
		code = getattr(resp, "status_code", 200)
		if isinstance(code, int) and code in _REDIRECT_STATUSES:
			headers = getattr(resp, "headers", None) or {}
			location = str(headers.get("Location") or headers.get("location") or "").strip()
			if not location:
				fail(unreachable, f"The {label} URL answered HTTP {code} without a Location header.")
			url = urljoin(url, location)
			if url in seen:
				fail(unreachable, f"The {label} URL redirects in a loop.")
			continue
		return resp, hop
	fail(unreachable, f"The {label} URL redirected more than {_SAMPLE_MAX_REDIRECTS} times (last status HTTP {code}).")


def _fetch_sample(sample: str, get: Callable[..., Any]) -> Any:
	"""GET a sample URL following up to 3 redirects by hand, checking EVERY hop (SSRF). Returns the 2xx response."""

	def fail(code: str, message: str) -> None:
		raise _sample_problem(code, message)

	resp, hop = _follow_redirects(sample, get, fail, "sample", timeout=30)
	code = getattr(resp, "status_code", 200)
	if not isinstance(code, int) or code >= 300:
		via = f" after {hop} redirect{'s' if hop != 1 else ''}" if hop else ""
		fail("sample_unreachable", f"The sample URL answered HTTP {code}{via}.")
	return resp


_LINK_PEEK_BYTES = 2048
_LINK_BUDGET_SECONDS = 10
_LINK_EXTENSIONS = {
	"image": (".jpg", ".jpeg", ".png"),
	"video": (".mp4", ".3gp", ".3gpp"),
	"audio": (".aac", ".amr", ".mp3", ".m4a", ".mp4", ".ogg", ".oga", ".opus"),
	"document": (".pdf", ".txt", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"),
	"sticker": (".webp",),
}
_LINK_MIME_PREFIX = {"image": "image/", "video": "video/", "audio": "audio/", "sticker": "image/"}
_GENERIC_MIMES = ("application/octet-stream", "binary/octet-stream", "")
_LINK_HINT = "Upload the file instead (file_url): that is the reliable way to send media."


def _link_problem(code: str, message: str) -> BridgeError:
	return BridgeError(_err(code, message=message, hint=_LINK_HINT))


def _link_mime_ok(kind: str, mime: str, path: str) -> bool:
	if mime in ("text/html", "application/xhtml+xml"):
		return False
	if mime in _GENERIC_MIMES:
		return path.lower().endswith(_LINK_EXTENSIONS[kind])
	if kind in _LINK_MIME_PREFIX:
		return mime.startswith(_LINK_MIME_PREFIX[kind]) and (kind != "sticker" or mime == "image/webp")
	return mime in wm.MEDIA_RULES["document"][1] or (mime.startswith("application/") and not mime.endswith(("+xml", "javascript")))


def preflight_media_link(kind: str, link: str, http_get: Callable[..., Any] | None = None) -> None:
	"""Check that Meta will be able to download ``link`` BEFORE any Graph call; raises :class:`BridgeError`.

	Meta fetches a media ``link`` asynchronously after accepting the send, so an unreachable or wrong
	link still returns a message id and is then silently never delivered. This fetches the link the way
	template header samples are fetched (https only, up to 3 redirects, every hop SSRF-checked, short
	timeout) and requires HTTP 200, a content type that matches ``kind`` (never HTML) and the Meta size cap.
	Codes: ``media_link_unreachable``, ``media_link_wrong_type``, ``media_link_too_large``.
	"""
	import time

	kind = str(kind or "").strip().lower()
	if kind not in wm.MEDIA_RULES:
		return

	def fail(code: str, message: str) -> None:
		# SSRF / transport failures from the shared redirect helper all read as "not reachable" to the caller.
		raise _link_problem("media_link_unreachable", "The media link is not publicly reachable; WhatsApp could not download it.")

	resp, _hops = _follow_redirects(link, http_get or _default_get, fail, "media link", timeout=10, stream=True)
	try:
		code = getattr(resp, "status_code", 200)
		if code != 200:
			fail("media_link_unreachable", "")
		headers = getattr(resp, "headers", None) or {}
		mime = wm.normalize_mime(headers.get("Content-Type") or headers.get("content-type"))
		path = urlparse(link).path
		peek = b""
		if hasattr(resp, "iter_content"):
			started = time.monotonic()
			total = 0
			limit = wm.MEDIA_RULES[kind][0]
			try:
				declared = int(headers.get("Content-Length") or headers.get("content-length") or 0)
			except (TypeError, ValueError):
				declared = 0
			for chunk in resp.iter_content(chunk_size=64 * 1024):
				if not peek:
					peek = bytes(chunk[:_LINK_PEEK_BYTES])
				total += len(chunk)
				if declared or total > limit or time.monotonic() - started > _LINK_BUDGET_SECONDS:
					break  # size is known from the header, over the cap, or the time budget is spent
			size = declared or total
		else:
			content = getattr(resp, "content", b"") or b""
			peek, size = bytes(content[:_LINK_PEEK_BYTES]), len(content)
	finally:
		close = getattr(resp, "close", None)
		if callable(close):
			close()
	head = peek.lstrip()[:15].lower()
	if head.startswith((b"<!doctype", b"<html")) or not _link_mime_ok(kind, mime, path):
		raise _link_problem(
			"media_link_wrong_type",
			f"The media link does not point to a {kind} file (it returned a web page or another type of file).",
		)
	limit = wm.MEDIA_RULES[kind][0]
	label = f"{limit // _MB} MB"
	if kind == "sticker":
		limit = wm.STICKER_ANIMATED_MAX if wm.webp_is_animated(peek) else wm.STICKER_STATIC_MAX
		label = f"{limit // 1024} KB"
	if size > limit:
		raise _link_problem("media_link_too_large", f"The {kind} at this link is larger than WhatsApp allows ({label}).")


def _preflight_link(kind: str, link: str | None, http_get: Callable[..., Any] | None) -> None:
	"""Preflight a media link send. Skipped under tests unless a fake ``http_get`` is injected (no real network)."""
	if not link:
		return
	if http_get is None and getattr(frappe.flags, "in_test", False):
		return
	preflight_media_link(kind, link, http_get)


def _read_header_sample(
	sample: str, header_type: str, http_get: Callable[..., Any] | None = None
) -> tuple[bytes, str]:
	"""Bytes and MIME type of a media header sample: a public URL or an uploaded Frappe File."""
	import mimetypes

	if wt.is_http_url(sample):
		resp = _fetch_sample(sample, http_get or _default_get)
		content = resp.content
		mime = str((getattr(resp, "headers", None) or {}).get("Content-Type") or "").split(";")[0].strip().lower()
		mime = mime or (mimetypes.guess_type(urlparse(sample).path)[0] or "")
	else:
		name = frappe.db.get_value("File", {"file_url": sample}, "name")
		if not name:
			raise _sample_problem("sample_not_found", "No uploaded file matches this sample path.")
		content = frappe.get_doc("File", name).get_content()
		if isinstance(content, str):
			content = content.encode()
		mime = mimetypes.guess_type(sample)[0] or ""
	if not mime.startswith(_MEDIA_MIME_PREFIXES[header_type]):
		raise _sample_problem("invalid_sample", f"The sample is {mime or 'of unknown type'}, not an {header_type} file.")
	if not content:
		raise _sample_problem("invalid_sample", "The sample file is empty.")
	if len(content) > _HEADER_SAMPLE_LIMITS[header_type]:
		raise _sample_problem("sample_too_large", f"The {header_type} sample is larger than {_HEADER_SAMPLE_LIMITS[header_type] // _MB} MB.")
	return content, mime


def _upload_file_name(sample: str, mime: str) -> str:
	"""``file_name`` query param of the upload session (documented as required)."""
	base = os.path.basename(urlparse(sample).path) if wt.is_http_url(sample) else os.path.basename(sample)
	base = re.sub(r"[^A-Za-z0-9._-]", "_", base)[:100]
	return base or "sample" + (mimetypes.guess_extension(mime) or "")


def upload_header_handle(
	acct: dict[str, Any],
	header_type: str,
	sample: str,
	http_post: Callable[..., Any] | None = None,
	http_get: Callable[..., Any] | None = None,
) -> str:
	"""Meta resumable upload of a header sample; returns the ``header_handle`` (``h``).

	Two calls, as in Meta's Resumable Upload API: ``POST /{app_id}/uploads`` opens a session
	(file length and type), ``POST /{session id}`` with the raw bytes returns the handle. Raises
	:class:`BridgeError` (validation error for a bad sample, ``upload_failed`` for a Meta refusal).
	"""
	if not acct.get("app_id"):
		raise _sample_problem("app_id_missing", "Set the App ID on the WhatsApp Account to upload header samples.")
	content, mime = _read_header_sample(sample, header_type, http_get)
	http_post = http_post or _default_post
	base = f"{acct['url']}/{acct['version']}"
	try:
		opened = http_post(
			f"{base}/{acct['app_id']}/uploads",
			params={"file_length": len(content), "file_type": mime, "file_name": _upload_file_name(sample, mime)},
			headers={"Authorization": f"Bearer {acct['token']}"},
			timeout=_HTTP_TIMEOUT,
		)
		code = getattr(opened, "status_code", 200)
		if isinstance(code, int) and code >= 400:
			raise BridgeError(_graph_err("upload_failed", opened))
		session = str(opened.json()["id"])
		sent = http_post(
			f"{base}/{session}",
			data=content,
			headers={"Authorization": f"OAuth {acct['token']}", "file_offset": "0"},
			timeout=60,
		)
		code = getattr(sent, "status_code", 200)
		if isinstance(code, int) and code >= 400:
			raise BridgeError(_graph_err("upload_failed", sent))
		return str(sent.json()["h"])
	except BridgeError:
		raise
	except Exception as exc:
		raise BridgeError(_graph_err("upload_failed", exc)) from exc


def _guard():
	from huf.ai.gateway_adapters import whatsapp_template_guard as guard

	return guard


def _meta_extras(components: Any, parameter_format: Any = None, ttl: Any = None) -> dict[str, Any]:
	"""Extras derivable from Meta's ``components``: format, named samples, header format, TTL."""
	named_samples: list[dict[str, str]] = []
	header_format = ""
	inferred = "POSITIONAL"
	for comp in components if isinstance(components, list) else []:
		if not isinstance(comp, dict):
			continue
		ctype = str(comp.get("type") or "").upper()
		if ctype == "HEADER":
			header_format = str(comp.get("format") or "").upper()
		text_vars = wt.variables(str(comp.get("text") or "")) if ctype in ("HEADER", "BODY") else []
		if any(not v.isdigit() for v in text_vars):
			inferred = "NAMED"
		if ctype == "BODY":
			for item in (comp.get("example") or {}).get("body_text_named_params") or []:
				if isinstance(item, dict) and item.get("param_name"):
					named_samples.append({"name": str(item["param_name"]), "example": str(item.get("example") or "")})
	fmt = str(parameter_format or "").upper()
	return {
		"parameter_format": fmt if fmt in wt.PARAMETER_FORMATS else inferred,
		"named_samples": named_samples,
		"header_format": header_format,
		"ttl_seconds": ttl if isinstance(ttl, int) and not isinstance(ttl, bool) and ttl != 0 else None,
	}


_LOCAL_HEADER_TYPES = ("TEXT", "IMAGE", "DOCUMENT")  # the WhatsApp Templates.header_type options


def _local_header_type(fmt: Any) -> str:
	"""header_type for the local row: Meta's format when the doctype can hold it, else '' (VIDEO / LOCATION are
	never mislabelled; the true format lives in the Template Extra's ``header_format``)."""
	fmt = str(fmt or "").upper()
	return fmt if fmt in _LOCAL_HEADER_TYPES else ""


def _button_rows(spec: dict[str, Any]) -> list[dict[str, Any]]:
	"""``wt.button_rows`` with the doctype's ``url_type`` default (Static) filled in."""
	return [{**row, "url_type": row.get("url_type") or "Static"} for row in wt.button_rows(spec)]


def _check_row_lengths(doc: Any) -> None:
	"""Raise ValueError when a Data column value would overflow (checked before any write)."""
	checks = [("WhatsApp Templates", _TEMPLATE_DATA_FIELDS, [doc])]
	checks.append(("WhatsApp Button", _BUTTON_DATA_FIELDS, list(doc.get("buttons") or [])))
	for dt, fieldnames, docs in checks:
		for row_doc in docs:
			for fieldname in fieldnames:
				value = getattr(row_doc, fieldname, None)
				if value is not None and len(str(value)) > _DATA_COLUMN_LEN:
					raise ValueError(f"{dt}.{fieldname} exceeds {_DATA_COLUMN_LEN} characters")


def _insert_mirror_row(doc: Any) -> str:
	"""``db_insert`` a ``WhatsApp Templates`` row and its buttons without controller hooks (so frappe_whatsapp's
	``after_insert`` never POSTs to Meta). Validates column lengths first so nothing is half-written."""
	_check_row_lengths(doc)
	now = frappe.utils.now()
	user = frappe.session.user
	doc.owner = doc.modified_by = user
	doc.creation = doc.modified = now
	doc.docstatus = 0
	doc.db_insert()
	for child in doc.get("buttons"):
		child.parent, child.parenttype, child.parentfield = doc.name, doc.doctype, "buttons"
		child.owner = child.modified_by = user
		child.creation = child.modified = now
		child.db_insert()
	return doc.name


def _extra_values(
	spec: dict[str, Any], tid: Any, components: list[dict[str, Any]], created_via: str | None = None
) -> dict[str, Any]:
	values: dict[str, Any] = {
		"template_id": str(tid or ""),
		"parameter_format": spec.get("parameter_format") or "POSITIONAL",
		"named_samples": list(spec.get("named_samples") or []),
		"header_format": spec.get("header_type") or "",
		"components_json": components,
	}
	if spec.get("ttl_seconds") is not None:
		values["ttl_seconds"] = spec["ttl_seconds"]
	if created_via:
		values["created_via"] = created_via
	return values


def create_template(
	account_name: str,
	payload: dict[str, Any],
	http_post: Callable[..., Any] | None = None,
	http_get: Callable[..., Any] | None = None,
	commit: bool = False,
) -> dict[str, Any]:
	"""Create a template on Meta (``POST /{waba}/message_templates``) and mirror it locally. Permission-checked (A8).

	Huf pushes straight to Graph with ``wt.build_meta_payload`` (``parameter_format``, full
	``components``, ``message_send_ttl_seconds``); frappe_whatsapp's own ``after_insert`` push is never
	used. IMAGE / VIDEO / DOCUMENT header samples (public URL or uploaded File) are uploaded through
	Meta's resumable upload API first to obtain the ``header_handle`` (or pass ``header_handle``).
	Only after Meta accepts is a ``WhatsApp Templates`` row written (``db_insert``, under
	``frappe.flags.huf_template_write``, ``doc.flags.huf_mirror``) together with its Template Extra
	(``created_via`` Huf). A Meta refusal leaves no local row and returns
	``{"error": "create_failed", "message": <redacted Meta message>}``. Validation failures return
	``{"error": "validation_failed", "errors": [...]}``.
	"""
	if not is_available():
		return _err("bridge_unavailable")
	if not frappe.has_permission("WhatsApp Templates", "create"):
		raise frappe.PermissionError("Not permitted to create WhatsApp Templates")
	checked = validate_create_payload(payload)
	if checked.get("error"):
		return checked["error"]
	name, category, language_code = checked["name"], checked["category"], checked["language_code"]
	language, spec = checked["language"], checked["spec"]
	docname = f"{name}-{language_code}"
	taken = _docname_taken_by_other_account(account_name, docname)
	if taken:
		return taken
	if frappe.db.exists("WhatsApp Templates", docname):
		return _err("create_failed", message=f"The template {docname} already exists for this account.")
	acct = resolve_account(account_name)
	if not acct or acct.get("error"):
		return _err("no_account")

	doc = frappe.new_doc("WhatsApp Templates")
	for key in _TEMPLATE_PASSTHROUGH:
		if payload.get(key):
			doc.set(key, payload[key])
	doc.update(
		{
			"name": docname,
			"template_name": name,
			"actual_name": name,
			"category": category,
			"language": language,
			"language_code": language_code,
			"whatsapp_account": account_name,
			"template": spec["body"],
			"sample_values": ",".join(spec["sample_values"]),
			"header_type": _local_header_type(spec["header_type"]),
			"footer": spec["footer"] or "",
		}
	)
	if spec["header_type"] == "TEXT":
		doc.header = spec["header_text"]
	if spec["header_sample"]:
		doc.sample = spec["header_sample"]
	for row in _button_rows(spec):
		doc.append("buttons", row)
	try:
		_check_row_lengths(doc)
	except ValueError as exc:
		return _err("create_failed", message=_redact(exc))

	if spec["header_type"] in wt.MEDIA_HEADER_TYPES and not spec["header_handle"]:
		try:
			spec["header_handle"] = upload_header_handle(acct, spec["header_type"], spec["header_sample"], http_post, http_get)
		except BridgeError as exc:
			return exc.payload

	meta = wt.build_meta_payload(spec)
	body = {"name": name, "language": language_code, "category": category, **meta}
	try:
		resp = (http_post or _default_post)(
			f"{acct['url']}/{acct['version']}/{acct['business_id']}/message_templates",
			json=body,
			headers={"Authorization": f"Bearer {acct['token']}", "Content-Type": "application/json"},
			timeout=_HTTP_TIMEOUT,
		)
	except Exception as exc:
		return _graph_err("create_failed", exc)
	code = getattr(resp, "status_code", 200)
	if isinstance(code, int) and code >= 400:
		return _graph_err("create_failed", resp)
	try:
		data = resp.json() or {}
		tid = str(data["id"])
	except Exception:
		return _err("create_failed", message="Unexpected response from WhatsApp.")
	status = str(data.get("status") or "PENDING").upper()
	meta_category = str(data.get("category") or category).upper()

	doc.id, doc.status, doc.category = tid, status, meta_category
	doc.flags.huf_mirror = True
	result: dict[str, Any] = {"success": True, "name": docname, "status": status, "id": tid}
	if spec.get("notes"):
		result["notes"] = spec["notes"]
	try:
		with _guard().huf_template_write():
			_insert_mirror_row(doc)
			_guard().upsert_extra(
				account_name, docname, **_extra_values(spec, tid, meta["components"], created_via="Huf")
			)
	except Exception as exc:
		# Meta has the template; the next sync imports it. Never report a Meta-accepted template as failed.
		result.update(mirrored=False, mirror_error=_redact(exc))
	record_template_state(
		docname=docname, template_id=tid, account=account_name, status=status, category=meta_category,
		components=meta["components"], source="create",
	)
	if commit:  # Meta accepted it: make the mirror durable before the caller records anything else
		frappe.db.commit()
	return result


def delete_template(name: str) -> dict[str, Any]:
	"""Delete a template (frappe_whatsapp on_trash removes it on Meta). Permission-checked."""
	if not is_available():
		return _err("bridge_unavailable")
	if not frappe.has_permission("WhatsApp Templates", "delete"):
		raise frappe.PermissionError("Not permitted to delete WhatsApp Templates")
	if not frappe.db.exists("WhatsApp Templates", name):
		return _err("not_found")
	# frappe_whatsapp's on_trash deletes the template on Meta *before* Frappe's link check
	# rejects the local delete, which would leave Meta and Huf out of sync. Check first.
	if frappe.db.exists("WhatsApp Message", {"template": name}):
		return _err(
			"template_in_use",
			message="This template has been used in sent messages and cannot be deleted.",
		)
	account = frappe.db.get_value("WhatsApp Templates", name, "whatsapp_account")
	try:
		with _guard().huf_template_write():  # Huf's own delete: the desk guard must let it through
			frappe.delete_doc("WhatsApp Templates", name)
			_guard().delete_extra(account, name)
	except frappe.PermissionError:
		raise
	except Exception as exc:
		return _graph_err("delete_failed", exc)
	return {"success": True, "name": name}


_META_BUTTON_TYPES = {
	"URL": "Visit Website",
	"PHONE_NUMBER": "Call Phone",
	"QUICK_REPLY": "Quick Reply",
	"FLOW": "Flow",
	"MPM": "Multi-Product Message",
	"CATALOG": "Catalog",
	"COPY_CODE": wt.DOCTYPE_BUTTON_TYPE["COPY_CODE"],
}


SYNC_FIELDS = (
	"id,name,status,rejected_reason,quality_score,category,previous_category,correct_category,"
	"language,parameter_format,components,message_send_ttl_seconds"
)


def _local_template(account_name: str, name: str, language: str) -> str | None:
	"""Docname of the local row for a Meta template (name + language), or None."""
	langs = [language, language.replace("-", "_")] if language else [None]
	for field in ("actual_name", "template_name"):
		for lang in langs:
			filters: dict[str, Any] = {"whatsapp_account": account_name, field: name}
			if lang:
				filters["language_code"] = lang
			found = frappe.db.get_value("WhatsApp Templates", filters, "name")
			if found:
				return found
		if language:  # legacy rows without a language code still match by name
			found = frappe.db.get_value(
				"WhatsApp Templates",
				{"whatsapp_account": account_name, field: name, "language_code": ["in", ["", None]]},
				"name",
			)
			if found:
				return found
	return None


def _parse_meta_components(components: Any) -> dict[str, Any]:
	"""Meta ``components`` -> WhatsApp Templates fields (``header_type``, ``header``, ``footer``,
	``template``, ``sample_values``) plus ``buttons`` child-row dicts. Absent parts stay empty."""
	out: dict[str, Any] = {"header_type": "", "header": "", "footer": "", "template": "", "sample_values": "", "buttons": [], "header_format": ""}
	for comp in components if isinstance(components, list) else []:
		if not isinstance(comp, dict):
			continue
		ctype = str(comp.get("type") or "").upper()
		if ctype == "HEADER":
			fmt = str(comp.get("format") or "").upper()
			out["header_type"] = _local_header_type(fmt)
			out["header_format"] = fmt
			if fmt == "TEXT":
				out["header"] = comp.get("text") or ""
		elif ctype == "FOOTER":
			out["footer"] = comp.get("text") or ""
		elif ctype == "BODY":
			out["template"] = comp.get("text") or ""
			body_text = (comp.get("example") or {}).get("body_text")
			if body_text and body_text[0]:
				out["sample_values"] = ",".join(str(v) for v in body_text[0])
		elif ctype == "BUTTONS":
			for i, btn in enumerate(comp.get("buttons") or [], start=1):
				btype = _META_BUTTON_TYPES.get(btn.get("type"))
				if not btype:
					continue
				row: dict[str, Any] = {"button_type": btype, "button_label": btn.get("text"), "sequence": i}
				if btn.get("type") == "URL":
					row["website_url"] = btn.get("url")
					row["url_type"] = "Dynamic" if "{{" in str(btn.get("url") or "") else "Static"
					if btn.get("example"):
						row["example_url"] = ",".join(btn["example"])
						if len(row["example_url"]) > _DATA_COLUMN_LEN:
							# Meta sample link (often a long signed CDN URL): not needed to send, so dropped
							row.pop("example_url")
				elif btn.get("type") == "COPY_CODE":
					row["example_url"] = str(btn.get("example") or "")[:_DATA_COLUMN_LEN]
				elif btn.get("type") == "PHONE_NUMBER":
					row["phone_number"] = btn.get("phone_number")
				out["buttons"].append(row)
	return out


def _write_buttons(parent: str, rows: list[dict[str, Any]]) -> None:
	"""Replace the ``WhatsApp Button`` children of a template with ``rows`` (no controller hooks)."""
	frappe.db.delete("WhatsApp Button", {"parent": parent, "parenttype": "WhatsApp Templates"})
	now, user = frappe.utils.now(), frappe.session.user
	for i, row in enumerate(rows, start=1):
		child = frappe.new_doc("WhatsApp Button")
		child.update(row)
		child.sequence = row.get("sequence") or i
		child.parent, child.parenttype, child.parentfield = parent, "WhatsApp Templates", "buttons"
		child.idx = i
		child.owner = child.modified_by = user
		child.creation = child.modified = now
		child.docstatus = 0
		child.db_insert()


def _button_sig(rows: list[dict[str, Any]]) -> list[tuple]:
	return [
		(r.get("button_type") or "", r.get("button_label") or "", r.get("website_url") or "", r.get("phone_number") or "")
		for r in rows
	]


def _refresh_local_components(name: str, tpl: dict[str, Any]) -> bool:
	"""Bring a local row's header/body/footer/buttons in line with Meta's components; True when changed."""
	comps = tpl.get("components")
	if not isinstance(comps, list) or not comps:
		return False  # no component info from Meta: leave the row alone
	parsed = _parse_meta_components(comps)
	current = frappe.db.get_value(
		"WhatsApp Templates", name, ["template", "header_type", "header", "footer", "sample_values"], as_dict=True
	) or {}
	changes = {}
	for key in ("template", "header_type", "header", "footer"):
		if (current.get(key) or "") != (parsed[key] or ""):
			changes[key] = parsed[key] or ""
	# Meta only returns body examples when it has them; never wipe local samples with nothing
	if parsed["sample_values"] and (current.get("sample_values") or "") != parsed["sample_values"]:
		changes["sample_values"] = parsed["sample_values"]
	local_buttons = frappe.get_all(
		"WhatsApp Button",
		filters={"parent": name, "parenttype": "WhatsApp Templates"},
		fields=["button_type", "button_label", "website_url", "phone_number"],
		order_by="idx asc",
	)
	buttons_changed = _button_sig(local_buttons) != _button_sig(parsed["buttons"])
	if changes:
		frappe.db.set_value("WhatsApp Templates", name, changes)
	if buttons_changed:
		_write_buttons(name, parsed["buttons"])
	return bool(changes or buttons_changed)


def _import_template(account_name: str, tpl: dict[str, Any]) -> str:
	"""Insert a ``WhatsApp Templates`` row for a template that already exists on Meta.

	Mirrors frappe_whatsapp's own ``fetch()``: the row is written with ``db_insert`` so the
	``after_insert`` hook (which would POST the template to Meta) never runs.
	"""
	name, language = str(tpl.get("name")), str(tpl.get("language") or "")
	doc = frappe.new_doc("WhatsApp Templates")
	doc.template_name = name
	doc.actual_name = name
	doc.language_code = language
	doc.language = _language_link(language, None) if language else None
	doc.status = tpl.get("status")
	doc.category = tpl.get("category")
	doc.id = tpl.get("id")
	doc.whatsapp_account = account_name
	doc.name = f"{name}-{language}"
	parsed = _parse_meta_components(tpl.get("components"))
	for key in ("header_type", "header", "footer", "template", "sample_values"):
		if parsed[key]:
			setattr(doc, key, parsed[key])
	for row in parsed["buttons"]:
		doc.append("buttons", row)
	_insert_mirror_row(doc)  # validated before any insert so an overflowing template never leaves a half-written row
	return doc.name


def _sync_extra(account_name: str, docname: str, tpl: dict[str, Any], imported: bool) -> None:
	"""Keep the Template Extra in line with what Meta returned (best effort; never fails a sync)."""
	comps = tpl.get("components")
	if not isinstance(comps, list) or not comps:
		return
	try:
		guard = _guard()
		derived = _meta_extras(comps, tpl.get("parameter_format"), tpl.get("message_send_ttl_seconds"))
		fields: dict[str, Any] = {
			"template_id": str(tpl.get("id") or ""),
			"parameter_format": derived["parameter_format"],
			"named_samples": derived["named_samples"],
			"header_format": derived["header_format"],
			"components_json": comps,
		}
		if derived["ttl_seconds"] is not None:
			fields["ttl_seconds"] = derived["ttl_seconds"]
		existing = guard.get_extra(account_name, docname)
		if imported or not existing:
			fields["created_via"] = "Meta sync"
		guard.upsert_extra(account_name, docname, **fields)
	except Exception:
		frappe.logger("huf").warning("WhatsApp template extra sync failed", exc_info=True)


def sync_templates(account_name: str, http_get: Callable[..., Any] | None = None) -> dict[str, Any]:
	"""Account-scoped template sync (A15); does not call frappe_whatsapp ``fetch()``.

	Templates that exist on Meta but not locally are IMPORTED (inserted without the
	frappe_whatsapp ``after_insert`` push, so nothing is POSTed to Meta); existing rows only
	get status/category/id refreshed. Returns ``imported``/``updated``/``unchanged`` counts; ``skipped`` counts templates that could not be imported (no language, docname collision, or a per-template failure) with redacted ``skipped_reasons``. Meta sample URLs longer than the column are dropped, not failed.
	"""
	if not is_available():
		return _err("bridge_unavailable")
	if not frappe.has_permission("WhatsApp Templates", "write"):
		raise frappe.PermissionError("Not permitted to sync WhatsApp Templates")
	acct = resolve_account(account_name)
	if not acct or acct.get("error"):
		return _err("no_account")
	http_get = http_get or _default_get
	url = f"{acct['url']}/{acct['version']}/{acct['business_id']}/message_templates"
	headers = {"Authorization": f"Bearer {acct['token']}"}
	imported = updated = unchanged = skipped = seen = 0
	skipped_reasons: list[str] = []
	params: dict[str, Any] | None = {"limit": 100, "fields": SYNC_FIELDS}
	try:
		while url:
			resp = http_get(url, headers=headers, params=params, timeout=_HTTP_TIMEOUT)
			resp.raise_for_status()
			data = resp.json()
			for tpl in data.get("data", []):
				seen += 1
				if not tpl.get("name"):
					continue
				# one template's failure must not fail the whole sync: count it and continue
				try:
					name = _local_template(account_name, tpl["name"], str(tpl.get("language") or ""))
					if not name:
						language = str(tpl.get("language") or "")
						# docname is <name>-<language> and unique site-wide: skip what cannot be named or collides
						if not language:
							skipped += 1
							skipped_reasons.append(_redact(f"{tpl['name']}: no language"))
							continue
						if frappe.db.exists("WhatsApp Templates", f"{tpl['name']}-{language}"):
							skipped += 1
							taken = _docname_taken_by_other_account(account_name, f"{tpl['name']}-{language}")
							code = "template_name_taken_by_other_account" if taken else "name collision"
							skipped_reasons.append(_redact(f"{tpl['name']}: {code} ({tpl['name']}-{language})"))
							continue
						sp = f"wa_import_{seen}"
						frappe.db.savepoint(sp)
						try:
							_import_template(account_name, tpl)
						except Exception as exc:
							frappe.db.rollback(save_point=sp)
							skipped += 1
							skipped_reasons.append(_redact(f"{tpl['name']}: import failed ({type(exc).__name__}: {exc})"))
							continue
						imported += 1
						_record_state_from_meta(account_name, tpl, f"{tpl['name']}-{language}")
						_sync_extra(account_name, f"{tpl['name']}-{language}", tpl, True)
						continue
					current = frappe.db.get_value("WhatsApp Templates", name, ["status", "category", "id"], as_dict=True) or {}
					changes = {
						k: tpl.get(k)
						for k in ("status", "category", "id")
						if tpl.get(k) is not None and tpl.get(k) != current.get(k)
					}
					if changes:
						frappe.db.set_value("WhatsApp Templates", name, changes)
					refreshed = _refresh_local_components(name, tpl)
					_record_state_from_meta(account_name, tpl, name)
					_sync_extra(account_name, name, tpl, False)
					if changes or refreshed:
						updated += 1
					else:
						unchanged += 1
				except Exception as exc:
					skipped += 1
					skipped_reasons.append(_redact(f"{tpl.get('name')}: {type(exc).__name__}: {exc}"))
			next_url = (data.get("paging") or {}).get("next")
			if next_url:
				nxt, base = urlparse(str(next_url)), urlparse(acct["url"])
				if nxt.scheme != "https" or (nxt.hostname or "").lower() != (base.hostname or "").lower():
					return _err("sync_failed", message="Unexpected paging URL host")
			url = next_url
			params = None
	except Exception as exc:
		return _graph_err("sync_failed", exc)
	return {
		"success": True,
		"seen": seen,
		"imported": imported,
		"updated": updated,
		"unchanged": unchanged,
		"skipped": skipped,
		"skipped_reasons": skipped_reasons,
	}


# ------------------------------------------------------------ template state
# Huf-owned review/quality state. Independent of frappe_whatsapp (works on sites without it):
# frappe_whatsapp stores no rejection reason or quality, and drops the webhook ``reason``.

STATE_DOCTYPE = "WhatsApp Template State"
DRAFT_DOCTYPE = "WhatsApp Template Draft"
MANAGER_URL = "https://business.facebook.com/latest/whatsapp_manager/message_templates"
EDIT_LIMIT_30D = 10
ADMIN_ROLES = ("System Manager", "Huf Admin")
TEMPLATE_STATUSES = (
	"APPROVED", "PENDING", "REJECTED", "PAUSED", "DISABLED", "IN_APPEAL", "LIMIT_EXCEEDED",
	"PENDING_DELETION", "DELETED",
)
# Webhook events that are not statuses (FLAGGED, REINSTATED, LOCKED, ARCHIVED, UNARCHIVED) only set ``last_event``.
_QUALITY_WORDS = {"GREEN": "GREEN", "HIGH": "GREEN", "YELLOW": "YELLOW", "MEDIUM": "YELLOW", "RED": "RED", "LOW": "RED"}
_DRAFT_OPEN = ("Draft", "Pending Review", "Failed")
_SUBMITTING = "Submitting"  # committed before the Graph POST; not a desk Select option (set with db.set_value)
_SUBMITTING_STALE_SECONDS = 120  # a draft stuck in Submitting longer than this lost its worker: approve may retry


def manager_url(business_id: str | None = None) -> str:
	"""WhatsApp Manager template list. Meta documents no query parameters, so none are added."""
	return MANAGER_URL


def derive_quality(raw: Any) -> str:
	"""GREEN/YELLOW/RED/UNKNOWN from Meta's quality value (string or object of unverified shape)."""

	def walk(value: Any, depth: int = 0) -> str | None:
		if isinstance(value, str):
			return _QUALITY_WORDS.get(value.strip().upper())
		if isinstance(value, dict) and depth < 3:
			for key in ("score", "quality_score", "new_quality_score", "quality", "value", "rating"):
				if key in value:
					found = walk(value[key], depth + 1)
					if found:
						return found
		return None

	return walk(raw) or "UNKNOWN"


def _utcnow() -> datetime:
	return datetime.now(timezone.utc)


def _parse_ts(value: Any) -> datetime | None:
	try:
		dt = datetime.fromisoformat(str(value))
	except (TypeError, ValueError):
		return None
	return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _loads(value: Any, default: Any = None) -> Any:
	if isinstance(value, (dict, list)):
		return value
	try:
		return json.loads(value) if value else default
	except (TypeError, ValueError):
		return default


STATE_KEY_SEP = "::"
_NAME_MAX = 140


def state_key(account: str | None, docname: str) -> str:
	"""Name of a ``WhatsApp Template State``: ``<account>::<template docname>`` (account-scoped).

	Over-long keys keep the account prefix and replace the template part with a hash, so two
	accounts never share a state row even when they hold a template of the same name.
	"""
	account = str(account or "")
	key = f"{account}{STATE_KEY_SEP}{docname}"
	if len(key) > _NAME_MAX:
		digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
		key = f"{account[:60]}{STATE_KEY_SEP}{digest}"
	return key


def _state_row(docname: str, account: str | None = None) -> dict[str, Any] | None:
	try:
		key = state_key(account, docname)
		if not frappe.db.exists(STATE_DOCTYPE, key):
			return None
		return frappe.db.get_value(STATE_DOCTYPE, key, "*", as_dict=True)
	except Exception:
		return None


def _publish_status(template: str, status: str, reason: str = "") -> None:
	try:
		frappe.publish_realtime("whatsapp_template_status", {"template": template, "status": status, "reason": reason})
	except Exception:
		pass


def _clean_reason(reason: Any) -> str:
	text = str(reason or "").strip()
	return "" if text.upper() == "NONE" else text


def _resolve_state_name(template_id: Any, name: Any, language: Any, account: str | None = None) -> str | None:
	"""Template docname for a webhook/sync reference, looked up inside ``account`` when given."""
	tid = str(template_id or "").strip()
	scope = {"whatsapp_account": account} if account else {}
	if tid:
		found = frappe.db.get_value(STATE_DOCTYPE, {"template_id": tid, **scope}, "template")
		if found:
			return found
		if frappe.db.exists("DocType", "WhatsApp Templates"):
			found = frappe.db.get_value("WhatsApp Templates", {"id": tid, **scope}, "name")
			if found:
				return found
	name, language = str(name or "").strip(), str(language or "").strip()
	if name and language and account and frappe.db.exists("DocType", "WhatsApp Templates"):
		# the account's own row for that Meta name + language (its docname may not be <name>-<language>)
		found = _local_template(account, name, language)
		if found:
			return found
	if name and language:
		docname = f"{name}-{language}"
		if account and frappe.db.exists("DocType", "WhatsApp Templates"):
			owner = frappe.db.get_value("WhatsApp Templates", docname, "whatsapp_account")
			if frappe.db.exists("WhatsApp Templates", docname) and (owner or "") != account:
				return None  # that document belongs to another account: never touch its state
		return docname
	if name and frappe.db.exists("DocType", "WhatsApp Templates"):
		found = frappe.db.get_value("WhatsApp Templates", {"actual_name": name, **scope}, "name")
		if found:
			return found
	return None


def record_template_state(
	*,
	template_id: Any = None,
	name: Any = None,
	language: Any = None,
	docname: str | None = None,
	account: str | None = None,
	status: str | None = None,
	event: str | None = None,
	category: str | None = None,
	previous_category: str | None = None,
	correct_category: str | None = None,
	reason: Any = None,
	recommendation: str | None = None,
	other_info: Any = None,
	quality: Any = None,
	components: Any = None,
	source: str = "webhook",
) -> str | None:
	"""Upsert the ``WhatsApp Template State`` of a template; best effort, never raises.

	``None`` leaves a field untouched, ``""`` clears it. ``event`` is a webhook event: it sets
	``last_event`` and, when it is a template status, ``status``. Publishes the
	``whatsapp_template_status`` realtime event when the status changed. Returns the docname.
	"""
	try:
		if not frappe.db.exists("DocType", STATE_DOCTYPE):
			return None
		account = str(account or "").strip()
		docname = docname or _resolve_state_name(template_id, name, language, account)
		if not docname:
			return None
		key = state_key(account, docname)
		event_u = str(event or "").strip().upper()
		new_status = str(status or "").strip().upper() or (event_u if event_u in TEMPLATE_STATUSES else "")
		now = frappe.utils.now_datetime()
		existing = frappe.db.exists(STATE_DOCTYPE, key)
		doc = frappe.get_doc(STATE_DOCTYPE, key) if existing else frappe.new_doc(STATE_DOCTYPE)
		if not existing:
			doc.state_key = key
			doc.template = docname
		old_status = (doc.get("status") or "") if existing else ""
		if template_id not in (None, ""):
			doc.template_id = str(template_id)
		if account:
			doc.whatsapp_account = account
		if new_status:
			doc.status = new_status
		if category not in (None, "") and category != doc.get("category"):
			if previous_category in (None, "") and doc.get("category"):
				previous_category = doc.get("category")
			doc.category = category
		if previous_category is not None:
			doc.previous_category = previous_category
		if correct_category is not None:
			doc.correct_category = correct_category
		cleaned = _clean_reason(reason)
		if cleaned:
			doc.rejected_reason = cleaned[:255]
		elif new_status in ("APPROVED", "PENDING") and (reason is not None or event_u):
			doc.rejected_reason = ""
			doc.rejection_recommendation = ""
		if recommendation:
			doc.rejection_recommendation = str(recommendation)
		if other_info:
			if isinstance(other_info, dict):
				bits = [str(other_info.get(k)) for k in ("title", "description") if other_info.get(k)]
				other_info = ": ".join(bits)
			doc.other_info = str(other_info)
		elif new_status == "APPROVED":
			doc.other_info = ""
		if quality is not None:
			doc.quality_raw = json.dumps(quality, default=str)
			doc.quality_score = derive_quality(quality)
		elif not doc.get("quality_score"):
			doc.quality_score = "UNKNOWN"
		if isinstance(components, list):
			doc.components = json.dumps(components)
		if event_u:
			doc.last_event = event_u
			doc.last_event_at = now
		doc.last_meta_update = now
		doc.flags.ignore_permissions = True
		if existing:
			doc.save()
		else:
			doc.insert()
		if new_status and (new_status != old_status):
			_publish_status(docname, new_status, doc.get("rejected_reason") or "")
		return docname
	except Exception:
		try:
			frappe.logger("huf").warning("WhatsApp template state update failed", exc_info=True)
		except Exception:
			pass
		return None


def record_template_webhook(update: dict[str, Any], account: str | None = None) -> str | None:
	"""State update from a parsed ``message_template_*`` webhook change (see gateway_webhook); also pauses
	Running broadcasts that use a template that was paused, disabled, rejected or flagged."""
	from huf.ai.whatsapp.broadcast.status import pause_on_template_update

	result = _record_template_webhook(update, account)
	pause_on_template_update(update, account)
	return result


def _record_template_webhook(update: dict[str, Any], account: str | None = None) -> str | None:
	try:
		kind = update.get("kind") or (
			"quality" if "new_quality_score" in update else "category" if "new_category" in update else "status"
		)
		common = {
			"template_id": update.get("message_template_id"),
			"name": update.get("message_template_name") or update.get("name"),
			"language": update.get("message_template_language") or update.get("language"),
			"account": account,
		}
		if kind == "quality":
			return record_template_state(**common, quality=update.get("new_quality_score"), event="QUALITY_UPDATE")
		if kind == "category":
			return record_template_state(
				**common,
				category=str(update.get("new_category") or "").upper() or None,
				previous_category=str(update.get("previous_category") or "").upper() or None,
				correct_category="",
				event="CATEGORY_UPDATE",
			)
		info = update.get("rejection_info") if isinstance(update.get("rejection_info"), dict) else {}
		return record_template_state(
			**common,
			event=str(update.get("event") or update.get("status") or "") or None,
			reason=update.get("reason") or info.get("reason"),
			recommendation=info.get("recommendation"),
			other_info=update.get("other_info") if isinstance(update.get("other_info"), dict) else None,
		)
	except Exception:
		return None


def _record_state_from_meta(account_name: str, tpl: dict[str, Any], docname: str) -> None:
	"""State update from one template of Meta's ``/message_templates`` listing (sync)."""
	record_template_state(
		docname=docname,
		template_id=tpl.get("id"),
		account=account_name,
		status=tpl.get("status"),
		category=tpl.get("category"),
		previous_category=tpl.get("previous_category") or None,
		correct_category=tpl.get("correct_category") or "",
		reason=tpl.get("rejected_reason"),
		quality=tpl.get("quality_score"),
		components=tpl.get("components"),
		source="sync",
	)


def edit_quota(status: str, edit_log: Any, now: datetime | None = None, blocked_until: str | None = None) -> dict[str, Any]:
	"""Meta edit rules for a template in ``status`` given its ``edit_log`` (ISO timestamps).

	APPROVED: at most 1 edit per 24h and 10 per 30 days; REJECTED/PAUSED: unlimited;
	anything else is not editable. ``edits_left`` is the remaining 30-day allowance for an
	APPROVED template (None = unlimited, 0 = none), ``next_edit_at`` the earliest time a
	blocked APPROVED template may be edited again.
	"""
	now = now or _utcnow()
	status = str(status or "").upper()
	times = sorted(t for t in (_parse_ts(x) for x in (_loads(edit_log, []) or [])) if t)
	last_30d = [t for t in times if now - t < timedelta(days=30)]
	out: dict[str, Any] = {
		"editable": False, "editable_reason": "", "editable_message": "", "edits_left": 0,
		"edits_30d": len(last_30d), "next_edit_at": None, "edit_blocked_until": None,
	}
	if status in ("REJECTED", "PAUSED"):
		out.update(editable=True, edits_left=None)
	elif status == "APPROVED":
		out["edits_left"] = max(0, EDIT_LIMIT_30D - len(last_30d))
		if len(last_30d) >= EDIT_LIMIT_30D:
			nxt = last_30d[0] + timedelta(days=30)
			out.update(editable_reason="edit_limit_30d", next_edit_at=nxt.isoformat(),
				editable_message=f"Approved templates can be edited {EDIT_LIMIT_30D} times in 30 days; the limit is used up.")
		elif last_30d and now - last_30d[-1] < timedelta(hours=24):
			nxt = last_30d[-1] + timedelta(hours=24)
			out.update(editable_reason="edit_limit_24h", next_edit_at=nxt.isoformat(),
				editable_message="Approved templates can be edited once every 24 hours.")
		else:
			out["editable"] = True
	else:
		out.update(editable_reason="status_not_editable",
			editable_message=template_plain.not_editable_text(status))
	until = _parse_ts(blocked_until) if blocked_until else None
	if out["editable"] and until and until > now:
		out.update(editable=False, editable_reason="edit_blocked", edit_blocked_until=until.isoformat(),
			editable_message=EDIT_BLOCKED_TEXT)
	return out


def _edit_blocked_key(account: Any, name: str) -> str:
	return f"huf_wa_edit_blocked:{account or ''}:{name}"


def _edit_blocked_until(account: Any, name: str) -> str | None:
	try:
		return frappe.cache().get_value(_edit_blocked_key(account, name), expires=True) or None  # expires=True: no local-cache memo of a miss
	except Exception:
		return None


def _mark_edit_blocked(account: Any, name: str) -> str | None:
	"""Remember for an hour that Meta refused an edit (2388039) so the UI does not invite retry loops."""
	until = (_utcnow() + timedelta(seconds=EDIT_BLOCKED_SECONDS)).isoformat()
	try:
		frappe.cache().set_value(_edit_blocked_key(account, name), until, expires_in_sec=EDIT_BLOCKED_SECONDS)
	except Exception:
		return None
	return until


def _button_dicts(docname: str) -> list[dict[str, Any]]:
	rows = frappe.get_all(
		"WhatsApp Button",
		filters={"parent": docname, "parenttype": "WhatsApp Templates"},
		fields=["button_type", "button_label", "url_type", "website_url", "phone_number", "example_url"],
		order_by="idx asc",
	)
	reverse = {v: k for k, v in wt.DOCTYPE_BUTTON_TYPE.items()}
	out = []
	for r in rows:
		btype = reverse.get(r.get("button_type"))
		if not btype:
			continue
		b: dict[str, Any] = {"type": btype, "text": r.get("button_label") or ""}
		if btype == "URL":
			b["url"] = r.get("website_url") or ""
			if r.get("example_url"):
				b["example"] = r["example_url"]
		elif btype == "PHONE_NUMBER":
			b["phone_number"] = r.get("phone_number") or ""
		out.append(b)
	return out


_ROW_FIELDS = [
	"name", "id", "actual_name", "template_name", "language_code", "category", "status", "whatsapp_account",
	"template", "header_type", "header", "sample", "footer", "sample_values",
]


def _extra_ttl(extra: dict[str, Any]) -> int | None:
	"""Stored TTL; the Int column's 0 means 'not set'."""
	ttl = extra.get("ttl_seconds")
	return ttl if isinstance(ttl, int) and not isinstance(ttl, bool) and ttl != 0 else None


def _row_parameter_format(row: dict[str, Any], extra: dict[str, Any]) -> str:
	fmt = str(extra.get("parameter_format") or "").upper()
	if fmt in wt.PARAMETER_FORMATS:
		return fmt
	named = any(not v.isdigit() for v in wt.variables(row.get("template") or "") + wt.variables(row.get("header") or ""))
	return "NAMED" if named else "POSITIONAL"


def _current_payload(row: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
	"""Local row (plus its Template Extra) as a create-style payload (the base an edit is merged onto)."""
	extra = extra or {}
	htype = str(extra.get("header_format") or row.get("header_type") or "").upper()
	payload: dict[str, Any] = {
		"template_name": row.get("actual_name") or row.get("template_name"),
		"category": row.get("category"),
		"language_code": row.get("language_code"),
		"body": row.get("template") or "",
		"sample_values": row.get("sample_values") or "",
		"footer": row.get("footer") or "",
		"buttons": _button_dicts(row["name"]),
		"parameter_format": _row_parameter_format(row, extra),
	}
	if payload["parameter_format"] == "NAMED" and extra.get("named_samples"):
		payload["named_samples"] = extra["named_samples"]
	if _extra_ttl(extra) is not None:
		payload["ttl_seconds"] = _extra_ttl(extra)
	if htype:
		payload["header_type"] = htype
		if htype == "TEXT":
			payload["header"] = row.get("header") or ""
		if row.get("sample") and htype != "LOCATION":
			payload["sample"] = row["sample"]
	return payload


def _stored_header_value(extra: dict[str, Any], state: dict[str, Any]) -> str:
	comps = extra.get("components_json") or _loads(state.get("components"), []) or []
	for comp in comps if isinstance(comps, list) else []:
		if isinstance(comp, dict) and str(comp.get("type")).upper() == "HEADER":
			handles = (comp.get("example") or {}).get("header_handle")
			if handles:
				return str(handles[0])
	return ""


def _existing_header_handle(extra: dict[str, Any], state: dict[str, Any]) -> str:
	"""The Meta upload handle of the template's current media header; '' when unknown or when the stored value
	is a URL (an imported template carries Meta's sample CDN URL, which is never a valid ``header_handle``)."""
	value = _stored_header_value(extra, state)
	return "" if wt.is_http_url(value) else value


def _existing_header_sample_url(extra: dict[str, Any], state: dict[str, Any]) -> str:
	"""The sample URL stored where a handle is expected (imported media headers), '' otherwise."""
	value = _stored_header_value(extra, state)
	return value if wt.is_http_url(value) else ""


_ROUNDTRIP_SECTIONS = ("HEADER", "BODY", "FOOTER", "BUTTONS")
_SECTION_RANK = {"HEADER": 0, "BODY": 1, "FOOTER": 3, "BUTTONS": 4}
_SECTION_KEYS = {
	"HEADER": ("header", "header_type", "sample", "header_handle"),
	"BODY": ("body", "template", "sample_values", "named_samples"),
	"FOOTER": ("footer",),
	"BUTTONS": ("buttons",),
}


def _unroundtrippable_buttons(components: Any) -> list[str]:
	"""Button types in Meta ``components`` that Huf cannot rebuild exactly (FLOW, MPM, CATALOG, ..., a COPY_CODE
	without its example, a dynamic URL button without its example)."""
	bad: list[str] = []
	for comp in components if isinstance(components, list) else []:
		if not isinstance(comp, dict) or str(comp.get("type")).upper() != "BUTTONS":
			continue
		for btn in comp.get("buttons") or []:
			btype = str((btn or {}).get("type") or "").upper()
			if btype not in wt.DOCTYPE_BUTTON_TYPE:
				bad.append(btype or "UNKNOWN")
			elif btype == "COPY_CODE" and not btn.get("example"):
				bad.append(btype)
			elif btype == "URL" and "{{" in str(btn.get("url") or "") and not btn.get("example"):
				bad.append("URL")
	return bad


def _unroundtrippable_local_buttons(docname: str) -> list[str]:
	"""Same check against the local button rows (fallback when no Template Extra holds Meta's components)."""
	reverse = {v: k for k, v in wt.DOCTYPE_BUTTON_TYPE.items()}
	rows = frappe.get_all(
		"WhatsApp Button", filters={"parent": docname, "parenttype": "WhatsApp Templates"},
		fields=["button_type", "url_type", "website_url", "example_url"], order_by="idx asc",
	)
	bad: list[str] = []
	for r in rows:
		btype = reverse.get(r.get("button_type"))
		if not btype:
			bad.append(str(r.get("button_type") or "UNKNOWN"))
		elif btype == "COPY_CODE" and not r.get("example_url"):
			bad.append(btype)
		elif btype == "URL" and ("{{" in str(r.get("website_url") or "") or r.get("url_type") == "Dynamic") and not r.get("example_url"):
			bad.append("URL")
	return bad


def _merge_components(base: list[dict[str, Any]], built: list[dict[str, Any]], changed: set[str]) -> list[dict[str, Any]]:
	"""Meta's own ``base`` components with only the ``changed`` sections replaced by the ``built`` ones."""
	built_by = {str(c.get("type")).upper(): c for c in built if isinstance(c, dict)}
	out: list[dict[str, Any]] = []
	seen: set[str] = set()
	for comp in base:
		ctype = str(comp.get("type")).upper() if isinstance(comp, dict) else ""
		if ctype in changed and ctype in _ROUNDTRIP_SECTIONS:
			if ctype in built_by:
				out.append(built_by[ctype])
				seen.add(ctype)
			continue
		out.append(copy.deepcopy(comp))
		seen.add(ctype)
	for ctype in _ROUNDTRIP_SECTIONS:
		if ctype in changed and ctype in built_by and ctype not in seen:
			out.append(built_by[ctype])
	out.sort(key=lambda c: _SECTION_RANK.get(str(c.get("type")).upper() if isinstance(c, dict) else "", 2))
	return out


def _components_sig(components: Any, ignore_media_example: bool) -> str:
	comps = copy.deepcopy(components if isinstance(components, list) else [])
	for comp in comps:
		if ignore_media_example and isinstance(comp, dict) and str(comp.get("type")).upper() == "HEADER":
			if str(comp.get("format") or "").upper() in wt.MEDIA_HEADER_TYPES:
				comp.pop("example", None)
	return json.dumps(comps, sort_keys=True, default=str)


def get_template(name: str) -> dict[str, Any]:
	"""Full detail of one template: components, review/quality state, edit allowance, manager link.

	Also ``parameter_format``, ``ttl_seconds``, ``header_format`` and ``named_samples`` (from the Template
	Extra when present, else derived from the stored Meta components) so an editor can prefill.
	"""
	if not is_available():
		return _err("bridge_unavailable")
	if not frappe.has_permission("WhatsApp Templates", "read"):
		raise frappe.PermissionError("Not permitted to read WhatsApp Templates")
	if not name or not frappe.db.exists("WhatsApp Templates", name):
		return _err("not_found")
	row = frappe.db.get_value("WhatsApp Templates", name, _ROW_FIELDS, as_dict=True)
	state = _state_row(name, row.get("whatsapp_account")) or {}
	status = (state.get("status") or row.get("status") or "").upper()
	quota = edit_quota(status, state.get("edit_log"), blocked_until=_edit_blocked_until(row.get("whatsapp_account"), name))
	extra = _get_extra(row.get("whatsapp_account"), name) or {}
	meta_components = extra.get("components_json") or _loads(state.get("components"), []) or []
	derived = _meta_extras(meta_components, extra.get("parameter_format"), _extra_ttl(extra))
	header_format = str(extra.get("header_format") or derived["header_format"] or row.get("header_type") or "").upper()
	named_samples = extra.get("named_samples") or derived["named_samples"] or []
	parameter_format = _row_parameter_format(row, {"parameter_format": extra.get("parameter_format") or derived["parameter_format"]})
	view = {
		"header": (
			{"type": header_format, "text": row.get("header") or "", "sample": row.get("sample") or ""}
			if header_format else None
		),
		"body": {
			"text": row.get("template") or "",
			"sample_values": [s for s in (row.get("sample_values") or "").split(",") if s],
			**({"named_samples": named_samples} if named_samples else {}),
		},
		"footer": {"text": row["footer"]} if row.get("footer") else None,
		"buttons": _button_dicts(name),
	}
	business_id = ""
	if row.get("whatsapp_account"):
		business_id = frappe.db.get_value("WhatsApp Account", row["whatsapp_account"], "business_id") or ""
	category = str(state.get("category") or row.get("category") or "").upper() or row.get("category")  # Meta's current one
	correct = state.get("correct_category") or ""
	previous = str(state.get("previous_category") or "").upper()
	return {
		"success": True,
		"name": name,
		"template_id": row.get("id") or state.get("template_id") or "",
		"template_name": row.get("actual_name") or row.get("template_name"),
		"language_code": row.get("language_code"),
		"category": category,
		"previous_category": previous,
		"category_changed_by_meta": bool(previous and previous != category),
		"correct_category": correct,
		"category_change_pending": bool(correct and correct != category),
		"status": status,
		"whatsapp_account": row.get("whatsapp_account"),
		"parameter_format": parameter_format,
		"ttl_seconds": _extra_ttl(extra) if _extra_ttl(extra) is not None else derived["ttl_seconds"],
		"header_format": header_format,
		"named_samples": named_samples,
		"components": view,
		"meta_components": _loads(state.get("components"), []),
		"state": {
			"rejected_reason": state.get("rejected_reason") or "",
			"rejection_recommendation": state.get("rejection_recommendation") or "",
			"other_info": state.get("other_info") or "",
			"quality_score": state.get("quality_score") or "UNKNOWN",
			"quality_raw": _loads(state.get("quality_raw")),
			"last_event": state.get("last_event") or "",
			"last_event_at": str(state["last_event_at"]) if state.get("last_event_at") else None,
			"last_meta_update": str(state["last_meta_update"]) if state.get("last_meta_update") else None,
		},
		**quota,
		"manager_url": manager_url(business_id),
		"business_id": business_id,
	}


def edit_template(
	name: str,
	payload: dict[str, Any],
	http_post: Callable[..., Any] | None = None,
	http_get: Callable[..., Any] | None = None,
) -> dict[str, Any]:
	"""Edit a template on Meta (``POST /{template-id}`` with the FULL components) and locally.

	Meta rules enforced here before any call: status must be APPROVED/REJECTED/PAUSED, an
	APPROVED template allows 1 edit/24h and 10/30 days, name, language and ``parameter_format`` are
	immutable. ``payload`` keys (body, sample_values, named_samples, header*, sample, header_handle,
	footer, buttons, category, ttl_seconds / message_send_ttl_seconds) are merged onto the current
	definition (local row + Template Extra) and sent through ``wt.build_meta_payload``. An unchanged
	media header re-sends its stored upload handle; a NEW media header needs a ``sample`` (uploaded
	again) or ``header_handle``, otherwise ``media_header_edit_unsupported``. After the edit the
	template is PENDING re-review and its row and Template Extra are updated. Permission-checked.
	"""
	if not is_available():
		return _err("bridge_unavailable")
	if not frappe.has_permission("WhatsApp Templates", "write"):
		raise frappe.PermissionError("Not permitted to edit WhatsApp Templates")
	if not isinstance(payload, dict):
		return _err("invalid_payload", message="payload must be an object")
	if not name or not frappe.db.exists("WhatsApp Templates", name):
		return _err("not_found")
	row = frappe.db.get_value("WhatsApp Templates", name, _ROW_FIELDS, as_dict=True)
	meta_name = row.get("actual_name") or row.get("template_name")
	for key, current in (("template_name", meta_name), ("name", meta_name), ("language_code", row.get("language_code"))):
		if payload.get(key) not in (None, "") and str(payload[key]) != str(current):
			return _err("immutable_field", field=key, message="Template name and language cannot be changed after creation.")
	if not row.get("id"):
		return _err("no_template_id", message="This template has no Meta ID yet; sync templates first.")
	state = _state_row(name, row.get("whatsapp_account")) or {}
	status = (state.get("status") or row.get("status") or "").upper()
	blocked_until = _edit_blocked_until(row.get("whatsapp_account"), name)
	quota = edit_quota(status, state.get("edit_log"), blocked_until=blocked_until)
	if not quota["editable"]:
		return _err(quota["editable_reason"], message=quota["editable_message"], status=status,
			next_edit_at=quota["next_edit_at"], edits_left=quota["edits_left"],
			edit_blocked_until=quota["edit_blocked_until"])
	acct = resolve_account(row.get("whatsapp_account"))
	if not acct or acct.get("error"):
		return _err("no_account")

	extra = _get_extra(row.get("whatsapp_account"), name) or {}
	base_components = extra.get("components_json")
	base_components = base_components if isinstance(base_components, list) and base_components else None
	buttons_edited = "buttons" in payload
	if base_components is None:
		unsafe = _unroundtrippable_local_buttons(name)
	else:
		unsafe = _unroundtrippable_buttons(base_components) if buttons_edited else []
	if unsafe:
		return _err(
			"edit_would_drop_buttons",
			message="This template has buttons Huf cannot re-send exactly (" + ", ".join(sorted(set(unsafe)))
			+ "); editing it here would remove them. Edit it in WhatsApp Manager.",
			button_types=sorted(set(unsafe)),
		)
	merged = _current_payload(row, extra)
	if base_components is not None and not buttons_edited:
		merged["buttons"] = []  # Meta's own BUTTONS are kept as they are; the local rows are not re-validated
	declared = payload.get("parameter_format")
	if declared not in (None, "") and str(declared).upper() != merged["parameter_format"]:
		return _err("immutable_field", field="parameter_format", message="The variable format (numbered or named) cannot be changed after creation.")
	current_header = str(merged.get("header_type") or "").upper()
	for key in ("body", "template", "sample_values", "named_samples", "header", "header_type", "sample", "header_handle", "footer", "buttons"):
		if key in payload:
			merged[key] = payload[key]
	if "template" in payload and "body" not in payload:
		merged.pop("body", None)
	if "header_type" in payload and not payload["header_type"]:
		for key in ("header_type", "header", "sample", "header_handle"):
			merged.pop(key, None)
	elif "header_type" in payload and str(payload["header_type"]).upper() != current_header:
		if "sample" not in payload:
			merged.pop("sample", None)  # the old header's sample belongs to the old media kind
		if str(payload["header_type"]).upper() != "TEXT" and "header" not in payload:
			merged.pop("header", None)
	# Meta may have reclassified the template (UTILITY -> MARKETING): compare with ITS category, not a stale one
	current_category = str(state.get("category") or row.get("category") or "").upper()
	category = str(payload.get("category") or current_category).upper()
	if category not in TEMPLATE_CATEGORIES:
		return _err("invalid_category", message="Category must be one of " + ", ".join(TEMPLATE_CATEGORIES))
	merged["category"] = category
	ttl = payload.get("message_send_ttl_seconds") if payload.get("message_send_ttl_seconds") is not None else payload.get("ttl_seconds")
	if ttl is not None and (isinstance(ttl, bool) or not isinstance(ttl, int)):
		return _err("invalid_ttl", message="message_send_ttl_seconds must be an integer")
	if ttl is not None:
		merged["ttl_seconds"] = ttl
	elif category != "UTILITY":
		merged.pop("ttl_seconds", None)  # a TTL only exists on UTILITY templates

	merged_header = str(merged.get("header_type") or "").upper()
	new_media_requested = bool(payload.get("sample") or payload.get("header_handle"))
	media_unchanged = (
		current_header in wt.MEDIA_HEADER_TYPES
		and merged_header == current_header
		and not new_media_requested
		and "header" not in payload
	)
	reuploaded = False
	if media_unchanged:
		handle = _existing_header_handle(extra, state)
		if handle:
			merged["header_handle"] = handle
		else:
			url = _existing_header_sample_url(extra, state)
			if not url:
				return _err("media_header_edit_unsupported", message="The current media header cannot be re-sent; provide a new sample file.")
			# imported header: only Meta's sample URL is known, which is not a handle: fetch and upload it again
			merged["sample"] = url
			media_unchanged = False
			reuploaded = True
	elif merged_header in wt.MEDIA_HEADER_TYPES and not (merged.get("sample") or merged.get("header_handle")):
		return _err(
			"media_header_edit_unsupported",
			message="A new image, video or document header needs a sample file (or an upload handle).",
		)
	spec, errors = wt.validate_template_spec(merged)
	if errors:
		return wt.validation_error(errors)
	if spec["header_type"] in wt.MEDIA_HEADER_TYPES and not media_unchanged and not spec["header_handle"]:
		problem = _check_sample_reference(spec["header_sample"])
		if problem:
			if reuploaded:
				return _err("media_header_edit_unsupported", message="The current media header cannot be re-sent and its sample could not be fetched; provide a new sample file.")
			return wt.validation_error([problem])
		try:
			spec["header_handle"] = upload_header_handle(acct, spec["header_type"], spec["header_sample"], http_post, http_get)
		except BridgeError as exc:
			if reuploaded:
				return _err("media_header_edit_unsupported", message="The current media header cannot be re-sent and its sample could not be fetched; provide a new sample file.", detail=exc.payload.get("message"))
			return exc.payload
	meta = wt.build_meta_payload(spec)
	built = meta["components"]
	if base_components is not None:
		changed = {sec for sec, keys in _SECTION_KEYS.items() if any(k in payload for k in keys)}
		if reuploaded:
			changed.add("HEADER")
		components = _merge_components(base_components, built, changed)
	else:
		components = built

	local_buttons = frappe.get_all(
		"WhatsApp Button", filters={"parent": name, "parenttype": "WhatsApp Templates"},
		fields=["button_type", "button_label", "website_url", "phone_number"], order_by="idx asc",
	)
	current_ttl = _extra_ttl(extra)
	same_header_sample = current_header != "TEXT" or (spec["header_sample"] or "") == (row.get("sample") or "")
	same_header_text = (spec["header_text"] or "") == ((row.get("header") or "") if current_header == "TEXT" else "")
	if base_components is not None:
		# Meta's own components are the truth: any difference (incl. a NAMED header variable / sample) is a change
		content_same = _components_sig(components, True) == _components_sig(base_components, True)
	else:
		content_same = (
			spec["body"] == (row.get("template") or "")
			and ",".join(spec["sample_values"]) == (row.get("sample_values") or "")
			and (spec["header_type"] or "") == current_header
			and same_header_text
			and same_header_sample
			and (spec["footer"] or "") == (row.get("footer") or "")
			and _button_sig(wt.button_rows(spec)) == _button_sig(local_buttons)
			and (spec["named_samples"] or []) == list(extra.get("named_samples") or spec["named_samples"] or [])
		)
	if (
		category == current_category
		and (spec["ttl_seconds"] or None) == (current_ttl or None)
		and content_same
		and not (spec["header_type"] in wt.MEDIA_HEADER_TYPES and not media_unchanged and not reuploaded)
	):
		return _err("no_changes", message="Nothing changed; no edit was sent to Meta.")

	body: dict[str, Any] = {"components": components}
	if category != current_category:  # only an operator's change; never re-send the stored category
		body["category"] = category
	if spec["ttl_seconds"] is not None:
		body["message_send_ttl_seconds"] = spec["ttl_seconds"]
	try:
		resp = (http_post or _default_post)(
			f"{acct['url']}/{acct['version']}/{row['id']}",
			json=body,
			headers={"Authorization": f"Bearer {acct['token']}", "Content-Type": "application/json"},
			timeout=_HTTP_TIMEOUT,
		)
	except Exception as exc:
		return _graph_err("edit_failed", exc)
	code = getattr(resp, "status_code", 200)
	if isinstance(code, int) and code >= 400:
		failed = _graph_err("edit_failed", resp, status=status, quota_used=False)
		if failed.get("kind") == "edit_blocked":
			failed["edit_blocked_until"] = _mark_edit_blocked(row.get("whatsapp_account"), name)
		return failed

	changes: dict[str, Any] = {
		"template": spec["body"],
		"sample_values": ",".join(spec["sample_values"]),
		"header_type": _local_header_type(spec["header_type"]),
		"footer": spec["footer"] or "",
		"category": category,
		"status": "PENDING",
	}
	if spec["header_type"] == "TEXT":
		changes["header"] = spec["header_text"]
		changes["sample"] = spec["header_sample"]
	elif not spec["header_type"]:
		changes["header"] = ""
		changes["sample"] = ""
	elif spec["header_type"] in wt.MEDIA_HEADER_TYPES and not media_unchanged:
		changes["header"] = ""
		if not reuploaded:  # a re-fetched Meta CDN URL is not a sample the user chose
			changes["sample"] = spec["header_sample"]
	elif spec["header_type"] == "LOCATION":
		changes["header"] = ""
		changes["sample"] = ""
	with _guard().huf_template_write():
		frappe.db.set_value("WhatsApp Templates", name, changes)
		if buttons_edited or base_components is None:  # otherwise the local rows (even ones Huf cannot rebuild) stay
			_write_buttons(name, _button_rows(spec))
		try:
			_guard().upsert_extra(row.get("whatsapp_account"), name, **_extra_values(spec, row["id"], components))
		except Exception:
			frappe.logger("huf").warning("WhatsApp template extra update failed", exc_info=True)

	log = _loads(state.get("edit_log"), []) or []
	if status == "APPROVED":  # only edits of an APPROVED template count against Meta's quota
		log.append(_utcnow().isoformat())
		cutoff = _utcnow() - timedelta(days=60)
		log = [t for t in log if (_parse_ts(t) or _utcnow()) > cutoff]
	record_template_state(
		docname=name, template_id=row["id"], account=row.get("whatsapp_account"), status="PENDING",
		category=category, reason="", recommendation="", components=components, source="edit",
	)
	edit_key = state_key(row.get("whatsapp_account"), name)
	if frappe.db.exists(STATE_DOCTYPE, edit_key):
		frappe.db.set_value(STATE_DOCTYPE, edit_key, "edit_log", json.dumps(log))
	try:
		frappe.cache().delete_value(_edit_blocked_key(row.get("whatsapp_account"), name))
	except Exception:
		pass
	return {
		"success": True,
		"name": name,
		"status": "PENDING",
		"edits_left": edit_quota("APPROVED", log)["edits_left"] if status == "APPROVED" else None,
		**({"notes": spec["notes"]} if spec.get("notes") else {}),
	}


# ------------------------------------------------------------------- drafts


def _is_admin() -> bool:
	return bool(set(frappe.get_roles() or []).intersection(ADMIN_ROLES))


def _draft_row(doc_or_row: Any) -> dict[str, Any]:
	g = doc_or_row.get
	return {
		"name": g("name"), "template_name": g("template_name"), "language_code": g("language_code"),
		"category": g("category"), "whatsapp_account": g("whatsapp_account"), "status": g("status"),
		"payload": _loads(g("payload"), {}), "requested_by": g("requested_by"), "requested_via": g("requested_via"),
		"agent_run": g("agent_run"), "reviewed_by": g("reviewed_by"),
		"reviewed_at": str(g("reviewed_at")) if g("reviewed_at") else None, "review_note": g("review_note"),
		"submitted_template": g("submitted_template"), "submit_error": g("submit_error"),
		"creation": str(g("creation")) if g("creation") else None,
	}


def create_draft(
	payload: dict[str, Any],
	requested_by: str | None = None,
	via: str = "User",
	agent_run: str | None = None,
	account: str | None = None,
	status: str = "Pending Review",
	trusted: bool = False,
) -> dict[str, Any]:
	"""Save a template draft (validated like ``create_template``); nothing is sent to Meta.

	``trusted`` skips the permission check (server-gated agent path only).
	"""
	if not isinstance(payload, dict):
		return _err("invalid_payload", message="payload must be an object")
	if status not in ("Draft", "Pending Review"):
		return _err("invalid_status", message="A new draft is either Draft or Pending Review.")
	if not trusted and not frappe.has_permission(DRAFT_DOCTYPE, "create"):
		raise frappe.PermissionError("Not permitted to create WhatsApp Template Drafts")
	checked = validate_create_payload(payload)
	if checked.get("error"):
		return checked["error"]
	clean = {k: v for k, v in payload.items() if k not in ("allow_whatsapp_management", "allow_proactive")}
	doc = frappe.get_doc(
		{
			"doctype": DRAFT_DOCTYPE,
			"template_name": checked["name"],
			"language_code": checked["language_code"],
			"category": checked["category"],
			"whatsapp_account": account or "",
			"payload": json.dumps(clean, default=str),
			"status": status,
			"requested_by": requested_by or frappe.session.user,
			"requested_via": "Agent run" if via == "Agent run" else "User",
			"agent_run": agent_run or "",
		}
	)
	doc.insert(ignore_permissions=bool(trusted))
	return {"success": True, "name": doc.name, "status": doc.status, "draft": _draft_row(doc)}


def _locked_draft(name: str) -> Any:
	if not name or not frappe.db.exists(DRAFT_DOCTYPE, name):
		return None
	return frappe.get_doc(DRAFT_DOCTYPE, name, for_update=True)


def approve_draft(name: str, note: str = "") -> dict[str, Any]:
	"""Admin approval: re-validate the payload and submit it to Meta exactly once.

	Sets ``Approved & Submitted`` (+ ``submitted_template``) on success, ``Failed`` (+
	``submit_error``) when Meta or validation refuses. A draft that is already submitted or
	rejected cannot be approved again.
	"""
	if not _is_admin():
		raise frappe.PermissionError("System Manager or Huf Admin role required")
	doc = _locked_draft(name)
	if not doc:
		return _err("not_found")
	stale_submitting = False
	if doc.status == _SUBMITTING:
		age = (frappe.utils.now_datetime() - frappe.utils.get_datetime(doc.modified)).total_seconds()
		stale_submitting = age > _SUBMITTING_STALE_SECONDS
	if doc.status not in _DRAFT_OPEN and not stale_submitting:
		return _err("already_processed", status=doc.status, message=f"This draft is {doc.status}.")
	payload = _loads(doc.payload, {}) or {}
	if is_available() and doc.whatsapp_account:
		# Close the duplicate-submit window: other approvers now see Submitting, not an open draft
		frappe.db.set_value(DRAFT_DOCTYPE, doc.name, "status", _SUBMITTING, update_modified=False)
		frappe.db.commit()
		doc.status = _SUBMITTING
	doc.reviewed_by = frappe.session.user
	doc.reviewed_at = frappe.utils.now_datetime()
	doc.review_note = note or ""
	account = doc.whatsapp_account
	if not is_available():
		result: dict[str, Any] = _err("bridge_unavailable")
	else:
		# the draft's own account only: no default-account guess at approval time
		try:
			result = create_template(account, payload, commit=True) if account else _err("no_account")
		except frappe.PermissionError:
			raise
		except Exception as exc:
			result = _err("create_failed", message=_redact(exc))
		if not result.get("success") and account and _is_duplicate_error(result):
			result = _recover_duplicate(account, payload) or result
	if result.get("success"):
		doc.status = "Approved & Submitted"
		doc.submitted_template = result.get("name")
		doc.submit_error = ""
		doc.whatsapp_account = account
	else:
		doc.status = "Failed"
		detail = result.get("message") or "; ".join(str(e.get("message")) for e in result.get("errors") or [])
		doc.submit_error = _redact(detail or result.get("error"))[:1000]
	doc.save(ignore_permissions=True)
	if doc.status == "Approved & Submitted":
		frappe.db.commit()  # the draft now points at the template Meta accepted
	out = {
		"success": bool(result.get("success")),
		"name": doc.name,
		"status": doc.status,
		"submitted_template": doc.submitted_template or "",
		"submit_error": doc.submit_error or "",
	}
	if not out["success"]:
		out["error"] = result.get("error")
		for key in ("user_title", "user_msg", "graph_code", "subcode", "kind", "retryable", "operator_text", "trace_id", "message"):
			if result.get(key) not in (None, ""):
				out[key] = result[key]
	return out


def _is_duplicate_error(result: dict[str, Any]) -> bool:
	text = str(result.get("message") or "").lower()
	return result.get("error") == "create_failed" and ("already exist" in text or "2388024" in text)


def _recover_duplicate(account: str, payload: dict[str, Any]) -> dict[str, Any] | None:
	"""Meta says the name+language already exists on this account (an earlier submit was accepted but never
	recorded): import it with a sync and report success with the local template; None when it cannot be found."""
	try:
		checked = validate_create_payload(payload)
		if checked.get("error"):
			return None
		synced = sync_templates(account)
		if not synced.get("success"):
			return None
		docname = _local_template(account, checked["name"], checked["language_code"])
		if not docname:
			return None
		status = frappe.db.get_value("WhatsApp Templates", docname, "status")
		frappe.db.commit()
		return {"success": True, "name": docname, "status": status, "recovered_duplicate": True}
	except Exception:
		return None


def reject_draft(name: str, note: str = "") -> dict[str, Any]:
	"""Admin rejection of a draft; never contacts Meta."""
	if not _is_admin():
		raise frappe.PermissionError("System Manager or Huf Admin role required")
	doc = _locked_draft(name)
	if not doc:
		return _err("not_found")
	if doc.status not in _DRAFT_OPEN:
		return _err("already_processed", status=doc.status, message=f"This draft is {doc.status}.")
	doc.status = "Rejected"
	doc.reviewed_by = frappe.session.user
	doc.reviewed_at = frappe.utils.now_datetime()
	doc.review_note = note or ""
	doc.save(ignore_permissions=True)
	return {"success": True, "name": doc.name, "status": doc.status}


def list_drafts(
	status: str | None = None, limit: int = 100, account: str | None = None
) -> list[dict[str, Any]]:
	"""Template drafts of ONE account, newest first (permission-checked read).

	``account=None`` raises ``gateway_required`` rather than listing every account's drafts;
	``account=""`` is the unscoped bucket of sites without frappe_whatsapp (drafts with no account).
	"""
	if not frappe.has_permission(DRAFT_DOCTYPE, "read"):
		raise frappe.PermissionError("Not permitted to read WhatsApp Template Drafts")
	if account is None:
		raise BridgeError(_gateway_required())
	filters: dict[str, Any] = {"whatsapp_account": account if account else ["is", "not set"]}
	if status:
		filters["status"] = status
	rows = frappe.get_all(DRAFT_DOCTYPE, filters=filters, fields=["*"], order_by="creation desc", limit_page_length=limit)
	return [_draft_row(r) for r in rows]


def get_draft_or_state(ref: str, account: str | None = None) -> dict[str, Any]:
	"""Agent-facing lookup by draft name or template name: draft state plus Meta review state.

	With ``account`` only that account's drafts and template states are consulted.
	"""
	ref = str(ref or "").strip()
	if not ref:
		return _err("invalid_name", message="template_name is required")
	out: dict[str, Any] = {"success": True}
	draft = None
	draft_scope = {"whatsapp_account": account} if account else {}
	if frappe.db.exists(DRAFT_DOCTYPE, {"name": ref, **draft_scope}):
		draft = frappe.get_doc(DRAFT_DOCTYPE, ref)
	else:
		hit = frappe.get_all(
			DRAFT_DOCTYPE,
			filters={"template_name": ref, **draft_scope},
			order_by="creation desc",
			limit_page_length=1,
			pluck="name",
		)
		if hit:
			draft = frappe.get_doc(DRAFT_DOCTYPE, hit[0])
	docname = None
	if draft is not None:
		out["draft"] = {
			"name": draft.name, "status": draft.status, "review_note": draft.review_note or "",
			"submit_error": draft.submit_error or "", "submitted_template": draft.submitted_template or "",
		}
		docname = draft.submitted_template or None
		account = account or (draft.get("whatsapp_account") or None)
	state_scope = {"whatsapp_account": account} if account else {}
	if not docname and frappe.db.exists(STATE_DOCTYPE, {"template": ref, **state_scope}):
		docname = ref
	if not docname:
		hit = frappe.get_all(
			STATE_DOCTYPE, filters={"template": ["like", f"{ref}-%"], **state_scope}, limit_page_length=1, pluck="template"
		)
		docname = hit[0] if hit else None
	if docname:
		state = _state_row(docname, account) or {}
		out.update(
			template=docname, status=state.get("status") or "", reason=state.get("rejected_reason") or "",
			recommendation=state.get("rejection_recommendation") or "",
			quality=state.get("quality_score") or "UNKNOWN",
			category=state.get("category") or "", correct_category=state.get("correct_category") or "",
		)
	elif draft is None:
		return _err("not_found", message=f"No template or draft named {ref}.")
	return out


def forward_status(change: dict[str, Any], _retry: bool = False) -> bool:
	"""Forward a status ``change`` to frappe_whatsapp's ``update_status`` (A4).

	Lazy import; never raises. Returns True only if a forward actually happened.
	A message status whose wamid is not (yet) known is not dropped: one delayed
	retry is enqueued (the outgoing row may still be uncommitted when Meta's
	webhook arrives). ``_retry`` marks that retry so it never loops.
	"""
	try:
		if not is_available():
			return False
		if change.get("field") == "messages":
			statuses = (change.get("value") or {}).get("statuses") or []
			if not statuses or not frappe.db.exists("WhatsApp Message", {"message_id": statuses[0].get("id")}):
				if statuses and not _retry:
					_enqueue_forward_retry(change)
				return False
		webhook = importlib.import_module("frappe_whatsapp.utils.webhook")
		webhook.update_status(change)
		return True
	except Exception:
		return False


def _enqueue_forward_retry(change: dict[str, Any]) -> None:
	try:
		frappe.enqueue(
			"huf.ai.gateway_adapters.whatsapp_bridge.retry_forward_status",
			queue="short",
			enqueue_after_commit=True,
			change=change,
		)
	except Exception:
		pass  # best effort


def retry_forward_status(change: dict[str, Any]) -> bool:
	"""Background job: wait briefly for the outgoing row to be committed, then forward once."""
	import time

	time.sleep(FORWARD_RETRY_DELAY_SECONDS)
	return forward_status(change, _retry=True)


def media_limit_for_mime(mime: str) -> int:
	"""Meta's inbound size limit for the media kind a MIME type belongs to."""
	mime = (mime or "").lower()
	if mime.startswith("image/"):
		return MEDIA_LIMITS_BY_KIND["image"]
	if mime.startswith("audio/"):
		return MEDIA_LIMITS_BY_KIND["audio"]
	if mime.startswith("video/"):
		return MEDIA_LIMITS_BY_KIND["video"]
	return MEDIA_LIMITS_BY_KIND["document"]


# Generic MIME types WhatsApp sends for files it cannot label (commonly .m4a documents).
_GENERIC_MIMES = ("", "application/octet-stream")
# Filename extension -> MIME, for inferring a generic declared type. Every value must already
# pass DEFAULT_MIME_PREFIXES; anything absent here (svg, html, exe, sh, js, csv, ...) is refused.
_EXTENSION_MIME = {
	"m4a": "audio/mp4",
	"mp3": "audio/mpeg",
	"ogg": "audio/ogg",
	"oga": "audio/ogg",
	"opus": "audio/ogg",
	"wav": "audio/wav",
	"aac": "audio/aac",
	"amr": "audio/amr",
	"mp4": "video/mp4",
	"3gp": "video/3gpp",
	"pdf": "application/pdf",
	"jpg": "image/jpeg",
	"jpeg": "image/jpeg",
	"png": "image/png",
	"webp": "image/webp",
	"txt": "text/plain",
	"doc": "application/msword",
	"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
	"xls": "application/vnd.ms-excel",
	"xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
	"ppt": "application/vnd.ms-powerpoint",
	"pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
_OLE_DOC_MIMES = ("application/msword", "application/vnd.ms-excel", "application/vnd.ms-powerpoint")


def _mime_from_filename(name: str) -> str:
	"""MIME type for a filename's extension, or "" when the extension is unknown or refused."""
	base = str(name or "").replace("\\", "/").rsplit("/", 1)[-1]
	if "." not in base:
		return ""
	return _EXTENSION_MIME.get(base.rsplit(".", 1)[-1].strip().lower(), "")


def _signature_matches(mime: str, content: bytes) -> bool:
	"""Check the payload's magic bytes against the inferred MIME. Unknown MIMEs never match."""
	head = content[:16]
	if mime in ("audio/mp4", "video/mp4", "video/3gpp"):
		return head[4:8] == b"ftyp"
	if mime in ("audio/mpeg", "audio/aac"):
		if head.startswith(b"ID3"):
			return True
		if len(head) < 2 or head[0] != 0xFF:
			return False
		return (head[1] & 0xE0) == 0xE0 if mime == "audio/mpeg" else (head[1] & 0xF6) == 0xF0
	if mime == "audio/ogg":
		return head.startswith(b"OggS")
	if mime == "audio/wav":
		return head[:4] == b"RIFF" and head[8:12] == b"WAVE"
	if mime == "audio/amr":
		return head.startswith(b"#!AMR")
	if mime == "image/jpeg":
		return head.startswith(b"\xff\xd8\xff")
	if mime == "image/png":
		return head.startswith(b"\x89PNG\r\n\x1a\n")
	if mime == "image/webp":
		return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
	if mime == "application/pdf":
		return head.startswith(b"%PDF")
	if mime.startswith("application/vnd.openxmlformats-officedocument."):
		return head.startswith(b"PK\x03\x04")
	if mime in _OLE_DOC_MIMES:
		return head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
	if mime == "text/plain":
		return b"\x00" not in content
	return False


def download_media(
	account_name: str,
	media_id: str,
	max_bytes: int | None = None,
	allowed_mime_prefixes: tuple[str, ...] = DEFAULT_MIME_PREFIXES,
	http_get: Callable[..., Any] | None = None,
	credentials: dict[str, Any] | None = None,
	kind: str | None = None,
	filename: str | None = None,
) -> dict[str, Any]:
	"""Fetch media by id at call time. Raises ValueError on caps/mime/failure.

	The size cap is ``max_bytes`` when given, else Meta's per-kind limit (``kind``
	when known, e.g. sticker, otherwise derived from the MIME type); declared and
	streamed sizes are both enforced.

	A generic declared type (empty or ``application/octet-stream``) is replaced by the
	MIME inferred from ``filename`` (or Meta's filename). The inferred type must be in
	the allow-list, and the payload's magic bytes must match it. Specific declared
	types are never overridden by the extension.

	``credentials`` (``token``, optional ``url``/``version``) serves direct-mode
	gateways that have no WhatsApp Account; otherwise the account is resolved.
	"""
	if credentials and credentials.get("token"):
		acct = {
			"token": credentials["token"],
			"url": str(credentials.get("url") or GRAPH_HOST).rstrip("/"),
			"version": credentials.get("version") or GRAPH_DEFAULT_VERSION,
		}
	else:
		acct = resolve_account(account_name)
	if not acct or acct.get("error"):
		raise ValueError("no_account")
	http_get = http_get or _default_get
	headers = {"Authorization": f"Bearer {acct['token']}"}
	meta_resp = http_get(
		f"{acct['url']}/{acct['version']}/{quote(str(media_id), safe='')}",
		headers=headers,
		timeout=_HTTP_TIMEOUT,
		allow_redirects=False,
	)
	meta_resp.raise_for_status()
	meta = meta_resp.json()
	declared = str(meta.get("mime_type") or "").split(";")[0].strip().lower()
	name_hint = str(filename or meta.get("filename") or "")
	infer = declared in _GENERIC_MIMES
	mime = _mime_from_filename(name_hint) if infer else declared
	if (
		not mime
		or mime.startswith(_BLOCKED_MIME_PREFIXES)
		or not any(mime.startswith(p) for p in allowed_mime_prefixes)
	):
		raise ValueError(f"mime_not_allowed: {declared or 'unknown'}")
	if max_bytes is None:
		max_bytes = MEDIA_LIMITS_BY_KIND.get(str(kind or "").lower()) or media_limit_for_mime(mime)
	declared = meta.get("file_size")
	if declared is not None and int(declared) > max_bytes:
		raise ValueError("media_too_large")
	media_url = meta.get("url")
	if not media_url:
		raise ValueError("media_url_missing")
	if not _is_media_host(str(media_url)):
		raise ValueError("media_url_host_not_allowed")
	resp = http_get(media_url, headers=headers, timeout=_HTTP_TIMEOUT, allow_redirects=False, stream=True)
	try:
		resp.raise_for_status()
		if hasattr(resp, "iter_content"):
			buf = bytearray()
			for chunk in resp.iter_content(chunk_size=64 * 1024):
				buf.extend(chunk)
				if len(buf) > max_bytes:
					raise ValueError("media_too_large")
			content = bytes(buf)
		else:
			content = resp.content
			if len(content) > max_bytes:
				raise ValueError("media_too_large")
	finally:
		close = getattr(resp, "close", None)
		if callable(close):
			close()
	if infer and not _signature_matches(mime, content):
		raise ValueError(f"mime_not_allowed: {declared or 'unknown'}")
	filename = re.sub(r"[^A-Za-z0-9._-]", "_", str(filename or meta.get("filename") or media_id))[:100] or "media"
	return {"content": content, "mime_type": mime, "filename": filename}


def list_messages(account_name: str | None = None, phone: str | None = None, limit: int = 50) -> dict[str, Any]:
	"""List WhatsApp Messages (newest first); bridge_unavailable error if absent (A15)."""
	if not is_available():
		return _err("bridge_unavailable")
	if not account_name:
		return _gateway_required()
	filters: dict[str, Any] = {"whatsapp_account": account_name}
	if phone:
		p = normalize_phone(phone)
		or_filters = {"to": p, "from": p}
		rows = frappe.get_list(
			"WhatsApp Message",
			filters=filters,
			or_filters=or_filters,
			fields=_MSG_FIELDS,
			order_by="creation desc",
			limit_page_length=limit,
		)
		return {"success": True, "messages": rows}
	rows = frappe.get_list(
		"WhatsApp Message", filters=filters, fields=_MSG_FIELDS, order_by="creation desc", limit_page_length=limit
	)
	return {"success": True, "messages": rows}


_MSG_FIELDS = ["name", "type", "to", "from", "message", "message_id", "content_type", "status", "creation", "whatsapp_account", "profile_name"]


def list_conversations(account_name: str | None = None, limit: int = 50) -> dict[str, Any]:
	"""Group recent messages by counterparty number (latest message each)."""
	if not is_available():
		return _err("bridge_unavailable")
	if not account_name:
		return _gateway_required()
	filters = {"whatsapp_account": account_name}
	rows = frappe.get_list(
		"WhatsApp Message",
		filters=filters,
		fields=_MSG_FIELDS,
		order_by="creation desc",
		limit_page_length=max(limit * 20, 200),
	)
	convs: dict[str, dict[str, Any]] = {}
	for row in rows:
		other = normalize_phone(row.get("from") if row.get("type") == "Incoming" else row.get("to"))
		if not other:
			continue
		conv = convs.setdefault(other, {"phone": other, "last_message": row, "count": 0, "profile_name": None})
		conv["count"] += 1
		if row.get("profile_name") and not conv["profile_name"]:
			conv["profile_name"] = row["profile_name"]
	return {"success": True, "conversations": list(convs.values())[:limit]}
