# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Pure rendering of inbound WhatsApp Cloud API messages into agent-readable text.

No Frappe imports: used by the adapter (``whatsapp._message_event``) and by the
frappe_whatsapp mirror (``whatsapp_bridge.record_incoming``) so both agree.
"""

from __future__ import annotations

import json
import re
from typing import Any

MAX_CONTACTS = 5
MAX_PHONES_PER_CONTACT = 3
MAX_ORDER_ITEMS = 10
MAX_FORM_BYTES = 2048
_NAME_CAP = 100
_PHONE_CAP = 32
_PLACE_CAP = 200
_ID_CAP = 128
_TITLE_CAP = 200

MEDIA_TYPES = ("image", "document", "audio", "video", "sticker")
# WhatsApp Message.content_type options (frappe_whatsapp) for each inbound type.
CONTENT_TYPES = {
	"text": "text", "document": "document", "image": "image", "video": "video", "audio": "audio",
	"sticker": "image", "reaction": "reaction", "location": "location", "contacts": "contact",
	"button": "button", "interactive": "interactive", "order": "order",
}


# Conversational types the agent may see. Anything else is record-only (see ``message_kind``).
CONVERSATIONAL_TYPES = frozenset(
	{"text", "interactive", "button", "location", "contacts", "order", *MEDIA_TYPES}
)
# kinds that are logged on a Gateway Event but never reach an agent or LLM
RECORD_ONLY_KINDS = frozenset({"edit", "revoke", "system", "unknown"})


def message_kind(msg_type: Any) -> str:
	"""Gateway kind for an inbound ``type``: message | reaction | unsupported | edit | revoke | system | unknown."""
	mtype = str(msg_type or "text")
	if mtype in CONVERSATIONAL_TYPES:
		return "message"
	if mtype in ("reaction", "unsupported", "edit", "revoke", "system"):
		return mtype
	return "unknown"


def cap(value: Any, limit: int) -> str:
	text = " ".join(str(value if value is not None else "").split())
	return text if len(text) <= limit else text[: max(limit - 1, 0)] + "…"


def _dict(value: Any) -> dict:
	return value if isinstance(value, dict) else {}


def _list(value: Any) -> list:
	return value if isinstance(value, list) else []


def cap_bytes(text: str, limit: int) -> str:
	raw = text.encode("utf-8")
	if len(raw) <= limit:
		return text
	return raw[: limit - 3].decode("utf-8", "ignore") + "..."


def render_location(loc: Any) -> str:
	loc = _dict(loc)
	parts = []
	lat, lng = loc.get("latitude"), loc.get("longitude")
	if lat is not None and lng is not None:
		parts.append(f"{cap(lat, 32)},{cap(lng, 32)}")
	elif lat is not None or lng is not None:
		parts.append(cap(lat if lat is not None else lng, 32))
	name = cap(loc.get("name"), _PLACE_CAP)
	if name:
		parts.append(f'"{name}"')
	address = cap(loc.get("address"), _PLACE_CAP)
	if address:
		parts.append(address)
	return f"[Location: {' '.join(parts)}]" if parts else "[Location]"


def render_contacts(contacts: Any) -> str:
	cards = [c for c in _list(contacts) if isinstance(c, dict)]
	lines = []
	for card in cards[:MAX_CONTACTS]:
		name = cap(_dict(card.get("name")).get("formatted_name"), _NAME_CAP)
		phones = []
		for ph in _list(card.get("phones"))[:MAX_PHONES_PER_CONTACT]:
			if isinstance(ph, dict):
				num = cap(ph.get("phone") or ph.get("wa_id"), _PHONE_CAP)
				if num:
					phones.append(num)
		body = " ".join(p for p in [name, " ".join(phones)] if p)
		lines.append(f"[Contact: {body}]" if body else "[Contact]")
	if len(cards) > MAX_CONTACTS:
		lines.append(f"[+{len(cards) - MAX_CONTACTS} more contacts]")
	return "\n".join(lines) or "[Contact]"


def render_order(order: Any) -> str:
	order = _dict(order)
	items = [i for i in _list(order.get("product_items")) if isinstance(i, dict)]
	head = f"{len(items)} item{'' if len(items) == 1 else 's'}"
	catalog = cap(order.get("catalog_id"), _ID_CAP)
	if catalog:
		head += f", catalog {catalog}"
	lines = []
	for item in items[:MAX_ORDER_ITEMS]:
		line = f"{cap(item.get('product_retailer_id'), _ID_CAP) or '?'} x{cap(item.get('quantity'), 12) or '?'}"
		if item.get("item_price") is not None and item.get("currency"):
			line += f" @ {cap(item.get('item_price'), 16)} {cap(item.get('currency'), 8)}"
		lines.append(line)
	if len(items) > MAX_ORDER_ITEMS:
		lines.append(f"(+{len(items) - MAX_ORDER_ITEMS} more)")
	text = f"[Order: {head}]"
	if lines:
		text += " " + ", ".join(lines)
	note = cap(order.get("text"), 500)
	return f"{text} {note}" if note else text


def render_form_response(nfm: Any) -> str:
	nfm = _dict(nfm)
	name = cap(nfm.get("name"), _NAME_CAP) or "flow"
	raw = nfm.get("response_json")
	compact = ""
	if isinstance(raw, (dict, list)):
		compact = json.dumps(raw, ensure_ascii=False, separators=(",", ":"))
	elif isinstance(raw, str) and raw.strip():
		try:
			compact = json.dumps(json.loads(raw), ensure_ascii=False, separators=(",", ":"))
		except ValueError:
			compact = raw.strip()
	head = f"[Form response: {name}]"
	return f"{head} {cap_bytes(compact, MAX_FORM_BYTES)}" if compact else head


def render_interactive(interactive: Any) -> str:
	interactive = _dict(interactive)
	for key in ("button_reply", "list_reply"):
		if key in interactive:
			reply = _dict(interactive[key])
			return str(reply.get("title") or reply.get("id") or "")
	if "nfm_reply" in interactive or interactive.get("type") == "nfm_reply":
		return render_form_response(interactive.get("nfm_reply"))
	if "product" in interactive:
		product = _dict(interactive["product"])
		label = " ".join(
			p for p in [cap(product.get("title"), _TITLE_CAP), f"({cap(product.get('retailer_id'), _ID_CAP)})" if product.get("retailer_id") else ""] if p
		)
		return f"[Product: {label}]" if label else "[Product]"
	return "[interactive message]"


_REF_RE = re.compile(r"(?<![A-Za-z0-9_-])ref:([A-Za-z0-9_-]{1,64})", re.IGNORECASE)


def extract_referral_tag(message: dict, text: str) -> str:
	"""Routing tag for an inbound message, or "".

	Convention: the Click-to-WhatsApp ad id (``referral.source_id``) wins; otherwise the
	first ``ref:<tag>`` token in the text (case-insensitive, tag chars ``[A-Za-z0-9_-]``,
	1-64 long). ``#tag`` is not a tag. The token is left in the text.
	"""
	referral = _dict(_dict(message).get("referral"))
	source_id = str(referral.get("source_id") or "").strip()
	if source_id:
		return source_id
	match = _REF_RE.search(text or "")
	return match.group(1) if match else ""


def extract_button_payload(msg: Any) -> str:
	"""Structured payload of a template quick-reply button or an interactive button/list reply."""
	msg = _dict(msg)
	if msg.get("type") == "button":
		return str(_dict(msg.get("button")).get("payload") or "")
	if msg.get("type") == "interactive":
		interactive = _dict(msg.get("interactive"))
		for key in ("button_reply", "list_reply"):
			if key in interactive:
				return str(_dict(interactive[key]).get("id") or "")
	return ""


def parse_button_payload(raw: str) -> dict | None:
	"""Parse ``sol:<solution>|<free>`` into ``{"solution", "free"}``; None for any other format.

	Only the first ``|`` splits; ``free`` may be empty or contain further ``|``.
	"""
	if not isinstance(raw, str) or not raw.startswith("sol:"):
		return None
	solution, _, free = raw[4:].partition("|")
	solution = solution.strip()
	if not solution:
		return None
	return {"solution": solution, "free": free}


def render_system(system: Any) -> str:
	body = cap(_dict(system).get("body"), 300)
	return f"[system message] {body}" if body else "[system message]"


def render_unsupported(msg: dict) -> str:
	utype = cap(_dict(msg.get("unsupported")).get("type"), 40)
	errors = _list(msg.get("errors"))
	first = _dict(errors[0]) if errors else {}
	title = cap(first.get("title") or first.get("message"), 200)
	head = f"[unsupported message: {utype}]" if utype else "[unsupported message]"
	return f"{head} {title}" if title else head


def render_reaction(msg: dict) -> tuple[str, str, str]:
	"""Return (text, emoji, target message id). A removed reaction has no emoji."""
	reaction = _dict(msg.get("reaction"))
	emoji = cap(reaction.get("emoji"), 16)
	target = cap(reaction.get("message_id"), _ID_CAP)
	if emoji:
		return f"[Reaction: {emoji} to {target}]" if target else f"[Reaction: {emoji}]", emoji, target
	return (f"[Reaction removed from {target}]" if target else "[Reaction removed]"), "", target


def render_message_text(msg: Any) -> str:
	"""Agent-readable text for any inbound message dict ("" when nothing to say)."""
	msg = _dict(msg)
	mtype = msg.get("type") or "text"
	if mtype == "text":
		body = msg.get("text")
		return (_dict(body).get("body") if isinstance(body, dict) else body) or ""
	if mtype == "interactive":
		return render_interactive(msg.get("interactive"))
	if mtype == "button":
		button = _dict(msg.get("button"))
		return button.get("text") or button.get("payload") or ""
	if mtype == "location":
		return render_location(msg.get("location"))
	if mtype == "contacts":
		return render_contacts(msg.get("contacts"))
	if mtype == "order":
		return render_order(msg.get("order"))
	if mtype == "reaction":
		return render_reaction(msg)[0]
	if mtype == "system":
		return render_system(msg.get("system"))
	if mtype == "unsupported":
		return render_unsupported(msg)
	if mtype in MEDIA_TYPES:
		return _dict(msg.get(mtype)).get("caption") or f"[{mtype} message]"
	return f"[{cap(mtype, 40)} message]"
