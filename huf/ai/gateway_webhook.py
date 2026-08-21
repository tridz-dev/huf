"""Runtime bridge between Gateway routing and provider-native adapters.

The module is intentionally lazy about provider imports: the Gateway foundation
can remain independently reviewable while regional adapter packages are merged
on top of the Adapter SDK.  A configured gateway still fails closed if its
adapter package or required credentials are unavailable.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from huf.ai.gateway_adapters.provider_ids import provider_to_service_id
from huf.ai.gateway_adapters.registered import get_adapter_class


def _adapter_class_for_provider(provider: str):
	"""Resolve a ``Gateway.provider`` display value to its adapter class.

	Routes through the shared ``provider_to_service_id`` transform and the
	``GatewayAdapterRegistry`` (via ``get_adapter_class``, which imports the
	adapter's module lazily on first use) rather than a hardcoded map.
	"""
	try:
		return get_adapter_class(provider_to_service_id(provider))
	except KeyError as exc:
		raise frappe.ValidationError(_("No installed Gateway Adapter supports this channel.")) from exc
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
		"display_name": getattr(event, "display_name", "") or "",
	}


def _text_response(value: str) -> None:
	"""Return a provider challenge as raw text rather than Frappe API JSON."""
	frappe.local.response.update(
		{"type": "txt", "doctype": "gateway-callback", "result": value}
	)


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def handle_gateway_webhook() -> dict | None:
	"""Verify a native provider callback, then hand only normalized data to Gateway.

	The URL contains a Gateway document name, never a credential.  Native
	verification happens before persistence or queueing, and no provider payload
	is normalized until that verification succeeds.

	gateway_name is read directly from the query string rather than taken as
	a function argument: every provider here posts application/json, and
	frappe.app.make_form_dict replaces frappe.form_dict wholesale with the
	parsed JSON body whenever Content-Type is JSON, so a query-string kwarg
	never actually reaches this function on a real webhook call.
	"""
	from huf.ai.gateway_service import ingest_gateway_event

	gateway_name = frappe.request.args.get("gateway_name") if frappe.request is not None else None
	if not gateway_name:
		return {"success": False, "error": "Missing gateway_name"}

	try:
		gateway = frappe.get_doc("Gateway", gateway_name)
	except frappe.DoesNotExistError:
		return {"success": False, "error": "Unknown gateway"}
	if not gateway.is_enabled:
		return {"success": False, "error": "Gateway is disabled"}

	adapter = get_gateway_adapter(gateway)
	request = _inbound_request()
	if request.method == "GET" and hasattr(adapter, "verify_url"):
		_text_response(adapter.verify_url(request) or "")
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
