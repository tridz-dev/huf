# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Live streaming of agent replies in Telegram private chats (Bot API 10.3 ``sendMessageDraft``).

A draft is an ephemeral ~30s preview; the final answer still goes out through the normal reply pipeline
(``sendMessage``), which also clears the draft. Streaming is best effort: any failure here only disables
the preview, it never loses or delays the final reply.

Pieces:
- ``DraftUpdater``: throttled (>= ``MIN_INTERVAL`` s between sends), coalescing, flood-control aware.
- ``StreamState``: per-chat state in the Frappe cache (shared by the worker running the agent and the web
  process that receives ``stopped_message_generation``).
- ``make_runner``: a ``run_agent_sync``-compatible callable that drives ``run_agent_stream`` and feeds the
  updater (needs the ``agent_runner`` provider hook call site in ``gateway_service``; see telegram_stream_hooks).
- ``handle_stopped``: the ``stopped_message_generation`` update handler (cancels the run).

Enabled by ``frappe.conf.huf_telegram_streaming`` (default off) and only for private chats; groups and
channels keep the typing action.
"""

from __future__ import annotations

import time
import zlib
from typing import Any, Callable

from huf.ai.gateway_adapters.telegram_client import TelegramApiError

MIN_INTERVAL = 1.0  # seconds between draft updates per chat
MAX_DRAFT_CHARS = 4096
MAX_CONSECUTIVE_ERRORS = 3
STATE_TTL = 15 * 60
NO_REPLY = "<NO_REPLY>"  # gateway_service.NO_REPLY_SENTINEL: the event is suppressed cleanly


def streaming_enabled(chat_type: str | None, conf: Any = None) -> bool:
	"""Private chats only (drafts are not supported elsewhere) and only when the flag is on."""
	if (chat_type or "private") != "private":
		return False
	if conf is None:
		import frappe

		conf = frappe.conf
	return bool(conf.get("huf_telegram_streaming"))


def draft_id_for(event_name: str) -> int:
	"""Stable non-zero positive 31-bit id per reply: all updates of one reply animate the same draft."""
	return (zlib.crc32(str(event_name).encode("utf-8")) & 0x7FFFFFFF) or 1


def event_chat_type(event: Any) -> str:
	raw = getattr(event, "raw_payload", None)
	if isinstance(raw, dict):
		return str((raw.get("telegram_meta") or {}).get("chat_type") or "private")
	return "private"


# -- shared state --------------------------------------------------------------------------------


def _cache(cache: Any = None) -> Any:
	if cache is not None:
		return cache
	import frappe

	return frappe.cache()


def _key(gateway: str, chat_id: Any) -> str:
	return f"huf_tg_stream:{gateway}:{chat_id}"


class StreamState:
	"""Per-chat stream record: ``{draft_id, run_id, event, keep_on_stop, stopped}``. Never raises."""

	def __init__(self, gateway: str, chat_id: Any, cache: Any = None) -> None:
		self.key = _key(gateway, chat_id)
		self._cache = cache

	def get(self) -> dict:
		try:
			value = _cache(self._cache).get_value(self.key)
		except Exception:
			return {}
		return dict(value) if isinstance(value, dict) else {}

	def update(self, **fields: Any) -> dict:
		value = {**self.get(), **fields}
		try:
			_cache(self._cache).set_value(self.key, value, expires_in_sec=STATE_TTL)
		except Exception:
			pass
		return value

	def clear(self) -> None:
		try:
			_cache(self._cache).set_value(self.key, {}, expires_in_sec=1)
		except Exception:
			pass

	def stopped(self) -> bool:
		return bool(self.get().get("stopped"))


# -- throttled draft updater -----------------------------------------------------------------------


class DraftUpdater:
	"""Sends ``sendMessageDraft`` at most once per ``min_interval`` seconds, coalescing intermediate text.

	``push(text)`` records the newest full text and sends it only if the interval elapsed (else it is
	pending until the next ``push``/``flush``). Flood control (``retry_after``) pauses sending; repeated or
	fatal errors (blocked, chat not found) disable the updater. Nothing here raises.
	"""

	def __init__(
		self,
		sender: Any,
		chat_id: Any,
		draft_id: int,
		*,
		thread_id: Any = None,
		can_stop: bool = True,
		keep_on_stop: bool = False,
		min_interval: float = MIN_INTERVAL,
		clock: Callable[[], float] = time.monotonic,
	) -> None:
		if not draft_id:
			raise ValueError("draft_id must be non-zero")
		self.sender, self.chat_id, self.draft_id, self.thread_id = sender, chat_id, int(draft_id), thread_id
		self.can_stop, self.keep_on_stop = can_stop, keep_on_stop
		self.min_interval, self._clock = min_interval, clock
		self.disabled = False
		self.sent_count = 0
		self._last_sent_at: float | None = None
		self._blocked_until = 0.0
		self._errors = 0
		self._pending: str | None = None
		self._last_text: str | None = None

	def push(self, text: str) -> bool:
		"""Record ``text`` (the full text so far); returns True when a draft was actually sent."""
		if self.disabled:
			return False
		self._pending = self._fit(text)
		return self._maybe_send()

	def flush(self) -> bool:
		"""Send the pending text now if the throttle/flood window allows."""
		return False if self.disabled else self._maybe_send()

	def start(self) -> bool:
		"""Show the "Thinking..." placeholder (empty draft text)."""
		return False if self.disabled else self._send("")

	@staticmethod
	def _fit(text: str) -> str:
		text = str(text or "")
		return text[-MAX_DRAFT_CHARS:] if len(text) > MAX_DRAFT_CHARS else text

	def _maybe_send(self) -> bool:
		if self._pending is None or self._pending == self._last_text:
			return False
		now = self._clock()
		if now < self._blocked_until:
			return False
		if self._last_sent_at is not None and now - self._last_sent_at < self.min_interval:
			return False
		return self._send(self._pending)

	def _send(self, text: str) -> bool:
		self._last_sent_at = self._clock()
		try:
			self.sender.send_message_draft(
				self.chat_id,
				self.draft_id,
				text,
				thread_id=self.thread_id,
				can_stop=self.can_stop,
				keep_on_stop=self.keep_on_stop,
			)
		except TelegramApiError as exc:
			if exc.flood_control:
				self._blocked_until = self._clock() + float(exc.retry_after or 5) + 0.5
				return False
			if exc.blocked_by_user or exc.chat_not_found:
				self.disabled = True
				return False
			self._error()
			return False
		except Exception:
			self._error()
			return False
		self._errors = 0
		self.sent_count += 1
		self._last_text = text
		self._pending = None
		return True

	def _error(self) -> None:
		self._errors += 1
		if self._errors >= MAX_CONSECUTIVE_ERRORS:
			self.disabled = True


# -- streaming runner (drop-in for run_agent_sync) -------------------------------------------------


def _default_stream(**kwargs: Any):
	from huf.ai.agent.integration import run_agent_stream

	return run_agent_stream(**kwargs)


def _stream_kwargs(kwargs: dict) -> dict:
	"""run_agent_sync kwargs -> run_agent_stream kwargs (stream has no ``now``)."""
	allowed = {
		"agent_name",
		"prompt",
		"provider",
		"model",
		"channel_id",
		"external_id",
		"conversation_id",
		"prompt_template",
		"prompt_version",
		"parent_conversation_id",
		"invoked_by_agent",
		"prompt_cache_options",
		"skip_user_message",
		"files",
		"project",
		"client_idempotency_key",
	}
	return {k: v for k, v in kwargs.items() if k in allowed}


def _consume(stream_factory: Callable[..., Any], kwargs: dict, on_chunk: Callable[[dict], bool]) -> dict:
	"""Drive the async chunk generator to completion on a private loop; ``on_chunk`` returns True to stop."""
	import asyncio

	async def run() -> dict:
		agen = stream_factory(**kwargs)
		final: dict = {}
		try:
			async for chunk in agen:
				if not isinstance(chunk, dict):
					continue
				if chunk.get("type") in ("complete", "error"):
					final = chunk
				if on_chunk(chunk):
					break
		finally:
			close = getattr(agen, "aclose", None)
			if close is not None:
				await close()
		return final

	loop = asyncio.new_event_loop()
	try:
		return loop.run_until_complete(run())
	finally:
		loop.close()


def make_runner(
	sender: Any,
	chat_id: Any,
	event_name: str,
	gateway_name: str,
	*,
	thread_id: Any = None,
	keep_on_stop: bool = False,
	cache: Any = None,
	stream_factory: Callable[..., Any] = _default_stream,
	clock: Callable[[], float] = time.monotonic,
	min_interval: float = MIN_INTERVAL,
) -> Callable[..., dict]:
	"""A ``run_agent_sync``-compatible callable that streams the reply as drafts.

	Returns the final ``complete`` chunk (same shape as ``run_agent_sync``). If the user pressed Stop, returns
	the partial text (``keep_on_stop``) or the NO_REPLY sentinel, so the gateway delivers nothing more.
	If streaming itself breaks the result is still the agent's final answer.
	"""
	state = StreamState(gateway_name, chat_id, cache)

	def runner(**kwargs: Any) -> dict:
		updater = DraftUpdater(
			sender,
			chat_id,
			draft_id_for(event_name),
			thread_id=thread_id,
			keep_on_stop=keep_on_stop,
			min_interval=min_interval,
			clock=clock,
		)
		state.update(
			draft_id=updater.draft_id,
			event=event_name,
			keep_on_stop=keep_on_stop,
			stopped=False,
			run_id="",
			draft_text=False,
		)
		partial = {"text": ""}
		snapshot: dict = {}

		def on_chunk(chunk: dict) -> bool:
			try:
				ctype = chunk.get("type")
				if ctype == "run_started":
					state.update(run_id=chunk.get("agent_run_id") or "")
					updater.start()
				elif ctype == "delta":
					partial["text"] = str(chunk.get("full_response") or partial["text"])
					if not state.stopped() and updater.push(partial["text"]) and partial["text"].strip():
						state.update(draft_text=True)  # real text is visible: typing keepalive can stop
			except Exception:
				pass  # streaming must never break the run
			return False

		try:
			final = _consume(stream_factory, _stream_kwargs(kwargs), on_chunk)
			snapshot = state.get()
			stopped = bool(snapshot.get("stopped"))
		finally:
			if not state.get().get("stopped"):
				state.clear()
		if stopped:
			state.clear()
			text = (final.get("response") if final.get("type") == "complete" else "") or partial["text"]
			if keep_on_stop and str(text).strip():
				return {
					"success": True,
					"response": str(text),
					"agent_run_id": final.get("agent_run_id") or snapshot.get("run_id"),
				}
			return {"success": True, "response": NO_REPLY, "agent_run_id": final.get("agent_run_id") or ""}
		if not final:
			return {"success": False, "error": "Agent stream ended without a result"}
		return final if final.get("type") != "error" else {**final, "success": False}

	return runner


# -- pipeline extension + stop handler ---------------------------------------------------------------


def before_send(event: Any, gateway: Any, parts: list[str], cache: Any = None) -> list[str]:
	"""Pipeline ``before_send``: the final reply replaces the draft, so just drop this chat's stream state."""
	try:
		StreamState(gateway.name, event.conversation_id, cache).clear()
	except Exception:
		pass
	return parts


