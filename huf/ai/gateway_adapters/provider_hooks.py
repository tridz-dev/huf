# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Provider hook registry: provider-specific gateway behaviour looked up by name, not by ``==``.

``gateway_service`` / ``gateway_webhook`` ask ``get(provider, hook)`` and fall back to the
provider-neutral default when nothing is registered. API (frozen): ``register``, ``get``, ``call``.
Provider modules (``whatsapp_hooks``, ``telegram_hooks``) are imported lazily on first lookup.

Hook signatures (``gateway`` / ``event`` are Gateway / Gateway Event documents):

- ``inbound_kind(event) -> str | None``: media type of the inbound message (None = no media).
- ``media_save(event, gateway) -> list[str]``: save inbound media, return File URLs. Never raises.
- ``callback(event, gateway, ...) -> Any``: inline-button / callback-query handling.
- ``typing(event, gateway) -> None``: read receipt / typing indicator. Best effort, never raises.
- ``send_reply(event, gateway, agent_run_id, text) -> dict``: full reply pipeline; returns the
  event result dict. Unregistered = generic ``send_gateway_reply`` path.
- ``error_text(exc) -> str``: operator-readable text for a delivery error.
- ``send_errors() -> tuple[type[BaseException], ...]``: "not sendable right now" exception types
  (unregistered = ``()``, matches nothing in ``except``).
- ``normalize_sender(entry_type, external_id) -> str``: canonical allowlist key.
- ``consent_required() -> bool``: STOP/START handling and per-sender limit apply.
- ``extra_event_fields(event, gateway, sender) -> dict``: extra keys merged into the flow payload.
- ``recover_reply_parts(response) -> list[str]``: rebuild reply parts from a finished run's text
  (unregistered = the retry cannot be rebuilt).
- ``linked_sender_ids(gateway_name, primary) -> list[str]``: alias ids that share a sender identity.
- ``adapter_context(gateway, contact_name) -> dict | None``: ``gateway_context`` kwarg for the adapter.
- ``record_pending_room(gateway, chat_id) -> str``: create a Pending Room access entry for an unknown room that
  addressed the bot (Telegram only; unregistered = no Room entries, e.g. WhatsApp groups).
- ``reply_target(event) -> tuple[thread_id, reply_to_provider_message_id]``: where a reply goes.
- ``send_parts(gateway, event, parts, quote) -> Any``: send pre-formatted text parts in order.
- ``webhook_signals() -> bool``: record verify/signature health timestamps on the Gateway.
- ``mark_read_typing(adapter, provider_event_id) -> bool``: adapter-level read receipt + typing.
- ``failed_status(gateway_name, status) -> None``: record a failed outbound delivery status.
- ``conversation_key(event) -> str | None``: agent conversation key (default thread/conversation/sender).
- ``guest_reply(event, gateway, response) -> dict | None``: provider-specific reply path; non-None short-circuits.
- ``agent_runner(event, gateway) -> callable | None``: replacement for run_agent_sync (e.g. streaming) (WP-6).
- ``agent_instructions() -> str``: short channel note prepended to the agent prompt for this provider (WP-5).
- ``agent_event_context(event, gateway) -> str``: one-line note about the inbound message (ids the agent needs for
  reply/react/edit tools), appended to the channel note. Default none; failures yield no note.
- ``attempt_reply_parts(event, gateway, parts, attempt) -> dict``: provider-owned send/retry of reply parts (WP-1b).
- ``reply_finished(event, gateway) -> None``: the run ended (reply starting, suppressed or failed); stop any typing
  keepalive. Called guarded, never raises. WhatsApp does not register it.
- ``ingest_update(gateway, adapter, request) -> response | None``: handle a verified webhook update before
  ``normalize_inbound``; a non-None return is the HTTP response (non-message updates, drops) (WP-1c).
- ``readiness_checks(gateway, adapter) -> list[dict]``: extra provider readiness items for
  ``preview_gateway_readiness``, each ``{id, label, done, hint}``; appended after the core checks and counted in
  ``blocking_count`` / ``ready``. ``adapter`` is None when it cannot be built yet. Use ``readiness_checks(gateway)``
  below to dispatch (never raises; a hook failure becomes one failing ``provider-checks`` item).
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Callable

_HOOKS: dict[tuple[str, str], Callable[..., Any]] = {}
_loaded = False


def register(provider: str, hook_name: str, fn: Callable[..., Any]) -> None:
	_HOOKS[(provider, hook_name)] = fn


def _load() -> None:
	global _loaded
	if _loaded:
		return
	# Set first so a hook module that calls ``get`` while importing cannot recurse.
	_loaded = True
	# WhatsApp first and each provider isolated: a broken Telegram module must never unregister WhatsApp.
	for module in ("gateway_adapters.whatsapp_hooks", "gateway_adapters.telegram_hooks", "teams.hooks"):
		try:
			importlib.import_module(f"huf.ai.{module}")
		except Exception:
			logging.getLogger("huf").exception("Gateway provider hooks failed to load: %s", module)


def get(provider: str | None, hook_name: str, default: Any = None) -> Any:
	_load()
	return _HOOKS.get((str(provider or ""), hook_name), default)


def call(provider: str | None, hook_name: str, *a: Any, **kw: Any) -> Any:
	"""Call the hook; raises ``LookupError`` when unregistered (use ``get`` for a default)."""
	fn = get(provider, hook_name)
	if fn is None:
		raise LookupError(f"No '{hook_name}' hook registered for provider '{provider}'")
	return fn(*a, **kw)


def readiness_checks(gateway: Any) -> list[dict]:
	"""Run the provider's optional ``readiness_checks`` hook; ``[]`` when unregistered."""
	hook = get(getattr(gateway, "provider", None), "readiness_checks")
	if hook is None:
		return []
	try:
		try:
			from huf.ai.gateway_webhook import get_gateway_adapter

			adapter = get_gateway_adapter(gateway)
		except Exception:
			adapter = None
		items = list(hook(gateway, adapter) or [])
		return [  # extra provider keys (e.g. ``endpoint_url``) pass through; the four core keys are normalised
			{
				**i,
				"id": str(i["id"]),
				"label": str(i.get("label") or i["id"]),
				"done": bool(i.get("done")),
				"hint": None if i.get("done") else (i.get("hint") or "Not ready"),
			}
			for i in items
		]
	except Exception as exc:
		from huf.ai.gateway_service import _redact_error_text

		hint = _redact_error_text(str(exc)) or "Provider readiness checks failed"
		return [{"id": "provider-checks", "label": "Provider readiness checks", "done": False, "hint": hint}]
