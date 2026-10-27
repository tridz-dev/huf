# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WhatsApp account-level webhooks: `account_update` connection state and `user_preferences` consent.

`account_update` carries no phone number metadata; it is applies only to the RECEIVING gateway, and only when ``entry[].id`` (the WABA id) equals that
gateway's own WABA (linked WhatsApp Account ``business_id`` or ``Gateway.whatsapp_business_account_id``); it sets
``Gateway.connection_state``: Disconnected (sends refused), Degraded (sends allowed, health
warns) or Connected. No Gateway Event is created; a short comment on the Gateway is the audit.

`user_preferences` (marketing stop/resume) appends a ``Gateway Consent`` row per sender id;
``is_marketing_allowed`` is what the template policy calls before any marketing send.
UNVERIFIED payload shape (Meta docs not re-fetched): ``value.user_preferences[]`` items with
``wa_id`` and/or ``user_id``, ``category`` = ``marketing_messages``, ``value`` = ``stop``|``resume``,
optional ``detail`` and ``timestamp``.
"""

from __future__ import annotations

from typing import Any

import time

import frappe

CONNECTED, DEGRADED, DISCONNECTED = "Connected", "Degraded", "Disconnected"
MARKETING = "marketing_messages"

_DISCONNECT_EVENTS = {
	"PARTNER_REMOVED": "The WhatsApp account was disconnected from Huf.",
	"ACCOUNT_OFFBOARDED": "The WhatsApp account was offboarded from Huf.",
	"ACCOUNT_DELETED": "The WhatsApp Business Account was deleted.",
}
_DEGRADE_EVENTS = {
	"ACCOUNT_RESTRICTION": "Meta restricted this WhatsApp account. Sending may fail until the restriction ends.",
	"ACCOUNT_VIOLATION": "Meta flagged a policy violation on this WhatsApp account.",
}


def classify_account_update(value: Any) -> dict[str, str] | None:
	"""Pure: an ``account_update`` change value -> ``{state, reason, event}``; None when it changes nothing."""
	if not isinstance(value, dict):
		return None
	event = str(value.get("event") or "").upper()
	if event in _DISCONNECT_EVENTS:
		reason = _DISCONNECT_EVENTS[event]
		info = value.get("disconnection_info")
		if isinstance(info, dict) and info.get("reason"):
			reason = f"{reason} Reason: {str(info['reason'])[:80]}."
		return {"state": DISCONNECTED, "reason": reason, "event": event}
	if event in _DEGRADE_EVENTS:
		return {"state": DEGRADED, "reason": _DEGRADE_EVENTS[event], "event": event}
	if event == "ACCOUNT_RECONNECTED":
		return {"state": CONNECTED, "reason": "", "event": event}
	if event == "DISABLED_UPDATE":
		info = value.get("ban_info")
		ban = str((info or {}).get("waba_ban_state") or "").upper() if isinstance(info, dict) else ""
		if ban == "DISABLE":
			return {"state": DISCONNECTED, "reason": "Meta disabled this WhatsApp Business Account.", "event": event}
		if ban == "SCHEDULE_FOR_DISABLE":
			return {"state": DEGRADED, "reason": "Meta scheduled this WhatsApp account to be disabled.", "event": event}
		if ban == "REINSTATE":
			return {"state": CONNECTED, "reason": "", "event": event}
	return None


def is_relevant(field: str, value: Any) -> bool:
	"""Whether the adapter should hand this change to the account handler (else it is just ignored)."""
	if field == "account_update":
		return classify_account_update(value) is not None
	return field == "user_preferences" and isinstance(value, dict)


# --- account_update -------------------------------------------------------------------


def _gateway_identity(gateway: str) -> dict[str, str]:
	"""The receiving Gateway's own phone number id and WABA id ('' when unknown).

	WABA: the linked WhatsApp Account's ``business_id``; direct-mode gateways (no account) use
	``Gateway.whatsapp_business_account_id``.
	"""
	from huf.ai.gateway_adapters import whatsapp_bridge as bridge

	row = frappe.db.get_value(
		"Gateway", gateway, ["phone_number_id", "whatsapp_account", "whatsapp_business_account_id"], as_dict=True
	) or {}
	account = str(row.get("whatsapp_account") or "").strip()
	waba = bridge.account_business_id(account) if account else ""
	if not waba:
		waba = str(row.get("whatsapp_business_account_id") or "").strip()
	return {"phone_number_id": str(row.get("phone_number_id") or "").strip(), "waba_id": waba}


def _set_state(gateway: str, state: str, reason: str) -> None:
	frappe.db.set_value("Gateway", gateway, {"connection_state": state, "connection_reason": reason[:500]}, update_modified=False)


def _audit(gateway: str, text: str) -> None:
	try:
		frappe.get_doc("Gateway", gateway).add_comment("Info", text)
	except Exception:
		pass


def apply_account_event(event: dict, gateway: str) -> list[str]:
	"""Apply one ``account_update``/``user_preferences`` change to the RECEIVING gateway only.

	Fail closed: account_update needs the payload WABA to equal the gateway's own WABA (and the
	phone id, when the payload names one, to equal its number); user_preferences needs the payload
	phone id to equal the gateway's number and, when the gateway's WABA is known, entry id to equal it. Anything else is dropped.
	"""
	field = event.get("field")
	waba_id = str(event.get("waba_id") or "").strip()
	phone_id = str(event.get("phone_id") or "").strip()
	value = {k: v for k, v in event.items() if k not in ("field", "waba_id", "phone_id")}
	if not gateway or field not in ("account_update", "user_preferences"):
		return []
	own = _gateway_identity(gateway)
	if field == "account_update":
		verdict = classify_account_update(value)
		if not verdict or not waba_id or waba_id != own.get("waba_id"):
			return []
		if phone_id and phone_id != own.get("phone_number_id"):
			return []
		_set_state(gateway, verdict["state"], verdict["reason"])
		_audit(gateway, f"WhatsApp account event {verdict['event']}: connection is now {verdict['state']}.")
		return [gateway]
	if not phone_id or phone_id != own.get("phone_number_id"):
		return []
	if own.get("waba_id") and waba_id != own["waba_id"]:
		return []
	record_user_preferences(gateway, value.get("user_preferences"))
	return [gateway]


def apply_account_events(events, gateway: str) -> int:
	"""Webhook entry: never raises (a failure here must not turn into a Meta retry storm)."""
	applied = 0
	for event in list(events or [])[:50]:
		try:
			applied += 1 if apply_account_event(event, gateway) else 0
		except Exception:
			frappe.log_error(frappe.get_traceback(), "WhatsApp account event failed")
	return applied


def _gateways_for_phone_id(phone_id: str) -> list[str]:
	if not phone_id:
		return []
	return list(frappe.get_all("Gateway", filters={"provider": "WhatsApp", "phone_number_id": phone_id}, pluck="name") or [])


def _state_for_phone_id(phone_id: str) -> tuple[str | None, str]:
	rows = frappe.get_all(
		"Gateway",
		filters={"provider": "WhatsApp", "phone_number_id": phone_id},
		fields=["connection_state", "connection_reason"],
		limit_page_length=5,
	)
	for row in rows or []:  # any enabled gateway on this number being Disconnected refuses the send
		if row.get("connection_state") == DISCONNECTED:
			return DISCONNECTED, row.get("connection_reason") or ""
	return (rows[0].get("connection_state") if rows else None), ""


def send_refusal(phone_id: Any) -> dict[str, Any] | None:
	"""Structured refusal for any outbound send on a Disconnected number, else None. Never raises."""
	try:
		phone = str(phone_id or "").strip()
		if not phone:
			return None
		state, reason = _state_for_phone_id(phone)
		if state != DISCONNECTED:
			return None
		return {
			"success": False,
			"error": "gateway_disconnected",
			"message": reason or "This WhatsApp account is disconnected; reconnect it before sending.",
		}
	except Exception:
		return None


def connection(gateway: dict[str, Any]) -> tuple[str, str]:
	state = str(gateway.get("connection_state") or CONNECTED)
	return state, str(gateway.get("connection_reason") or "")


# --- user_preferences -----------------------------------------------------------------


def _norm_sender(sender: Any) -> str:
	raw = str(sender or "").strip()
	digits = "".join(ch for ch in raw if ch.isdigit())
	if raw.lstrip("+").replace(" ", "").replace("-", "").isdigit():
		return digits
	return raw  # BSUID / user id: keep as given


def _meta_ts(value: Any) -> int | None:
	try:
		ts = int(float(value))
	except (TypeError, ValueError):
		return None
	return ts if ts > 0 else None


def _insert_consent(gateway: str, sender: str, category: str, value: str, detail: str = "", timestamp: Any = None) -> bool:
	"""Insert one consent row; False when Meta's (gateway, sender, category, value, timestamp) was already stored."""
	meta_ts = _meta_ts(timestamp)
	if meta_ts is not None and frappe.db.exists(
		"Gateway Consent",
		{"gateway": gateway, "sender_id": sender, "category": category, "value": value, "meta_timestamp": meta_ts},
	):
		return False
	frappe.get_doc(
		{
			"doctype": "Gateway Consent",
			"gateway": gateway,
			"sender_id": sender,
			"category": category,
			"value": value,
			"detail": (detail or "")[:500],
			"changed_at": frappe.utils.now_datetime(),
			# Meta's event time (UTC epoch) orders rows; a missing one falls back to receipt time as a UTC epoch
			# (now_datetime() is naive site-tz, so its .timestamp() would be skewed by the site offset)
			"meta_timestamp": meta_ts or int(time.time()),
		}
	).insert(ignore_permissions=True)
	return True


