"""Run-time filters of the gateway trigger nodes (``trigger.gateway|whatsapp|telegram``).

Routes decide which Flow gets a message; this module only narrows it. ``matches`` implements every param in the
registry against the flat ``input.*`` payload. A missing or empty param is no filter; an unknown key is ignored (publish
already rejects it). Pure Python apart from two lazy frappe calls (first message, rate counter).
"""

from __future__ import annotations

import re

GATEWAY_NODE_TYPES = ("trigger.gateway", "trigger.whatsapp", "trigger.telegram")
DEFAULT_RATE_CAP = 30
RATE_WINDOW_SECONDS = 3600
#: Event kinds that may start a run; reactions, statuses and joins never do.
STARTING_KINDS = ("message", "callback")

REASON_NO_CHANNEL = "no channel chosen"
REASON_OTHER_CHANNEL = "another channel"
REASON_RATE_LIMIT = "rate limit"


def param_map(config) -> dict:
	"""``{key: value}`` from the stored ``params`` array (last one wins)."""
	out = {}
	items = config.get("params") if isinstance(config, dict) else None
	for item in items if isinstance(items, list) else []:
		if isinstance(item, dict) and isinstance(item.get("key"), str):
			out[item["key"]] = item.get("value")
	return out


def _list(value) -> list[str]:
	if value is None or value == "":
		return []
	items = value if isinstance(value, (list, tuple)) else [value]
	return [str(v).strip() for v in items if str(v).strip()]


def _digits(value) -> str:
	return re.sub(r"\D", "", str(value or ""))


def _text(payload: dict) -> str:
	return str(payload.get("text") or payload.get("message") or "")


def _gateway_name(gateway) -> str:
	return str(getattr(gateway, "name", gateway) or "")


def _provider_of(gateway, payload: dict) -> str:
	return str(getattr(gateway, "provider", None) or payload.get("provider") or "").lower()


def _is_sender(allowed: list[str], payload: dict) -> bool:
	ids = {str(payload.get(k) or "").strip().lower().lstrip("@") for k in ("sender_id", "wa_id", "telegram_user_id", "username")}
	ids.discard("")
	nums = {_digits(i) for i in ids if _digits(i)}
	for entry in allowed:
		low = entry.lower().lstrip("@+")
		if low in ids or (_digits(entry) and _digits(entry) in nums and _digits(entry) == _digits(low)):
			return True
	return False


def _has_word(text: str, word: str) -> bool:
	return bool(re.search(r"(?<!\w)" + re.escape(word.lower()) + r"(?!\w)", text.lower()))


def _command(payload: dict) -> str:
	raw = str(payload.get("command") or "")
	if not raw:
		text = _text(payload).strip()
		raw = text.split()[0] if text.startswith("/") and text.split() else ""
	return raw.lstrip("/").split("@", 1)[0].lower()


def _is_first_message(payload: dict, gateway) -> bool:
	import frappe

	sender = str(payload.get("sender_id") or "")
	current = str(payload.get("gateway_event") or "")
	if not sender or not current:
		return True
	creation = frappe.db.get_value("Gateway Event", current, "creation")
	filters = {"gateway": _gateway_name(gateway), "sender_id": sender, "name": ["!=", current]}
	if creation:
		filters["creation"] = ["<", creation]
	return not frappe.db.exists("Gateway Event", filters)


