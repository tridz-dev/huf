"""Microsoft Teams Outgoing Webhook adapter for the Gateway foundation.

This deliberately supports Teams *Outgoing Webhooks*, rather than pretending
to be a full Bot Framework adapter.  Teams sends an HMAC-signed Activity when
the webhook is @mentioned in a public channel; Huf verifies that signature,
records/routes the event through the provider-neutral Gateway service, then
returns a synchronous acknowledgement in the same Teams thread.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from huf.ai.gateway_service import ingest_gateway_event


TEAMS_SERVICE = "microsoft_teams"
HMAC_CREDENTIAL_KEY = "teams_outgoing_webhook_hmac_key"


def verify_teams_hmac(signing_key: str, raw_body: bytes, authorization: str | None) -> bool:
	"""Verify the `Authorization: HMAC <base64>` header from Teams.

	The signing key shown once by Teams is base64-encoded.  It is kept in the
	linked Integration Settings credential table, never in the Gateway Event.
	"""
	if not signing_key or not authorization:
		return False
	try:
		scheme, supplied = authorization.split(" ", 1)
		key = base64.b64decode(signing_key, validate=True)
	except (ValueError, TypeError):
		return False
	if scheme.lower() != "hmac" or not supplied:
		return False
	expected = base64.b64encode(hmac.new(key, raw_body, hashlib.sha256).digest()).decode("utf-8")
	return hmac.compare_digest(supplied.strip(), expected)


def teams_event_context(activity: dict[str, Any]) -> tuple[str, dict[str, Any]]:
	"""Normalize the stable subset of a Teams Activity needed by Gateways."""
	event_id = str(activity.get("id") or "")
	if not event_id:
		raise frappe.ValidationError(_("Microsoft Teams activity ID is required."))
	conversation = activity.get("conversation") or {}
	sender = activity.get("from") or {}
	return event_id, {
		"sender_id": str(sender.get("id") or ""),
		"conversation_id": str(conversation.get("id") or ""),
		"thread_id": str(activity.get("replyToId") or activity.get("id") or ""),
		"message_text": str(activity.get("text") or ""),
	}


def _gateway_settings(gateway_name: str):
	gateway = frappe.get_doc("Gateway", gateway_name)
	if not gateway.is_enabled:
		raise frappe.DoesNotExistError
	if gateway.provider != "Microsoft Teams":
		raise frappe.ValidationError(_("Gateway is not a Microsoft Teams gateway."))
	if not gateway.integration_settings:
		raise frappe.ValidationError(_("Microsoft Teams gateway needs a connected integration."))
	settings = frappe.get_doc("Integration Settings", gateway.integration_settings)
	if settings.service != TEAMS_SERVICE or not settings.is_active:
		raise frappe.ValidationError(_("Connected Microsoft Teams integration is not active."))
	return settings


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=100, seconds=60)
def handle_teams_outgoing_webhook(gateway_name: str) -> dict[str, str]:
	"""Receive a verified Teams Outgoing Webhook Activity and acknowledge it.

	This endpoint intentionally never runs a model inline: Microsoft gives an
	Outgoing Webhook only a short synchronous response window.  Huf queues the
	approved event and sends the fixed acknowledgement in the original thread.
	"""
	settings = _gateway_settings(gateway_name)
	raw_body = frappe.request.get_data(as_text=False)
	authorization = frappe.get_request_header("Authorization")
	if not verify_teams_hmac(settings.get_credential(HMAC_CREDENTIAL_KEY), raw_body, authorization):
		frappe.local.response["http_status_code"] = 401
		return {"type": "message", "text": "Unauthorized webhook request."}
	try:
		activity = json.loads(raw_body.decode("utf-8"))
	except (UnicodeDecodeError, json.JSONDecodeError):
		frappe.local.response["http_status_code"] = 400
		return {"type": "message", "text": "Invalid webhook payload."}

	# Ignore installation and other non-message Activities; a successful empty
	# response prevents Teams retrying an event that cannot start Huf work.
	if activity.get("type") != "message":
		return {"type": "message", "text": ""}
	event_id, context = teams_event_context(activity)
	result = ingest_gateway_event(
		gateway_name,
		event_id,
		context,
		verified_sender=True,
		raw_payload=activity,
	)
	if result.get("status") == "Queued" or result.get("duplicate"):
		return {"type": "message", "text": "Thanks — Huf has received your message."}
	return {"type": "message", "text": "This gateway is not accepting messages from this sender."}
