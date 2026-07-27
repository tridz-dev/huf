"""Google Chat Gateway Adapter for two-way Google Workspace Chat communications."""

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


class GoogleChatGatewayAdapter(GatewayAdapter):
	"""Handle Google Chat webhook verification and message replies."""

	provider_id = "google_chat"
	credential_schema = GatewayCredentialSchema(
		(
			GatewayCredentialField("webhook_url", "Google Chat Incoming Webhook URL (Optional)", required=False),
			GatewayCredentialField("verification_token", "Verification Token (Optional)", required=False),
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
		self._webhook_url = credentials.get("webhook_url", "")
		self._verification_token = credentials.get("verification_token", "")
		self._http_post = http_post

	def verify_inbound(self, request: GatewayInboundRequest) -> bool:
		"""Verify verification_token if configured."""
		if not self._verification_token:
			return True
		try:
			payload = json.loads(request.body.decode("utf-8")) if request.body else {}
			return payload.get("token") == self._verification_token
		except Exception:
			return False

	def normalize_inbound(self, request: GatewayInboundRequest) -> NormalizedGatewayEvent:
		if not self.verify_inbound(request):
			raise ValueError("Google Chat verification token mismatch")

		try:
			payload = json.loads(request.body.decode("utf-8")) if request.body else {}
		except Exception as exc:
			raise ValueError("Invalid Google Chat JSON payload") from exc

		message = payload.get("message") or {}
		sender = payload.get("user") or message.get("sender") or {}
		space = payload.get("space") or message.get("space") or {}

		sender_id = str(sender.get("name") or sender.get("displayName") or "")
		space_name = str(space.get("name") or "")
		text = str(message.get("text") or payload.get("text") or "")
		event_id = str(message.get("name") or payload.get("eventTime") or hash(f"{sender_id}:{text}"))

		thread = message.get("thread") or {}
		thread_id = str(thread.get("name") or "") if thread else None

		return NormalizedGatewayEvent(
			provider_event_id=event_id,
			sender_id=sender_id,
			conversation_id=space_name,
			message_text=text.strip(),
			thread_id=thread_id,
			is_room=True,
			raw_payload=payload,
		)

	def send_reply(self, reply: GatewayReply) -> OutboundDelivery:
		"""Deliver Google Chat reply via webhook or REST API."""
		target_url = self._webhook_url
		if not target_url and reply.conversation_id.startswith("spaces/"):
			target_url = f"https://chat.googleapis.com/v1/{reply.conversation_id}/messages"

		if not target_url:
			raise ValueError("Google Chat adapter has no configured webhook_url or valid space target")

		data: dict[str, Any] = {"text": reply.text}
		if reply.thread_id:
			data["thread"] = {"name": reply.thread_id}

		response = self._http_post(
			target_url,
			headers={"Content-Type": "application/json"},
			json_data=data,
			timeout=10,
		)
		body = response.json() if hasattr(response, "json") else response
		msg_id = str(body.get("name") or f"gchat-{hash(reply.text)}") if isinstance(body, dict) else f"gchat-{hash(reply.text)}"

		return OutboundDelivery(msg_id, provider_response=body if isinstance(body, dict) else {"status": "ok"})
