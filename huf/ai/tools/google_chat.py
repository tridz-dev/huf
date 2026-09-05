"""
Google Chat integration tools for proactively posting to a space.

Uses HUF Integration Settings for credential management. Wraps
GoogleChatGatewayAdapter.send_reply/send_card (huf/ai/gateway_adapters/google_chat.py)
so this module never re-implements Google Chat authentication or REST
plumbing -- an Agent-callable tool and the inbound auto-reply path share the
exact same authenticated send code.
"""

import json

import frappe

logger = frappe.logger("huf")

from huf.ai.gateway_adapters.google_chat import GoogleChatGatewayAdapter
from huf.ai.gateway_adapters.types import GatewayReply
from huf.ai.tools.credentials import get_credential, update_last_error

SERVICE_NAME = "google_chat"


def _get_adapter() -> GoogleChatGatewayAdapter:
	credentials = {
		"audience": get_credential(SERVICE_NAME, "audience", ""),
		"service_account_key": get_credential(SERVICE_NAME, "service_account_key", ""),
		"webhook_url": get_credential(SERVICE_NAME, "webhook_url", ""),
	}
	return GoogleChatGatewayAdapter(credentials)


def handle_send_message(**kwargs) -> str:
	"""Proactively send a text message to a Google Chat space."""
	try:
		space_id = kwargs.get("space_id")
		message = kwargs.get("message")
		thread_id = kwargs.get("thread_id")
		if not all([space_id, message]):
			return json.dumps({"success": False, "error": "space_id and message are required"}, default=str)

		adapter = _get_adapter()
		reply = GatewayReply(conversation_id=space_id, text=message, thread_id=thread_id or None)
		delivery = adapter.send_reply(reply)

		return json.dumps({
			"success": True,
			"results": {"message_id": delivery.provider_message_id},
		})
	except Exception as e:
		error_msg = f"Google Chat Send Message Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_send_card(**kwargs) -> str:
	"""Proactively send a Card V2 interactive message to a Google Chat space."""
	try:
		space_id = kwargs.get("space_id")
		card = kwargs.get("card")
		thread_id = kwargs.get("thread_id")
		if not all([space_id, card]):
			return json.dumps({"success": False, "error": "space_id and card are required"}, default=str)

		if isinstance(card, str):
			try:
				card = json.loads(card)
			except Exception as exc:
				return json.dumps({"success": False, "error": f"card must be valid JSON: {exc}"}, default=str)

		adapter = _get_adapter()
		delivery = adapter.send_card(space_id, card, thread_id=thread_id or None)

		return json.dumps({
			"success": True,
			"results": {"message_id": delivery.provider_message_id},
		})
	except Exception as e:
		error_msg = f"Google Chat Send Card Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)
