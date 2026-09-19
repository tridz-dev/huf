"""The provider contract implemented by each messaging gateway adapter."""

from __future__ import annotations

from abc import ABC, abstractmethod
from huf.ai.gateway_adapters.types import (
	GatewayCapabilities,
	GatewayCredentialSchema,
	GatewayInboundRequest,
	GatewayReply,
	GatewayTemplateSpec,
	GatewayTemplateStatus,
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

	# Template methods are intentionally not `@abstractmethod`: most adapters
	# declare `capabilities.supports_templates = False` and never implement
	# these. Callers must check that flag before invoking any of them.

	def list_templates(self) -> list[GatewayTemplateStatus]:
		"""Return every template known to the provider for this gateway's account."""
		raise NotImplementedError(f"{self.provider_id} adapter does not support templates")

	def push_template(self, template: GatewayTemplateSpec) -> GatewayTemplateStatus:
		"""Create (``external_id`` unset) or update (``external_id`` set) a template."""
		raise NotImplementedError(f"{self.provider_id} adapter does not support templates")

	def sync_template_status(self, external_id: str) -> GatewayTemplateStatus:
		"""Fetch the provider's current review/approval status for one template."""
		raise NotImplementedError(f"{self.provider_id} adapter does not support templates")

	def delete_template(self, external_id: str) -> None:
		"""Delete a template from the provider's account."""
		raise NotImplementedError(f"{self.provider_id} adapter does not support templates")
