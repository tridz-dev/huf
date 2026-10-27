"""Microsoft Teams Gateway Adapter: thin delegates to :mod:`huf.ai.teams`.

Supports single-tenant Azure bot registrations only (app_id + client secret + tenant_id). MultiTenant
bots, user-assigned managed identity (MSI) and sovereign clouds are out of scope.
"""

from __future__ import annotations

from typing import Any
from collections.abc import Callable, Mapping

from huf.ai.gateway_adapters.adapter import GatewayAdapter
from huf.ai.gateway_adapters.types import (
	GatewayCapabilities,
	GatewayCredentialField,
	GatewayCredentialSchema,
	GatewayInboundRequest,
	GatewayReply,
	NormalizedGatewayEvent,
	OutboundDelivery,
)


class TeamsGatewayAdapter(GatewayAdapter):
	"""Handle Microsoft Teams Bot Framework activities, and replies."""

	# NOTE: must equal provider_to_service_id("Microsoft Teams") == "microsoft_teams"
	# (see huf.ai.gateway_adapters.provider_ids).
	provider_id = "microsoft_teams"
	credential_schema = GatewayCredentialSchema(
		(
			GatewayCredentialField("app_id", "Microsoft App ID", secret=False),
			GatewayCredentialField("app_password", "Microsoft App Secret / Password"),
			GatewayCredentialField(
				"tenant_id",
				"Microsoft Entra Tenant ID",
				secret=False,
				description="Directory (tenant) ID of the single-tenant bot registration.",
			),
			GatewayCredentialField(
				"allowed_tenant_ids",
				"Allowed Tenant IDs",
				required=False,
				secret=False,
				description="Optional comma-separated tenant IDs allowed to message the bot.",
			),
		)
	)
	capabilities = GatewayCapabilities(
		frozenset({"webhook"}),
		supports_thread_reply=True,
		max_outbound_messages_per_second=20,
	)

	def __init__(
		self,
		credentials: Mapping[str, str],
		*,
		gateway_context: Mapping[str, Any] | None = None,
		transport: Callable[..., Any] | None = None,
	) -> None:
		missing = self.credential_schema.missing_required(credentials)
		if missing:
			raise ValueError(f"Microsoft Teams adapter is missing required credentials: {', '.join(missing)}")
		self._app_id = credentials["app_id"]
		self._app_password = credentials["app_password"]
		self._tenant_id = credentials["tenant_id"]
		self._allowed_tenant_ids = str(credentials.get("allowed_tenant_ids") or "")
		self._gateway_name = str((gateway_context or {}).get("gateway_name") or "")
		self._transport = transport

	def verify_inbound(self, request: GatewayInboundRequest) -> bool:
		from huf.ai.teams import auth

		return auth.verify_request(request, self._credentials())

	def normalize_inbound(self, request: GatewayInboundRequest) -> NormalizedGatewayEvent:
		from huf.ai.teams import activity

		return activity.normalize(request, self._credentials())

	def send_reply(self, reply: GatewayReply) -> OutboundDelivery:
		from huf.ai.teams import client

		return client.send_reply(
			reply, self._credentials(), gateway_name=self._gateway_name, transport=self._transport
		)

	def _credentials(self) -> dict[str, str]:
		return {
			"app_id": self._app_id,
			"app_password": self._app_password,
			"tenant_id": self._tenant_id,
			"allowed_tenant_ids": self._allowed_tenant_ids,
		}
