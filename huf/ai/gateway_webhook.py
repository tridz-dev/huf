"""Runtime bridge between Gateway routing and provider-native adapters.

The module is intentionally lazy about provider imports: the Gateway foundation
can remain independently reviewable while regional adapter packages are merged
on top of the Adapter SDK.  A configured gateway still fails closed if its
adapter package or required credentials are unavailable.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

import frappe
from frappe import _


_ADAPTER_CLASSES = {
	"WhatsApp": ("huf.ai.gateway_adapters.whatsapp", "WhatsAppGatewayAdapter"),
	"Messenger": ("huf.ai.gateway_adapters.messenger", "MessengerGatewayAdapter"),
	"Instagram": ("huf.ai.gateway_adapters.instagram", "InstagramGatewayAdapter"),
	"Discord": ("huf.ai.gateway_adapters.discord", "DiscordGatewayAdapter"),
	"Email": ("huf.ai.gateway_adapters.email", "EmailGatewayAdapter"),
	"SMS": ("huf.ai.gateway_adapters.sms", "SMSGatewayAdapter"),
	"Google Chat": ("huf.ai.gateway_adapters.google_chat", "GoogleChatGatewayAdapter"),
	"Microsoft Teams": ("huf.ai.gateway_adapters.teams", "TeamsGatewayAdapter"),
	"VK": ("huf.ai.gateway_adapters.vk", "VKGatewayAdapter"),
	"WeCom": ("huf.ai.gateway_adapters.wecom", "WeComGatewayAdapter"),
}


def _adapter_class_for_provider(provider: str):
	try:
		module_name, class_name = _ADAPTER_CLASSES[provider]
	except KeyError as exc:
		raise frappe.ValidationError(_("No installed Gateway Adapter supports this channel.")) from exc
	try:
		return getattr(import_module(module_name), class_name)
	except (ImportError, AttributeError) as exc:
		raise frappe.ValidationError(
			_("The Gateway Adapter package for this channel is not installed.")
		) from exc


def _gateway_credentials(gateway) -> dict[str, str]:
	if not gateway.integration_settings:
		raise frappe.ValidationError(_("This gateway needs a connected integration for its credentials."))
	settings = frappe.get_doc("Integration Settings", gateway.integration_settings)
	credentials = {}
	for row in settings.credentials or []:
		if row.key:
			credentials[row.key] = row.get_password("value") or ""
	return credentials


def get_gateway_adapter(gateway):
	"""Instantiate the configured adapter without exposing stored credentials."""
	return _adapter_class_for_provider(gateway.provider)(_gateway_credentials(gateway))


def _inbound_request():
	from huf.ai.gateway_adapters.types import GatewayInboundRequest

	request = frappe.request
	if not request:
		raise frappe.ValidationError(_("A provider HTTP request is required."))
	return GatewayInboundRequest(
		body=request.get_data(),
		headers=dict(request.headers),
		query=dict(request.args),
		method=request.method,
	)


def _event_context(event) -> dict[str, Any]:
	return {
		"sender_id": event.sender_id,
		"conversation_id": event.conversation_id,
		"thread_id": event.thread_id,
		"message_text": event.message_text,
		"is_room": event.is_room,
		"mentioned": event.mentioned,
	}


def _text_response(value: str) -> None:
	"""Return a provider challenge as raw text rather than Frappe API JSON."""
	frappe.local.response.update(
		{"type": "txt", "doctype": "gateway-callback", "result": value}
	)


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def handle_gateway_webhook(gateway_name: str) -> dict | None:
	"""Verify a native provider callback, then hand only normalized data to Gateway.

	The URL contains a Gateway document name, never a credential.  Native
	verification happens before persistence or queueing, and no provider payload
	is normalized until that verification succeeds.
	"""
	from huf.ai.gateway_service import ingest_gateway_event

	try:
		gateway = frappe.get_doc("Gateway", gateway_name)
	except frappe.DoesNotExistError:
		return {"success": False, "error": "Unknown gateway"}
	if not gateway.is_enabled:
		return {"success": False, "error": "Gateway is disabled"}

	adapter = get_gateway_adapter(gateway)
	request = _inbound_request()
	if request.method == "GET" and hasattr(adapter, "verify_url"):
		_text_response(adapter.verify_url(request))
		return None
	if not adapter.verify_inbound(request):
		return {"success": False, "error": "Provider verification failed"}

	event = adapter.normalize_inbound(request)
	result = ingest_gateway_event(
		gateway.name,
		event.provider_event_id,
		_event_context(event),
		verified_sender=True,
		raw_payload=dict(event.raw_payload),
	)
	return {"success": True, **result}


def send_gateway_reply(gateway, event, text: str):
	"""Deliver one completed Agent response through the same verified gateway."""
	from huf.ai.gateway_adapters.types import GatewayReply

	adapter = get_gateway_adapter(gateway)
	return adapter.send_reply(
		GatewayReply(
			conversation_id=event.conversation_id,
			text=text,
			thread_id=event.thread_id or None,
			reply_to_provider_message_id=event.thread_id or None,
		)
	)
