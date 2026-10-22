# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""What the agent is told it can do on Telegram (WP-C).

``build_instructions(gateway)`` is the ``agent_instructions`` channel note: compact plain text, at most
``MAX_CHARS``, built from the reply features that always exist plus the capability flags enabled on the
Gateway. ``capabilities(gateway)`` exposes the same flags as data for tools and the UI. Never includes
tokens, secrets or chat ids.
"""

from __future__ import annotations

from huf.ai.gateway_adapters import telegram_buttons

MAX_CHARS = 1200

FLAG_GROUP_ADMIN = "telegram_agent_allow_group_admin"
FLAG_BUSINESS = "telegram_agent_allow_business"
FLAG_PROFILE = "telegram_agent_allow_profile"
VOICE_MODE_FIELD = "voice_reply_mode"

MEDIA_TEXT = (
	"Media and rich content: add a fenced ```telegram-media block with JSON {\"items\": [{\"type\": "
	"\"photo|video|animation|audio|voice|document|sticker|video_note|location|contact|venue|poll|dice\", "
	"\"source\": \"file_url|file_id|url|text\", \"value\": \"...\", \"caption\": \"\"}]}. It is removed from "
	"the reply and sent before the text. Reactions and typing indicators are automatic."
)
TOOL_TEXT = (
	"telegram tool: send, edit and delete messages; templates (list_templates, send_template); polls; "
	"topics; get_file."
)
FLAG_TEXT = {
	FLAG_GROUP_ADMIN: "telegram_admin tool: group moderation (requires confirm).",
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


def _sections(gateway) -> list[str]:
	caps = capabilities(gateway)
	sections = [telegram_buttons.AGENT_INSTRUCTIONS, MEDIA_TEXT, TOOL_TEXT]
	for flag in (FLAG_GROUP_ADMIN, FLAG_BUSINESS, FLAG_PROFILE):
		key = {FLAG_GROUP_ADMIN: "group_admin", FLAG_BUSINESS: "business", FLAG_PROFILE: "profile"}[flag]
		if caps[key]:
			sections.append(FLAG_TEXT[flag])
	if caps["voice_reply"]:
		sections.append(
			f"Voice replies are on ({caps['voice_reply_mode']}): a voice note from the customer may be "
			"answered with a voice note."
		)
	return sections


def build_instructions(gateway) -> str:
	"""Channel note for the agent prompt. Sections are added whole while the result stays within MAX_CHARS."""
	out = ""
	for section in _sections(gateway):
		candidate = f"{out} {section}" if out else section
		if len(candidate) > MAX_CHARS:
			break
		out = candidate
	return out
