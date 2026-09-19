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
	GatewayAttachment,
	GatewayCapabilities,
	GatewayCredentialField,
	GatewayCredentialSchema,
	GatewayInboundRequest,
	GatewayReply,
	GatewayTemplateSpec,
	GatewayTemplateStatus,
	NormalizedGatewayEvent,
	OutboundDelivery,
)

META_GRAPH_URL = "https://graph.facebook.com/v18.0"


def _requests_post(url: str, *, json: dict, headers: dict, timeout: int) -> Any:
	import requests

	return requests.post(url, json=json, headers=headers, timeout=timeout)


def _requests_get(url: str, *, headers: dict, timeout: int) -> Any:
	import requests

	return requests.get(url, headers=headers, timeout=timeout)


def _requests_delete(url: str, *, headers: dict, timeout: int) -> Any:
	import requests

	return requests.delete(url, headers=headers, timeout=timeout)


class WhatsAppGatewayAdapter(GatewayAdapter):
	"""Authenticate Meta WhatsApp Cloud API webhooks and deliver text replies."""

	provider_id = "whatsapp"
	credential_schema = GatewayCredentialSchema(
		(
			GatewayCredentialField("phone_number_id", "Phone Number ID", secret=False),
			GatewayCredentialField("access_token", "Meta Permanent/System Access Token"),
			GatewayCredentialField("webhook_verify_token", "Webhook Verify Token"),
			GatewayCredentialField("app_secret", "Meta App Secret (for HMAC signature verification)", required=True),
			GatewayCredentialField("business_id", "WhatsApp Business Account ID", secret=False, required=True),
		)
	)
	capabilities = GatewayCapabilities(
		frozenset({"webhook"}),
		supports_text_reply=True,
		supports_thread_reply=True,
		supports_media_reply=False,  # GW-32: send_reply only sends text today
		supports_templates=True,
		max_outbound_messages_per_second=80,
	)

	def __init__(
		self,
		credentials: Mapping[str, str],
		*,
		http_post: Callable[..., Any] = _requests_post,
		http_get: Callable[..., Any] = _requests_get,
		http_delete: Callable[..., Any] = _requests_delete,
	) -> None:
		missing = self.credential_schema.missing_required(credentials)
		if missing:
			raise ValueError(f"WhatsApp adapter is missing required credentials: {', '.join(missing)}")
		self._phone_number_id = str(credentials["phone_number_id"]).strip()
		self._access_token = str(credentials["access_token"]).strip()
		self._verify_token = str(credentials["webhook_verify_token"]).strip()
		self._app_secret = str(credentials.get("app_secret") or "").strip()
		self._business_id = str(credentials["business_id"]).strip()
		self._http_post = http_post
		self._http_get = http_get
		self._http_delete = http_delete

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

		attachments = []
		if msg_type in ("image", "document", "audio", "video", "sticker"):
			media = msg.get(msg_type) or {}
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

		return NormalizedGatewayEvent(
			provider_event_id=provider_event_id,
			sender_id=sender_id,
			conversation_id=conversation_id,
			message_text=message_text,
			thread_id=reply_to_id,
			is_room=False,
			raw_payload=payload,
			attachments=tuple(attachments),
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

	def list_templates(self) -> list[GatewayTemplateStatus]:
		"""Fetch all message templates from Meta's account."""
		url = f"{META_GRAPH_URL}/{self._business_id}/message_templates"
		headers = {
			"Authorization": f"Bearer {self._access_token}",
		}
		response = self._http_get(url, headers=headers, timeout=15)
		if hasattr(response, "raise_for_status"):
			response.raise_for_status()
		body = response.json() if hasattr(response, "json") else response

		if not isinstance(body, Mapping) or "data" not in body:
			raise ValueError(f"WhatsApp template list API returned invalid response: {body}")

		templates = []
		for entry in body.get("data", []):
			if "id" in entry:
				quality_rating = None
				if "quality_score" in entry and isinstance(entry["quality_score"], Mapping):
					quality_rating = str(entry["quality_score"].get("score"))
				templates.append(
					GatewayTemplateStatus(
						external_id=str(entry["id"]),
						status=str(entry.get("status", "PENDING")),
						quality_rating=quality_rating,
					)
				)
		return templates

	def push_template(self, template: GatewayTemplateSpec) -> GatewayTemplateStatus:
		"""Create a new template or update an existing one."""
		headers = {
			"Authorization": f"Bearer {self._access_token}",
			"Content-Type": "application/json",
		}

		if not template.external_id:
			url = f"{META_GRAPH_URL}/{self._business_id}/message_templates"
			components_list = template.components.get("components", []) if template.components else []
			data = {
				"name": template.name,
				"language": template.language,
				"category": template.category.upper(),
				"components": components_list,
			}
			response = self._http_post(url, json=data, headers=headers, timeout=15)
			if hasattr(response, "raise_for_status"):
				response.raise_for_status()
			body = response.json() if hasattr(response, "json") else response

			if not isinstance(body, Mapping) or "id" not in body:
				raise ValueError(f"WhatsApp template creation API returned invalid response: {body}")

			return GatewayTemplateStatus(
				external_id=str(body["id"]),
				status=str(body.get("status", "PENDING")),
			)
		else:
			url = f"{META_GRAPH_URL}/{template.external_id}"
			components_list = template.components.get("components", []) if template.components else []
			data = {
				"components": components_list,
			}
			response = self._http_post(url, json=data, headers=headers, timeout=15)
			if hasattr(response, "raise_for_status"):
				response.raise_for_status()
			body = response.json() if hasattr(response, "json") else response

			if isinstance(body, Mapping) and "error" in body:
				raise ValueError(f"WhatsApp template update API returned error: {body['error']}")

			return GatewayTemplateStatus(
				external_id=template.external_id,
				status="PENDING",
			)

	def sync_template_status(self, external_id: str) -> GatewayTemplateStatus:
		"""Fetch the current review/approval status for one template."""
		url = f"{META_GRAPH_URL}/{external_id}"
		headers = {
			"Authorization": f"Bearer {self._access_token}",
		}
		response = self._http_get(url, headers=headers, timeout=15)
		if hasattr(response, "raise_for_status"):
			response.raise_for_status()
		body = response.json() if hasattr(response, "json") else response

		if not isinstance(body, Mapping) or "id" not in body:
			raise ValueError(f"WhatsApp template fetch API returned invalid response: {body}")

		quality_rating = None
		if "quality_score" in body and isinstance(body["quality_score"], Mapping):
			quality_rating = str(body["quality_score"].get("score"))

		return GatewayTemplateStatus(
			external_id=str(body["id"]),
			status=str(body.get("status", "PENDING")),
			quality_rating=quality_rating,
			rejected_reason=body.get("rejected_reason"),
		)

	def delete_template(self, external_id: str) -> None:
		"""Delete a template from the provider's account."""
		url = f"{META_GRAPH_URL}/{self._business_id}/message_templates"
		params_str = f"?hsm_id={external_id}"
		full_url = url + params_str
		headers = {
			"Authorization": f"Bearer {self._access_token}",
		}
		response = self._http_delete(full_url, headers=headers, timeout=15)
		if hasattr(response, "raise_for_status"):
			try:
				response.raise_for_status()
			except Exception as e:
				if "not found" in str(e).lower() or (hasattr(response, "status_code") and response.status_code == 404):
					return
				raise

		body = response.json() if hasattr(response, "json") else response
		if isinstance(body, Mapping) and "error" in body:
			error = body["error"]
			if isinstance(error, Mapping):
				error_code = error.get("code")
				if error_code == 368:
					return
				raise ValueError(f"WhatsApp template delete API returned error: {error}")
			elif "not found" not in str(error).lower():
				raise ValueError(f"WhatsApp template delete API returned error: {error}")
