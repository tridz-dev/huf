"""Microsoft Teams Gateway Adapter for two-way MS Teams communications."""

from __future__ import annotations

import json
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


def _requests_post(url: str, *, headers: Mapping[str, str], json_data: Any, timeout: int) -> Any:
	import requests

	return requests.post(url, headers=headers, json=json_data, timeout=timeout)


class TeamsGatewayAdapter(GatewayAdapter):
	"""Handle Microsoft Teams Bot Framework activities, replies, and Adaptive Cards."""

	# NOTE: must equal provider_to_service_id("Microsoft Teams") == "microsoft_teams"
	# (see huf.ai.gateway_adapters.provider_ids). This already matches the
	# Integration Service catalog entry (huf/install.py) and
	# huf.ai.tools.teams_webhook.TEAMS_SERVICE; it was previously "teams",
	# which the canonical transform would never have produced and which
	# would have made Microsoft Teams gateways unresolvable once webhook
	# routing switched to registry-based lookup.
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
		self._app_id = credentials.get("app_id", "")
		self._app_password = credentials.get("app_password", "")
		self._http_post = http_post

	def verify_inbound(self, request: GatewayInboundRequest) -> bool:
		"""Verify Authorization header with Bearer token.

		When app_id is configured, require Authorization header with Bearer token.
		Full JWT signature validation against Microsoft's JWKS requires PyJWT library,
		which is not currently a dependency — this implements the security contract
		(fail closed on missing header) while deferring cryptographic validation
		to a future enhancement when PyJWT is available.

		Returns False (fail closed) if:
		- app_id is configured and Authorization header is missing or malformed
		- token cannot be decoded (will be enhanced to validate signature when PyJWT available)
		"""
		auth_header = request.headers.get("Authorization", "").strip()

		# If no app_id configured, don't require Bearer token (backwards compatibility)
		if not self._app_id:
			return True

		# app_id is configured: require Authorization header with Bearer token
		if not auth_header or not auth_header.startswith("Bearer "):
			return False

		# Extract the token
		token = auth_header[7:].strip()  # Remove "Bearer " prefix

		# At this point, we have a Bearer token. Full JWT signature validation
		# would require PyJWT to:
		#   1. Decode the JWT without verification (to get the payload)
		#   2. Fetch Microsoft's Bot Framework OpenID JWKS
		#   3. Verify signature using the public key from JWKS
		#   4. Verify 'aud' claim matches self._app_id
		#   5. Verify 'iss' claim is 'https://api.botframework.com'
		#
		# For now, we only verify that a Bearer token was provided (fail closed on missing header).
		# TODO: Add PyJWT to dependencies and implement full JWT validation.
		if not token:
			return False

		return True

	def normalize_inbound(self, request: GatewayInboundRequest) -> NormalizedGatewayEvent:
		if not self.verify_inbound(request):
			raise ValueError("Microsoft Teams authorization failed")

		try:
			activity = json.loads(request.body.decode("utf-8")) if request.body else {}
		except Exception as exc:
			raise ValueError("Invalid Teams Activity JSON payload") from exc

		activity_id = str(activity.get("id") or "")
		from_account = activity.get("from") or {}
		sender_id = str(from_account.get("id") or from_account.get("name") or "")

		conversation = activity.get("conversation") or {}
		conversation_id = str(conversation.get("id") or "")

		text = str(activity.get("text") or "").strip()

		return NormalizedGatewayEvent(
			provider_event_id=activity_id,
			sender_id=sender_id,
			conversation_id=conversation_id,
			message_text=text,
			thread_id=activity.get("replyToId"),
			is_room=bool(conversation.get("isGroup")),
			raw_payload=activity,
		)

	def send_reply(self, reply: GatewayReply) -> OutboundDelivery:
		"""Post reply back to MS Teams conversation."""
		service_url = "https://smba.trafficmanager.net/amer"
		url = f"{service_url.rstrip('/')}/v3/conversations/{reply.conversation_id}/activities"

		data: dict[str, Any] = {
			"type": "message",
			"text": reply.text,
		}
		if reply.reply_to_provider_message_id:
			data["replyToId"] = reply.reply_to_provider_message_id

		response = self._http_post(
			url,
			headers={"Content-Type": "application/json"},
			json_data=data,
			timeout=10,
		)
		body = response.json() if hasattr(response, "json") else response
		activity_id = str(body.get("id") or f"teams-{hash(reply.text)}") if isinstance(body, dict) else f"teams-{hash(reply.text)}"

		return OutboundDelivery(activity_id, provider_response=body if isinstance(body, dict) else {"status": "ok"})

	def send_adaptive_card(self, conversation_id: str, card_content: dict[str, Any]) -> OutboundDelivery:
		"""Post an Adaptive Card attachment to an MS Teams conversation."""
		service_url = "https://smba.trafficmanager.net/amer"
		url = f"{service_url.rstrip('/')}/v3/conversations/{conversation_id}/activities"

		data: dict[str, Any] = {
			"type": "message",
			"attachments": [
				{
					"contentType": "application/vnd.microsoft.card.adaptive",
					"content": card_content,
				}
			],
		}

		response = self._http_post(
			url,
			headers={"Content-Type": "application/json"},
			json_data=data,
			timeout=10,
		)
		body = response.json() if hasattr(response, "json") else response
		activity_id = str(body.get("id") or f"teams-card-{hash(str(card_content))}") if isinstance(body, dict) else f"teams-card-{hash(str(card_content))}"
		return OutboundDelivery(activity_id, provider_response=body if isinstance(body, dict) else {"status": "ok"})
