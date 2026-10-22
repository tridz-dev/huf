# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Registers the WP-8e ingest pre-filter (bot-to-bot loop guard + group addressing). Imported once from
``telegram_hooks``. The filter runs before the normal ingest and never calls the live API on the hot path
except one cached ``getMe`` (bot username) when a group message needs the addressing check.
"""

from __future__ import annotations

from typing import Any

from huf.ai.gateway_adapters import telegram_ingest as ing, telegram_loop_guard as lg, telegram_threads as th

_KINDS = ("message", "edited_message", "channel_post")
_ME_TTL = 86400


def _message(parsed) -> dict:
	msg = (getattr(parsed, "raw", None) or {}).get(parsed.kind)
	return msg if isinstance(msg, dict) else {}


def _cache():
	import frappe

	return frappe.cache() if callable(frappe.cache) else frappe.cache


def _own_id(adapter) -> str:
	return str(getattr(adapter, "_token", "") or "").split(":", 1)[0]


def _bot_username(adapter, gateway) -> str:
	"""Bot @username from a cached getMe; '' when unavailable (addressing check is then skipped)."""
	try:
		cache, key = _cache(), f"huf_tg_me:{gateway.name}"
		cached = cache.get_value(key)
		if cached:
			return str(cached)
		name = str((adapter.client.get_me() or {}).get("username") or "")
		if name:
			cache.set_value(key, name, expires_in_sec=_ME_TTL)
		return name
	except Exception:
		return ""


def _credentials(gateway) -> dict:
	try:
		from huf.ai.gateway_webhook import _gateway_credentials

		return _gateway_credentials(gateway)
	except Exception:
		return {}


def prefilter(gateway, adapter, parsed, request) -> dict | None:
	msg = _message(parsed)
	if not msg:
		return None
	chat_id = parsed.chat_id or (msg.get("chat") or {}).get("id")
	thread = th.thread_id_for_reply(msg)
	bot_id = lg.sender_bot_id(msg)
	if bot_id is None:
		if parsed.is_room and not parsed.is_channel and getattr(gateway, "mention_required", 0):
			username = _bot_username(adapter, gateway)
			if username and not th.is_addressed_to_bot(msg, username, _own_id(adapter)):
				return ing._ack(parsed.kind, "group message not addressed to the bot")
		lg.LoopGuard(_cache()).note_human(gateway.name, chat_id, thread)
		return None
	creds = _credentials(gateway)
	guard = lg.LoopGuard.from_credentials(_cache(), creds)
	decision = guard.check_bot(
		gateway.name, chat_id, thread, bot_id, own_id=_own_id(adapter),
		allowlist=lg.parse_allowlist(creds.get("bot_allowlist")), update_id=parsed.update_id,
	)
	if decision.allow:
		return None
	return ing._ack(parsed.kind, f"bot message dropped: {decision.reason}")


def _chained(key: str):
	prior = ing._UPDATE_HANDLERS.get(key)

	def run(gateway, adapter, parsed, request) -> Any:
		handled = prefilter(gateway, adapter, parsed, request)
		if handled is not None or prior is None:
			return handled
		return prior(gateway, adapter, parsed, request)

	return run


for _kind in _KINDS:
	ing.register_update_handler(_kind, _chained(_kind))
