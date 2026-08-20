# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Lazily populates the default ``GatewayAdapterRegistry`` with every installed adapter.

``huf.ai.gateway_webhook`` used to hardcode its own ``_ADAPTER_CLASSES`` map of
provider display name -> (module, class name), imported on demand via
``importlib``. That duplicated the ``GatewayAdapterRegistry`` (which already
exists precisely to be the single source of truth for "which adapter class
handles this provider") and was keyed differently (display name vs.
``provider_id``).

This module replaces it while preserving the historical *laziness*: an
adapter's module (and therefore its dependencies, e.g. ``cryptography`` for
WeCom) is only imported the first time that provider is actually requested,
not at import time of this module or of the ``huf.ai.gateway_adapters``
package. Configuring one gateway must not force every other provider
package to load.

Callers should use ``get_adapter_class(provider_id)`` rather than reaching
into ``default_registry`` directly, so the lazy-import step always runs
before a lookup.
"""

from __future__ import annotations

from importlib import import_module

from huf.ai.gateway_adapters.registry import GatewayAdapterRegistry

# provider_id -> (module path, class name).
#
# This is bookkeeping for *where to import from*, not a second provider ->
# service mapping: the key here is always a canonical provider_id (see
# huf.ai.gateway_adapters.provider_ids.provider_to_service_id), and once a
# module is imported the class is registered into `default_registry` under
# the `provider_id` it declares on itself - that registration is what
# actually makes the registry authoritative.
_ADAPTER_LOCATIONS: dict[str, tuple[str, str]] = {
	"whatsapp": ("huf.ai.gateway_adapters.whatsapp", "WhatsAppGatewayAdapter"),
	"telegram": ("huf.ai.gateway_adapters.telegram", "TelegramGatewayAdapter"),
	"messenger": ("huf.ai.gateway_adapters.messenger", "MessengerGatewayAdapter"),
	"instagram": ("huf.ai.gateway_adapters.instagram", "InstagramGatewayAdapter"),
	"email": ("huf.ai.gateway_adapters.email", "EmailGatewayAdapter"),
	"google_chat": ("huf.ai.gateway_adapters.google_chat", "GoogleChatGatewayAdapter"),
	"microsoft_teams": ("huf.ai.gateway_adapters.teams", "TeamsGatewayAdapter"),
	"slack": ("huf.ai.gateway_adapters.slack", "SlackGatewayAdapter"),
}

default_registry = GatewayAdapterRegistry()


def get_adapter_class(provider_id: str):
	"""Return the adapter class registered for ``provider_id``.

	Imports and registers the adapter's module on first use for that
	``provider_id``; subsequent calls are served from ``default_registry``
	without re-importing. Raises ``KeyError`` for a ``provider_id`` with no
	known adapter (e.g. ``"unknown_provider"``), matching ``GatewayAdapterRegistry.get``'s
	contract.
	"""
	if provider_id not in default_registry:
		module_name, class_name = _ADAPTER_LOCATIONS[provider_id]  # KeyError propagates as-is
		adapter_cls = getattr(import_module(module_name), class_name)
		default_registry.register(adapter_cls)
	return default_registry.get(provider_id)
