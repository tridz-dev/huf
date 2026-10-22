# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Who an agent may message over Telegram, and how much (mirrors ``whatsapp_send_scope``).

A prompt-injected agent must never reach arbitrary chats or spam. By default an agent can send only to
the chat of its current conversation. Each Gateway can widen that (an explicit allow-list, any Approved
sender, or any chat) and sets per-run and rolling-24h caps, using the same Gateway fields as WhatsApp
(``agent_recipient_scope``, ``agent_recipient_allowlist``, ``agent_send_cap_per_run``,
``agent_send_cap_per_day``). All of it is read server-side from the run's own Gateway; nothing here is
controllable from tool arguments.

Refusals are JSON tool results with a stable ``error`` code (``recipient_not_permitted`` or
``send_cap_exceeded``). Unlike WhatsApp there is no durable send-key doctype for Telegram, so caps are
counted in the Frappe cache (per-run counter, rolling-24h timestamp list); a cache flush resets them.
A send is claimed before it goes out and released when it fails.
"""

from __future__ import annotations

import contextvars
import json
import re
import threading
import time
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, Optional

import frappe

PROVIDER = "Telegram"
SCOPES = ("Current contact", "Allow-list", "Approved contacts", "Any number")
DEFAULT_SCOPE = SCOPES[0]
DEFAULT_PER_RUN = 20
DEFAULT_PER_DAY = 200
DAY_SECONDS = 24 * 3600
_FIELDS = ["agent_recipient_scope", "agent_recipient_allowlist", "agent_send_cap_per_run", "agent_send_cap_per_day"]

_trusted_gateway: contextvars.ContextVar = contextvars.ContextVar("huf_telegram_trusted_gateway", default="")
_trusted_chat: contextvars.ContextVar = contextvars.ContextVar("huf_telegram_trusted_chat", default="")
_trusted_run: contextvars.ContextVar = contextvars.ContextVar("huf_telegram_trusted_run", default="")


@contextmanager
def trusted_gateway(gateway_name: str, run_id: str = "", chat_id: str = ""):
	"""Bind the gateway for a TRUSTED, deterministic server-side caller (never tool arguments)."""
	tokens = (
		_trusted_gateway.set(str(gateway_name or "").strip()),
		_trusted_run.set(str(run_id or "").strip()),
		_trusted_chat.set(str(chat_id or "").strip()),
	)
	try:
		yield
	finally:
		_trusted_chat.reset(tokens[2])
		_trusted_run.reset(tokens[1])
		_trusted_gateway.reset(tokens[0])


def effective_run_id() -> Optional[str]:
	return getattr(frappe.flags, "huf_current_agent_run_id", None) or _trusted_run.get() or None


def gateway_state() -> tuple[str, str]:
	"""``(state, gateway)``: ``none`` (not inside any gateway run), ``telegram`` (enabled Telegram gateway)
	or ``invalid`` (inside a gateway run that is disabled, missing, another provider, or failed to resolve).
	Fails closed: any lookup error while inside a gateway run is ``invalid``."""
	try:
		name = _trusted_gateway.get()
		if not name:
			try:
				run_id = getattr(frappe.flags, "huf_current_agent_run_id", None)
			except Exception:  # no frappe context at all: cannot be inside an agent run
				run_id = None
			if not run_id:
				return ("none", "")
			conversation = frappe.db.get_value("Agent Run", run_id, "conversation")
			channel = (
				str(frappe.db.get_value("Agent Conversation", conversation, "channel") or "") if conversation else ""
			)
			if not channel.startswith("gateway:"):
				return ("none", "")
			name = channel[len("gateway:"):].strip()
		row = frappe.db.get_value("Gateway", name, ["provider", "is_enabled"], as_dict=True) if name else None
		if not row or row.get("provider") != PROVIDER or not row.get("is_enabled"):
			return ("invalid", "")
		return ("telegram", name)
	except Exception:
		return ("invalid", "")


def run_gateway() -> str:
	"""The enabled Telegram Gateway the current run belongs to, or '' (see ``gateway_state``)."""
	state, name = gateway_state()
	return name if state == "telegram" else ""


# -- chat id normalisation ---------------------------------------------------------------------


def normalize_chat(raw: Any) -> str:
	"""Numeric chat ids compare as plain integers; ``@username`` is lower-cased; anything else is ''."""
	value = str(raw if raw is not None else "").strip()
	if re.fullmatch(r"-?\d{1,20}", value):
		return str(int(value))
	if re.fullmatch(r"@[A-Za-z][A-Za-z0-9_]{3,31}", value):
		return value.lower()
	return ""


def _entries(text: Any) -> list[str]:
	return [part.strip() for part in re.split(r"[,;\s]+", str(text or "")) if part.strip()]


def parse_allowlist(text: Any) -> list[str]:
	seen: list[str] = []
	for entry in _entries(text):
		chat = normalize_chat(entry)
		if chat and chat not in seen:
			seen.append(chat)
	return seen


def invalid_allowlist_entries(text: Any) -> list[str]:
	return [e for e in _entries(text) if not normalize_chat(e)]


def _cap(value: Any, default: int) -> int:
	try:
		return max(int(value), 0) if value not in (None, "") else default
	except (TypeError, ValueError):
		return default


def settings(gateway: str) -> dict:
	"""The gateway's send scope and caps. Fails closed: any error means the narrowest scope and default caps."""
	try:
		row = frappe.db.get_value("Gateway", gateway, _FIELDS, as_dict=True) or {}
	except Exception:
		row = {}
	scope = row.get("agent_recipient_scope") or DEFAULT_SCOPE
	return {
		"scope": scope if scope in SCOPES else DEFAULT_SCOPE,
		"allowlist": parse_allowlist(row.get("agent_recipient_allowlist")),
		"per_run": _cap(row.get("agent_send_cap_per_run"), DEFAULT_PER_RUN),
		"per_day": _cap(row.get("agent_send_cap_per_day"), DEFAULT_PER_DAY),
	}