def matches(node_config, payload: dict, gateway, node_type: str = "trigger.gateway", flow_id: str | None = None):
	"""``(True, "")`` when this trigger should start a run for ``payload``, else ``(False, reason)``.

	``gateway`` is the Gateway doc or its name. A dedicated node (``trigger.whatsapp`` / ``trigger.telegram``) also needs
	the message's provider to be its own. With ``flow_id`` the per-sender hourly cap is counted last.
	"""
	from huf.ai.flow.gateways.registry import provider_for_node_type

	config = node_config if isinstance(node_config, dict) else {}
	chosen = str(config.get("gateway") or "").strip()
	if not chosen:
		return False, REASON_NO_CHANNEL
	if chosen != _gateway_name(gateway) and chosen != str(payload.get("gateway") or ""):
		return False, REASON_OTHER_CHANNEL
	wanted_provider = provider_for_node_type(node_type)
	if wanted_provider and _provider_of(gateway, payload) != wanted_provider.lower():
		return False, REASON_OTHER_CHANNEL
	p = param_map(config)

	kind = str(payload.get("kind") or "message")
	if kind not in STARTING_KINDS:
		return False, f"{kind} events do not start flows"
	if payload.get("edited") and not p.get("include_edits"):
		return False, "edited message"
	if payload.get("is_channel_post") and not p.get("include_channel_posts"):
		return False, "channel post"
	if p.get("ignore_bots", True) is not False and payload.get("sender_is_bot"):
		return False, "sent by a bot"

	senders = _list(p.get("only_senders"))
	if senders and not _is_sender(senders, payload):
		return False, "sender not listed"
	kinds = _list(p.get("message_kinds"))
	if kinds and str(payload.get("message_type") or "text") not in kinds:
		return False, "message kind"
	text = _text(payload)
	words = _list(p.get("keywords"))
	if words and not any(_has_word(text, w) for w in words):
		return False, "keywords"
	start = str(p.get("starts_with") or "").strip()
	if start and not text.lstrip().lower().startswith(start.lower()):
		return False, "starts with"
	scope = p.get("chat_scope") or "both"
	room = bool(payload.get("is_room"))
	if scope == "direct" and room:
		return False, "group chat"
	if scope == "groups" and not room:
		return False, "one-to-one chat"
	if p.get("only_when_mentioned") and room and scope != "direct" and not payload.get("mentioned"):
		return False, "not mentioned"
	if p.get("has_attachment") and not payload.get("attachments"):
		return False, "no attachment"
	langs = [v.lower() for v in _list(p.get("language"))]
	if langs:
		got = str(payload.get("language") or "").lower()
		if not any(got == v or got.split("-")[0] == v.split("-")[0] for v in langs):
			return False, "language"

	reply = payload.get("interactive_reply") if isinstance(payload.get("interactive_reply"), dict) else {}
	ids = _list(p.get("button_reply_ids"))
	if ids and str(payload.get("button_id") or reply.get("id") or "") not in ids:
		return False, "button"
	payloads = _list(p.get("button_payloads"))
	if payloads and str(payload.get("button_payload") or payload.get("callback_data") or "") not in payloads:
		return False, "button value"
	tags = _list(p.get("ad_tags"))
	referral = payload.get("referral") if isinstance(payload.get("referral"), dict) else {}
	if tags and str(payload.get("referral_tag") or referral.get("source_id") or "") not in tags:
		return False, "ad tag"
	if p.get("first_message_only") and not _is_first_message(payload, gateway):
		return False, "not the first message"

	chats = [c.lower().lstrip("@") for c in _list(p.get("only_chats"))]
	if chats:
		have = {str(payload.get(k) or "").lower().lstrip("@") for k in ("telegram_chat_id", "conversation_id", "username")}
		if not have & set(chats):
			return False, "chat"
	chat_kinds = _list(p.get("chat_kinds"))
	if chat_kinds and str(payload.get("telegram_chat_type") or "") not in chat_kinds:
		return False, "chat kind"
	topics = _list(p.get("topics"))
	if topics and str(payload.get("topic_id") or payload.get("message_thread_id") or "") not in topics:
		return False, "topic"
	commands = [c.lstrip("/").split("@", 1)[0].lower() for c in _list(p.get("commands"))]
	if commands and _command(payload) not in commands:
		return False, "command"
	prefixes = _list(p.get("callback_prefixes"))
	data = str(payload.get("callback_data") or "")
	if prefixes and not any(data.startswith(x) for x in prefixes):
		return False, "button prefix"

	if flow_id and over_rate_cap(flow_id, chosen, payload.get("sender_id"), p.get("max_runs_per_sender_per_hour")):
		return False, REASON_RATE_LIMIT
	return True, ""


def rate_cap_of(value) -> int:
	"""The configured cap; a blank value is the default, 0 or less turns the cap off."""
	if value is None or isinstance(value, bool) or value == "":
		return DEFAULT_RATE_CAP
	try:
		return int(value)
	except (TypeError, ValueError):
		return DEFAULT_RATE_CAP


def over_rate_cap(flow_id: str, gateway: str, sender, cap_value=None) -> bool:
	"""Count one run for (flow, gateway, sender) in the current hour; True when it goes over the cap.

	A Redis failure never blocks a message (the gateway's own sender limit still applies)."""
	cap = rate_cap_of(cap_value)
	if cap <= 0 or not sender:
		return False
	try:
		import time

		import frappe

		bucket = int(time.time() // RATE_WINDOW_SECONDS)
		key = f"huf:gwtrig-rate:{frappe.local.site}:{flow_id}:{gateway}:{sender}:{bucket}"
		cache = frappe.cache()
		count = int(cache.incr(key))
		if count == 1:
			cache.expire(key, RATE_WINDOW_SECONDS + 5)
		return count > cap
	except Exception:
		return False
