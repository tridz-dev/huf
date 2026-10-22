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


def run_gateway() -> str:
	"""The enabled Telegram Gateway the current run belongs to, or '' (not a gateway run)."""
	try:
		bound = _trusted_gateway.get()
		name = bound
		if not name:
			run_id = getattr(frappe.flags, "huf_current_agent_run_id", None)
			if not run_id:
				return ""
			conversation = frappe.db.get_value("Agent Run", run_id, "conversation")
			channel = str(frappe.db.get_value("Agent Conversation", conversation, "channel") or "") if conversation else ""
			if not channel.startswith("gateway:"):
				return ""
			name = channel[len("gateway:"):].strip()
		row = frappe.db.get_value("Gateway", name, ["provider", "is_enabled"], as_dict=True) if name else None
		if not row or row.get("provider") != PROVIDER or not row.get("is_enabled"):
			return ""
		return name
	except Exception:
		return ""


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


def claim_send(gateway: str, run_id: Optional[str], *, now: Optional[float] = None) -> Optional[str]:
	"""Count one send against the run/day caps. Refusal JSON when over a cap (nothing is counted), else None."""
	conf = settings(gateway)
	now = time.time() if now is None else now
	run_sends = _load(_run_key(gateway, run_id)) if (conf["per_run"] and run_id) else []
	if conf["per_run"] and run_id and len(run_sends) >= conf["per_run"]:
		return _refusal(
			"send_cap_exceeded",
			f"This run has already sent its limit of {conf['per_run']} Telegram messages. No more are sent in this run.",
			cap="run", limit=conf["per_run"], retry_after=None,
		)
	day = [t for t in _load(_day_key(gateway)) if isinstance(t, (int, float)) and t > now - DAY_SECONDS]
	if conf["per_day"] and len(day) >= conf["per_day"]:
		oldest = sorted(day)[len(day) - conf["per_day"]]
		retry = int(oldest + DAY_SECONDS - now)
		return _refusal(
			"send_cap_exceeded",
			f"This gateway reached its limit of {conf['per_day']} agent Telegram messages in 24 hours. Try again later.",
			cap="day", limit=conf["per_day"], retry_after=max(1, min(retry, DAY_SECONDS)),
		)
	if conf["per_run"] and run_id:
		_save(_run_key(gateway, run_id), run_sends + [now], DAY_SECONDS)
	if conf["per_day"]:
		_save(_day_key(gateway), day + [now], DAY_SECONDS)
	return None


def release_send(gateway: str, run_id: Optional[str]) -> None:
	"""Undo the most recent claim after a failed or refused send."""
	conf = settings(gateway)
	if conf["per_run"] and run_id:
		sends = _load(_run_key(gateway, run_id))
		if sends:
			_save(_run_key(gateway, run_id), sends[:-1], DAY_SECONDS)
	if conf["per_day"]:
		day = _load(_day_key(gateway))
		if day:
			_save(_day_key(gateway), day[:-1], DAY_SECONDS)
