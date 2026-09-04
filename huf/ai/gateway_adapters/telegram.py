# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram Bot API adapter.

This adapter owns only Telegram's native webhook verification, update
normalization, and outbound ``sendMessage`` delivery. It has no Frappe
persistence and no knowledge of routing or admission policy.
"""

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


TELEGRAM_API_BASE = "https://api.telegram.org"
WEBHOOK_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


def _requests_post(url: str, *, json_data: Mapping[str, Any], timeout: int) -> Any:
	"""Lazily import requests so the SDK itself has no import-time dependency."""
	import requests

	return requests.post(url, json=json_data, timeout=timeout)


class TelegramGatewayAdapter(GatewayAdapter):
	"""Authenticate Telegram Bot API webhook updates and deliver text replies."""

	provider_id = "telegram"
	credential_schema = GatewayCredentialSchema(
		(
			GatewayCredentialField("token", "Telegram Bot Token"),
			GatewayCredentialField(
				"webhook_secret",
				"Webhook secret token",
				required=True,
				description=(
					"Value passed to Telegram's setWebhook secret_token; "
					"verified against the X-Telegram-Bot-Api-Secret-Token header."
				),
			),
		)
	)
	capabilities = GatewayCapabilities(
		frozenset({"webhook"}),
		supports_thread_reply=True,
		max_outbound_messages_per_second=30,
	)

	def __init__(
		self,
		credentials: Mapping[str, str],
		*,
		http_post: Callable[..., Any] = _requests_post,
	) -> None:
		missing = self.credential_schema.missing_required(credentials)
		if missing:
			raise ValueError("Telegram adapter is missing required credentials: " + ", ".join(missing))
		self._token = credentials["token"]
		self._webhook_secret = credentials.get("webhook_secret", "")
		self._http_post = http_post

	def verify_inbound(self, request: GatewayInboundRequest) -> bool:
		"""Verify webhook secret token using constant-time comparison.

		Requires webhook_secret to be configured at Gateway creation (no fallback).
		Fails closed (returns False) if:
		- webhook_secret is not configured
		- X-Telegram-Bot-Api-Secret-Token header is missing
		- provided secret does not match configured secret

		Uses hmac.compare_digest for constant-time comparison to prevent timing attacks.
		"""
		# Fail closed: webhook_secret is mandatory (schema marks it required=True)
		if not self._webhook_secret:
			return False

		# Look for secret in header
		provided = request.headers.get(WEBHOOK_SECRET_HEADER, "").strip()

		# Fail closed if header is not provided
		if not provided:
			return False

		# Use constant-time comparison to prevent timing attacks
		import hmac
		return hmac.compare_digest(provided, self._webhook_secret)

	def normalize_inbound(self, request: GatewayInboundRequest) -> NormalizedGatewayEvent:
		if not self.verify_inbound(request):
			raise ValueError("Telegram webhook secret verification failed")

		try:
			update = json.loads(request.body.decode("utf-8")) if request.body else {}
		except (UnicodeDecodeError, json.JSONDecodeError) as exc:
			raise ValueError("Invalid Telegram update payload") from exc

		message = update.get("message") or update.get("edited_message") or {}
		chat = message.get("chat") or {}
		sender = message.get("from") or {}

		provider_event_id = str(update.get("update_id") or "")
		sender_id = str(sender.get("id") or "")
		conversation_id = str(chat.get("id") or "")
		if not provider_event_id or not sender_id or not conversation_id:
			raise ValueError("Telegram update is missing update, sender, or chat identifiers")

		chat_type = str(chat.get("type") or "private")
		text = str(message.get("text") or message.get("caption") or "")
		mentioned = any(
			entity.get("type") in ("mention", "bot_command")
			for entity in (message.get("entities") or [])
		)

		username = str(sender.get("username") or "").strip()
		first_name = str(sender.get("first_name") or "").strip()
		display_name = f"@{username}" if username else first_name

		return NormalizedGatewayEvent(
			provider_event_id=provider_event_id,
			sender_id=sender_id,
			conversation_id=conversation_id,
			message_text=text,
			thread_id=str(message["message_id"]) if message.get("message_id") is not None else None,
			is_room=chat_type in {"group", "supergroup"},
			mentioned=mentioned,
			raw_payload=update,
			display_name=display_name,
		)

	def send_reply(self, reply: GatewayReply) -> OutboundDelivery:
		"""Send a Telegram ``sendMessage`` text reply using the bot token."""
		url = f"{TELEGRAM_API_BASE}/bot{self._token}/sendMessage"
		data: dict[str, Any] = {
			"chat_id": reply.conversation_id,
			"text": reply.text,
		}
		if reply.reply_to_provider_message_id:
			try:
				data["reply_to_message_id"] = int(reply.reply_to_provider_message_id)
			except (TypeError, ValueError):
				pass

		response = self._http_post(url, json_data=data, timeout=10)
		if hasattr(response, "raise_for_status"):
			response.raise_for_status()
		body = response.json() if hasattr(response, "json") else response
		if not isinstance(body, Mapping) or not body.get("ok"):
			description = body.get("description") if isinstance(body, Mapping) else "Telegram API rejected reply"
			raise ValueError(f"Telegram sendMessage failed: {description}")

		result = body.get("result") or {}
		message_id = result.get("message_id")
		if message_id is None:
			raise ValueError("Telegram sendMessage response did not include a message_id")
		return OutboundDelivery(str(message_id), provider_response=body)
