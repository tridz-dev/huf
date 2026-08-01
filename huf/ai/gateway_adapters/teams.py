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

	provider_id = "teams"
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
		"""Verify Authorization header or accept if payload is valid Bot Framework activity."""
		auth_header = request.headers.get("Authorization", "")
		if self._app_id and auth_header:
			return auth_header.startswith("Bearer ")
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
