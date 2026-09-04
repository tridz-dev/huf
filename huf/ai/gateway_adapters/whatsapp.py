# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Meta WhatsApp Cloud API adapter for Huf Gateway.

Integrates WhatsApp Cloud API with Huf's fail-closed Gateway ingress and routing,
leveraging frappe_whatsapp for document persistence and message tracking.
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


def _requests_post(url: str, *, json: dict, headers: dict, timeout: int) -> Any:
	import requests

	return requests.post(url, json=json, headers=headers, timeout=timeout)


class WhatsAppGatewayAdapter(GatewayAdapter):
	"""Authenticate Meta WhatsApp Cloud API webhooks and deliver text replies."""

	provider_id = "whatsapp"
	credential_schema = GatewayCredentialSchema(
		(
			GatewayCredentialField("phone_number_id", "Phone Number ID", secret=False),
			GatewayCredentialField("access_token", "Meta Permanent/System Access Token"),
			GatewayCredentialField("webhook_verify_token", "Webhook Verify Token"),
			GatewayCredentialField("app_secret", "Meta App Secret (for HMAC signature verification)", required=True),
		)
	)
	capabilities = GatewayCapabilities(
		frozenset({"webhook"}),
		supports_text_reply=True,
		supports_thread_reply=True,
		supports_media_reply=True,
		max_outbound_messages_per_second=80,
	)

	def __init__(
		self,
		credentials: Mapping[str, str],
		*,
		http_post: Callable[..., Any] = _requests_post,
	) -> None:
		missing = self.credential_schema.missing_required(credentials)
		if missing:
			raise ValueError(f"WhatsApp adapter is missing required credentials: {', '.join(missing)}")
		self._phone_number_id = str(credentials["phone_number_id"]).strip()
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
		raise ValueError("WhatsApp webhook verification token mismatch")

	def verify_inbound(self, request: GatewayInboundRequest) -> bool:
		"""Verify Meta webhook signature using HMAC-SHA256.

		For GET requests (initial verification): validate hub.verify_token matches configured token.
		For POST requests (events): require X-Hub-Signature-256 HMAC-SHA256 signature verification.

		Fails closed (returns False) if:
		- POST request: X-Hub-Signature-256 header is missing or invalid
		- POST request: signature does not match HMAC-SHA256(app_secret, body)
		"""
		if request.method == "GET":
			query = request.query or {}
			token = query.get("hub.verify_token") or query.get("hub_verify_token")
			return bool(token and token == self._verify_token)

		# POST request: mandatory HMAC-SHA256 signature verification
		# app_secret is required (schema marks it required=True)
		if not self._app_secret:
			return False

		signature = request.headers.get("x-hub-signature-256") or request.headers.get("X-Hub-Signature-256")
		if not signature or not signature.startswith("sha256="):
			return False

		# Extract and validate the signature
		expected = hmac.new(self._app_secret.encode("utf-8"), request.body, "sha256").hexdigest()
		return hmac.compare_digest(signature[7:], expected)

	def normalize_inbound(self, request: GatewayInboundRequest) -> NormalizedGatewayEvent:
		"""Extract normalized event from Meta WhatsApp payload."""
		payload = self._payload(request)
		if not payload:
			raise ValueError("Invalid JSON payload in WhatsApp request")

		entries = payload.get("entry") or []
		if not entries:
			raise ValueError("WhatsApp payload has no entry array")

		entry = entries[0]
		changes = entry.get("changes") or []
		if not changes:
			raise ValueError("WhatsApp entry has no changes array")

		value = changes[0].get("value") or {}
		messages = value.get("messages") or []
		if not messages:
			raise ValueError("WhatsApp change payload contains no message events")

		msg = messages[0]
		provider_event_id = str(msg.get("id") or "")
		sender_id = str(msg.get("from") or "")
		conversation_id = sender_id  # WhatsApp DMs use sender phone number as conversation ID

		msg_type = msg.get("type", "text")
		message_text = ""
		if msg_type == "text":
			message_text = (msg.get("text") or {}).get("body") or ""
		elif msg_type == "interactive":
			interactive = msg.get("interactive") or {}
			if "button_reply" in interactive:
				message_text = (interactive["button_reply"]).get("title") or (interactive["button_reply"]).get("id") or ""
			elif "list_reply" in interactive:
				message_text = (interactive["list_reply"]).get("title") or (interactive["list_reply"]).get("id") or ""
		elif msg_type == "button":
			message_text = (msg.get("button") or {}).get("text") or ""
		else:
			message_text = (msg.get(msg_type) or {}).get("caption") or f"[{msg_type} message]"

		context = msg.get("context") or {}
		reply_to_id = str(context.get("id") or "") if context else None

		return NormalizedGatewayEvent(
			provider_event_id=provider_event_id,
			sender_id=sender_id,
			conversation_id=conversation_id,
			message_text=message_text,
			thread_id=reply_to_id,
			is_room=False,
			raw_payload=payload,
		)

	def send_reply(self, reply: GatewayReply) -> OutboundDelivery:
		"""Send outbound text message via Meta WhatsApp Cloud API and record in frappe_whatsapp."""
		url = f"{META_GRAPH_URL}/{self._phone_number_id}/messages"
		headers = {
			"Authorization": f"Bearer {self._access_token}",
			"Content-Type": "application/json",
		}
		data: dict[str, Any] = {
			"messaging_product": "whatsapp",
			"recipient_type": "individual",
			"to": reply.conversation_id,
			"type": "text",
			"text": {"preview_url": False, "body": reply.text},
		}
		if reply.reply_to_provider_message_id:
			data["context"] = {"message_id": reply.reply_to_provider_message_id}

		response = self._http_post(url, json=data, headers=headers, timeout=15)
		if hasattr(response, "raise_for_status"):
			response.raise_for_status()
		body = response.json() if hasattr(response, "json") else response

		if not isinstance(body, Mapping) or "messages" not in body:
			raise ValueError(f"WhatsApp API rejected outbound reply: {body}")

		msg_id = body["messages"][0]["id"]

		# Best-effort sync with frappe_whatsapp DocType if installed
		try:
			if frappe.db.exists("DocType", "WhatsApp Message"):
				frappe.get_doc({
					"doctype": "WhatsApp Message",
					"type": "Outgoing",
					"from": self._phone_number_id,
					"to": reply.conversation_id,
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
