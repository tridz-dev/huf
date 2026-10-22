# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram typing indicator counters, kept in the frappe cache per Gateway (observability without log level).

Key ``huf_tg_typing:<gateway>`` holds one dict: ``last_sent_at`` (site time string), ``last_chat`` (internal
only, never exposed), ``last_ok`` (bool), ``sent_count_24h`` (approximate; resets after 24h),
``window_start``, ``last_error`` (exception or API error *type name* only, never text), ``last_error_at`` and
``keepalive_ticks``. Every call is best effort: a cache outage must never fail a run or a reply.
"""

from __future__ import annotations

from typing import Any

import time
from datetime import datetime

import frappe

KEY_PREFIX = "huf_tg_typing:"
WINDOW_SECONDS = 24 * 60 * 60


def key_for(gateway: Any) -> str:
	return f"{KEY_PREFIX}{gateway}"


def _load(gateway: Any) -> dict[str, Any]:
	try:
		data = frappe.cache().get_value(key_for(gateway))
	except Exception:
		return {}
	return dict(data) if isinstance(data, dict) else {}


def _save(gateway: Any, data: dict[str, Any]) -> None:
	try:
		frappe.cache().set_value(key_for(gateway), data, expires_in_sec=WINDOW_SECONDS * 8)
	except Exception:
		pass


def _ts() -> float:
	return time.time()


def _stamp() -> str:
	"""Server-local ``YYYY-MM-DD HH:MM:SS`` (stdlib, so it works without a bound site)."""
	return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def record_sent(gateway: Any, chat_id: Any) -> None:
	"""A typing action was accepted by Telegram."""
	try:
		data = _load(gateway)
		t = _ts()
		if not data.get("window_start") or t - float(data["window_start"]) >= WINDOW_SECONDS:
			data["window_start"] = t
			data["sent_count_24h"] = 0
		data["sent_count_24h"] = int(data.get("sent_count_24h") or 0) + 1
		data["last_sent_at"] = _stamp()
		data["last_chat"] = str(chat_id or "")
		data["last_ok"] = True
		_save(gateway, data)
	except Exception:
		pass


def record_error(gateway: Any, exc: BaseException | str) -> None:
	"""A typing action failed; only the error type name is stored (never the message: it can echo the token)."""
	try:
		data = _load(gateway)
		data["last_ok"] = False
		data["last_error"] = exc if isinstance(exc, str) else type(exc).__name__
		data["last_error_at"] = _stamp()
		_save(gateway, data)
	except Exception:
		pass


def record_keepalive_tick(gateway: Any) -> None:
	try:
		data = _load(gateway)
		data["keepalive_ticks"] = int(data.get("keepalive_ticks") or 0) + 1
		_save(gateway, data)
	except Exception:
		pass


def read(gateway: Any) -> dict[str, Any]:
	"""Client-safe view: no chat ids, no error text."""
	data = _load(gateway)
	count = int(data.get("sent_count_24h") or 0)
	if data.get("window_start") and _ts() - float(data["window_start"]) >= WINDOW_SECONDS:
		count = 0
	return {
		"last_sent_at": data.get("last_sent_at") or None,
		"sent_count_24h": count,
		"last_error": data.get("last_error") or None,
		"last_error_at": data.get("last_error_at") or None,
		"keepalive_ticks": int(data.get("keepalive_ticks") or 0),
	}
