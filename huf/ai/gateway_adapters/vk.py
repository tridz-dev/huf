# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""VK Community Callback API adapter.

This adapter owns only VK's native verification, event normalization, and
outbound message request. A Gateway endpoint or long-poll worker is responsible
for passing verified events to Huf's routing foundation.
"""

from __future__ import annotations

import hmac
import json
import secrets
from collections.abc import Callable, Mapping
from typing import Any

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


VK_MESSAGES_SEND_URL = "https://api.vk.ru/method/messages.send"
VK_API_VERSION = "5.199"


def _requests_post(url: str, *, data: Mapping[str, str], timeout: int) -> Any:
	"""Lazily import requests so the SDK itself has no import-time dependency."""
	import requests

	return requests.post(url, data=data, timeout=timeout)


class VKGatewayAdapter(GatewayAdapter):
	"""Authenticate VK Callback API payloads and deliver text replies."""

	provider_id = "vk"
	credential_schema = GatewayCredentialSchema(
		(
			GatewayCredentialField("community_token", "Community access token"),
			GatewayCredentialField("callback_secret", "Callback API secret"),
			GatewayCredentialField("confirmation_string", "Callback confirmation string"),
		)
	)
	capabilities = GatewayCapabilities(
		frozenset({"webhook", "long_poll"}),
		supports_thread_reply=True,
		max_outbound_messages_per_second=20,
	)

	def __init__(
		self,
		credentials: Mapping[str, str],
		*,
		http_post: Callable[..., Any] = _requests_post,
		random_id_factory: Callable[[], int] | None = None,
	) -> None:
		missing = self.credential_schema.missing_required(credentials)
		if missing:
			raise ValueError(f"VK adapter is missing required credentials: {', '.join(missing)}")
		self._community_token = credentials["community_token"]
		self._callback_secret = credentials["callback_secret"]
		self._confirmation_string = credentials["confirmation_string"]
		self._http_post = http_post
		self._random_id_factory = random_id_factory or (lambda: secrets.randbelow(2**63))

	def confirmation_response(self, request: GatewayInboundRequest) -> str | None:
		"""Return VK's configured confirmation string for a confirmation request.

		The caller must return this exact string before normal event ingestion.
		Confirmation has its own handshake shape and is not a message event.
		"""
		payload = self._payload(request)
		if payload and payload.get("type") == "confirmation":
			return self._confirmation_string
		return None

	def verify_inbound(self, request: GatewayInboundRequest) -> bool:
		"""Fail closed unless this is a VK message event with the configured secret."""
		payload = self._payload(request)
		if not payload or payload.get("type") != "message_new":
			return False
		provided_secret = payload.get("secret")
		return isinstance(provided_secret, str) and hmac.compare_digest(provided_secret, self._callback_secret)

	def normalize_inbound(self, request: GatewayInboundRequest) -> NormalizedGatewayEvent:
		"""Normalize a verified VK ``message_new`` callback payload."""
		if not self.verify_inbound(request):
			raise ValueError("VK Callback API request was not verified")
		payload = self._payload(request) or {}
		message = (payload.get("object") or {}).get("message") or {}
		provider_event_id = str(payload.get("event_id") or "")
		sender_id = str(message.get("from_id") or "")
		conversation_id = str(message.get("peer_id") or "")
		if not provider_event_id or not sender_id or not conversation_id:
			raise ValueError("VK message event is missing event, sender, or peer identifiers")
		return NormalizedGatewayEvent(
			provider_event_id=provider_event_id,
			sender_id=sender_id,
			conversation_id=conversation_id,
			message_text=str(message.get("text") or ""),
			thread_id=str(message["conversation_message_id"]) if message.get("conversation_message_id") else None,
			is_room=int(conversation_id) >= 2_000_000_000,
			raw_payload=payload,
		)

	def send_reply(self, reply: GatewayReply) -> OutboundDelivery:
		"""Send a VK ``messages.send`` text reply using the community token."""
		try:
			peer_id = int(reply.conversation_id)
		except (TypeError, ValueError) as exc:
			raise ValueError("VK conversation_id must be a numeric peer_id") from exc

		data = {
			"access_token": self._community_token,
			"v": VK_API_VERSION,
			"peer_id": str(peer_id),
			"message": reply.text,
			"random_id": str(self._random_id_factory()),
		}
		if reply.reply_to_provider_message_id:
			data["reply_to"] = reply.reply_to_provider_message_id

		response = self._http_post(VK_MESSAGES_SEND_URL, data=data, timeout=10)
		if hasattr(response, "raise_for_status"):
			response.raise_for_status()
		body = response.json() if hasattr(response, "json") else response
		if not isinstance(body, Mapping):
			raise ValueError("VK messages.send returned an invalid response")
		if body.get("error"):
			error = body["error"]
			message = error.get("error_msg") if isinstance(error, Mapping) else "VK API rejected reply"
			raise ValueError(f"VK messages.send failed: {message}")
		message_id = body.get("response")
		if not message_id:
			raise ValueError("VK messages.send response did not include a message id")
		return OutboundDelivery(str(message_id), provider_response=body)

	@staticmethod
	def _payload(request: GatewayInboundRequest) -> dict[str, Any] | None:
		try:
			payload = json.loads(request.body.decode("utf-8"))
		except (UnicodeDecodeError, json.JSONDecodeError):
			return None
		return payload if isinstance(payload, dict) else None
