# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Cross-channel failover (HUFCRM-04b): when a WhatsApp send terminally fails, try SMS then email.

Single shared helper (the OTP SMS fallback reuses ``run_chain``). Rules:

* Trigger only from ``status.apply_status`` on a terminal ``failed`` with a retry-safe error code
  (``RETRY_SAFE_CODES``). Never on sent-but-not-delivered timeouts; 131050 (user stopped marketing) never fails over.
* Needs an explicit plain-text ``fallback_body`` (no template-to-text guessing) and ``fallback_channels``
  (ordered JSON list such as ["sms", "email"]); recipient-row values override the broadcast's.
* The recipient row is locked (FOR UPDATE); a non-empty ``fallback_attempts`` is the claim, so duplicate or
  out-of-order webhooks cannot fire two chains. First terminal outcome wins: a late WA delivered/read is
  audited but triggers nothing.
* ``has_consent`` is checked before each leg (denied -> leg skipped with an audit entry). Email is refused
  when ``fallback_body_kind == "otp"``.
"""

from __future__ import annotations

import json
from typing import Any, Callable

import frappe
from frappe.utils import now_datetime

RECIPIENT = "WhatsApp Broadcast Recipient"
BROADCAST = "WhatsApp Broadcast"
# Meta codes where the message was definitively not delivered and a resend elsewhere is safe.
RETRY_SAFE_CODES = frozenset({131026, 131030, 131021})
SUPPORTED = ("sms", "email")
_FIELDS = ("fallback_channels", "fallback_body", "fallback_body_kind", "fallback_sms_gateway", "fallback_email_gateway")


def parse_channels(raw: Any) -> list[str]:
	"""Ordered, de-duplicated list of supported channels; anything malformed yields []."""
	if isinstance(raw, str):
		try:
			raw = json.loads(raw) if raw.strip() else []
		except ValueError:
			return []
	if not isinstance(raw, (list, tuple)):
		return []
	out: list[str] = []
	for c in raw:
		c = str(c or "").strip().lower()
		if c in SUPPORTED and c not in out:
			out.append(c)
	return out


def _entry(channel: str, status: str, **extra: Any) -> dict[str, Any]:
	return {"channel": channel, "time": str(now_datetime()), "status": status, "cost": extra.pop("cost", None), **extra}


def _send_sms(gateway: str | None, to: str, body: str) -> dict[str, Any]:
	from huf.ai.gateway_adapters.sms import send_sms_message

	creds = _credentials(gateway) if gateway else {"mode": "frappe_sms"}
	return send_sms_message(creds, to, body)


def _send_email(gateway: str | None, to: str, body: str) -> dict[str, Any]:
	try:
		from huf.ai.gateway_adapters.email import EmailGatewayAdapter
		from huf.ai.gateway_adapters.types import GatewayReply

		adapter = EmailGatewayAdapter(_credentials(gateway) if gateway else {})
		delivery = adapter.send_reply(GatewayReply(conversation_id=to, text=body))
		return {"ok": True, "id": delivery.provider_message_id, "status": "sent", "error": None}
	except Exception as exc:  # noqa: BLE001
		return {"ok": False, "id": None, "status": "failed", "error": str(exc)}


def _credentials(gateway: str) -> dict[str, str]:
	from huf.ai.gateway_webhook import _gateway_credentials

	return _gateway_credentials(frappe.get_doc("Gateway", gateway))


def run_chain(
	channels: list[str],
	*,
	phone: str | None,
	email: str | None,
	body: str,
	body_kind: str = "",
	sms_gateway: str | None = None,
	email_gateway: str | None = None,
	senders: dict[str, Callable[..., dict[str, Any]]] | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
	"""Try each channel in order until one accepts. Returns (audit entries, delivered channel or None).

	Reusable by any caller that has a body and addresses (e.g. OTP SMS fallback). Never raises."""
	from huf.ai.channels.channel_consent import has_consent

	senders = senders or {}
	purpose = "utility" if str(body_kind or "").lower() in ("otp", "utility") else "marketing"
	attempts: list[dict[str, Any]] = []
	for channel in channels:
		if channel not in SUPPORTED:
			attempts.append(_entry(channel, "skipped", reason="unsupported_channel"))
			continue
		if channel == "email" and str(body_kind or "").lower() == "otp":
			attempts.append(_entry(channel, "refused", reason="otp_email_refused"))
			continue
		to = f"+{phone}" if channel == "sms" and phone and str(phone).isdigit() else (phone if channel == "sms" else email)
		if not to:
			attempts.append(_entry(channel, "skipped", reason="no_address"))
			continue
		try:
			ok, reason = has_consent(channel, to, purpose)
		except Exception:  # noqa: BLE001 - fail closed
			ok, reason = False, "consent_check_failed"
		if not ok:
			attempts.append(_entry(channel, "skipped", reason=reason))
			continue
		send = senders.get(channel) or (_send_sms if channel == "sms" else _send_email)
		gateway = sms_gateway if channel == "sms" else email_gateway
		try:
			res = send(gateway, to, body)
		except Exception as exc:  # noqa: BLE001
			res = {"ok": False, "status": "failed", "error": str(exc)}
		if res.get("ok"):
			attempts.append(_entry(channel, str(res.get("status") or "sent"), message_id=res.get("id"), cost=res.get("cost")))
			return attempts, channel
		attempts.append(_entry(channel, "failed", error=str(res.get("error") or "")[:300]))
	return attempts, None


def _load_attempts(raw: Any) -> list[dict[str, Any]]:
	try:
		val = json.loads(raw) if isinstance(raw, str) and raw.strip() else raw
	except ValueError:
		return []
	return [a for a in val if isinstance(a, dict)] if isinstance(val, list) else []


def _config(row: dict[str, Any]) -> dict[str, Any]:
	bc = frappe.db.get_value(BROADCAST, row["broadcast"], list(_FIELDS), as_dict=True) or {}
	return {k: (row.get(k) or bc.get(k) or "") for k in _FIELDS}


def maybe_failover(recipient_name: str, error_code: int | None, senders: dict | None = None) -> bool:
	"""Called by status.apply_status right after a row became ``failed``. True if a chain ran. Never raises."""
	try:
		if int(error_code or 0) not in RETRY_SAFE_CODES:
			return False
		cols = ["name", "broadcast", "recipient", "status", "channel_delivered", "fallback_attempts", "fallback_email", *_FIELDS]
		row = frappe.db.get_value(RECIPIENT, recipient_name, cols, as_dict=True, for_update=True)
		if not row or row["status"] != "failed" or row.get("channel_delivered") or _load_attempts(row.get("fallback_attempts")):
			return False  # first terminal outcome wins; claim already taken
		cfg = _config(row)
		channels = parse_channels(cfg["fallback_channels"])
		body = str(cfg["fallback_body"] or "").strip()
		if not channels or not body:
			return False
		attempts, delivered = run_chain(
			channels,
			phone=row["recipient"],
			email=row.get("fallback_email"),
			body=body,
			body_kind=cfg["fallback_body_kind"],
			sms_gateway=cfg["fallback_sms_gateway"] or None,
			email_gateway=cfg["fallback_email_gateway"] or None,
			senders=senders,
		)
		values: dict[str, Any] = {"fallback_attempts": json.dumps(attempts)}
		if delivered:
			values["channel_delivered"] = delivered
		frappe.db.set_value(RECIPIENT, recipient_name, values, update_modified=False)
		return True
	except Exception:
		frappe.log_error(title="WhatsApp broadcast failover failed", message=frappe.get_traceback())
		return False


def note_wa_delivered(recipient_name: str, status: str) -> None:
	"""A WA delivered/read was applied. Record channel_delivered=whatsapp if nothing delivered yet; if a fallback
	already ran, only audit the late WhatsApp delivery (nothing is triggered). Never raises."""
	try:
		row = frappe.db.get_value(RECIPIENT, recipient_name, ["channel_delivered", "fallback_attempts"], as_dict=True, for_update=True)
		if not row:
			return
		values: dict[str, Any] = {}
		attempts = _load_attempts(row.get("fallback_attempts"))
		if attempts:
			attempts.append(_entry("whatsapp", f"{status}_late"))
			values["fallback_attempts"] = json.dumps(attempts)
		if not row.get("channel_delivered"):
			values["channel_delivered"] = "whatsapp"
		if values:
			frappe.db.set_value(RECIPIENT, recipient_name, values, update_modified=False)
	except Exception:
		frappe.log_error(title="WhatsApp broadcast failover audit failed", message=frappe.get_traceback())