def _skip_broadcast_rows(gateway: str, sender: str) -> None:
	"""A marketing stop skips that contact's pending broadcast rows. Never raises."""
	try:
		from huf.ai.whatsapp import broadcast_status

		broadcast_status.apply_user_stop(gateway, sender)
	except Exception:
		frappe.log_error(title="WhatsApp broadcast user-stop failed", message=frappe.get_traceback())


def record_user_preferences(gateway: str, items: Any) -> int:
	"""Append a consent row per identifier (wa_id and user_id) of each marketing stop/resume item; returns rows added."""
	count = 0
	for item in items if isinstance(items, list) else []:
		if not isinstance(item, dict) or item.get("category") != MARKETING or item.get("value") not in ("stop", "resume"):
			continue
		for key in ("wa_id", "user_id"):
			sender = _norm_sender(item.get(key))
			if sender:
				if _insert_consent(gateway, sender, MARKETING, item["value"], str(item.get("detail") or ""), item.get("timestamp")):
					count += 1
				if item["value"] == "stop":
					_skip_broadcast_rows(gateway, sender)
	return count


def _latest_consent(gateway: str, sender: str, category: str) -> str | None:
	rows = frappe.get_all(
		"Gateway Consent",
		filters={"gateway": gateway, "sender_id": sender, "category": category},
		fields=["value"],
		order_by="meta_timestamp desc, creation desc, name desc",
		limit_page_length=1,
	)
	return rows[0]["value"] if rows else None


def is_marketing_allowed(gateway: str, sender: Any) -> bool:
	"""False when the sender's latest marketing preference is ``stop``. For the template policy (WP-6)."""
	key = _norm_sender(sender)
	if not key:
		return True
	return _latest_consent(gateway, key, MARKETING) != "stop"
