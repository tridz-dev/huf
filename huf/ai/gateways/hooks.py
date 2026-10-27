"""Gateway extension hooks.

Later work packages register handlers from their own modules; nobody edits
``gateway_service.py`` again. Handlers may be restricted to one provider
(``gateway.provider``, case-insensitive) and run in ascending ``priority``
order (ties keep registration order).

Hook names and signatures (``kind`` is ``"agent"`` or ``"flow"``):

- ``on_event_received(gateway, event)``
- ``pre_ingest_filter(gateway, context) -> bool`` (False drops the event)
- ``resolve_run_user(gateway, event) -> user | None``
- ``resolve_conversation_key(gateway, event) -> str | None``
- ``build_prompt(gateway, event, text) -> text`` (chain)
- ``resolve_reply_target(gateway, event, reply_text) -> str | None``: optional;
  called with ``call_first``. A returned string replaces the conversation id
  the reply is sent to (applied in memory on the event only, not persisted).
- ``on_run_start(gateway, event, kind)``
- ``on_run_success(gateway, event, kind, response)``
- ``on_run_failure(gateway, event, kind, error)``

A handler raising ``GatewayHookDenied`` aborts the dispatch (the caller marks
the event Rejected with ``.reason``). Any other exception is logged and the
handler is skipped.
"""

from __future__ import annotations

import importlib
from typing import Any, Callable

import frappe

ON_EVENT_RECEIVED = "on_event_received"
PRE_INGEST_FILTER = "pre_ingest_filter"
RESOLVE_RUN_USER = "resolve_run_user"
RESOLVE_CONVERSATION_KEY = "resolve_conversation_key"
BUILD_PROMPT = "build_prompt"
RESOLVE_REPLY_TARGET = "resolve_reply_target"
ON_RUN_START = "on_run_start"
ON_RUN_SUCCESS = "on_run_success"
ON_RUN_FAILURE = "on_run_failure"


class GatewayHookDenied(Exception):
	"""Raised by a handler to refuse the event; ``reason`` is user-visible."""

	def __init__(self, reason: str = ""):
		super().__init__(reason)
		self.reason = reason


_HANDLERS: dict[str, list[tuple[int, int, str | None, Callable]]] = {}
_SEQ = 0
_REGISTERED = False


def register(hook: str, fn: Callable, *, provider: str | None = None, priority: int = 100) -> None:
	global _SEQ
	_SEQ += 1
	prov = provider.lower() if provider else None
	_HANDLERS.setdefault(hook, []).append((priority, _SEQ, prov, fn))
	_HANDLERS[hook].sort(key=lambda h: (h[0], h[1]))


def clear() -> None:
	"""Remove all handlers and reset register_all (tests)."""
	global _REGISTERED
	_HANDLERS.clear()
	_REGISTERED = False


def register_all() -> None:
	"""Import every module listed in ``_registered.MODULES`` once."""
	global _REGISTERED
	if _REGISTERED:
		return
	_REGISTERED = True
	from huf.ai.gateways import _registered

	for name in _registered.MODULES:
		importlib.import_module(name)


def _provider_of(args: tuple) -> str | None:
	gateway = args[0] if args else None
	provider = getattr(gateway, "provider", None)
	if provider is None and isinstance(gateway, dict):
		provider = gateway.get("provider")
	return str(provider).lower() if provider else None


def _matching(hook: str, args: tuple) -> list[Callable]:
	provider = _provider_of(args)
	return [fn for _p, _s, prov, fn in list(_HANDLERS.get(hook, ())) if prov is None or prov == provider]


def _invoke(hook: str, fn: Callable, args: tuple, kw: dict) -> tuple[bool, Any]:
	try:
		return True, fn(*args, **kw)
	except GatewayHookDenied:
		raise
	except Exception:
		try:
			frappe.log_error(frappe.get_traceback(), f"Gateway hook failed: {hook}"[:140])
		except Exception:
			pass
		return False, None


def call_all(hook: str, *args, **kw) -> list:
	results = []
	for fn in _matching(hook, args):
		ok, value = _invoke(hook, fn, args, kw)
		if ok:
			results.append(value)
	return results


def call_first(hook: str, *args, **kw):
	for fn in _matching(hook, args):
		ok, value = _invoke(hook, fn, args, kw)
		if ok and value is not None:
			return value
	return None


def call_chain(hook: str, value, *args, **kw):
	"""Thread ``value`` through handlers: each gets ``(*args, value)`` as its last arg."""
	for fn in _matching(hook, args):
		ok, new = _invoke(hook, fn, (*args, value), kw)
		if ok and new is not None:
			value = new
	return value
