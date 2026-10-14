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

import hashlib
import importlib
import json
import re
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlparse

import frappe
import frappe.utils

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


def normalize_phone(raw: Any) -> str:
	"""Return digits only (no +, spaces, dashes, parens, leading ``00``)."""
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


def accounts_for_waba(waba_id: Any) -> list[str]:
	"""WhatsApp Accounts whose ``business_id`` is the given WABA id (payload ``entry[].id``)."""
	waba = str(waba_id or "").strip()
	if not waba or not is_available():
		return []
	try:
		return list(frappe.get_all("WhatsApp Account", filters={"business_id": waba}, pluck="name") or [])
	except Exception:
		return []


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
	last = None
	for row in rows or []:
		if not row.get("verified_sender"):
			continue
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
	content_type = message.get("type") or message.get("content_type") or "text"
	body = ""
	if content_type == "text":
		body = (message.get("text") or {}).get("body", "") if isinstance(message.get("text"), dict) else message.get("text") or ""
	elif isinstance(message.get(content_type), dict):
		body = message[content_type].get("caption", "") or ""
	if not body:
		body = message.get("body") or message.get("message") or ""
	allowed = {"text", "document", "image", "video", "audio", "flow", "reaction", "location", "contact", "button", "interactive", "order"}
	doc = frappe.get_doc(
		{
			"doctype": "WhatsApp Message",
			"type": "Incoming",
			"from": normalize_phone(message.get("from")),
			"message": body,
			"message_id": message_id,
			"content_type": content_type if content_type in allowed else "text",
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
) -> dict[str, Any]:
	"""Send a free-form text via ``WhatsApp Message`` (it performs the one send, A1).

	``trusted=True`` is only for the gateway-internal reply path and skips
	permission checks; user-initiated calls must leave it False. Raises
	:class:`BridgeError` (``.payload`` is the error dict) on failure.
	"""
	_account_or_error(account_name)
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
		doc.insert(ignore_permissions=bool(trusted))
		if trusted:
			# Gateway reply path runs in a background job: persist the outgoing row
			# now so Meta's status webhook can match its wamid straight away.
			frappe.db.commit()
	except frappe.PermissionError:
		raise
	except Exception as exc:
		raise BridgeError(_err("send_failed", message=_redact(exc))) from exc
	return _readback(doc)


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


def _graph_post_message(acct: dict[str, Any], data: dict[str, Any], http_post: Callable[..., Any] | None = None) -> str:
	"""POST a ``/messages`` body with the account credentials; returns the wamid or raises BridgeError."""
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
		raise BridgeError(_err("send_failed", message=graph_error_message(resp)))
	try:
		return str(resp.json()["messages"][0]["id"])
	except Exception as exc:
		raise BridgeError(_err("send_failed", message="Unexpected response from WhatsApp.")) from exc


def _template_row(docname: str) -> dict[str, Any] | None:
	"""Header/body/button definition of a WhatsApp Templates document (None if unknown)."""
	if not frappe.db.exists("WhatsApp Templates", docname):
		return None
	row = frappe.db.get_value(
		"WhatsApp Templates",
		docname,
		[
			"template", "header_type", "header", "sample", "actual_name", "template_name", "language_code", "status",
			"whatsapp_account",
		],
		as_dict=True,
	)
	row["buttons"] = frappe.get_all(
		"WhatsApp Button",
		filters={"parent": docname, "parenttype": "WhatsApp Templates"},
		fields=["button_type", "button_label", "url_type", "website_url"],
		order_by="idx asc",
	)
	return row


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
		doc.insert(ignore_permissions=bool(trusted))
		if trusted:
			frappe.db.commit()
		return {"success": True, "name": doc.name, "message_id": wamid, "status": doc.get("status")}
	except Exception:
		# The template is already delivered; a failed audit row must not fail the send.
		return {"success": True, "name": None, "message_id": wamid, "status": "Success", "mirrored": False}


def send_template(
	account_name: str,
	to: str,
	template_name: str,
	body_params: list | None = None,
	header_params: list | None = None,
	trusted: bool = False,
	language_code: str | None = None,
	button_params: list | None = None,
	http_post: Callable[..., Any] | None = None,
) -> dict[str, Any]:
	"""Send an approved template.

	Plain body-only sends use an Outgoing ``WhatsApp Message`` (use_template=1),
	which frappe_whatsapp sends. Sends with header or button parameters (text
	header variable, media header link, dynamic URL suffix) need components that
	frappe_whatsapp cannot build without a reference document, so those are
	posted to Graph with the account credentials and mirrored into
	``WhatsApp Message`` without a second send.

	``header_params``: one text string or one ``{"type": image|document|video,
	"link": ..., "filename"?: ...}``. ``button_params``: ``[{"index": 0,
	"sub_type": "url", "text": "<suffix>"}]`` (a bare string is the URL suffix at
	its list position). Permission-checked unless ``trusted=True`` (gateway-internal
	reply path). Raises :class:`BridgeError` (``.payload`` is the error dict).
	"""
	acct = _account_or_error(account_name)
	errors: list[dict[str, str]] = []
	params = [wt.validate_param_text(f"body_params[{i}]", p, errors) for i, p in enumerate(body_params or [])]
	headers_n, header_errors = wt.normalize_header_params(header_params)
	buttons_n, button_errors = wt.normalize_button_params(button_params)
	errors += header_errors + button_errors
	docname = _template_docname(account_name, template_name, language_code)
	tpl = _template_row(docname)
	if tpl and (tpl.get("whatsapp_account") or "") != (account_name or ""):
		# the docname resolves to another account's template: never send it from this account
		raise BridgeError(_err("template_not_found", message="That template does not belong to this WhatsApp account."))
	if tpl:
		errors += _check_send_against_template(tpl, params, headers_n, buttons_n)
	if errors:
		raise BridgeError(wt.validation_error(errors))

	header_type = (tpl or {}).get("header_type") or ""
	if (
		tpl
		and header_type in wt.MEDIA_HEADER_TYPES
		and not headers_n
		and not (header_type == "IMAGE" and wt.is_http_url(str(tpl.get("sample") or "")))
	):
		raise BridgeError(
			wt.validation_error(
				[wt._e("header_params", "required", f"This template has an {header_type} header; provide a media link.")]
			)
		)

	if headers_n or buttons_n or (tpl and _has_dynamic_url(tpl)):
		if not trusted and not frappe.has_permission("WhatsApp Message", "create"):
			raise frappe.PermissionError("Not permitted to send WhatsApp messages")
		for item in headers_n:
			if isinstance(item, dict) and not item.get("type"):
				item["type"] = header_type.lower() if header_type else "image"
		template_payload: dict[str, Any] = {
			"name": (tpl or {}).get("actual_name") or (tpl or {}).get("template_name") or template_name,
			"language": {"code": (tpl or {}).get("language_code") or language_code or "en_US"},
		}
		components = wt.build_template_components(params, headers_n, buttons_n, header_type, always_body=bool(params))
		if components:
			template_payload["components"] = components
		wamid = _graph_post_message(
			acct,
			{
				"messaging_product": "whatsapp",
				"recipient_type": "individual",
				"to": normalize_phone(to),
				"type": "template",
				"template": template_payload,
			},
			http_post,
		)
		mirror: dict[str, Any] = {"template_parameters": ",".join(params)}
		if params:
			mirror["body_param"] = json.dumps({str(i + 1): p for i, p in enumerate(params)})
		media = next((h for h in headers_n if isinstance(h, dict)), None)
		if media:
			mirror["attach"] = media["link"]
		elif headers_n:
			mirror["template_header_parameters"] = str(headers_n[0])
		return _mirror_template_send(acct, docname, to, wamid, mirror, trusted)

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
		"body_param": json.dumps({str(i + 1): p for i, p in enumerate(params)}),
	}
	try:
		doc = frappe.get_doc(values)
		doc.insert(ignore_permissions=bool(trusted))
		if trusted:
			# Gateway reply path runs in a background job: persist the outgoing row
			# now so Meta's status webhook can match its wamid straight away.
			frappe.db.commit()
	except frappe.PermissionError:
		raise
	except Exception as exc:
		raise BridgeError(_err("send_failed", message=_redact(exc))) from exc
	return _readback(doc)