def current_chat(run_id: Optional[str]) -> str:
	"""The Telegram chat (normalised) of the run's conversation, or '' when there is none."""
	bound = _trusted_chat.get()
	if bound:
		return normalize_chat(bound)
	if not run_id:
		return ""
	try:
		conversation = frappe.db.get_value("Agent Run", run_id, "conversation")
		external = frappe.db.get_value("Agent Conversation", conversation, "external_id") if conversation else ""
		# A forum-topic conversation may carry "<chat>:<thread>"; the chat is the first segment.
		return normalize_chat(str(external or "").split(":", 1)[0])
	except Exception:
		return ""


def _is_approved(gateway: str, chat: str) -> bool:
	from huf.ai import gateway_service

	try:
		return bool(gateway_service._has_access_entry(SimpleNamespace(name=gateway, provider=PROVIDER), "Sender", chat))
	except Exception:
		return False


def _refusal(error: str, message: str, **extra: Any) -> str:
	return json.dumps({"success": False, "error": error, "message": message, **extra}, default=str)


def check_recipient(gateway: str, run_id: Optional[str], recipient: Any) -> Optional[str]:
	"""Refusal JSON when ``recipient`` is outside the gateway's scope for this run, else None."""
	chat = normalize_chat(recipient)
	conf = settings(gateway)
	scope = conf["scope"] if conf["scope"] in SCOPES else DEFAULT_SCOPE
	if chat and chat == current_chat(run_id):
		return None
	allowed = bool(chat) and (
		scope == "Any number"
		or (scope == "Allow-list" and chat in conf["allowlist"])
		or (scope == "Approved contacts" and _is_approved(gateway, chat))
	)
	if allowed:
		return None
	hint = {
		"Current contact": "this gateway lets agents message only the chat of the current conversation",
		"Allow-list": "this chat is not on the gateway's allowed-recipient list",
		"Approved contacts": "this chat is not an Approved sender on the gateway",
		"Any number": "the chat id is not a valid numeric id or @username",
	}[scope]
	return _refusal(
		"recipient_not_permitted",
		f"That recipient is not permitted: {hint}. Ask a gateway admin to widen the recipient scope if this is intended.",
		scope=scope,
	)


# -- caps --------------------------------------------------------------------------------------


def _cache():
	return frappe.cache()


def _run_key(gateway: str, run_id: str) -> str:
	return f"huf_tg_sends_run:{gateway}:{run_id}"


def _day_key(gateway: str) -> str:
	return f"huf_tg_sends_day:{gateway}"


def _load(key: str) -> list:
	try:
		value = _cache().get_value(key)
	except Exception:
		value = None
	return list(value) if isinstance(value, (list, tuple)) else []


def _save(key: str, value: list, ttl: int) -> None:
	try:
		_cache().set_value(key, value, expires_in_sec=ttl)
	except Exception:
		pass


