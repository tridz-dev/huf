"""Reusable contract checks for provider gateway adapter implementations."""

from __future__ import annotations

from huf.ai.gateway_adapters.adapter import GatewayAdapter
from huf.ai.gateway_adapters.types import GatewayInboundRequest, GatewayReply, NormalizedGatewayEvent


class GatewayAdapterConformanceError(ValueError):
	"""Raised when an adapter violates the minimum Huf gateway contract."""


def assert_adapter_conforms(
	adapter: GatewayAdapter,
	verified_request: GatewayInboundRequest,
	reply: GatewayReply,
) -> NormalizedGatewayEvent:
	"""Exercise the mandatory verified-inbound and outbound-reply contract.

	Provider packages call this from their own fixture tests. It deliberately does
	not make network calls or persist data; it verifies only the adapter boundary.
	"""
	if not isinstance(getattr(adapter, "provider_id", None), str) or not adapter.provider_id.strip():
		raise GatewayAdapterConformanceError("Adapter provider_id is required")
	if not adapter.credential_schema.fields:
		raise GatewayAdapterConformanceError("Adapter must declare a credential schema")
	if not adapter.capabilities.ingress_transports:
		raise GatewayAdapterConformanceError("Adapter must declare an ingress transport")
	if not adapter.capabilities.supports_text_reply:
		raise GatewayAdapterConformanceError("MVP adapters must support text replies")
	if not adapter.verify_inbound(verified_request):
		raise GatewayAdapterConformanceError("Verified fixture was rejected")

	event = adapter.normalize_inbound(verified_request)
	if not isinstance(event, NormalizedGatewayEvent):
		raise GatewayAdapterConformanceError("Adapter did not return a NormalizedGatewayEvent")
	delivery = adapter.send_reply(reply)
	if not delivery.accepted:
		raise GatewayAdapterConformanceError("Adapter rejected the outbound reply")
	return event
