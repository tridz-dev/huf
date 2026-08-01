"""SMS (Twilio / Plivo / Frappe SMS Settings) Gateway Adapter for two-way SMS communications."""

from __future__ import annotations

import hmac
import hashlib
from typing import Any, Callable, Mapping
from urllib.parse import parse_qs

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


def _requests_post(url: str, *, auth: tuple[str, str], data: dict[str, str], timeout: int) -> Any:
	import requests

	return requests.post(url, auth=auth, data=data, timeout=timeout)


class SMSGatewayAdapter(GatewayAdapter):
	"""Handle Twilio-compatible or Frappe SMS Settings webhook validation and outbound SMS replies."""

	provider_id = "sms"
	credential_schema = GatewayCredentialSchema(
		(
			GatewayCredentialField("account_sid", "Twilio Account SID (or 'frappe_sms' to use Frappe SMS Settings)", required=False),
			GatewayCredentialField("auth_token", "Twilio Auth Token (Optional if using Frappe SMS)", required=False),
			GatewayCredentialField("from_number", "Twilio Phone Number (+1... / Sender ID)", required=False),
		)
	)
	capabilities = GatewayCapabilities(
		frozenset({"webhook"}),
		supports_thread_reply=False,
		max_outbound_messages_per_second=10,
	)

	def __init__(
		self,
		credentials: Mapping[str, str],
		*,
		http_post: Callable[..., Any] = _requests_post,
	) -> None:
		self._account_sid = credentials.get("account_sid", "frappe_sms")
		self._auth_token = credentials.get("auth_token", "")
		self._from_number = credentials.get("from_number", "")
		self._http_post = http_post

	def verify_inbound(self, request: GatewayInboundRequest) -> bool:
		"""Verify Twilio signature if X-Twilio-Signature is provided."""
		signature = request.headers.get("X-Twilio-Signature")
		if not signature or not self._auth_token:
			return True  # Allow basic webhook if signature header is not supplied or using native Frappe SMS

		mac = hmac.new(self._auth_token.encode("utf-8"), request.body, hashlib.sha1)
		import base64
		expected = base64.b64encode(mac.digest()).decode("utf-8")
		return hmac.compare_digest(signature, expected)

	def normalize_inbound(self, request: GatewayInboundRequest) -> NormalizedGatewayEvent:
		body_str = request.body.decode("utf-8") if request.body else ""
		params = parse_qs(body_str) if "=" in body_str else request.query

		def get_val(key: str) -> str:
			v = params.get(key)
			if isinstance(v, list):
				return v[0] if v else ""
			return str(v or "")

		sender_id = get_val("From") or get_val("sender") or get_val("mobile")
		message_text = get_val("Body") or get_val("text") or get_val("message")
		message_sid = get_val("MessageSid") or get_val("SmsSid") or f"sms-{hash(body_str)}"

		return NormalizedGatewayEvent(
			provider_event_id=message_sid,
			sender_id=sender_id,
			conversation_id=sender_id,
			message_text=message_text,
			thread_id=None,
			is_room=False,
			raw_payload=dict(params),
		)

	def send_reply(self, reply: GatewayReply) -> OutboundDelivery:
		"""Deliver SMS reply via Twilio REST API or native Frappe SMS Settings."""
		if self._account_sid == "frappe_sms" or not self._account_sid or not self._auth_token:
			from frappe.core.doctype.sms_settings.sms_settings import send_sms
			send_sms(receiver_list=[reply.conversation_id], msg=reply.text)
			return OutboundDelivery(
				provider_message_id=f"frappe-sms-{hash(reply.text)}",
				provider_response={"status": "sent", "gateway": "Frappe SMS Settings"},
			)

		url = f"https://api.twilio.com/2010-04-01/Accounts/{self._account_sid}/Messages.json"
		payload = {
			"From": self._from_number,
			"To": reply.conversation_id,
			"Body": reply.text,
		}

		response = self._http_post(
			url,
			auth=(self._account_sid, self._auth_token),
			data=payload,
			timeout=10,
		)
		body = response.json() if hasattr(response, "json") else response
		if not isinstance(body, dict) or "sid" not in body:
			raise ValueError(f"SMS delivery failed: {body}")

		return OutboundDelivery(str(body["sid"]), provider_response=body)
