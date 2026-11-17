# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""OTP delivery over a WhatsApp AUTHENTICATION template (HUFCRM-01a).

HUF only *delivers* the code. It never generates or verifies one (verification stays in the calling
app). The code lives only in this request's memory: it is sent synchronously (never queued), stripped
from every error / Meta echo before anything leaves this module, and the bridge mirror row is written
with redacted parameters. It is deliberately NOT an agent tool and is not seeded by ``app_seeding``.

Callers need the ``HUF OTP Sender`` role (or System Manager). Abuse limits (Redis): per phone and per
caller sliding windows. Idempotency: ``sha256(caller|gateway|phone|key)`` claims a Redis slot; a replay
returns the original message id and sends nothing. ``get_otp_status`` only answers for the caller that
sent the message.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

import frappe
from frappe import _

from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.whatsapp import management

OTP_SENDER_ROLE = "HUF OTP Sender"
_ALLOWED_ROLES = {OTP_SENDER_ROLE, "System Manager"}
_CODE_RE = re.compile(r"^[A-Za-z0-9]{4,15}$")  # copy-code button limit is 15 characters
PHONE_LIMIT, PHONE_WINDOW = 3, 600  # sends per phone per 10 minutes
CALLER_LIMIT, CALLER_WINDOW = 60, 60  # sends per caller per minute
IDEMPOTENCY_TTL = 24 * 3600
OWNER_TTL = 7 * 24 * 3600
_PENDING = "pending"


def _err(code: str, message: str, **extra: Any) -> dict[str, Any]:
	return {"success": False, "error": code, "message": message, **extra}


def _digest(*parts: Any) -> str:
	return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


def _key(kind: str, digest: str) -> str:
	return f"huf_otp:{frappe.local.site}:{kind}:{digest}"


def _scrub(value: Any, code: str) -> Any:
	"""Recursively remove every occurrence of ``code`` from strings (and dict keys) in ``value``."""
	if isinstance(value, str):
		return value.replace(code, "[redacted]") if code else value
	if isinstance(value, dict):
		return {_scrub(k, code): _scrub(v, code) for k, v in value.items()}
	if isinstance(value, (list, tuple)):
		return [_scrub(v, code) for v in value]
	return value


def _require_sender() -> str:
	user = frappe.session.user
	if user == "Guest" or not _ALLOWED_ROLES.intersection(frappe.get_roles(user) or []):
		raise frappe.PermissionError(_("HUF OTP Sender role required"))
	return user


def _hit(kind: str, digest: str, limit: int, window: int) -> bool:
	"""Count one hit in a fixed window; True when still within ``limit``."""
	cache = frappe.cache()
	key = _key(kind, digest)
	count = cache.incr(key)
	if count == 1:
		cache.expire(key, window)
	return int(count) <= limit


def _unhit(kind: str, digest: str) -> None:
	try:
		frappe.cache().decr(_key(kind, digest))
	except Exception:  # noqa: BLE001, S110 - best-effort counter rollback
		pass