def _has_dynamic_url(tpl: dict[str, Any]) -> bool:
	return any(b.get("button_type") == "Visit Website" and b.get("url_type") == "Dynamic" for b in tpl.get("buttons") or [])


def _check_send_against_template(
	tpl: dict[str, Any], params: list[str], headers_n: list[Any], buttons_n: list[dict[str, Any]]
) -> list[dict[str, str]]:
	errors: list[dict[str, str]] = []
	expected = len(wt.placeholders(tpl.get("template") or ""))
	if expected != len(params):
		errors.append(wt._e("body_params", "param_count_mismatch", f"This template takes {expected} body parameter(s); got {len(params)}."))
	header_type = tpl.get("header_type") or ""
	header_vars = len(wt.placeholders(tpl.get("header") or "")) if header_type == "TEXT" else 0
	if header_type == "TEXT":
		if header_vars and not headers_n:
			errors.append(wt._e("header_params", "required", "This template header has a variable; provide one header parameter."))
		elif not header_vars and headers_n:
			errors.append(wt._e("header_params", "not_expected", "This template header takes no parameter."))
		elif headers_n and isinstance(headers_n[0], dict):
			errors.append(wt._e("header_params", "invalid_type", "This template header needs text, not media."))
	elif header_type in wt.MEDIA_HEADER_TYPES:
		if headers_n and not isinstance(headers_n[0], dict):
			errors.append(wt._e("header_params", "invalid_type", f"This template has an {header_type} header; provide a media link."))
		elif headers_n and headers_n[0].get("type") and headers_n[0]["type"] != header_type.lower():
			errors.append(wt._e("header_params", "invalid_type", f"This template has an {header_type} header."))
	elif headers_n:
		errors.append(wt._e("header_params", "not_expected", "This template has no header."))
	buttons = tpl.get("buttons") or []
	dynamic = {i for i, b in enumerate(buttons) if b.get("button_type") == "Visit Website" and b.get("url_type") == "Dynamic"}
	given = set()
	for bp in buttons_n:
		idx = bp["index"]
		if bp["sub_type"] == "url":
			if idx not in dynamic:
				errors.append(wt._e("button_params", "unexpected", f"Button {idx} is not a dynamic URL button."))
			given.add(idx)
		elif idx >= len(buttons) or buttons[idx].get("button_type") != "Quick Reply":
			errors.append(wt._e("button_params", "unexpected", f"Button {idx} is not a quick-reply button."))
	for idx in sorted(dynamic - given):
		errors.append(wt._e("button_params", "required", f"Button {idx} is a dynamic URL button and needs its URL suffix."))
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
) -> dict[str, Any]:
	"""Send an image/document/audio/video as an Outgoing ``WhatsApp Message`` (it performs the send).

	frappe_whatsapp's ``send_outgoing`` takes the media from ``attach`` (a public
	link) and the caption from ``message``. It cannot send an uploaded media id or
	a document filename, so those are rejected / ignored here. The caller is
	responsible for the 24h window check; free-form media is subject to it.
	"""
	_account_or_error(account_name)
	media, errors = wt.validate_media_request(kind, link, media_id, caption, filename)
	if not errors and media["media_id"]:
		errors.append(wt._e("media_id", "unsupported_in_bridge", "Bridge mode sends media by link; media_id needs direct mode."))
	if errors:
		raise BridgeError(wt.validation_error(errors))
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
		doc.insert(ignore_permissions=bool(trusted))
		if trusted:
			frappe.db.commit()
	except frappe.PermissionError:
		raise
	except Exception as exc:
		raise BridgeError(_err("send_failed", message=_redact(exc))) from exc
	return _readback(doc)


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


