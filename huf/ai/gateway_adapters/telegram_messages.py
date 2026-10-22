# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Store of Telegram message ids Huf sent, so edit-in-place, streaming and buttons can find them.

Backed by the Frappe cache with a TTL (no doctype fields). The first id of a reply is also kept on
the Gateway Event (``reply_message_id``). ``cache`` is injectable: anything with
``set_value(key, value, expires_in_sec=)`` / ``get_value(key)``.
"""

from __future__ import annotations

from typing import Any

TTL_SECONDS = 7 * 24 * 3600
_MAX_PER_KEY = 200


def _cache(cache: Any = None) -> Any:
	if cache is not None:
		return cache
	import frappe

	return frappe.cache()


def _event_key(gateway: str, event_name: str) -> str:
	return f"huf_tg_msgs:ev:{gateway}:{event_name}"


def _chat_key(gateway: str, chat_id: Any) -> str:
	return f"huf_tg_msgs:chat:{gateway}:{chat_id}"


def _load(c: Any, key: str) -> list:
	try:
		value = c.get_value(key)
	except Exception:
		return []
	return list(value) if isinstance(value, (list, tuple)) else []


def record_sent(
	gateway: str, chat_id: Any, event_name: str, message_ids: list, *, kind: str = "text", cache: Any = None
) -> None:
	"""Remember ``message_ids`` (Telegram ints, in send order) sent for ``event_name``. Never raises."""
	ids = [int(m) for m in message_ids if m not in (None, "")]
	if not ids:
		return
	try:
		c = _cache(cache)
		ev = _load(c, _event_key(gateway, event_name)) + [{"id": i, "kind": kind} for i in ids]
		c.set_value(_event_key(gateway, event_name), ev[-_MAX_PER_KEY:], expires_in_sec=TTL_SECONDS)
		chat = _load(c, _chat_key(gateway, chat_id)) + [
			{"id": i, "kind": kind, "event": event_name} for i in ids
		]
		c.set_value(_chat_key(gateway, chat_id), chat[-_MAX_PER_KEY:], expires_in_sec=TTL_SECONDS)
	except Exception:
		pass


def sent_for_event(gateway: str, event_name: str, *, cache: Any = None) -> list[int]:
	"""Message ids sent for the event, in order (empty when unknown/expired)."""
	return [int(r["id"]) for r in _load(_cache(cache), _event_key(gateway, event_name))]


def last_in_chat(gateway: str, chat_id: Any, *, cache: Any = None) -> int | None:
	"""Most recent message id Huf sent in the chat (edit target), or None."""
	rows = _load(_cache(cache), _chat_key(gateway, chat_id))
	return int(rows[-1]["id"]) if rows else None
