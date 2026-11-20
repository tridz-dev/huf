"""SMS gateway adapter (Twilio two-way, Twilio send-only, Frappe SMS Settings).

Modes (credential ``mode``, required, no inference): ``twilio`` (send + signed inbound),
``send_only`` (Twilio send, inbound always rejected), ``frappe_sms`` (Frappe SMS Settings
send, inbound always rejected).

Fail-closed guarantees: unset/unknown mode, missing credentials, a missing or wrong
X-Twilio-Signature, or an undeterminable request URL all reject inbound. Verification uses
Twilio's real scheme (URL + sorted POST params, HMAC-SHA1, constant-time compare; JSON bodies
also verify ``bodySHA256``). Send failures raise; ids are never fabricated as "sent".

Security review: docs/gateways/SMS_SECURITY_REVIEW.md
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from typing import Any, Callable, Mapping
from urllib.parse import parse_qsl, urlsplit

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
			GatewayCredentialField("webhook_base_url", "Public origin Twilio calls, e.g. https://crm.example.com (twilio mode; recommended behind proxies)", required=False, secret=False),
			GatewayCredentialField("trusted_proxy", "Set to 1 only if X-Forwarded-Proto/Host are set by your own proxy (twilio mode)", required=False, secret=False),
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
		self._webhook_base_url = str(credentials.get("webhook_base_url", "") or "").strip().rstrip("/")
		self._trusted_proxy = str(credentials.get("trusted_proxy", "") or "").strip().lower() in ("1", "true", "yes")
		self._http_post = http_post

	@staticmethod
	def _header(request: GatewayInboundRequest, name: str) -> str:
		for key, value in (request.headers or {}).items():
			if str(key).lower() == name.lower():
				return str(value).strip()
		return ""

	def _public_url(self, request: GatewayInboundRequest) -> str:
		"""The exact URL Twilio called, or "" when it cannot be determined (caller rejects)."""
		tail = (request.path or "") + (f"?{request.query_string}" if request.query_string else "")
		if self._webhook_base_url:
			if not self._webhook_base_url.startswith(("https://", "http://")) or not request.path:
				return ""
			return self._webhook_base_url + tail
		if self._trusted_proxy:
			proto = self._header(request, "X-Forwarded-Proto").split(",")[0].strip().lower()
			host = self._header(request, "X-Forwarded-Host").split(",")[0].strip()
			if proto not in ("http", "https") or not host or not request.path:
				return ""
			return f"{proto}://{host}{tail}"
		return request.url or ""

	@staticmethod
	def _url_candidates(url: str) -> list[str]:
		"""Twilio signs the URL as configured; accept it with or without the default port."""
		parts = urlsplit(url)
		if not parts.scheme or not parts.hostname:
			return []
		default = {"https": 443, "http": 80}.get(parts.scheme)
		out = [url]
		try:
			port = parts.port
		except ValueError:
			return []
		host = parts.hostname if ":" not in parts.hostname else f"[{parts.hostname}]"
		if port is not None and port == default:
			out.append(parts._replace(netloc=host).geturl())
		elif port is None and default:
			out.append(parts._replace(netloc=f"{host}:{default}").geturl())
		return out

	@staticmethod
	def _is_json(request: GatewayInboundRequest) -> bool:
		for key, value in (request.headers or {}).items():
			if str(key).lower() == "content-type":
				return "json" in str(value).lower()
		return False

	@staticmethod
	def _form_params(request: GatewayInboundRequest) -> list[tuple[str, str]]:
		body = (request.body or b"").decode("utf-8", "replace")
		if body:
			return parse_qsl(body, keep_blank_values=True)
		return list((request.query or {}).items()) if request.method.upper() == "GET" else []

	def verify_inbound(self, request: GatewayInboundRequest) -> bool:
		"""Fail closed. Only mode 'twilio' with credentials and a valid Twilio signature passes.

		X-Twilio-Signature = base64(HMAC-SHA1(auth_token, URL + sorted POST params as key+value)).
		For JSON bodies Twilio signs only the URL, which carries ?bodySHA256=<hex sha256(body)>;
		that hash is verified too.
		"""
		if self._mode != "twilio" or not self._auth_token or not self._account_sid:
			return False
		signature = self._header(request, "X-Twilio-Signature")
		if not signature:
			return False
		url = self._public_url(request)
		candidates = self._url_candidates(url) if url else []
		if not candidates:
			return False
		body = request.body or b""
		if self._is_json(request):
			query = dict(parse_qsl(urlsplit(url).query, keep_blank_values=True))
			expected_hash = hashlib.sha256(body).hexdigest()
			if not hmac.compare_digest(str(query.get("bodySHA256", "")).lower(), expected_hash):
				return False
			suffix = ""
		else:
			params = sorted(self._form_params(request))
			suffix = "".join(f"{k}{v}" for k, v in params)
		key = self._auth_token.encode("utf-8")
		ok = False
		for candidate in candidates:  # no early exit: keep timing independent of which matches
			mac = hmac.new(key, (candidate + suffix).encode("utf-8"), hashlib.sha1)
			expected = base64.b64encode(mac.digest()).decode("utf-8")
			ok |= hmac.compare_digest(signature.encode("utf-8"), expected.encode("utf-8"))
		return ok

	def normalize_inbound(self, request: GatewayInboundRequest) -> NormalizedGatewayEvent:
		if not self.verify_inbound(request):
			raise PermissionError("SMS inbound rejected: unverified or inbound disabled")
		if self._is_json(request):
			try:
				data = json.loads((request.body or b"").decode("utf-8") or "{}")
			except ValueError:
				data = {}
			params = {str(k): v for k, v in data.items()} if isinstance(data, dict) else {}
		else:
			params = {}
			for k, v in self._form_params(request):
				params.setdefault(k, v)

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

		# Only reached after verify_inbound (twilio mode + valid signature): STOP/START keywords update consent.
		from huf.ai.channels.channel_consent import handle_keyword

		handle_keyword("sms", sender_id, message_text, "sms_inbound")

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
