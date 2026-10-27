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
from dataclasses import dataclass
from typing import Any

import frappe
from huf.ai.whatsapp import account_events as account_events_mod
from huf.ai.whatsapp import outbound_policy as policy
from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.gateway_adapters import whatsapp_calls as wc
from huf.ai.gateway_adapters import whatsapp_errors as we
from huf.ai.gateway_adapters import whatsapp_format as wf
from huf.ai.gateway_adapters import whatsapp_inbound as inbound
from huf.ai.gateway_adapters import whatsapp_messages as wm
from huf.ai.gateway_adapters import whatsapp_templates as wt
from huf.ai.gateway_adapters.whatsapp_bridge import direct_send_components, send_error
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

GRAPH_VERSION = bridge.GRAPH_DEFAULT_VERSION
META_GRAPH_URL = f"{bridge.GRAPH_HOST}/{GRAPH_VERSION}"
DEFAULT_TEMPLATE_LANGUAGE = "en_US"
_TEMPLATE_FIELD_KINDS = {
	"message_template_status_update": "status",
	"message_template_quality_update": "quality",
	"template_category_update": "category",
}
_MEDIA_TYPES = inbound.MEDIA_TYPES
# Webhook fields whose content is ingested; a change on any other field yields zero events.
_INGESTED_FIELDS = frozenset({"messages", "statuses", "calls"})
_ACCOUNT_EVENT_FIELDS = frozenset({"account_update", "user_preferences"})


def _log_ignored(reason: str) -> None:
	"""Log a dropped webhook change (reason only: never payload content, never a phone number)."""
	try:
		frappe.logger("huf.whatsapp").info(f"WhatsApp webhook change ignored: {reason}")
	except Exception:
		pass


def _log_info(line: str) -> None:
	try:
		frappe.logger("huf.whatsapp").info(line)
	except Exception:
		pass


class WhatsAppWindowClosed(frappe.ValidationError):
	"""The 24h customer-service window is closed and no template fallback is configured."""


class WhatsAppFallbackUnavailable(WhatsAppWindowClosed):
	"""The window is closed and the configured fallback template cannot be sent.

	Subclasses :class:`WhatsAppWindowClosed` so every caller that already treats a closed window as
	"not sendable right now" handles it. ``code`` is the stable machine-readable reason (a refusal is a
	raised typed error, not a delivery: ``OutboundDelivery`` requires a real provider message id).
	"""

	def __init__(self, message: str, code: str):
		super().__init__(message)
		self.code = code


class WhatsAppSendError(ValueError):
	"""A Graph send failed. ``classification`` is the :func:`whatsapp_errors.classify` result."""

	def __init__(self, message: str, classification: dict[str, Any] | None = None):
		super().__init__(message)
		self.classification = classification or we.classify(message)


class WhatsAppPartsError(Exception):
	"""A multi-part text reply stopped part-way.

	``sent_ids`` are the wamids already accepted by Meta (in order), ``remaining`` the formatted
	parts still to send, ``cause`` the original error. Retry the SEND with ``remaining`` only.
	"""

	def __init__(self, cause: BaseException, sent_ids: list[str], remaining: list[str]):
		super().__init__(str(cause))
		self.cause = cause
		self.sent_ids = list(sent_ids)
		self.remaining = list(remaining)


def classify_send_exception(exc: BaseException) -> dict[str, Any]:
	"""Classify whatever a WhatsApp send path raised (parts error, bridge error, Graph error, timeout)."""
	if isinstance(exc, WhatsAppPartsError):
		return classify_send_exception(exc.cause)
	if isinstance(exc, WhatsAppWindowClosed):
		return we.classify((None, {"error": {"code": 131047, "message": str(exc)}}))
	if isinstance(exc, WhatsAppSendError):
		return exc.classification
	if isinstance(exc, bridge.BridgeError):
		payload = exc.payload if isinstance(exc.payload, dict) else {}
		code = payload.get("graph_code")
		if code is not None or payload.get("kind"):
			base = we.classify((None, {"error": {"code": code, "message": payload.get("message") or ""}})) if code is not None else {}
			return {
				"code": code,
				"subcode": payload.get("subcode"),
				"kind": payload.get("kind") or base.get("kind") or "unknown",
				"retryable": bool(payload.get("retryable", base.get("retryable"))),
				"retry_after_hint": base.get("retry_after_hint"),
				"operator_text": payload.get("operator_text") or base.get("operator_text") or "",
				"user_msg": payload.get("user_msg"),
				"message": payload.get("message") or "",
				"http_status": base.get("http_status"),
			}
		return we.classify(str(payload.get("message") or payload.get("error") or exc))
	return we.classify(exc)


@dataclass(frozen=True)
class WhatsAppParsed:
	"""Everything actionable in one Meta webhook delivery (batched payloads, A5/A14)."""

	messages: tuple[NormalizedGatewayEvent, ...]
	statuses: tuple[dict, ...]
	template_updates: tuple[dict, ...]
	ignored: int
	unknown_phone_ids: tuple[str, ...] = ()
	calls: tuple[wc.WhatsAppCall, ...] = ()  # `calls` webhook field (normalised, metadata + in-memory SDP)
	account_events: tuple[dict, ...] = ()  # account_update / user_preferences, routed by WABA id or phone id


