# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""The ONE mapping between a Gateway's provider display value and everything downstream.

``Gateway.provider`` stores a human-readable display value (e.g. "Google Chat",
"Microsoft Teams") chosen from a Select field. That single string is expected
to also identify:

- the ``provider_id`` a ``GatewayAdapter`` subclass registers itself under
  (see ``huf.ai.gateway_adapters.registry.GatewayAdapterRegistry``), and
- the ``service_name`` of the ``Integration Service`` whose credentials the
  gateway's linked ``Integration Settings`` must use.

This module owns the ONE transform between those three. Every caller that
needs to go from a ``Gateway.provider`` value to either a ``provider_id`` or
a ``service_name`` should import ``provider_to_service_id`` from here instead
of re-deriving it (or hardcoding a lookup table), so the three stay in sync.

This module has no dependencies beyond the standard library, so it can be
imported from anywhere in the codebase (webhook routing, Document
validation, adapter registration) without risk of circular imports.
"""

from __future__ import annotations


def provider_to_service_id(provider: str) -> str:
	"""Return the canonical id for a ``Gateway.provider`` display value.

	e.g. ``"Google Chat"`` -> ``"google_chat"``, ``"WhatsApp"`` -> ``"whatsapp"``.

	This is the ONE mapping between a ``Gateway.provider`` display value, a
	``GatewayAdapter.provider_id``, and an ``Integration Service.service_name``.
	"""
	return provider.lower().replace(" ", "_")
