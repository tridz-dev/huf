"""Email Gateway Adapter for two-way Email communications."""

from __future__ import annotations

import json
from typing import Any, Callable, Mapping

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


class EmailGatewayAdapter(GatewayAdapter):
	"""Handle incoming email webhooks and outbound email delivery."""

	provider_id = "email"
	credential_schema = GatewayCredentialSchema(
		(
			GatewayCredentialField("webhook_secret", "Webhook Verification Secret (Optional)", required=False),
			GatewayCredentialField("sender_email", "Default Outbound Sender Email (Optional)", required=False),
		)
	)
	capabilities = GatewayCapabilities(
		frozenset({"webhook"}),
		supports_thread_reply=True,
		max_outbound_messages_per_second=10,
	)

	def __init__(
		self,
		credentials: Mapping[str, str],
	) -> None:
		self._secret = credentials.get("webhook_secret", "")
		self._sender_email = credentials.get("sender_email", "")

	def verify_inbound(self, request: GatewayInboundRequest) -> bool:
		"""Verify optional secret token if configured."""
		if not self._secret:
			return True
		token = request.headers.get("X-Webhook-Secret") or request.query.get("secret", "")
		return token == self._secret

	def normalize_inbound(self, request: GatewayInboundRequest) -> NormalizedGatewayEvent:
		if not self.verify_inbound(request):
			raise ValueError("Email webhook verification failed")

		try:
			payload = json.loads(request.body.decode("utf-8")) if request.body else request.query
		except Exception:
			payload = request.query

		sender_id = payload.get("from") or payload.get("sender") or ""
		conversation_id = payload.get("to") or payload.get("recipient") or sender_id
		message_text = payload.get("body") or payload.get("text") or payload.get("subject") or ""
		event_id = payload.get("message_id") or payload.get("id") or str(hash(f"{sender_id}:{message_text}"))

		return NormalizedGatewayEvent(
			provider_event_id=event_id,
			sender_id=sender_id,
			conversation_id=conversation_id,
			message_text=message_text.strip(),
			thread_id=payload.get("thread_id"),
			is_room=False,
			raw_payload=payload,
		)

	def send_reply(self, reply: GatewayReply) -> OutboundDelivery:
		"""Deliver email reply via frappe.sendmail."""
		recipient = reply.conversation_id
		subject = "Re: Agent Response"
		sender = self._sender_email or None

		frappe.sendmail(
			recipients=[recipient],
			subject=subject,
			message=reply.text,
			sender=sender,
			now=True,
		)

		return OutboundDelivery(
			provider_message_id=f"email-{hash(reply.text)}",
			provider_response={"status": "sent", "recipient": recipient},
		)
