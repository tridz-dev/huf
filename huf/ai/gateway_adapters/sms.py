"""SMS (Twilio / Plivo / Frappe SMS Settings) Gateway Adapter for two-way SMS communications."""

# PARKED PROVIDER (2026-09-05) - review completed by agent; owner sign-off pending.
# The fail-open inbound bypass was removed (see docs/gateways/SMS_SECURITY_REVIEW.md).
# Do not treat as production-approved until the owner signs off on provider choice and residual risks.

from __future__ import annotations

import base64
import hmac
import hashlib
import uuid
from typing import Any, Callable, Mapping
from urllib.parse import parse_qs

import frappe

from huf.ai.gateway_adapters.adapter import GatewayAdapter
from huf.ai.gateway_adapters.types import (
	GatewayAttachment,
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
			GatewayCredentialField("mode", "Mode: 'twilio' (inbound+send), 'send_only' (Twilio creds, inbound rejected) or 'frappe_sms' (Frappe SMS Settings, inbound rejected). Required.", required=True),
			GatewayCredentialField("account_sid", "Twilio Account SID (twilio/send_only modes)", required=False),
			GatewayCredentialField("auth_token", "Twilio Auth Token (twilio/send_only modes)", required=False),
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
		self._mode = str(credentials.get("mode", "") or "").strip().lower()
		self._account_sid = credentials.get("account_sid", "") or ""
		self._auth_token = credentials.get("auth_token", "") or ""
		self._from_number = credentials.get("from_number", "") or ""
		self._http_post = http_post

	def verify_inbound(self, request: GatewayInboundRequest) -> bool:
		"""Fail closed. Only explicit mode 'twilio' with credentials and a valid signature passes.

		Missing/unknown mode, send_only, frappe_sms, missing credentials, missing or
		invalid X-Twilio-Signature all return False.
		"""
		if self._mode != "twilio" or not self._auth_token or not self._account_sid:
			return False
		signature = request.headers.get("X-Twilio-Signature", "").strip()
		if not signature:
			return False
		mac = hmac.new(self._auth_token.encode("utf-8"), request.body or b"", hashlib.sha1)
		expected = base64.b64encode(mac.digest()).decode("utf-8")
		return hmac.compare_digest(signature, expected)

	def normalize_inbound(self, request: GatewayInboundRequest) -> NormalizedGatewayEvent:
		if not self.verify_inbound(request):
			raise PermissionError("SMS inbound rejected: unverified or inbound disabled")
		body_str = request.body.decode("utf-8") if request.body else ""
		params = parse_qs(body_str) if "=" in body_str else request.query

		def get_val(key: str) -> str:
			v = params.get(key)
			if isinstance(v, list):
				return v[0] if v else ""
			return str(v or "")

		sender_id = get_val("From") or get_val("sender") or get_val("mobile")
		message_text = get_val("Body") or get_val("text") or get_val("message")
		message_sid = get_val("MessageSid") or get_val("SmsSid") or f"sms-unknown-{uuid.uuid4().hex}"

		try:
			num_media = int(get_val("NumMedia") or "0")
		except ValueError:
			num_media = 0
		attachments = []
		for index in range(num_media):
			media_url = get_val(f"MediaUrl{index}")
			if not media_url:
				continue
			attachments.append(
				GatewayAttachment(
					mime_type=get_val(f"MediaContentType{index}"),
					url=media_url,
					kind="file",
				)
			)

		return NormalizedGatewayEvent(
			provider_event_id=message_sid,
			sender_id=sender_id,
			conversation_id=sender_id,
			message_text=message_text,
			thread_id=None,
			is_room=False,
			raw_payload=dict(params),
			attachments=tuple(attachments),
		)

	def send_reply(self, reply: GatewayReply) -> OutboundDelivery:
		"""Deliver SMS. Raises on any failure; never reports an unreal "sent" status."""
		if self._mode == "frappe_sms":
			from frappe.core.doctype.sms_settings.sms_settings import send_sms

			send_sms(receiver_list=[reply.conversation_id], msg=reply.text)
			# Frappe SMS Settings returns no provider id and no delivery receipt.
			return OutboundDelivery(
				provider_message_id=f"frappe-sms-unknown-{uuid.uuid4().hex}",
				provider_response={"status": "unknown", "gateway": "Frappe SMS Settings"},
			)
		if self._mode not in ("twilio", "send_only"):
			raise ValueError("SMS mode must be explicitly set to twilio, send_only or frappe_sms")
		if not self._account_sid or not self._auth_token or not self._from_number:
			raise ValueError("SMS delivery failed: account_sid, auth_token and from_number are required")

		url = f"https://api.twilio.com/2010-04-01/Accounts/{self._account_sid}/Messages.json"
		payload = {"From": self._from_number, "To": reply.conversation_id, "Body": reply.text}
		response = self._http_post(
			url, auth=(self._account_sid, self._auth_token), data=payload, timeout=10
		)
		body = response.json() if hasattr(response, "json") else response
		if not isinstance(body, dict) or not body.get("sid") or body.get("error_code"):
			raise ValueError(f"SMS delivery failed: {body}")
		return OutboundDelivery(str(body["sid"]), provider_response=body)


def send_sms_message(gateway: Mapping[str, str] | SMSGatewayAdapter, to: str, body: str) -> dict[str, Any]:
	"""Send one SMS for OTP/failover. Returns {ok, id, status, error}; never raises."""
	try:
		adapter = gateway if isinstance(gateway, SMSGatewayAdapter) else SMSGatewayAdapter(gateway)
		delivery = adapter.send_reply(GatewayReply(conversation_id=to, text=body))
		status = str(delivery.provider_response.get("status", "queued"))
		return {"ok": True, "id": delivery.provider_message_id, "status": status, "error": None}
	except Exception as exc:  # noqa: BLE001 - failover callers need a result, not a raise
		return {"ok": False, "id": None, "status": "failed", "error": str(exc)}
