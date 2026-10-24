# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Bot-to-bot loop prevention (WP-8e, R9).

Telegram only lets bots see each other with "Bot-to-Bot Communication Mode" and warns that it can loop
forever ("Loop Prevention Requirements": rate limit, max interaction depth, dedupe). Policy here:

* messages from a bot (``from.is_bot``, ``via_bot`` or ``sender_business_bot``) are DROPPED unless the sender
  bot id is in the per-gateway allow-list (Integration Settings credential key ``bot_allowlist``, comma
  separated ids);
* an allowed bot is still cut off after ``max_hops`` consecutive bot messages in a chat/thread (a human
  message resets the counter) and above ``rate_cap`` messages per ``rate_window`` per chat+bot;
* our own bot id is never admitted.

State lives in the Frappe cache (no doctype fields). Counters are read-modify-write, so concurrent workers can
undercount by one; the caps are safety nets, not exact quotas.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

DEFAULT_MAX_HOPS = 3
DEFAULT_RATE_CAP = 5
DEFAULT_RATE_WINDOW = 60
_TTL = 3600


def parse_allowlist(value: Any) -> frozenset[str]:
	if isinstance(value, (list, tuple, set, frozenset)):
		items = [str(v) for v in value]
	else:
		items = str(value or "").replace(";", ",").replace("\n", ",").split(",")
	return frozenset(i.strip().lstrip("@") for i in items if i.strip())


def _int(value: Any, default: int) -> int:
	try:
		n = int(str(value).strip())
		return n if n > 0 else default
	except (TypeError, ValueError):
		return default


def sender_bot_id(message: Mapping[str, Any]) -> str | None:
	"""Id of the bot that produced ``message`` (None for a human). ``via_bot`` and business bots count."""
	sender = message.get("from") or {}
	if isinstance(sender, Mapping) and sender.get("is_bot"):
		return str(sender.get("id") or "unknown")
	via = message.get("via_bot")
	if isinstance(via, Mapping) and via:
		return str(via.get("id") or "unknown")
	biz = message.get("sender_business_bot")
	if isinstance(biz, Mapping) and biz:
		return str(biz.get("id") or "unknown")
	return None


@dataclass(frozen=True)
class Decision:
	allow: bool
	reason: str = ""


class LoopGuard:
	def __init__(
		self,
		cache: Any,
		*,
		max_hops: int = DEFAULT_MAX_HOPS,
		rate_cap: int = DEFAULT_RATE_CAP,
		rate_window: int = DEFAULT_RATE_WINDOW,
		clock: Callable[[], float] = time.time,
	) -> None:
		self.cache = cache
		self.max_hops = max_hops
		self.rate_cap = rate_cap
		self.rate_window = rate_window
		self.clock = clock

	@classmethod
	def from_credentials(cls, cache: Any, credentials: Mapping[str, str] | None) -> LoopGuard:
		c = credentials or {}
		return cls(
			cache,
			max_hops=_int(c.get("bot_max_hops"), DEFAULT_MAX_HOPS),
			rate_cap=_int(c.get("bot_rate_cap"), DEFAULT_RATE_CAP),
		)

	def _get(self, key: str) -> Any:
		return self.cache.get_value(key)

	def _set(self, key: str, value: Any, ttl: int = _TTL) -> None:
		self.cache.set_value(key, value, expires_in_sec=ttl)

	@staticmethod
	def _scope(gateway: str, chat_id: Any, thread_id: Any) -> str:
		return f"huf_tg_loop:{gateway}:{chat_id}:{thread_id or 0}"

	def note_human(self, gateway: str, chat_id: Any, thread_id: Any = None) -> None:
		"""A human message resets the consecutive-bot-message counter for that chat/thread."""
		self._set(self._scope(gateway, chat_id, thread_id) + ":hops", 0)

	def check_bot(
		self,
		gateway: str,
		chat_id: Any,
		thread_id: Any,
		bot_id: str,
		*,
		own_id: str,
		allowlist: frozenset[str],
		update_id: Any = None,
	) -> Decision:
		"""Decide on a message from bot ``bot_id``. Idempotent per ``update_id`` (the registry may call twice)."""
		seen_key = f"huf_tg_loop:{gateway}:seen:{update_id}" if update_id not in (None, "") else None
		if seen_key:
			prior = self._get(seen_key)
			if prior is not None:
				return Decision(prior == "allow", "" if prior == "allow" else str(prior))
		decision = self._decide(gateway, chat_id, thread_id, str(bot_id), str(own_id), allowlist)
		if seen_key:
			self._set(seen_key, "allow" if decision.allow else decision.reason, 600)
		return decision

	def _decide(self, gateway, chat_id, thread_id, bot_id, own_id, allowlist) -> Decision:
		if own_id and bot_id == own_id:
			return Decision(False, "own bot message")
		if bot_id not in allowlist:
			return Decision(False, "bot sender not in allow-list")
		scope = self._scope(gateway, chat_id, thread_id)
		hops = int(self._get(scope + ":hops") or 0)
		if hops >= self.max_hops:
			return Decision(False, f"hop limit {self.max_hops} reached; waiting for a human message")
		bucket = int(self.clock() // self.rate_window)
		rate_key = f"huf_tg_loop:{gateway}:{chat_id}:{bot_id}:rate:{bucket}"
		count = int(self._get(rate_key) or 0)
		if count >= self.rate_cap:
			return Decision(False, f"rate cap {self.rate_cap}/{self.rate_window}s exceeded")
		self._set(rate_key, count + 1, self.rate_window * 2)
		self._set(scope + ":hops", hops + 1)
		return Decision(True)
