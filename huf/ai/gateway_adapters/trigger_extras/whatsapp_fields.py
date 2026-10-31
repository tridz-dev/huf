"""WhatsApp fields a flow trigger sees under ``input.*`` (names equal the registry ``payload_fields``).

Read from the signed inbound message stored on the Gateway Event. The text keeps the rendered form
(``whatsapp_inbound.render_message_text``); these add the structured data. Pure functions over the stored payload.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from huf.ai.gateway_adapters import whatsapp_inbound as inbound

_REFERRAL_KEYS = ("source_id", "source_url", "source_type", "headline", "body", "ctwa_clid")


def _dict(value) -> dict:
	return value if isinstance(value, dict) else {}


def load_raw(event) -> dict:
	raw = getattr(event, "raw_payload", None)
	if raw is None and hasattr(event, "get"):
		raw = event.get("raw_payload")
	if isinstance(raw, (str, bytes)):
		try:
			raw = json.loads(raw)
		except ValueError:
			return {}
	return raw if isinstance(raw, dict) else {}


def _number(value):
	try:
		return float(value)
	except (TypeError, ValueError):
		return None


def location_of(message: dict) -> dict | None:
	loc = _dict(message.get("location"))
	if not loc:
		return None
	return {"lat": _number(loc.get("latitude")), "lng": _number(loc.get("longitude")), "name": loc.get("name") or "", "address": loc.get("address") or ""}


def contacts_of(message: dict) -> list[dict]:
	cards = []
	for card in (message.get("contacts") or [])[: inbound.MAX_CONTACTS]:
		if not isinstance(card, dict):
			continue
		phones = [str(_dict(p).get("phone") or _dict(p).get("wa_id")) for p in (card.get("phones") or []) if isinstance(p, dict) and (p.get("phone") or p.get("wa_id"))]
		cards.append({"name": _dict(card.get("name")).get("formatted_name") or "", "phones": phones[: inbound.MAX_PHONES_PER_CONTACT]})
	return cards


def order_of(message: dict) -> dict | None:
	order = _dict(message.get("order"))
	if not order:
		return None
	items, total, currency = [], 0.0, ""
	for item in (order.get("product_items") or [])[: inbound.MAX_ORDER_ITEMS]:
		if not isinstance(item, dict):
			continue
		qty, price = _number(item.get("quantity")) or 0, _number(item.get("item_price"))
		currency = currency or str(item.get("currency") or "")
		total += (price or 0) * qty
		items.append({"product_id": item.get("product_retailer_id") or "", "quantity": qty, "price": price, "currency": item.get("currency") or ""})
	return {"items": items, "total": round(total, 2), "currency": currency, "note": order.get("text") or ""}


def message_extras(raw: dict, sender: str) -> dict[str, Any]:
	"""The structured fields of one inbound message; empty values are left out (booleans always present)."""
	message = _dict(raw.get("message"))
	interactive = _dict(message.get("interactive"))
	reply = _dict(interactive.get("button_reply")) or _dict(interactive.get("list_reply"))
	button = _dict(message.get("button"))
	referral = _dict(message.get("referral"))
	text = str(message.get("text", {}).get("body") if isinstance(message.get("text"), dict) else "")
	context = _dict(message.get("context"))
	values = {
		"wa_id": sender,
		"button_id": reply.get("id") or "",
		"button_title": reply.get("title") or button.get("text") or "",
		"button_payload": inbound.extract_button_payload(message),
		"referral": {k: referral.get(k) or "" for k in _REFERRAL_KEYS} if referral else None,
		"referral_tag": inbound.extract_referral_tag(message, text),
		"forwarded": bool(context.get("forwarded") or context.get("frequently_forwarded")),
		"contact_name": str(raw.get("contact_name") or "").strip(),
		"location": location_of(message),
		"contacts": contacts_of(message),
		"order": order_of(message),
		"kind": str(raw.get("kind") or "") or "message",
		"is_room": False,
	}
	if values["contact_name"]:
		values["display_name"] = values["contact_name"]
	return {k: v for k, v in values.items() if v not in ("", None, [])}


def hours_since_previous(gateway_name: str, sender: str, received_at, db_get_all=None) -> float | None:
	"""Hours between this message and the same person's previous one on this channel (None for a first message)."""
	if not sender or not received_at:
		return None
	import frappe

	get_all = db_get_all or frappe.get_all
	rows = get_all(
		"Gateway Event",
		filters={"gateway": gateway_name, "sender_id": sender, "verified_sender": 1, "received_at": ["<", received_at]},
		fields=["received_at"],
		order_by="received_at desc",
		limit_page_length=1,
	)
	if not rows or not rows[0].get("received_at"):
		return None
	now = received_at if isinstance(received_at, datetime) else frappe.utils.get_datetime(received_at)
	return round(max((now - frappe.utils.get_datetime(rows[0]["received_at"])).total_seconds(), 0) / 3600, 1)
