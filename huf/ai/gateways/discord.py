"""Discord Interactions ingress for Huf Gateways.

Discord signs every Interaction using Ed25519 over the exact request timestamp
concatenated with the unmodified request body.  This adapter verifies that
signature before it acknowledges or stores anything.

Discord requires a response within three seconds.  Non-ping interactions are
therefore deferred and sent through the queue-first gateway service.  The
existing Discord agent tools remain the outbound capability; a later generic
agent-completion callback can use them to post an eventual answer.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from huf.ai.gateway_service import ingest_gateway_event


SIGNATURE_HEADER = "X-Signature-Ed25519"
TIMESTAMP_HEADER = "X-Signature-Timestamp"
PING = 1
APPLICATION_COMMAND = 2
DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE = 5


def _request_header(name: str) -> str:
	return (frappe.request.headers.get(name) or "").strip() if frappe.request else ""


def _request_body() -> bytes:
	return frappe.request.get_data() if frappe.request else b""


def _gateway_public_key(gateway) -> str:
	"""Read Discord's public key from the Gateway's linked credentials only."""
	if not gateway.integration_settings:
		return ""
	settings = frappe.get_doc("Integration Settings", gateway.integration_settings)
	if settings.service != "discord" or not settings.is_active:
		return ""
	for credential in settings.credentials:
		if credential.key == "interactions_public_key":
			return credential.get_password("value") or ""
	return ""


def verify_interaction_signature(public_key: str, signature: str, timestamp: str, body: bytes) -> bool:
	"""Return whether a Discord Ed25519 Interaction signature is valid."""
	if not all([public_key, signature, timestamp, body]):
		return False
	try:
		from cryptography.exceptions import InvalidSignature
		from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

		key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key))
		key.verify(bytes.fromhex(signature), timestamp.encode() + body)
		return True
	except (ImportError, InvalidSignature, ValueError, TypeError):
		return False


def _interaction_context(payload: dict) -> dict:
	member = payload.get("member") or {}
	user = member.get("user") or payload.get("user") or {}
	data = payload.get("data") or {}
	options = data.get("options") or []
	option_text = " ".join(str(option.get("value", "")) for option in options if option.get("value") is not None)
	command = str(data.get("name") or "interaction")
	return {
		"sender_id": str(user.get("id") or ""),
		"conversation_id": str(payload.get("channel_id") or ""),
		"thread_id": str((payload.get("message") or {}).get("id") or ""),
		"message_text": " ".join(part for part in [command, option_text] if part),
	}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=100, seconds=60)
def handle_interaction(gateway_name: str | None = None) -> dict:
	"""Verify and queue one Discord Interaction for a configured Gateway.

	The endpoint is ``/api/method/huf.ai.gateways.discord.handle_interaction``
	with a ``gateway_name`` query parameter.  It deliberately accepts only
	Discord application interactions, rather than unsigned message events.
	"""
	if not gateway_name or not frappe.db.exists("Gateway", gateway_name):
		return {"error": "Unknown gateway"}

	gateway = frappe.get_doc("Gateway", gateway_name)
	if gateway.provider != "Discord" or not gateway.is_enabled:
		return {"error": "Gateway is inactive"}

	body = _request_body()
	if not verify_interaction_signature(
		_gateway_public_key(gateway),
		_request_header(SIGNATURE_HEADER),
		_request_header(TIMESTAMP_HEADER),
		body,
	):
		frappe.local.response.http_status_code = 401
		return {"error": "Invalid Discord signature"}

	try:
		payload = json.loads(body)
	except (TypeError, ValueError):
		frappe.local.response.http_status_code = 400
		return {"error": "Invalid JSON payload"}

	if payload.get("type") == PING:
		return {"type": PING}
	if payload.get("type") != APPLICATION_COMMAND or not payload.get("id"):
		frappe.local.response.http_status_code = 400
		return {"error": "Unsupported Discord interaction"}

	context = _interaction_context(payload)
	if not context["sender_id"]:
		frappe.local.response.http_status_code = 400
		return {"error": "Discord interaction has no sender"}

	ingest_gateway_event(
		gateway.name,
		str(payload["id"]),
		context,
		verified_sender=True,
		raw_payload=payload,
	)
	return {"type": DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE}
