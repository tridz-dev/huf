# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram typing keepalive: re-send ``sendChatAction`` every ~4s while an agent run is in flight.

Telegram clears the typing status after ~5s. The ``typing`` hook starts one daemon thread per chat; it stops on
``stop`` (reply started / suppressed / failed), after ``MAX_SECONDS``, or when a draft stream is active. The thread
uses only the ``send`` callable it was given (a plain HTTP client built before start); it never touches frappe
request state and never raises. Disabled under unit tests unless ``ENABLED`` is set True.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

INTERVAL = 4.0
MAX_SECONDS = 90.0
MAX_THREADS = 50
ENABLED: bool | None = None  # None = on, except under frappe tests

_lock = threading.Lock()
_active: dict[str, "_Keepalive"] = {}


def enabled() -> bool:
	if ENABLED is not None:
		return bool(ENABLED)
	try:
		import frappe

		return not getattr(frappe.flags, "in_test", False)
	except Exception:
		return True


def key_for(gateway_name: Any, chat_id: Any, thread_id: Any = None) -> str:
	return f"{gateway_name}:{chat_id}:{thread_id or ''}"


class _Keepalive:
	def __init__(self, key, send, skip, clock, wait, interval, max_seconds, site=None) -> None:
		self.key = key
		self.site = site
		self.send = send
		self.skip = skip
		self.clock = clock
		self.interval = interval
		self.max_seconds = max_seconds
		self.stop_flag = threading.Event()
		self.wait = wait or self.stop_flag.wait
		self.deadline = clock() + max_seconds

	def _bind_site(self) -> bool:
		"""Give this thread a Frappe site context (cache access) once; True when we own it and must destroy."""
		if not self.site:
			return False
		try:
			import frappe

			if getattr(frappe.local, "site", None):
				return False
			frappe.init(site=self.site)
			return True
		except Exception:
			return False

	def run(self) -> None:
		owns_ctx = self._bind_site()
		try:
			while not self.stop_flag.is_set():
				self.wait(self.interval)
				if self.stop_flag.is_set() or self.clock() >= self.deadline:
					break
				try:
					if self.skip is not None and self.skip():
						break
					self.send()
				except Exception:
					pass
		except Exception:
			pass
		finally:
			if owns_ctx:
				try:
					import frappe

					frappe.destroy()
				except Exception:
					pass
			with _lock:
				if _active.get(self.key) is self:
					_active.pop(self.key, None)


def start(
	key: str,
	send: Callable[[], Any],
	skip: Callable[[], bool] | None = None,
	*,
	clock: Callable[[], float] = time.monotonic,
	wait: Callable[[float], Any] | None = None,
	interval: float = INTERVAL,
	max_seconds: float = MAX_SECONDS,
	spawn: bool = True,
	site: str | None = None,
) -> bool:
	"""Start (or extend) the keepalive for ``key``. Returns True when a thread is running. Never raises."""
	try:
		if not enabled():
			return False
		with _lock:
			existing = _active.get(key)
			if existing is not None:
				existing.deadline = clock() + max_seconds
				return True
			if len(_active) >= MAX_THREADS:
				return False
			ka = _Keepalive(key, send, skip, clock, wait, interval, max_seconds, site)
			_active[key] = ka
		if spawn:
			threading.Thread(target=ka.run, name="huf-tg-typing", daemon=True).start()
		return True
	except Exception:
		return False


def stop(key: str) -> None:
	try:
		with _lock:
			ka = _active.pop(key, None)
		if ka is not None:
			ka.stop_flag.set()
	except Exception:
		pass


def active_count() -> int:
	with _lock:
		return len(_active)
