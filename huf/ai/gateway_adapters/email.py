"""Email Gateway Adapter for two-way Email communications using Frappe Communication and Email Account."""

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
	"""Handle incoming email webhooks and outbound email delivery via Frappe Communication Engine."""

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

	@property
	def sender_email(self) -> str:
		"""This gateway's configured outbound sender address, if any."""
		return self._sender_email

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
		conversation_id = sender_id
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
		"""Deliver email reply via frappe.sendmail and log Communication record."""
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

		# Log to Frappe Communication DocType
		try:
			comm = frappe.get_doc({
				"doctype": "Communication",
				"communication_type": "Communication",
				"communication_medium": "Email",
				"sent_or_received": "Sent",
				"sender": sender or frappe.session.user,
				"recipients": recipient,
				"subject": subject,
				"content": reply.text,
			})
			comm.insert(ignore_permissions=True)
			message_id = comm.name
		except Exception:
			message_id = f"email-{hash(reply.text)}"

		return OutboundDelivery(
			provider_message_id=message_id,
			provider_response={"status": "sent", "recipient": recipient},
		)


def on_communication_inserted(doc, method=None):
	"""Frappe doc_event hook triggered when a new Communication is created."""
	if doc.communication_type != "Communication" or doc.sent_or_received != "Received":
		return

	# Check if an Email Gateway exists and is enabled
	gateways = frappe.get_all(
		"Gateway",
		filters={"provider": "Email", "is_enabled": 1},
		fields=["name"],
	)
	if not gateways:
		return

	from huf.ai.gateway_service import ingest_gateway_event

	for gw in gateways:
		context = {
			"sender_id": doc.sender or "",
			"conversation_id": doc.sender or "",
			"thread_id": doc.in_reply_to or None,
			"message_text": doc.content or doc.subject or "",
		}
		ingest_gateway_event(
			gw["name"],
			doc.message_id or doc.name,
			context,
			verified_sender=True,
			raw_payload=doc.as_dict(),
		)
