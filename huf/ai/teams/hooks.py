"""Teams provider hooks (skeleton), registered under the Gateway provider name ``Microsoft Teams``.

Only ``ingest_update`` is registered: it is the one hook whose ``None`` return means "carry on". Call
sites for most other hooks treat a registered hook's return value as authoritative (``reply_target``
must be a tuple, ``media_save`` a list, ...), so a blanket no-op registration would break the generic
defaults. Later work packages register additional hooks here as they implement them.
"""

from __future__ import annotations

from typing import Any

from huf.ai.gateway_adapters import provider_hooks

PROVIDER = "Microsoft Teams"


def ingest_update(gateway, adapter, request) -> Any:
	"""Called as ``(gateway, adapter, request)`` by gateway_webhook (the provider_hooks docstring lists
	another order). A non-None return becomes the HTTP response and skips normalize/ingest.

	Skeleton: ``None`` (continue normally). WP-T3 implements ignore signals and reference saving.
	"""
	return None


provider_hooks.register(PROVIDER, "ingest_update", ingest_update)

from huf.ai.teams import client as _client

_client.register_hooks(provider_hooks, PROVIDER)
