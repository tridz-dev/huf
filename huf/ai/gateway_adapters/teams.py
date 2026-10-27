"""Microsoft Teams Gateway Adapter: thin delegates to :mod:`huf.ai.teams`."""

from __future__ import annotations

from typing import Any, Callable, Mapping

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
from huf.ai.teams.http import _requests_post


class TeamsGatewayAdapter(GatewayAdapter):
	"""Handle Microsoft Teams Bot Framework activities, replies, and Adaptive Cards."""

	# NOTE: must equal provider_to_service_id("Microsoft Teams") == "microsoft_teams"
	# (see huf.ai.gateway_adapters.provider_ids).
	provider_id = "microsoft_teams"
	credential_schema = GatewayCredentialSchema(
		(
			GatewayCredentialField("app_id", "Microsoft App ID"),
			GatewayCredentialField("app_password", "Microsoft App Secret / Password"),
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
		http_post: Callable[..., Any] = _requests_post,
	) -> None:
		missing = self.credential_schema.missing_required(credentials)
		if missing:
			raise ValueError(f"Microsoft Teams adapter is missing required credentials: {', '.join(missing)}")
		self._app_id = credentials["app_id"]
		self._app_password = credentials["app_password"]
		self._http_post = http_post

	def verify_inbound(self, request: GatewayInboundRequest) -> bool:
		from huf.ai.teams import auth

		return auth.verify_request(request, self._credentials())

	def normalize_inbound(self, request: GatewayInboundRequest) -> NormalizedGatewayEvent:
		from huf.ai.teams import activity

		return activity.normalize(request, self._credentials())

	def send_reply(self, reply: GatewayReply) -> OutboundDelivery:
		from huf.ai.teams import client

		return client.send_reply(reply, self._credentials(), self._http_post)

	def send_adaptive_card(self, conversation_id: str, card_content: dict[str, Any]) -> OutboundDelivery:
		from huf.ai.teams import client

		return client.send_adaptive_card(conversation_id, card_content, self._http_post)

	def _credentials(self) -> dict[str, str]:
		return {"app_id": self._app_id, "app_password": self._app_password}
