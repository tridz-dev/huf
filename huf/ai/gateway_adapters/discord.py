"""Discord Gateway Adapter for two-way messaging, DMs, interactions, and reactions."""

from __future__ import annotations

import json
from typing import Any, Callable, Mapping
from urllib.parse import quote

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


def _requests_put(url: str, *, headers: Mapping[str, str], timeout: int) -> Any:
	import requests

	return requests.put(url, headers=headers, timeout=timeout)


class DiscordGatewayAdapter(GatewayAdapter):
	"""Verify Discord Ed25519 interactions and deliver bot message replies, DMs, and reactions."""

	provider_id = "discord"
	credential_schema = GatewayCredentialSchema(
		(
			GatewayCredentialField("bot_token", "Discord Bot Token"),
			GatewayCredentialField("public_key", "Application Public Key (Ed25519)"),
		)
	)
	capabilities = GatewayCapabilities(
		frozenset({"webhook"}),
		supports_thread_reply=True,
		max_outbound_messages_per_second=50,
	)

	def __init__(
		self,
		credentials: Mapping[str, str],
		*,
		http_post: Callable[..., Any] = _requests_post,
		http_put: Callable[..., Any] = _requests_put,
	) -> None:
		missing = self.credential_schema.missing_required(credentials)
		if missing:
			raise ValueError(f"Discord adapter missing credentials: {', '.join(missing)}")
		self._bot_token = credentials["bot_token"]
		self._public_key = credentials["public_key"]
		self._http_post = http_post
		self._http_put = http_put

	def verify_inbound(self, request: GatewayInboundRequest) -> bool:
		"""Verify Ed25519 signature from Discord."""
		signature = request.headers.get("X-Signature-Ed25519", "").strip()
		timestamp = request.headers.get("X-Signature-Timestamp", "").strip()
		if not signature or not timestamp or not request.body:
			return False
		try:
			from cryptography.exceptions import InvalidSignature
			from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

			key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(self._public_key))
			key.verify(bytes.fromhex(signature), timestamp.encode() + request.body)
			return True
		except Exception:
			return False

	def normalize_inbound(self, request: GatewayInboundRequest) -> NormalizedGatewayEvent:
		if not self.verify_inbound(request):
			raise ValueError("Discord interaction signature verification failed")
		try:
			payload = json.loads(request.body.decode("utf-8"))
		except Exception as exc:
			raise ValueError("Invalid Discord JSON payload") from exc

		event_id = str(payload.get("id") or "")
		channel_id = str(payload.get("channel_id") or "")
		member = payload.get("member") or {}
		user = member.get("user") or payload.get("user") or {}
		sender_id = str(user.get("id") or "")

		data = payload.get("data") or {}
		command_name = str(data.get("name") or "message")
		options = data.get("options") or []
		message_text = f"/{command_name} " + " ".join(str(opt.get("value", "")) for option in options for opt in [option])

		return NormalizedGatewayEvent(
			provider_event_id=event_id,
			sender_id=sender_id,
			conversation_id=channel_id,
			message_text=message_text.strip(),
			thread_id=None,
			is_room=bool(payload.get("guild_id")),
			raw_payload=payload,
		)

	def send_reply(self, reply: GatewayReply) -> OutboundDelivery:
		"""Send reply message to a Discord channel or DM via REST API."""
		url = f"https://discord.com/api/v10/channels/{reply.conversation_id}/messages"
		headers = {
			"Authorization": f"Bot {self._bot_token}",
			"Content-Type": "application/json",
		}
		data: dict[str, Any] = {"content": reply.text}
		if reply.reply_to_provider_message_id:
			data["message_reference"] = {"message_id": reply.reply_to_provider_message_id}

		response = self._http_post(url, headers=headers, json_data=data, timeout=10)
		body = response.json() if hasattr(response, "json") else response
		if not isinstance(body, dict) or "id" not in body:
			raise ValueError(f"Discord message delivery failed: {body}")

		return OutboundDelivery(str(body["id"]), provider_response=body)

	def send_dm(self, user_id: str, text: str) -> OutboundDelivery:
		"""Create a DM channel with a user and send a direct message."""
		headers = {
			"Authorization": f"Bot {self._bot_token}",
			"Content-Type": "application/json",
		}
		dm_res = self._http_post(
			"https://discord.com/api/v10/users/@me/channels",
			headers=headers,
			json_data={"recipient_id": user_id},
			timeout=10,
		)
		dm_channel = dm_res.json() if hasattr(dm_res, "json") else dm_res
		channel_id = dm_channel.get("id")
		if not channel_id:
			raise ValueError(f"Failed to open DM channel with user {user_id}: {dm_channel}")

		return self.send_reply(GatewayReply(conversation_id=channel_id, text=text))

	def add_reaction(self, channel_id: str, message_id: str, emoji: str) -> bool:
		"""Add an emoji reaction to a Discord message."""
		headers = {"Authorization": f"Bot {self._bot_token}"}
		encoded_emoji = quote(emoji)
		url = f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}/reactions/{encoded_emoji}/@me"
		res = self._http_put(url, headers=headers, timeout=10)
		return getattr(res, "status_code", 200) in (200, 204)