def _resolve_template(account: str, template: str | None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
	"""``(row, None)`` for an approved AUTHENTICATION template, else ``(None, error)``."""
	filters: dict[str, Any] = {"whatsapp_account": account, "category": "AUTHENTICATION"}
	if template:
		name = bridge._template_docname(account, str(template).strip())
		if not frappe.db.exists("WhatsApp Templates", {"name": name, "whatsapp_account": account}):
			return None, _err("template_not_found", "Template not found for this gateway.")
		filters["name"] = name
	rows = frappe.get_all(
		"WhatsApp Templates", filters=filters,
		fields=["name", "status", "actual_name", "template_name", "language_code"], limit_page_length=50,
	)
	if not rows:
		return None, _err("template_not_found", "No AUTHENTICATION template exists for this gateway.")
	approved = [r for r in rows if str(r.get("status") or "").upper() == "APPROVED"]
	if not approved:
		return None, _err("template_not_approved", "The authentication template is not approved by Meta.")
	return approved[0], None


def _map_refusal(payload: dict[str, Any]) -> tuple[str, str]:
	code = str(payload.get("error") or "send_failed")
	if code == "opted_out":
		return "not_opted_in", "The recipient has not opted in to messages from this gateway."
	if code == "template_not_approved":
		return code, "The authentication template is not approved by Meta."
	if str(payload.get("graph_code") or "") in {"130429", "131056", "80007", "4", "17", "613"} or payload.get("kind") == "rate_limit":
		return "throughput", "WhatsApp throughput limit reached; retry later."
	if str(payload.get("graph_code") or "") in {"131047", "131026"}:
		return "window", "Message could not be delivered (outside the allowed window or unreachable recipient)."
	return code if code in {"recipient_not_allowlisted", "bsuid_recipient", "gateway_disconnected", "no_account", "validation_failed"} else "send_failed", "The OTP could not be sent."


@frappe.whitelist(methods=["POST"])
def send_otp(
	gateway: str | None = None,
	phone: str | None = None,
	code: str | None = None,
	template: str | None = None,
	idempotency_key: str | None = None,
	fallback: str | None = None,
	sms_gateway: str | None = None,
	fallback_text: str | None = None,
) -> dict[str, Any]:
	"""Send ``code`` to ``phone`` over WhatsApp using the gateway's approved authentication template.

	Returns ``{success, message_id, status}`` or ``{success: False, error, message}`` with error one of
	``invalid_*``, ``rate_limited``, ``not_opted_in``, ``template_not_found``, ``template_not_approved``,
	``throughput``, ``window``, ``in_progress``, ``send_failed``, ``invalid_fallback``. The code is never in the
	return value. Success carries ``channel`` (``whatsapp`` | ``sms``).

	SMS fallback (``fallback="sms"``; email is never allowed for OTP -> ``invalid_fallback``): requires
	``sms_gateway`` (a Gateway name) and ``fallback_text`` containing ``{code}``. It fires synchronously, only
	when the WhatsApp send is refused terminally at send time with ``not_opted_in`` or ``window`` (not opted in /
	undeliverable recipient); never for throughput, template, auth or other errors, and never from the status
	webhook (so a sent-but-undelivered OTP is not duplicated). The SMS goes through failover.run_chain, which
	checks SMS utility consent via channel_consent.has_consent. Result then has ``channel: "sms"`` and a
	``fallback_attempts`` audit (channel/status/reason only; no body, code scrubbed). No consent -> the original
	WhatsApp error is returned.
	"""
	user = _require_sender()
	code_str = "" if code is None else str(code)
	try:
		return _send(user, gateway, phone, code_str, template, idempotency_key, fallback, sms_gateway, fallback_text)
	except frappe.PermissionError:
		raise
	except Exception as exc:  # noqa: BLE001 - never let a traceback (which can hold the code in locals/args) reach logs
		_ = exc
		frappe.clear_last_message()
		return _err("send_failed", "The OTP could not be sent.")


def _check_fallback(code, fallback, sms_gateway, fallback_text) -> dict[str, Any] | None:
	if fallback in (None, ""):
		return None
	if str(fallback).lower() != "sms":
		return _err("invalid_fallback", "Only 'sms' is allowed as an OTP fallback (email is never allowed).")
	if not sms_gateway or not frappe.db.exists("Gateway", sms_gateway):
		return _err("invalid_fallback", "sms_gateway is required for the SMS fallback.")
	if not fallback_text or "{code}" not in str(fallback_text):
		return _err("invalid_fallback", "fallback_text containing {code} is required for the SMS fallback.")
	return None


def _sms_fallback(code, to, sms_gateway, fallback_text) -> dict[str, Any] | None:
	"""Run the shared failover chain for SMS only. Returns the success payload, or None if SMS did not go out."""
	from huf.ai.whatsapp.broadcast.failover import run_chain

	body = str(fallback_text).replace("{code}", code)
	attempts, delivered = run_chain(
		["sms"], phone=to, email=None, body=body, body_kind="otp", sms_gateway=sms_gateway,
	)
	if delivered != "sms":
		return None
	mid = next((str(a.get("message_id") or "") for a in attempts if a.get("channel") == "sms"), "")
	return {"success": True, "message_id": mid, "status": "sent", "channel": "sms", "fallback_attempts": _scrub(attempts, code)}


def _send(user, gateway, phone, code, template, idempotency_key, fallback=None, sms_gateway=None, fallback_text=None) -> dict[str, Any]:
	if not gateway or not frappe.db.exists("Gateway", gateway):
		return _err("invalid_gateway", "Gateway not found.")
	if not _CODE_RE.match(code):
		return _err("invalid_code", "Code must be 4-15 letters or digits.")
	bad_fb = _check_fallback(code, fallback, sms_gateway, fallback_text)
	if bad_fb:
		return bad_fb
	to = management._validate_recipient(phone)
	if isinstance(to, dict):
		return to | {"error": "invalid_phone"}
	if not bridge.is_available():
		return _err("bridge_unavailable", "WhatsApp is not available on this site.")
	account = management._resolve_account_name(management._gateway_whatsapp_account(gateway))
	if isinstance(account, dict):
		return _err("no_account", "The gateway has no WhatsApp account.")
	row, bad = _resolve_template(account, template)
	if bad:
		return bad

	caller = _digest(user)
	idem_slot = None
	if idempotency_key:
		idem_slot = _key("idem", _digest(user, gateway, to, idempotency_key))
		cache = frappe.cache()
		if cache.set(idem_slot, _PENDING, ex=IDEMPOTENCY_TTL, nx=True) is None:
			prior = cache.get(idem_slot)
			prior = prior.decode() if isinstance(prior, bytes) else prior
			if prior and prior != _PENDING:
				chan = "sms" if prior.startswith("sms:") else "whatsapp"
				return {"success": True, "message_id": prior.removeprefix("sms:"), "status": "sent", "channel": chan, "replayed": True}
			return _err("in_progress", "A send with this idempotency key is already in progress.")

	def release() -> None:
		if idem_slot:
			frappe.cache().delete(idem_slot)

	phone_digest = _digest(gateway, to)
	if not _hit("caller", caller, CALLER_LIMIT, CALLER_WINDOW):
		release()
		return _err("rate_limited", "Too many OTP requests from this caller.", scope="caller")
	if not _hit("phone", phone_digest, PHONE_LIMIT, PHONE_WINDOW):
		release()
		return _err("rate_limited", "Too many OTP requests for this number.", scope="phone")

	try:
		result = bridge.send_template(
			account, to, row.get("actual_name") or row.get("template_name") or row["name"],
			[code], None, trusted=True, language_code=row.get("language_code"),
			gateway_name=gateway, force_graph=True, redact_params=True,
		)
	except bridge.BridgeError as exc:
		error, message = _map_refusal(_scrub(exc.payload, code))
		if fallback and error in ("not_opted_in", "window"):
			sms = _sms_fallback(code, to, sms_gateway, fallback_text)
			if sms:
				if idem_slot:
					frappe.cache().set(idem_slot, "sms:" + sms["message_id"], ex=IDEMPOTENCY_TTL)
				return sms
		release()
		return _err(error, message)
	except Exception:  # noqa: BLE001 - never surface a traceback that could hold the code
		release()
		return _err("send_failed", "The OTP could not be sent.")

	message_id = str(result.get("message_id") or result.get("wamid") or "")
	if idem_slot:
		frappe.cache().set(idem_slot, message_id, ex=IDEMPOTENCY_TTL)
	frappe.cache().set(_key("owner", _digest(message_id)), caller, ex=OWNER_TTL)
	return {"success": True, "message_id": message_id, "status": result.get("message_status") or "sent", "channel": "whatsapp"}


@frappe.whitelist()
def get_otp_status(message_id: str | None = None) -> dict[str, Any]:
	"""Delivery status (``sent|delivered|read|failed``) of an OTP this caller sent, from the status webhook rows."""
	user = _require_sender()
	if not message_id:
		return _err("invalid_message_id", "message_id is required.")
	owner = frappe.cache().get(_key("owner", _digest(message_id)))
	owner = owner.decode() if isinstance(owner, bytes) else owner
	if not owner or owner != _digest(user):
		return _err("not_found", "Message not found.")
	row = frappe.db.get_value("WhatsApp Message", {"message_id": message_id}, ["status", "type"], as_dict=True)
	if not row:
		return _err("not_found", "Message not found.")
	status = str(row.get("status") or "").lower()
	mapped = {"success": "sent", "sent": "sent", "delivered": "delivered", "read": "read", "failed": "failed"}.get(status, status or "sent")
	return {"success": True, "message_id": message_id, "status": mapped}