def create_template(account_name: str, payload: dict[str, Any]) -> dict[str, Any]:
	"""Create a WhatsApp Templates row (its after_insert pushes to Meta). Permission-checked (A8).

	Supports an optional header (TEXT with at most one variable, or IMAGE/DOCUMENT
	with a sample file), footer and up to 3 quick-reply / 2 call-to-action
	buttons, validated against Meta limits first. Field mapping follows the
	``WhatsApp Templates`` / ``WhatsApp Button`` doctypes: ``header_type``,
	``header``, ``sample``, ``footer``, ``sample_values`` and ``buttons`` child
	rows. Validation failures return ``{"error": "validation_failed", "errors": [...]}``.
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
	taken = _docname_taken_by_other_account(account_name, f"{name}-{language_code}")
	if taken:
		return taken
	values: dict[str, Any] = {k: payload[k] for k in _TEMPLATE_PASSTHROUGH if payload.get(k)}
	values.update(
		{
			"doctype": "WhatsApp Templates",
			"template_name": name,
			"category": category,
			"language": language,
			"language_code": language_code,
			"whatsapp_account": account_name,
			"template": spec["body"],
			"sample_values": ",".join(spec["sample_values"]),
		}
	)
	if spec["header_type"]:
		values["header_type"] = spec["header_type"]
		if spec["header_type"] == "TEXT":
			values["header"] = spec["header_text"]
		if spec["header_sample"]:
			values["sample"] = spec["header_sample"]
	if spec["footer"]:
		values["footer"] = spec["footer"]
	rows = wt.button_rows(spec)
	if rows:
		values["buttons"] = rows
	doc = None
	try:
		doc = frappe.get_doc(values)
		doc.insert()
	except frappe.PermissionError:
		raise
	except Exception as exc:
		# frappe_whatsapp pushes to Meta in after_insert, so a Meta rejection leaves a
		# local row that never existed on Meta. Drop it (no hooks) so it cannot linger as PENDING.
		orphan = getattr(doc, "name", None)
		if orphan and not doc.get("id") and frappe.db.exists("WhatsApp Templates", orphan):
			frappe.db.delete("WhatsApp Templates", {"name": orphan})
		return _err("create_failed", message=_redact(exc))
	record_template_state(
		docname=doc.name, template_id=doc.get("id"), account=account_name, status=doc.get("status") or "PENDING",
		category=category, source="create",
	)
	return {"success": True, "name": doc.name, "status": doc.get("status"), "id": doc.get("id")}


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
	try:
		frappe.delete_doc("WhatsApp Templates", name)
	except frappe.PermissionError:
		raise
	except Exception as exc:
		return _err("delete_failed", message=_redact(exc))
	return {"success": True, "name": name}


_META_BUTTON_TYPES = {
	"URL": "Visit Website",
	"PHONE_NUMBER": "Call Phone",
	"QUICK_REPLY": "Quick Reply",
	"FLOW": "Flow",
	"MPM": "Multi-Product Message",
	"CATALOG": "Catalog",
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
	out: dict[str, Any] = {"header_type": "", "header": "", "footer": "", "template": "", "sample_values": "", "buttons": []}
	for comp in components if isinstance(components, list) else []:
		if not isinstance(comp, dict):
			continue
		ctype = str(comp.get("type") or "").upper()
		if ctype == "HEADER":
			fmt = str(comp.get("format") or "").upper()
			if fmt in ("TEXT", "IMAGE", "DOCUMENT"):
				out["header_type"] = fmt
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
	# validate before any insert so an overflowing template never leaves a half-written parent row
	checks = [("WhatsApp Templates", _TEMPLATE_DATA_FIELDS, [doc])]
	checks.append(("WhatsApp Button", _BUTTON_DATA_FIELDS, list(doc.get("buttons") or [])))
	for dt, fieldnames, docs in checks:
		for row_doc in docs:
			for fieldname in fieldnames:
				value = getattr(row_doc, fieldname, None)
				if value is not None and len(str(value)) > _DATA_COLUMN_LEN:
					raise ValueError(f"{dt}.{fieldname} exceeds {_DATA_COLUMN_LEN} characters")
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
		return _err("sync_failed", message=_redact(exc))
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
		digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
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
	"""State update from a parsed ``message_template_*`` webhook change (see gateway_webhook)."""
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


def edit_quota(status: str, edit_log: Any, now: datetime | None = None) -> dict[str, Any]:
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
		"edits_30d": len(last_30d), "next_edit_at": None,
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
			editable_message=f"A template with status {status or 'UNKNOWN'} cannot be edited (only APPROVED, REJECTED or PAUSED).")
	return out


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


def _current_payload(row: dict[str, Any]) -> dict[str, Any]:
	"""Local row as a create-style payload (the base an edit is merged onto)."""
	payload: dict[str, Any] = {
		"template_name": row.get("actual_name") or row.get("template_name"),
		"category": row.get("category"),
		"language_code": row.get("language_code"),
		"body": row.get("template") or "",
		"sample_values": row.get("sample_values") or "",
		"footer": row.get("footer") or "",
		"buttons": _button_dicts(row["name"]),
	}
	if row.get("header_type"):
		payload["header_type"] = row["header_type"]
		if row["header_type"] == "TEXT":
			payload["header"] = row.get("header") or ""
		if row.get("sample"):
			payload["sample"] = row["sample"]
	return payload


def get_template(name: str) -> dict[str, Any]:
	"""Full detail of one template: components, review/quality state, edit allowance, manager link."""
	if not is_available():
		return _err("bridge_unavailable")
	if not frappe.has_permission("WhatsApp Templates", "read"):
		raise frappe.PermissionError("Not permitted to read WhatsApp Templates")
	if not name or not frappe.db.exists("WhatsApp Templates", name):
		return _err("not_found")
	row = frappe.db.get_value("WhatsApp Templates", name, _ROW_FIELDS, as_dict=True)
	state = _state_row(name, row.get("whatsapp_account")) or {}
	status = (state.get("status") or row.get("status") or "").upper()
	quota = edit_quota(status, state.get("edit_log"))
	view = {
		"header": (
			{"type": row["header_type"], "text": row.get("header") or "", "sample": row.get("sample") or ""}
			if row.get("header_type") else None
		),
		"body": {"text": row.get("template") or "", "sample_values": [s for s in (row.get("sample_values") or "").split(",") if s]},
		"footer": {"text": row["footer"]} if row.get("footer") else None,
		"buttons": _button_dicts(name),
	}
	business_id = ""
	if row.get("whatsapp_account"):
		business_id = frappe.db.get_value("WhatsApp Account", row["whatsapp_account"], "business_id") or ""
	category = row.get("category")
	correct = state.get("correct_category") or ""
	return {
		"success": True,
		"name": name,
		"template_id": row.get("id") or state.get("template_id") or "",
		"template_name": row.get("actual_name") or row.get("template_name"),
		"language_code": row.get("language_code"),
		"category": category,
		"previous_category": state.get("previous_category") or "",
		"correct_category": correct,
		"category_change_pending": bool(correct and correct != category),
		"status": status,
		"whatsapp_account": row.get("whatsapp_account"),
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


def edit_template(name: str, payload: dict[str, Any]) -> dict[str, Any]:
	"""Edit a template on Meta (``POST /{template-id}`` with the FULL components) and locally.

	Meta rules enforced here before any call: status must be APPROVED/REJECTED/PAUSED, an
	APPROVED template allows 1 edit/24h and 10/30 days, name and language are immutable.
	``payload`` keys (body, sample_values, header*, sample, footer, buttons, category,
	message_send_ttl_seconds) are merged onto the current definition. After the edit the
	template is PENDING re-review. Permission-checked.
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
	quota = edit_quota(status, state.get("edit_log"))
	if not quota["editable"]:
		return _err(quota["editable_reason"], message=quota["editable_message"], status=status,
			next_edit_at=quota["next_edit_at"], edits_left=quota["edits_left"])
	acct = resolve_account(row.get("whatsapp_account"))
	if not acct or acct.get("error"):
		return _err("no_account")

	merged = _current_payload(row)
	for key in ("body", "template", "sample_values", "header", "header_type", "sample", "footer", "buttons"):
		if key in payload:
			merged[key] = payload[key]
	if "template" in payload and "body" not in payload:
		merged.pop("body", None)
	if "header_type" in payload and not payload["header_type"]:
		for key in ("header_type", "header", "sample"):
			merged.pop(key, None)
	category = str(payload.get("category") or row.get("category") or "").upper()
	if category not in TEMPLATE_CATEGORIES:
		return _err("invalid_category", message="Category must be one of " + ", ".join(TEMPLATE_CATEGORIES))
	ttl = payload.get("message_send_ttl_seconds")
	if ttl is not None and (isinstance(ttl, bool) or not isinstance(ttl, int)):
		return _err("invalid_ttl", message="message_send_ttl_seconds must be an integer")

	media_unchanged = row.get("header_type") in wt.MEDIA_HEADER_TYPES and not any(
		k in payload for k in ("header_type", "header", "sample")
	)
	if media_unchanged:
		merged["sample"] = "https://existing.invalid/header"  # satisfied by the reused Meta header below
	spec, errors = wt.validate_template_spec(merged)
	if spec["header_type"] in wt.MEDIA_HEADER_TYPES and not media_unchanged:
		return _err(
			"media_header_edit_unsupported",
			message="Changing an image/document header needs a fresh upload; edit it in WhatsApp Manager.",
		)
	if errors:
		return wt.validation_error(errors)
	media_header = None
	if media_unchanged:
		for comp in _loads(state.get("components"), []) or []:
			if isinstance(comp, dict) and str(comp.get("type")).upper() == "HEADER":
				if (comp.get("example") or {}).get("header_handle"):
					media_header = comp
		if not media_header:
			return _err("media_header_edit_unsupported", message="The current media header cannot be re-sent; edit it in WhatsApp Manager.")
	components = wt.build_meta_components(spec, media_header)

	local_buttons = frappe.get_all(
		"WhatsApp Button", filters={"parent": name, "parenttype": "WhatsApp Templates"},
		fields=["button_type", "button_label", "website_url", "phone_number"], order_by="idx asc",
	)
	same_header_text = (spec["header_text"] or "") == ((row.get("header") or "") if row.get("header_type") == "TEXT" else "")
	if (
		category == str(row.get("category") or "").upper()
		and ttl is None
		and spec["body"] == (row.get("template") or "")
		and ",".join(spec["sample_values"]) == (row.get("sample_values") or "")
		and (spec["header_type"] or "") == (row.get("header_type") or "")
		and same_header_text
		and (spec["footer"] or "") == (row.get("footer") or "")
		and _button_sig(wt.button_rows(spec)) == _button_sig(local_buttons)
	):
		return _err("no_changes", message="Nothing changed; no edit was sent to Meta.")

	body: dict[str, Any] = {"components": components}
	if category != str(row.get("category") or "").upper():
		body["category"] = category
	if ttl is not None:
		body["message_send_ttl_seconds"] = ttl
	try:
		resp = _default_post(
			f"{acct['url']}/{acct['version']}/{row['id']}",
			json=body,
			headers={"Authorization": f"Bearer {acct['token']}", "Content-Type": "application/json"},
			timeout=_HTTP_TIMEOUT,
		)
	except Exception as exc:
		return _err("edit_failed", message=_redact(exc))
	code = getattr(resp, "status_code", 200)
	if isinstance(code, int) and code >= 400:
		return _err("edit_failed", message=graph_error_message(resp))

	changes: dict[str, Any] = {
		"template": spec["body"],
		"sample_values": ",".join(spec["sample_values"]),
		"header_type": spec["header_type"] or "",
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
	frappe.db.set_value("WhatsApp Templates", name, changes)
	_write_buttons(name, wt.button_rows(spec))

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
	return {
		"success": True,
		"name": name,
		"status": "PENDING",
		"edits_left": edit_quota("APPROVED", log)["edits_left"] if status == "APPROVED" else None,
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
	if doc.status not in _DRAFT_OPEN:
		return _err("already_processed", status=doc.status, message=f"This draft is {doc.status}.")
	payload = _loads(doc.payload, {}) or {}
	doc.reviewed_by = frappe.session.user
	doc.reviewed_at = frappe.utils.now_datetime()
	doc.review_note = note or ""
	account = doc.whatsapp_account
	if not is_available():
		result: dict[str, Any] = _err("bridge_unavailable")
	else:
		# the draft's own account only: no default-account guess at approval time
		try:
			result = create_template(account, payload) if account else _err("no_account")
		except frappe.PermissionError:
			raise
		except Exception as exc:
			result = _err("create_failed", message=_redact(exc))
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
	out = {
		"success": bool(result.get("success")),
		"name": doc.name,
		"status": doc.status,
		"submitted_template": doc.submitted_template or "",
		"submit_error": doc.submit_error or "",
	}
	if not out["success"]:
		out["error"] = result.get("error")
	return out


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


def download_media(
	account_name: str,
	media_id: str,
	max_bytes: int | None = None,
	allowed_mime_prefixes: tuple[str, ...] = DEFAULT_MIME_PREFIXES,
	http_get: Callable[..., Any] | None = None,
	credentials: dict[str, Any] | None = None,
	kind: str | None = None,
) -> dict[str, Any]:
	"""Fetch media by id at call time. Raises ValueError on caps/mime/failure.

	The size cap is ``max_bytes`` when given, else Meta's per-kind limit (``kind``
	when known, e.g. sticker, otherwise derived from the MIME type); declared and
	streamed sizes are both enforced.

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
	mime = str(meta.get("mime_type") or "").split(";")[0].strip().lower()
	if (
		not mime
		or mime.startswith(_BLOCKED_MIME_PREFIXES)
		or not any(mime.startswith(p) for p in allowed_mime_prefixes)
	):
		raise ValueError(f"mime_not_allowed: {mime or 'unknown'}")
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
	filename = re.sub(r"[^A-Za-z0-9._-]", "_", str(meta.get("filename") or media_id))[:100] or "media"
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
