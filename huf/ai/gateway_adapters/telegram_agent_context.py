# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""What the agent is told it can do on Telegram (WP-C).

``build_instructions(gateway)`` is the ``agent_instructions`` channel note: compact plain text, at most
``MAX_CHARS``, built from the reply features that always exist plus the capability flags enabled on the
Gateway. ``capabilities(gateway)`` exposes the same flags as data for tools and the UI. Never includes
tokens, secrets or chat ids.
"""

from __future__ import annotations

import re
from typing import Any

from huf.ai.gateway_adapters import telegram_blocks, telegram_buttons

MAX_CHARS = 2000  # static feature docs + this gateway's capability lines; per-message prompt cost

FLAG_GROUP_ADMIN = "telegram_agent_allow_group_admin"
FLAG_BUSINESS = "telegram_agent_allow_business"
FLAG_PROFILE = "telegram_agent_allow_profile"
VOICE_MODE_FIELD = "voice_reply_mode"

MEDIA_TEXT = (
	'Media: add a ```telegram-media block {"items":[...]} (max 10, sent before your text). File item: {"type":"photo|video|'
	'animation|audio|voice|document|sticker|video_note","media":"<https url | file_id | /files/.. path>","caption":"",'
	'"has_spoiler":true,"show_caption_above_media":true}; audio also title, performer, duration. Others: location{latitude,'
	"longitude}, venue{+title,address}, contact{phone_number,first_name,last_name}, poll|quiz{question,options[],is_anonymous,"
	"allows_multiple_answers,correct_option_id,explanation,open_period}, dice{emoji}. Any item: disable_notification, "
	"protect_content, reply_to_message_id, message_thread_id. Invalid blocks are reported back to you."
)
TOOL_TEXT = (
	"telegram tool: send_message/reply_to_message, set_reaction, edit_message_text, delete_message (ids from "
	"'Current message'/list_messages); after a tool send here add no final text; list_templates/send_template, send_poll, get_file; "
	"send_speech(text)=voice."
)
FLAG_TEXT = {
	FLAG_GROUP_ADMIN: "telegram_admin tool: group moderation; state changes need a bound admin chat + human Approve.",
	FLAG_BUSINESS: "Secretary/business actions are allowed.",
	FLAG_PROFILE: "Bot commands and profile can be changed.",
}


def _flag(gateway, name: str) -> bool:
	return bool(getattr(gateway, name, 0))


def _voice_mode(gateway) -> str:
	return str(getattr(gateway, VOICE_MODE_FIELD, "") or "Off")


def capabilities(gateway) -> dict:
	"""Flags and mode booleans for this gateway. Plain data, no secrets."""
	return {
		"group_admin": _flag(gateway, FLAG_GROUP_ADMIN),
		"business": _flag(gateway, FLAG_BUSINESS),
		"profile": _flag(gateway, FLAG_PROFILE),
		"voice_reply": _voice_mode(gateway) != "Off",
		"voice_reply_mode": _voice_mode(gateway),
	}


def _static_sections() -> list[str]:
	return [telegram_buttons.AGENT_INSTRUCTIONS, MEDIA_TEXT, TOOL_TEXT]


def _capability_sections(gateway) -> list[str]:
	"""What THIS gateway allows (flags, voice mode). Short and decision-relevant, so never dropped."""
	caps = capabilities(gateway)
	out = [
		FLAG_TEXT[flag]
		for flag, key in (
			(FLAG_GROUP_ADMIN, "group_admin"),
			(FLAG_BUSINESS, "business"),
			(FLAG_PROFILE, "profile"),
		)
		if caps[key]
	]
	if caps["voice_reply"]:
		out.append(f"Voice replies are on ({caps['voice_reply_mode']}).")
	return out


def _sections(gateway) -> list[str]:
	return _static_sections() + _capability_sections(gateway)


def build_instructions(gateway) -> str:
	"""Channel note for the agent prompt, within MAX_CHARS.

	Capability lines are reserved first and always kept; static sections are added whole while they fit in
	what is left, so a growing feature description can never push out what this gateway actually allows."""
	capability = _capability_sections(gateway)
	budget = MAX_CHARS - sum(len(c) + 1 for c in capability)
	out = ""
	for section in _static_sections():
		candidate = f"{out} {section}" if out else section
		if len(candidate) > budget:
			break
		out = candidate
	return " ".join([p for p in [out, *capability] if p])


_MESSAGE_KEYS = ("message", "edited_message", "business_message", "channel_post")
_NAME_MAX = 40


def _clean_name(value: Any) -> str:
	text = re.sub(r"[^\w .'-]", "", str(value or ""), flags=re.UNICODE)
	return " ".join(text.split())[:_NAME_MAX]


def _id(value: Any) -> str:
	text = str(value if value is not None else "").strip()
	return text if re.fullmatch(r"-?\d{1,20}", text) else ""


def event_context(event, gateway=None) -> str:
	"""Channel note about the inbound event: ``Current message: chat_id=..., message_id=...`` plus, once, what
	was wrong with the agent's previous reply blocks in this conversation. '' when there is nothing to say."""
	line = _message_line(event, gateway)
	gw = str(getattr(gateway, "name", "") or getattr(event, "gateway", "") or "")
	chat = str(getattr(event, "conversation_id", "") or "")
	feedback = telegram_blocks.feedback_line(gw, chat) if gw and chat else ""
	return " ".join(p for p in (line, feedback) if p)


def _message_line(event, gateway=None) -> str:
	"""One-line ``Current message: chat_id=..., message_id=...`` for the inbound event, or '' when unknown."""
	from huf.ai.gateway_adapters import telegram_pipeline

	raw = getattr(event, "raw_payload", None)
	raw = raw if isinstance(raw, dict) else {}
	msg: dict = {}
	for key in _MESSAGE_KEYS:
		if isinstance(raw.get(key), dict):
			msg = raw[key]
			break
	else:
		cb = raw.get("callback_query")
		if isinstance(cb, dict) and isinstance(cb.get("message"), dict):
			msg = cb["message"]
	chat = msg.get("chat") if isinstance(msg.get("chat"), dict) else {}
	chat_id = _id(chat.get("id")) or _id(str(getattr(event, "conversation_id", "") or "").split(":", 1)[0])
	message_id = _id(msg.get("message_id")) or _id(getattr(event, "thread_id", None))
	if not chat_id or not message_id:
		return ""
	parts = [f"chat_id={chat_id}", f"message_id={message_id}"]
	thread = _id(telegram_pipeline.forum_thread_id(event))
	if thread:
		parts.append(f"thread_id={thread}")
	sender = msg.get("from") if isinstance(msg.get("from"), dict) else {}
	name = _clean_name(" ".join(str(sender.get(k) or "") for k in ("first_name", "last_name")))
	if name:
		parts.append(f"sender={name}")
	line = "Current message: " + ", ".join(parts)
	try:
		from huf.ai.gateway_adapters import telegram_messages

		gw = str(getattr(gateway, "name", "") or getattr(event, "gateway", "") or "")
		last = telegram_messages.last_outbound_id(gw, chat_id) if gw else None
	except Exception:
		last = None
	return f"{line}. Your previous message: id={last}" if last else line
