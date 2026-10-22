# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt
"""Ephemeral command replies (G-EPHEMERAL). Pure helpers, no Frappe.

An ephemeral command (``BotCommand.is_ephemeral``) arrives in a group as a message carrying
``ephemeral_message_id`` / ``receiver_user``. Replies must carry ``ephemeral_message_parameters`` so only
that user sees them. Private chats are never ephemeral. sendChatAction has no documented ephemeral
parameter, so typing stays unchanged; media is not sent ephemerally (see pipeline).
"""

from __future__ import annotations

from typing import Any, Mapping

from huf.ai.gateway_adapters.telegram_threads import ephemeral_reply_params, is_ephemeral

MESSAGE_KEYS = ("message", "edited_message", "business_message", "channel_post")


def _message(raw: Any) -> Mapping[str, Any]:
	if not isinstance(raw, Mapping):
		return {}
	for key in MESSAGE_KEYS:
		msg = raw.get(key)
		if isinstance(msg, Mapping):
			return msg
	return {}


def is_ephemeral_command(raw: Any) -> bool:
	"""True for an ephemeral inbound in a non-private chat."""
	msg = _message(raw)
	if not msg or str((msg.get("chat") or {}).get("type") or "") == "private":
		return False
	return is_ephemeral(msg)


def ephemeral_params(raw: Any) -> dict[str, Any]:
	"""``ephemeral_message_parameters`` (+ quote) for replying to ``raw``; {} when not an ephemeral command."""
	if not is_ephemeral_command(raw):
		return {}
	return ephemeral_reply_params(_message(raw))
