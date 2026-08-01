# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Meta Facebook Messenger API adapter for Huf Gateway.

Integrates Facebook Page messaging with Huf's fail-closed Gateway ingress and routing,
leveraging frappe_messenger for document persistence and conversation tracking.
"""

from __future__ import annotations

import hmac
import json
from collections.abc import Callable, Mapping
from typing import Any

import frappe
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

META_GRAPH_URL = "https://graph.facebook.com/v18.0"


def _requests_post(url: str, *, json: dict, params: dict, timeout: int) -> Any:
	import requests

	return requests.post(url, json=json, params=params, timeout=timeout)


class MessengerGatewayAdapter(GatewayAdapter):
	"""Authenticate Facebook Messenger webhooks and deliver text replies."""

	provider_id = "messenger"
	credential_schema = GatewayCredentialSchema(
		(
			GatewayCredentialField("page_id", "Facebook Page ID", secret=False),
			GatewayCredentialField("access_token", "Facebook Page Access Token"),
			GatewayCredentialField("webhook_verify_token", "Webhook Verify Token"),
			GatewayCredentialField("app_secret", "Meta App Secret (for HMAC signature verification)", required=False),
		)
	)
	capabilities = GatewayCapabilities(
		frozenset({"webhook"}),
		supports_text_reply=True,
		supports_thread_reply=True,
		supports_media_reply=True,
		max_outbound_messages_per_second=50,
	)

	def __init__(
		self,
		credentials: Mapping[str, str],
		*,
		http_post: Callable[..., Any] = _requests_post,
	) -> None:
		missing = self.credential_schema.missing_required(credentials)
		if missing:
			raise ValueError(f"Messenger adapter is missing required credentials: {', '.join(missing)}")
		self._page_id = str(credentials["page_id"]).strip()
		self._access_token = str(credentials["access_token"]).strip()
		self._verify_token = str(credentials["webhook_verify_token"]).strip()
		self._app_secret = str(credentials.get("app_secret") or "").strip()
		self._http_post = http_post

	def verify_url(self, request: GatewayInboundRequest) -> str:
		"""Return Meta hub.challenge if verify token matches GET request."""
		query = request.query or {}
		token = query.get("hub.verify_token") or query.get("hub_verify_token")
		challenge = query.get("hub.challenge") or query.get("hub_challenge") or ""
		if token == self._verify_token:
			return challenge
		raise ValueError("Messenger webhook verification token mismatch")

	def verify_inbound(self, request: GatewayInboundRequest) -> bool:
		"""Verify Facebook Messenger webhook signature or object."""
		if request.method == "GET":
			query = request.query or {}
			token = query.get("hub.verify_token") or query.get("hub_verify_token")
			return bool(token and token == self._verify_token)

		if self._app_secret:
			signature = request.headers.get("x-hub-signature-256") or request.headers.get("X-Hub-Signature-256")
			if not signature or not signature.startswith("sha256="):
				return False
			expected = hmac.new(self._app_secret.encode("utf-8"), request.body, "sha256").hexdigest()
			return hmac.compare_digest(signature[7:], expected)

		payload = self._payload(request)
		if not payload or payload.get("object") not in ("page", "instagram"):
			return False
		return True

	def normalize_inbound(self, request: GatewayInboundRequest) -> NormalizedGatewayEvent:
		"""Extract normalized event from Facebook Messenger payload."""
		payload = self._payload(request)
		if not payload:
			raise ValueError("Invalid JSON payload in Messenger request")

		entries = payload.get("entry") or []
		if not entries:
			raise ValueError("Messenger payload has no entry array")

		entry = entries[0]
		messaging_events = entry.get("messaging") or []
		if not messaging_events:
			raise ValueError("Messenger entry has no messaging events")

		event = messaging_events[0]
		sender_id = str((event.get("sender") or {}).get("id") or "")
		recipient_id = str((event.get("recipient") or {}).get("id") or "")

		# Skip echo messages (sent by page itself)
		message = event.get("message") or {}
		if not message or message.get("is_echo"):
			raise ValueError("Messenger event is an echo or status update")

		provider_event_id = str(message.get("mid") or f"{sender_id}:{event.get('timestamp')}")
		message_text = str(message.get("text") or "")

		if not message_text and "attachments" in message:
			att_type = message["attachments"][0].get("type", "attachment")
			message_text = f"[{att_type} attachment]"

		return NormalizedGatewayEvent(
			provider_event_id=provider_event_id,
			sender_id=sender_id,
			conversation_id=sender_id,
			message_text=message_text,
			thread_id=str(message["reply_to"]["mid"]) if message.get("reply_to") else None,
			is_room=False,
			raw_payload=payload,
		)

	def send_reply(self, reply: GatewayReply) -> OutboundDelivery:
		"""Send outbound text message via Meta Graph API for Facebook Messenger."""
		url = f"{META_GRAPH_URL}/me/messages"
		params = {"access_token": self._access_token}
		data: dict[str, Any] = {
			"recipient": {"id": reply.conversation_id},
			"message": {"text": reply.text},
		}

		response = self._http_post(url, json=data, params=params, timeout=15)
		if hasattr(response, "raise_for_status"):
			response.raise_for_status()
		body = response.json() if hasattr(response, "json") else response

		if not isinstance(body, Mapping) or "message_id" not in body:
			raise ValueError(f"Messenger API rejected outbound reply: {body}")

		msg_id = body["message_id"]

		# Best-effort sync with frappe_messenger DocType if installed
		try:
			if frappe.db.exists("DocType", "Messenger Message"):
				frappe.get_doc({
					"doctype": "Messenger Message",
					"message_direction": "Outgoing",
					"sender_id": self._page_id,
					"recipient_id": reply.conversation_id,
					"message": reply.text,
					"message_id": msg_id,
					"status": "Sent",
				}).insert(ignore_permissions=True)
		except Exception:
			pass

		return OutboundDelivery(provider_message_id=str(msg_id), provider_response=dict(body))

	@staticmethod
	def _payload(request: GatewayInboundRequest) -> dict[str, Any] | None:
		try:
			payload = json.loads(request.body.decode("utf-8"))
		except (UnicodeDecodeError, json.JSONDecodeError):
			return None
		return payload if isinstance(payload, dict) else None
