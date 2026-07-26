"""The provider contract implemented by each messaging gateway adapter."""

from __future__ import annotations

from abc import ABC, abstractmethod
from huf.ai.gateway_adapters.types import (
	GatewayCapabilities,
	GatewayCredentialSchema,
	GatewayInboundRequest,
	GatewayReply,
	NormalizedGatewayEvent,
	OutboundDelivery,
)


class GatewayAdapter(ABC):
	"""Fail-closed contract for one provider's inbound and outbound transport."""

	provider_id: str
	credential_schema: GatewayCredentialSchema
	capabilities: GatewayCapabilities

	@abstractmethod
	def verify_inbound(self, request: GatewayInboundRequest) -> bool:
		"""Return true only when the provider has authenticated this request."""

	@abstractmethod
	def normalize_inbound(self, request: GatewayInboundRequest) -> NormalizedGatewayEvent:
		"""Convert an already verified provider request into a Huf event."""

	@abstractmethod
	def send_reply(self, reply: GatewayReply) -> OutboundDelivery:
		"""Send an outbound reply and return the provider delivery receipt."""