_LOCK = threading.Lock()


def _redis():
	"""``(client, make_key)`` when the cache exposes atomic counters, else None."""
	try:
		c = _cache()
		if getattr(c, "make_key", None) and all(hasattr(c, n) for n in ("incrby", "decrby", "expire")):
			return c
	except Exception:
		pass
	return None


def _refuse_run(limit: int) -> str:
	return _refusal(
		"send_cap_exceeded",
		f"This run has already sent its limit of {limit} Telegram messages. No more are sent in this run.",
		cap="run", limit=limit, retry_after=None,
	)


def _refuse_day(limit: int, retry: int) -> str:
	return _refusal(
		"send_cap_exceeded",
		f"This gateway reached its limit of {limit} agent Telegram messages in 24 hours. Try again later.",
		cap="day", limit=limit, retry_after=max(1, min(retry, DAY_SECONDS)),
	)


def _claim_atomic(c, conf: dict, gateway: str, run_id: Optional[str]) -> Optional[str]:
	"""INCR + EXPIRE counters (fixed 24h window from the first send); over-cap increments are rolled back."""
	run_k = c.make_key(_run_key(gateway, run_id) + ":n") if (conf["per_run"] and run_id) else None
	day_k = c.make_key(_day_key(gateway) + ":n") if conf["per_day"] else None
	if run_k:
		n = int(c.incrby(run_k, 1))
		if n == 1:
			c.expire(run_k, DAY_SECONDS)
		if n > conf["per_run"]:
			c.decrby(run_k, 1)
			return _refuse_run(conf["per_run"])
	if day_k:
		n = int(c.incrby(day_k, 1))
		if n == 1:
			c.expire(day_k, DAY_SECONDS)
		if n > conf["per_day"]:
			c.decrby(day_k, 1)
			if run_k:
				c.decrby(run_k, 1)
			try:
				ttl = int(c.ttl(day_k))
			except Exception:
				ttl = DAY_SECONDS
			return _refuse_day(conf["per_day"], ttl if ttl > 0 else DAY_SECONDS)
	return None


def claim_send(gateway: str, run_id: Optional[str], *, now: Optional[float] = None) -> Optional[str]:
	"""Count one send against the run/day caps. Refusal JSON when over a cap (nothing is counted), else None.

	Atomic via Redis INCR+EXPIRE when available (rolled back on overshoot); otherwise a process-local lock
	around a read-modify-write of timestamp lists.
	"""
	conf = settings(gateway)
	c = _redis() if now is None else None
	if c is not None:
		try:
			return _claim_atomic(c, conf, gateway, run_id)
		except Exception:
			pass
	now = time.time() if now is None else now
	with _LOCK:
		run_sends = _load(_run_key(gateway, run_id)) if (conf["per_run"] and run_id) else []
		if conf["per_run"] and run_id and len(run_sends) >= conf["per_run"]:
			return _refuse_run(conf["per_run"])
		day = [t for t in _load(_day_key(gateway)) if isinstance(t, (int, float)) and t > now - DAY_SECONDS]
		if conf["per_day"] and len(day) >= conf["per_day"]:
			oldest = sorted(day)[len(day) - conf["per_day"]]
			return _refuse_day(conf["per_day"], int(oldest + DAY_SECONDS - now))
		if conf["per_run"] and run_id:
			_save(_run_key(gateway, run_id), run_sends + [now], DAY_SECONDS)
		if conf["per_day"]:
			_save(_day_key(gateway), day + [now], DAY_SECONDS)
	return None


def release_send(gateway: str, run_id: Optional[str]) -> None:
	"""Undo the most recent claim after a failed or refused send."""
	conf = settings(gateway)
	c = _redis()
	if c is not None:
		try:
			if conf["per_run"] and run_id:
				c.decrby(c.make_key(_run_key(gateway, run_id) + ":n"), 1)
			if conf["per_day"]:
				c.decrby(c.make_key(_day_key(gateway) + ":n"), 1)
			return
		except Exception:
			pass
	with _LOCK:
		if conf["per_run"] and run_id:
			sends = _load(_run_key(gateway, run_id))
			if sends:
				_save(_run_key(gateway, run_id), sends[:-1], DAY_SECONDS)
		if conf["per_day"]:
			day = _load(_day_key(gateway))
			if day:
				_save(_day_key(gateway), day[:-1], DAY_SECONDS)