def handle_stopped(
	gateway: Any,
	adapter: Any,
	parsed: Any,
	request: Any = None,
	*,
	cache: Any = None,
	cancel: Callable[[str], Any] | None = None,
) -> dict | None:
	"""``stopped_message_generation``: mark the stream stopped and cancel the agent run if known."""
	raw = getattr(parsed, "raw", None) or {}
	info = raw.get("stopped_message_generation")
	if not isinstance(info, dict):
		return None
	chat_id = (info.get("chat") or {}).get("id") or getattr(parsed, "chat_id", "")
	state = StreamState(gateway.name, chat_id, cache)
	current = state.get()
	if not current:
		return {"success": True, "ignored": "stopped_message_generation", "note": "no active stream"}
	if info.get("draft_id") is not None and current.get("draft_id") not in (None, info.get("draft_id")):
		return {"success": True, "ignored": "stopped_message_generation", "note": "stale draft"}
	state.update(stopped=True)
	run_id = current.get("run_id")
	cancelled = False
	if run_id:
		try:
			if cancel is None:
				from huf.ai.run_control import cancel_agent_run as cancel
			import frappe

			prior = frappe.session.user
			try:
				if getattr(gateway, "execution_user", None):
					frappe.set_user(gateway.execution_user)
				cancel(run_id)
				cancelled = True
			finally:
				frappe.set_user(prior)
		except Exception:
			cancelled = False
	return {
		"success": True,
		"ignored": "stopped_message_generation",
		"stopped": True,
		"run_cancelled": cancelled,
	}