def _requests_post(url: str, *, json: dict, headers: dict, timeout: int) -> Any:
	import requests

	return requests.post(url, json=json, headers=headers, timeout=timeout)


class WhatsAppGatewayAdapter(GatewayAdapter):
	"""Authenticate Meta WhatsApp Cloud API webhooks and deliver window-aware replies."""

	provider_id = "whatsapp"
	credential_schema = GatewayCredentialSchema(
		(
			GatewayCredentialField(
				"phone_number_id", "Phone Number ID", secret=False,
				description="Meta app > WhatsApp > API setup, under the phone number.",
			),
			GatewayCredentialField(
				"business_account_id", "WhatsApp Business Account ID", secret=False,
				description="Meta app > WhatsApp > API setup, next to the phone number ID.",
			),
			GatewayCredentialField(
				"app_id", "Meta App ID", secret=False,
				description="Meta app dashboard > App settings > Basic.",
			),
			GatewayCredentialField(
				"access_token", "Permanent Access Token",
				description="A system user token from Meta Business settings, with WhatsApp messaging and management access.",
			),
			GatewayCredentialField(
				"app_secret", "Meta App Secret",
				description="Meta app dashboard > App settings > Basic. Used to confirm messages really come from Meta.",
			),
			GatewayCredentialField(
				"webhook_verify_token", "Webhook Verify Token",
				description="Any phrase you choose. Paste the same phrase into Meta when you add the webhook URL.",
			),
			GatewayCredentialField(
				"graph_api_version", "Graph API Version", required=False, secret=False,
				description=f"Optional. Defaults to {bridge.GRAPH_DEFAULT_VERSION}.",
			),
		)
	)
	# Needed to receive and send. The rest of the schema is required when the credential is saved
	# (it feeds templates, account linking and webhook subscription) but older gateways created
	# before those fields existed must keep running.
	runtime_credentials = ("phone_number_id", "access_token", "webhook_verify_token", "app_secret")
	capabilities = GatewayCapabilities(
		frozenset({"webhook"}),
		supports_text_reply=True,
		supports_thread_reply=False,  # A2: quoting never fragments the conversation
		supports_media_reply=True,  # send_media() and GatewayReply.attachments (url / media-id attachments)
		max_outbound_messages_per_second=80,
	)

	def __init__(
		self,
		credentials: Mapping[str, str],
		*,
		http_post: Callable[..., Any] = _requests_post,
		gateway_context: Mapping[str, Any] | None = None,
	) -> None:
		missing = [key for key in self.runtime_credentials if not str(credentials.get(key) or "").strip()]
		if missing:
			raise ValueError(f"WhatsApp adapter is missing required credentials: {', '.join(missing)}")
		self._phone_number_id = str(credentials["phone_number_id"]).strip()
		self._access_token = str(credentials["access_token"]).strip()
		self._verify_token = str(credentials["webhook_verify_token"]).strip()
		self._app_secret = str(credentials.get("app_secret") or "").strip()
		# graph_api_url is honoured only under frappe.flags.in_test (see bridge.graph_base_url);
		# graph_api_version (e.g. "v25.0") optionally pins a Graph version for this gateway.
		version = str(credentials.get("graph_api_version") or "").strip() or bridge.GRAPH_DEFAULT_VERSION
		self._graph_url = f"{bridge.graph_base_url(str(credentials.get('graph_api_url') or ''))}/{version}"
		self._http_post = http_post
		ctx = gateway_context or {}
		self._gateway_name = str(ctx.get("gateway_name") or "").strip()
		self._account = str(ctx.get("whatsapp_account") or "").strip()
		self._fallback_template = str(ctx.get("fallback_template") or "").strip()
		self._fallback_language = str(ctx.get("fallback_template_language") or "").strip() or DEFAULT_TEMPLATE_LANGUAGE
		raw_params = ctx.get("fallback_template_params")
		self._fallback_params: Any = (
			{str(k): str(v) for k, v in raw_params.items()}
			if isinstance(raw_params, dict)
			else [str(p) for p in raw_params]
			if isinstance(raw_params, (list, tuple))
			else None
		)
		self._contact_name = str(ctx.get("contact_name") or "").strip()
		# Optional: attribute template sends (e.g. the fallback template) to a run / solution for usage tracking.
		self._run_id = str(ctx.get("run_id") or "").strip()
		self._solution = str(ctx.get("solution") or "").strip()
		self._preview_url = str(ctx.get("preview_url") or "").strip().lower() == "on"

	# ------------------------------------------------------------------ ingress
	def verify_url(self, request: GatewayInboundRequest) -> str:
		"""Return Meta hub.challenge if the verify token matches the GET request."""
		query = request.query or {}
		mode = query.get("hub.mode") if "hub.mode" in query else query.get("hub_mode")
		if mode is not None and str(mode) != "subscribe":
			raise frappe.PermissionError("WhatsApp webhook verification mode must be subscribe")
		token = str(query.get("hub.verify_token") or query.get("hub_verify_token") or "")
		challenge = query.get("hub.challenge") or query.get("hub_challenge") or ""
		if token and hmac.compare_digest(token.encode("utf-8"), self._verify_token.encode("utf-8")):
			return challenge
		raise frappe.PermissionError("WhatsApp webhook verification token mismatch")

	def verify_inbound(self, request: GatewayInboundRequest) -> bool:
		"""Verify the Meta webhook signature (fail closed).

		GET: hub.verify_token must match. POST: X-Hub-Signature-256 must equal
		HMAC-SHA256(app_secret, body); a missing app_secret always fails.
		"""
		if request.method == "GET":
			query = request.query or {}
			token = str(query.get("hub.verify_token") or query.get("hub_verify_token") or "")
			return bool(token) and hmac.compare_digest(token.encode("utf-8"), self._verify_token.encode("utf-8"))

		if not self._app_secret:
			return False

		headers = request.headers or {}
		signature = headers.get("x-hub-signature-256") or headers.get("X-Hub-Signature-256")
		if not signature or not signature.startswith("sha256="):
			return False

		expected = hmac.new(self._app_secret.encode("utf-8"), request.body, "sha256").hexdigest()
		return hmac.compare_digest(signature[7:], expected)

	def parse_payload(self, request: GatewayInboundRequest) -> WhatsAppParsed:
		"""Parse every entry/change of a (possibly batched) payload. Never raises on benign content."""
		payload = self._payload(request)
		if payload is None:
			raise ValueError("Invalid JSON payload in WhatsApp request")

		messages: list[NormalizedGatewayEvent] = []
		statuses: list[dict] = []
		template_updates: list[dict] = []
		ignored = 0
		unknown_phone_ids: list[str] = []
		calls: list[wc.WhatsAppCall] = []
		account_events: list[dict] = []

		for entry in _as_list(payload.get("entry")):
			for change in _as_list(entry.get("changes") if isinstance(entry, dict) else None):
				if not isinstance(change, dict):
					ignored += 1
					continue
				value = change.get("value")
				if not isinstance(value, dict):
					ignored += 1
					continue
				field = change.get("field")
				if field in _TEMPLATE_FIELD_KINDS:
					# the WABA id (entry[].id) is what routes a template update to its WhatsApp Account
					waba_id = str(entry.get("id") or "") if isinstance(entry, dict) else ""
					template_updates.append({**value, "kind": _TEMPLATE_FIELD_KINDS[field], "waba_id": waba_id})
					continue
				if field in _ACCOUNT_EVENT_FIELDS and account_events_mod.is_relevant(field, value):
					# account_update has no phone metadata (routed by the WABA id, entry[].id); user_preferences
					# must name this gateway's number. A named phone id that is not ours is never applied.
					waba_id = str(entry.get("id") or "") if isinstance(entry, dict) else ""
					meta = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
					event_phone = str(meta.get("phone_number_id") or "")
					if (event_phone or field == "user_preferences") and not (
						event_phone and self._phone_id_accepted(event_phone)
					):
						ignored += 1
						if event_phone and event_phone not in unknown_phone_ids:
							unknown_phone_ids.append(event_phone)
						continue
					account_events.append({**value, "field": field, "waba_id": waba_id, "phone_id": event_phone})
					continue
				if field not in _INGESTED_FIELDS:
					# standby/echo/account_review/... : never ingest, only count and log (no payload content)
					ignored += 1
					_log_ignored(f"field_not_ingested field={str(field)[:64]}")
					continue
				items = _as_list(value.get("messages")) + _as_list(value.get("statuses")) + _as_list(value.get("calls"))
				metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
				phone_id = str(metadata.get("phone_number_id") or "")
				# Fail closed: a change without metadata.phone_number_id is ignored.
				if not phone_id or not self._phone_id_accepted(phone_id):
					if phone_id and phone_id not in unknown_phone_ids:
						unknown_phone_ids.append(phone_id)
					ignored += max(len(items), 1)
					continue
				if field == "calls" or "calls" in value or any(wc.is_call_status(x) for x in _as_list(value.get("statuses"))):
					found = wc.normalize_calls(value)
					calls.extend(found)
					ignored += max(len(_as_list(value.get("calls"))) - len([c for c in found if c.event != "status"]), 0)
				for status in _as_list(value.get("statuses")):
					if wc.is_call_status(status):
						continue  # handled above as a call status
					if isinstance(status, dict):
						statuses.append(dict(status))
					else:
						ignored += 1
				if "messages" not in value:
					if not value.get("statuses") and not value.get("calls"):
						ignored += 1  # account_update, errors-only, etc.
					continue
				names = _contact_names(value)
				for msg in _as_list(value.get("messages")):
					event = self._message_event(msg, metadata, names)
					if event is None:
						ignored += 1
					else:
						messages.append(event)

		return WhatsAppParsed(tuple(messages), tuple(statuses), tuple(template_updates), ignored, tuple(unknown_phone_ids), tuple(calls), tuple(account_events))

	def normalize_inbound(self, request: GatewayInboundRequest) -> NormalizedGatewayEvent:
		"""Return the first message event; ValueError only if nothing actionable exists."""
		parsed = self.parse_payload(request)
		if parsed.messages:
			return parsed.messages[0]
		if parsed.statuses or parsed.template_updates or parsed.calls:
			raise ValueError("WhatsApp payload carries only status or template events, no message")
		raise ValueError("WhatsApp payload contains no message, status or template events")

	def _phone_id_accepted(self, payload_phone_id: str) -> bool:
		if payload_phone_id != self._phone_number_id:
			return False
		if self._account and bridge.is_available():
			return bool(bridge.account_matches_phone_id(self._account, payload_phone_id))
		return True

	def _message_event(
		self, msg: Any, metadata: Mapping[str, Any], names: Mapping[str, str]
	) -> NormalizedGatewayEvent | None:
		if not isinstance(msg, dict):
			return None
		msg_type = msg.get("type") or "text"
		provider_event_id = str(msg.get("id") or "").strip()
		sender = bridge.normalize_phone(msg.get("from"))
		bsuid = bridge.normalize_phone(msg.get("from_user_id") or msg.get("user_id"))
		if not bridge.is_bsuid(bsuid):
			bsuid = ""
		if not sender and bsuid:
			sender = bsuid  # BSUID-only sender: key kept verbatim, never digit-normalised
			_log_info(f"WhatsApp bsuid_only_sender ingested tail=...{bsuid[-4:]}")
		if not provider_event_id or not sender:
			return None
		display = bridge.normalize_phone(metadata.get("display_phone_number"))
		if display and sender == display:
			# echo-shaped: the business's own number as sender must never become an inbound event
			_log_ignored("echo_shaped_message_dropped")
			return None
		try:
			return self._build_event(msg, msg_type, provider_event_id, sender, metadata, names, bsuid)
		except Exception:  # never let one odd message break a batch
			return None

	def _build_event(
		self, msg: dict, msg_type: str, provider_event_id: str, sender: str,
		metadata: Mapping[str, Any], names: Mapping[str, str], bsuid: str = "",
	) -> NormalizedGatewayEvent | None:
		emoji, reaction_to = "", ""
		kind = inbound.message_kind(msg_type)
		if msg_type == "reaction":
			message_text, emoji, reaction_to = inbound.render_reaction(msg)
		else:
			message_text = inbound.render_message_text(msg)
		if not message_text.strip():
			if kind in inbound.RECORD_ONLY_KINDS:
				message_text = f"[{kind} message]"
			else:
				return None

		attachments = []
		if msg_type in _MEDIA_TYPES:
			media = msg.get(msg_type) if isinstance(msg.get(msg_type), dict) else {}
			media_id = str(media.get("id") or "")
			if media_id:
				attachments.append(
					GatewayAttachment(
						mime_type=str(media.get("mime_type") or ""),
						filename=str(media.get("filename") or ""),
						file_id=media_id,
						kind=msg_type,
					)
				)

		context = msg.get("context") if isinstance(msg.get("context"), dict) else {}
		quoted = str(context.get("id") or "") or None
		raw: dict[str, Any] = {
			"message": msg,
			"metadata": dict(metadata),
			"quoted_message_id": quoted,
			"reply_to_message_id": quoted,
			"forwarded": bool(context.get("forwarded") or context.get("frequently_forwarded")),
		}
		contact_name = names.get(sender) or names.get(bsuid, "")
		if contact_name:
			raw["contact_name"] = contact_name  # for the fallback template's default parameter
		if bsuid:
			raw["bsuid"] = bsuid  # kept next to the phone key for a later identity merge
		referral = msg.get("referral") if isinstance(msg.get("referral"), dict) else {}
		referral_tag = inbound.extract_referral_tag(msg, message_text)  # before the ad prefix is added
		if referral_tag:
			raw["referral_tag"] = referral_tag
		if referral:
			raw["referral"] = {
				k: referral[k]
				for k in ("source_url", "source_id", "source_type", "headline", "body", "ctwa_clid")
				if referral.get(k)
			}
			headline = inbound.cap(referral.get("headline"), 120)
			if headline and kind == "message":
				message_text = f"[Ad referral: {headline}] {message_text}"
		button_payload = inbound.extract_button_payload(msg)
		if button_payload:
			raw["button_payload"] = button_payload
		if kind == "reaction":
			# Meta: a reaction is not a customer-service-window opener (UNVERIFIED in docs).
			# bridge.window_state must skip rows whose raw_payload.kind == "reaction".
			raw.update({"kind": "reaction", "reaction_to": reaction_to, "reaction_emoji": emoji})
		elif kind != "message":
			raw["kind"] = kind
			if kind in ("edit", "revoke"):
				original = msg.get(kind) if isinstance(msg.get(kind), dict) else {}
				raw["original_message_id"] = str(original.get("original_message_id") or "")
		return NormalizedGatewayEvent(
			provider_event_id=provider_event_id,
			sender_id=sender,
			conversation_id=sender,
			message_text=message_text,
			thread_id=None,  # A2: quoted id stays in raw_payload only
			is_room=False,
			raw_payload=raw,
			display_name=names.get(sender) or names.get(bsuid, ""),
			attachments=tuple(attachments),
			kind=kind,
			reaction_emoji=emoji,
			reaction_to=reaction_to,
		)

	# ------------------------------------------------------------------ egress
	def _bridge_mode(self) -> bool:
		return bool(self._account) and bridge.is_available()

	def send_reply(self, reply: GatewayReply) -> OutboundDelivery:
		"""Send a reply; window-aware (24h) with optional template fallback. One sender only (A1)."""
		if self._gateway_name:
			state = bridge.window_state(self._gateway_name, reply.conversation_id)
			if not state.get("open"):
				if self._fallback_template:
					return self._window_fallback(reply.conversation_id)
				self._guard(reply.conversation_id)
				raise WhatsAppWindowClosed(
					f"WhatsApp 24-hour customer-service window is closed for {reply.conversation_id}. "
					"Free-form replies are not allowed; set a Fallback template on the Gateway "
					"or wait for the customer to message again."
				)
		self._guard(reply.conversation_id)

		if reply.attachments:
			return self._send_reply_media(reply)

		parts = wf.split_body(wf.to_whatsapp(reply.text)) or ([str(reply.text)] if str(reply.text or "").strip() else [])
		if not parts:
			raise ValueError("Cannot send an empty WhatsApp reply")
		try:
			return self._send_parts(reply.conversation_id, parts, reply.reply_to_provider_message_id)
		except WhatsAppPartsError as exc:
			raise exc.cause from exc  # callers of send_reply see the underlying send error

	def send_text_parts(
		self, conversation_id: str, parts: list[str], reply_to: str | None = None
	) -> OutboundDelivery:
		"""Send already formatted text parts in order; each part only after the previous was accepted.

		The ``reply_to`` quote goes on the first part sent by this call only. On failure raises
		:class:`WhatsAppPartsError` (what was sent, what remains). A 131047 (window closed) on the very first
		part uses the Gateway's fallback template when one is configured.
		"""
		if self._gateway_name:
			state = bridge.window_state(self._gateway_name, conversation_id)
			if not state.get("open"):
				if self._fallback_template:
					return self._window_fallback(conversation_id)
				self._guard(conversation_id)
				raise WhatsAppWindowClosed(
					f"WhatsApp 24-hour customer-service window is closed for {conversation_id}. "
					"Free-form replies are not allowed; set a Fallback template on the Gateway "
					"or wait for the customer to message again."
				)
		self._guard(conversation_id)
		return self._send_parts(conversation_id, parts, reply_to)

	def _send_parts(self, conversation_id: str, parts: list[str], reply_to: str | None) -> OutboundDelivery:
		sent: list[str] = []
		responses: list[Mapping[str, Any]] = []
		for part in parts:
			try:
				delivery = self._send_text_part(conversation_id, part, reply_to if not sent else None)
			except Exception as exc:
				if not sent and self._fallback_template and classify_send_exception(exc).get("code") == 131047:
					return self._window_fallback(conversation_id)
				raise WhatsAppPartsError(exc, sent, list(parts[len(sent):])) from exc
			sent.append(delivery.provider_message_id)
			responses.append(delivery.provider_response)
		if not sent:
			raise ValueError("Cannot send an empty WhatsApp reply")
		return OutboundDelivery(
			provider_message_id=sent[0],
			provider_response={**dict(responses[0]), "message_ids": sent, "parts": len(sent)},
		)

	def _window_fallback(self, to: str) -> OutboundDelivery:
		"""Send the Gateway's fallback template with its body parameters.

		Refuses (raises :class:`WhatsAppFallbackUnavailable`) when the template is known and not APPROVED.
		Parameters: the Gateway's ``fallback_template_params`` when configured, else one default value per
		body variable (the contact name, or "there").
		"""
		try:
			policy.check_recipient(self._gateway_name or None, to)
		except policy.OutboundRefused as exc:
			code = "recipient_opted_out" if exc.code == "opted_out" else exc.code
			raise WhatsAppFallbackUnavailable(
				f"{exc} The 24-hour window is closed so the fallback template was not sent.", code
			) from exc
		language = self._fallback_language
		params: Any = self._fallback_params
		if self._bridge_mode():
			language = bridge.template_language(self._account, self._fallback_template, language) or language
			info = bridge.fallback_template_info(self._account, self._fallback_template, language)
			if isinstance(info, dict):
				status = str(info.get("status") or "").upper()
				if status and status != "APPROVED":
					raise WhatsAppFallbackUnavailable(
						f"WhatsApp fallback template '{self._fallback_template}' is {status.lower()}, not approved; "
						"the 24-hour window is closed so the reply was not sent.",
						"fallback_template_not_approved",
					)
				if params is None:
					variables = info.get("variables") or []
					default = self._contact_name or "there"
					params = {str(v): default for v in variables} if any(not str(v).isdigit() for v in variables) else [
						default for _ in variables
					]
		delivery = self.send_template(to, self._fallback_template, language, params or [], trusted=True)
		return OutboundDelivery(
			provider_message_id=delivery.provider_message_id,
			provider_response={**dict(delivery.provider_response), "fallback_template_sent": True},
		)

	def _send_text_part(self, to: str, text: str, reply_to: str | None) -> OutboundDelivery:
		if self._bridge_mode():
			return _delivery_from_bridge(
				bridge.send_text(
					self._account, to, text, reply_to=reply_to, trusted=True, preview_url=self._preview_url
				)
			)
		data: dict[str, Any] = {
			"messaging_product": "whatsapp",
			"recipient_type": "individual",
			"to": bridge.normalize_phone(to),
			"type": "text",
			"text": {"preview_url": self._preview_url, "body": text},
		}
		if reply_to:
			data["context"] = {"message_id": reply_to}
		return self._graph_send(data)

	def mark_read_typing(self, message_id: str) -> bool:
		"""Mark an inbound wamid read and show the typing indicator (<= 25 s). Best effort: never raises, no retry."""
		try:
			if not message_id:
				return False
			if self._bridge_mode():
				return bridge.mark_read_typing(self._account, message_id)
			response = self._http_post(
				f"{self._graph_url}/{self._phone_number_id}/messages",
				json=bridge.read_typing_payload(message_id),
				headers={"Authorization": f"Bearer {self._access_token}", "Content-Type": "application/json"},
				timeout=bridge.READ_TYPING_TIMEOUT,
			)
			status = getattr(response, "status_code", 200)
			return not (isinstance(status, int) and status >= 400)
		except Exception:
			return False

	def _send_reply_media(self, reply: GatewayReply) -> OutboundDelivery:
		"""Send the first attachment of a reply (caption = reply text), then audio's text separately."""
		att = reply.attachments[0]
		kind = (att.kind if att.kind in wt.MEDIA_KINDS else "") or _kind_from_mime(att.mime_type)
		# Audio and stickers cannot carry a caption (Meta rejects it): send the text separately.
		is_audio = kind in ("audio", "sticker")
		# Caption is formatted and <= 1024 chars; the remaining text follows as text parts (never lost).
		caption_parts = [] if is_audio else wf.split_body(wf.to_whatsapp(reply.text), wt.MAX_CAPTION)
		caption = caption_parts[0] if caption_parts else None
		delivery = self._deliver_media(
			reply.conversation_id,
			kind,
			link=att.url,
			media_id=None if att.url else att.file_id,
			caption=caption,
			filename=att.filename or None,
			reply_to=reply.reply_to_provider_message_id,
			trusted=True,
		)
		if is_audio and str(reply.text or "").strip():
			# No caption allowed: follow with the text as a normal message.
			text = self._send_text(reply)
			return OutboundDelivery(
				provider_message_id=text.provider_message_id,
				provider_response={**dict(text.provider_response), "media_message_id": delivery.provider_message_id},
			)
		if len(caption_parts) > 1:
			try:
				rest = self._send_parts(reply.conversation_id, caption_parts[1:], None)
			except WhatsAppPartsError as exc:
				raise exc.cause from exc
			return OutboundDelivery(
				provider_message_id=delivery.provider_message_id,
				provider_response={
					**dict(delivery.provider_response),
					"message_ids": [delivery.provider_message_id, *rest.provider_response.get("message_ids", [])],
				},
			)
		return delivery

	def _send_text(self, reply: GatewayReply) -> OutboundDelivery:
		parts = wf.split_body(wf.to_whatsapp(reply.text)) or [str(reply.text)]
		try:
			return self._send_parts(reply.conversation_id, parts, reply.reply_to_provider_message_id)
		except WhatsAppPartsError as exc:
			raise exc.cause from exc

	def send_media(
		self,
		to: str,
		kind: str,
		link: str | None = None,
		media_id: str | None = None,
		caption: str | None = None,
		filename: str | None = None,
		reply_to: str | None = None,
		trusted: bool = False,
		voice: bool | None = None,
	) -> OutboundDelivery:
		"""Send an image/document/audio/video/sticker (by public link or uploaded media id).

		Free-form media is subject to the same 24h customer-service window as text:
		a closed window raises :class:`WhatsAppWindowClosed` (there is no template
		fallback for media). ``voice=True`` sends audio as a voice note (Ogg/Opus).
		"""
		self._ensure_window(to)
		return self._deliver_media(to, kind, link, media_id, caption, filename, reply_to, trusted, voice)

	def _guard(self, to: str) -> None:
		"""Outbound policy (STOP, BSUID) for one recipient; raises :class:`OutboundRefused`."""
		policy.check_recipient(self._gateway_name or None, to)

	def _ensure_window(self, to: str) -> None:
		self._guard(to)
		if self._gateway_name and not bridge.window_state(self._gateway_name, to).get("open"):
			raise WhatsAppWindowClosed(
				f"WhatsApp 24-hour customer-service window is closed for {to}. "
				"Free-form media is not allowed; send an approved template or wait for the customer to message again."
			)

	def _deliver_media(
		self, to, kind, link=None, media_id=None, caption=None, filename=None, reply_to=None, trusted=False, voice=None
	) -> OutboundDelivery:
		if self._bridge_mode():
			return _delivery_from_bridge(
				bridge.send_media(
					self._account, to, kind, link=link, media_id=media_id, caption=caption,
					filename=filename, reply_to=reply_to, trusted=trusted, voice=voice,
				)
			)
		media, errors = wt.validate_media_request(kind, link, media_id, caption, filename, voice)
		if errors:
			raise bridge.BridgeError(wt.validation_error(errors))
		return self._graph_send(wt.build_media_payload(bridge.normalize_phone(to), media, reply_to))

	# ---------------------------------------------------- non-text types (T5)
	def send_sticker(
		self, to: str, link: str | None = None, media_id: str | None = None, reply_to: str | None = None,
		trusted: bool = False,
	) -> OutboundDelivery:
		"""Send a webp sticker by public link or uploaded media id (free-form: needs an open 24h window)."""
		self._ensure_window(to)
		if self._bridge_mode():
			return _delivery_from_bridge(
				bridge.send_sticker(self._account, to, link=link, media_id=media_id, reply_to=reply_to, trusted=trusted)
			)
		return self._send_built(wm.build_sticker_payload(bridge.normalize_phone(to), link, media_id, reply_to))

	def send_location(
		self, to: str, latitude: Any, longitude: Any, name: str | None = None, address: str | None = None,
		reply_to: str | None = None, trusted: bool = False,
	) -> OutboundDelivery:
		self._ensure_window(to)
		if self._bridge_mode():
			return _delivery_from_bridge(
				bridge.send_location(
					self._account, to, latitude, longitude, name=name, address=address, reply_to=reply_to, trusted=trusted
				)
			)
		return self._send_built(wm.build_location_payload(bridge.normalize_phone(to), latitude, longitude, name, address, reply_to))

	def send_contacts(self, to: str, contacts: Any, reply_to: str | None = None, trusted: bool = False) -> OutboundDelivery:
		self._ensure_window(to)
		if self._bridge_mode():
			return _delivery_from_bridge(bridge.send_contacts(self._account, to, contacts, reply_to=reply_to, trusted=trusted))
		return self._send_built(wm.build_contacts_payload(bridge.normalize_phone(to), contacts, reply_to))

	def send_reaction(
		self, to: str, message_id: str, emoji: str = "", remove: bool = False, trusted: bool = False
	) -> OutboundDelivery:
		"""React to an inbound message (<= 30 days old); an empty emoji / ``remove=True`` removes the reaction."""
		self._ensure_window(to)
		if self._bridge_mode():
			return _delivery_from_bridge(
				bridge.send_reaction(self._account, to, message_id, emoji, remove=remove, trusted=trusted)
			)
		return self._send_built(wm.build_reaction_payload(bridge.normalize_phone(to), message_id, emoji, remove))

	def send_interactive(
		self, to: str, kind: str, spec: dict[str, Any], reply_to: str | None = None, trusted: bool = False
	) -> OutboundDelivery:
		"""Reply buttons / list / CTA URL / flow / location request; ``spec`` carries that kind's fields."""
		self._ensure_window(to)
		if self._bridge_mode():
			return _delivery_from_bridge(
				bridge.send_interactive(self._account, to, kind, spec, reply_to=reply_to, trusted=trusted)
			)
		return self._send_built(wm.build_interactive_payload(bridge.normalize_phone(to), kind, spec or {}, reply_to))

	def upload_media(self, content: bytes, mime_type: str, filename: str = "", kind: str | None = None, voice: bool = False) -> str:
		"""Upload bytes to Meta (``POST /{phone_id}/media``) and return the media id."""
		if self._bridge_mode():
			return bridge.upload_media(self._account, content, mime_type, filename, kind, voice, trusted=True)["media_id"]
		mime = wm.normalize_mime(mime_type)
		kind, errors = wm.validate_upload(mime_type, content, kind, voice)
		if errors:
			raise bridge.BridgeError(wt.validation_error(errors))
		return bridge.post_media_upload(self._graph_url, self._phone_number_id, self._access_token, content, mime, filename)

	def _send_built(self, built: tuple[dict[str, Any] | None, list[dict[str, str]]]) -> OutboundDelivery:
		payload, errors = built
		if errors or payload is None:
			raise bridge.BridgeError(wt.validation_error(errors))
		return self._graph_send(payload)

	def send_template(
		self,
		to: str,
		template_name: str,
		language_code: str = DEFAULT_TEMPLATE_LANGUAGE,
		body_params: list | tuple | dict | None = None,
		trusted: bool = False,
		header_params: list | tuple | dict | None = None,
		button_params: list | tuple | None = None,
		run_id: str | None = None,
		solution: str | None = None,
	) -> OutboundDelivery:
		"""Send an approved template (always allowed, window-independent).

		``run_id`` / ``solution`` (optional; default to the adapter context) attribute the send to a Solution
		for template usage tracking.

		``body_params``: an ordered list, or (NAMED templates) ``{name: value}`` / ``[{name, value}]``; named
		values are sent with ``parameter_name``. ``header_params``: a text variable string, a ``{"type", "link"}``
		media dict or a ``{"type": "location", "latitude", "longitude"}`` dict. ``button_params``:
		``[{"index": 0, "sub_type": "url", "text": "<suffix>"}]`` or ``{"index": n, "sub_type": "copy_code", "code": ...}``.
		"""
		if isinstance(body_params, dict):
			params: Any = {str(k): str(v) for k, v in body_params.items()}
		else:
			params = [p if isinstance(p, dict) else str(p) for p in (body_params or [])]
		header_arg: Any = header_params if isinstance(header_params, dict) else list(header_params or [])
		self._guard(to)
		if self._bridge_mode():
			usage: dict[str, Any] = {}
			if run_id or self._run_id:
				usage["run_id"] = run_id or self._run_id
			if solution or self._solution:
				usage["solution"] = solution or self._solution
			result = bridge.send_template(
				self._account, to, template_name, params, header_params=header_arg,
				trusted=trusted, language_code=language_code, button_params=list(button_params or []),
				gateway_name=self._gateway_name or None, **usage,
			)
			return _delivery_from_bridge(result)
		components, errors = direct_send_components(params, header_arg, list(button_params or []))
		if errors:
			raise bridge.BridgeError(send_error(errors))
		template: dict[str, Any] = {"name": template_name, "language": {"code": language_code or DEFAULT_TEMPLATE_LANGUAGE}}
		if components:
			template["components"] = components
		delivery = self._graph_send(
			{
				"messaging_product": "whatsapp",
				"recipient_type": "individual",
				"to": bridge.normalize_phone(to),
				"type": "template",
				"template": template,
			}
		)
		if self._gateway_name:
			policy.record_template_outreach(self._gateway_name, to)
		return delivery

	def _graph_send(self, data: dict[str, Any]) -> OutboundDelivery:
		refusal = account_events_mod.send_refusal(self._phone_number_id)
		if refusal:
			raise WhatsAppSendError(refusal["message"], {"kind": "gateway_disconnected", "retryable": False, "message": refusal["message"]})
		url = f"{self._graph_url}/{self._phone_number_id}/messages"
		headers = {
			"Authorization": f"Bearer {self._access_token}",
			"Content-Type": "application/json",
		}
		try:
			response = self._http_post(url, json=data, headers=headers, timeout=15)
		except Exception as exc:
			raise WhatsAppSendError(f"WhatsApp API request failed: {bridge._redact(exc)}", we.classify(exc)) from exc
		status = getattr(response, "status_code", 200)
		if isinstance(status, int) and status >= 400:
			raise WhatsAppSendError(
				f"WhatsApp API error {status}: {bridge.graph_error_message(response)}", we.classify(response)
			)
		if hasattr(response, "raise_for_status"):
			try:
				response.raise_for_status()
			except Exception as exc:
				raise WhatsAppSendError(f"WhatsApp API error: {bridge._redact(exc)}", we.classify(exc)) from exc
		body = response.json() if hasattr(response, "json") else response
		if not isinstance(body, Mapping) or not body.get("messages"):
			raise WhatsAppSendError(f"WhatsApp API rejected outbound message: {body}", we.classify(body))
		return OutboundDelivery(provider_message_id=str(body["messages"][0]["id"]), provider_response=dict(body))

	@staticmethod
	def _payload(request: GatewayInboundRequest) -> dict[str, Any] | None:
		try:
			payload = json.loads(request.body.decode("utf-8"))
		except (UnicodeDecodeError, ValueError, TypeError, RecursionError):
			return None
		return payload if isinstance(payload, dict) else None


def _kind_from_mime(mime: str) -> str:
	prefix = (mime or "").split("/")[0].lower()
	return prefix if prefix in ("image", "audio", "video") else "document"


def _as_list(value: Any) -> list:
	return list(value) if isinstance(value, (list, tuple)) else []


def _contact_names(value: Mapping[str, Any]) -> dict[str, str]:
	names: dict[str, str] = {}
	for contact in _as_list(value.get("contacts")):
		if isinstance(contact, dict):
			wa_id = bridge.normalize_phone(contact.get("wa_id") or contact.get("user_id"))
			name = (contact.get("profile") or {}).get("name") if isinstance(contact.get("profile"), dict) else ""
			if wa_id and name:
				names[wa_id] = str(name)
	return names


def _delivery_from_bridge(result: Mapping[str, Any]) -> OutboundDelivery:
	message_id = str(result.get("message_id") or result.get("name") or "")
	return OutboundDelivery(provider_message_id=message_id, provider_response=dict(result))
