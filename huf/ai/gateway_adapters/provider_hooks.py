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
- ``reply_target(event) -> tuple[thread_id, reply_to_provider_message_id]``: where a reply goes.
- ``send_parts(gateway, event, parts, quote) -> Any``: send pre-formatted text parts in order.
- ``webhook_signals() -> bool``: record verify/signature health timestamps on the Gateway.
- ``mark_read_typing(adapter, provider_event_id) -> bool``: adapter-level read receipt + typing.
- ``failed_status(gateway_name, status) -> None``: record a failed outbound delivery status.
"""

from __future__ import annotations

from typing import Any, Callable

_HOOKS: dict[tuple[str, str], Callable[..., Any]] = {}
_loaded = False


def register(provider: str, hook_name: str, fn: Callable[..., Any]) -> None:
	_HOOKS[(provider, hook_name)] = fn


def _load() -> None:
	global _loaded
	if _loaded:
		return
	_loaded = True
	import huf.ai.gateway_adapters.telegram_hooks  # noqa: F401
	import huf.ai.gateway_adapters.whatsapp_hooks  # noqa: F401


def get(provider: str | None, hook_name: str, default: Any = None) -> Any:
	_load()
	return _HOOKS.get((str(provider or ""), hook_name), default)


def call(provider: str | None, hook_name: str, *a: Any, **kw: Any) -> Any:
	"""Call the hook; raises ``LookupError`` when unregistered (use ``get`` for a default)."""
	fn = get(provider, hook_name)
	if fn is None:
		raise LookupError(f"No '{hook_name}' hook registered for provider '{provider}'")
	return fn(*a, **kw)
