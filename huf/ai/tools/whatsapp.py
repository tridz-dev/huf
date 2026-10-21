# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WhatsApp integration tools for HUF agents.

Single consolidated tool that performs Meta WhatsApp Cloud API actions via an
`action` parameter.
"""

import json
from typing import Optional, Any

import frappe
import requests

from huf.ai.gateway_adapters.whatsapp import META_GRAPH_URL, WhatsAppSender


def _error(msg: str) -> str:
	return json.dumps({"success": False, "error": msg}, default=str)


def _success(data: Any) -> str:
	return json.dumps({"success": True, "data": data}, default=str)


def _get_whatsapp_credentials(kwargs: dict) -> tuple[str, str]:
	"""Resolve (phone_number_id, access_token).

	Explicit arguments win. Otherwise use the credentials of the enabled
	WhatsApp Gateway's connected Integration Settings (the same source the
	gateway adapter uses), then fall back to a frappe_whatsapp WhatsApp Account.
	"""
	phone_number_id = (kwargs.get("phone_number_id") or "").strip()
	access_token = (kwargs.get("access_token") or "").strip()
	if phone_number_id and access_token:
		return phone_number_id, access_token

	try:
		from huf.ai.gateway_webhook import _gateway_credentials

		filters = {"provider": "WhatsApp", "is_enabled": 1}
		if kwargs.get("gateway"):
			filters["name"] = kwargs["gateway"]
		names = frappe.get_all("Gateway", filters=filters, pluck="name", limit=1)
		if names:
			creds = _gateway_credentials(frappe.get_doc("Gateway", names[0]))
			phone_number_id = phone_number_id or (creds.get("phone_number_id") or "").strip()
			access_token = access_token or (creds.get("access_token") or "").strip()
	except Exception:
		frappe.log_error(title="WhatsApp tool: gateway credential lookup failed")

	if (not phone_number_id or not access_token) and frappe.db.exists("DocType", "WhatsApp Account"):
		accounts = frappe.get_all("WhatsApp Account", fields=["name", "phone_number_id"], limit=1)
		if accounts:
			doc = frappe.get_doc("WhatsApp Account", accounts[0].name)
			phone_number_id = phone_number_id or doc.phone_number_id or ""
			access_token = access_token or doc.get_password("token") or ""

	return phone_number_id, access_token


def handle_action(action: str, **kwargs: Any) -> str:
	"""Handle WhatsApp agent tool invocation."""
	action = (action or "").strip().lower()

	if action == "send_message":
		return _send_message(kwargs)
	elif action == "send_template":
		return _send_template(kwargs)
	elif action == "list_messages":
		return _list_messages(kwargs)
	elif action == "get_account_info":
		return _get_account_info(kwargs)
	else:
		return _error(f"Unknown action '{action}'. Supported actions: send_message, send_template, list_messages, get_account_info")


def _send_message(kwargs: dict) -> str:
	phone_number_id, access_token = _get_whatsapp_credentials(kwargs)
	recipient = (kwargs.get("to") or kwargs.get("recipient") or kwargs.get("phone_number") or "").strip()
	message = (kwargs.get("message") or kwargs.get("text") or "").strip()

	if not recipient:
		return _error("Recipient phone number ('to') is required")
	if not message:
		return _error("Message text ('message') is required")
	if not phone_number_id or not access_token:
		return _error("WhatsApp credentials (phone_number_id and access_token) not found")

	try:
		delivery = WhatsAppSender(phone_number_id, access_token).send_text(recipient, message)
		return _success(
			{"message_id": delivery.provider_message_id, "recipient": recipient, "status": "sent"}
		)
	except Exception as e:
		return _error(f"Failed to send WhatsApp message: {str(e)}")


def _send_template(kwargs: dict) -> str:
	"""Send a pre-approved WhatsApp template message.

	``parameters``, when supplied, is a plain list of strings that fill the
	template's body placeholders in order (``{{1}}``, ``{{2}}``, ...) -- the
	shape the GW-36 template-selection UI builds from its structured
	parameter rows, rather than requiring a caller to hand-construct Meta's
	full ``components`` array.
	"""
	phone_number_id, access_token = _get_whatsapp_credentials(kwargs)
	recipient = (kwargs.get("to") or kwargs.get("recipient") or "").strip()
	template_name = (kwargs.get("template_name") or "").strip()
	language_code = (kwargs.get("language_code") or "en").strip()
	parameters = kwargs.get("parameters") or []

	if not recipient or not template_name:
		return _error("Recipient ('to') and 'template_name' are required")
	if not phone_number_id or not access_token:
		return _error("WhatsApp credentials not found")
	if not isinstance(parameters, list):
		return _error("'parameters' must be a list of strings")

	try:
		delivery = WhatsAppSender(phone_number_id, access_token).send_template(
			recipient, template_name, language_code, parameters
		)
		return _success(delivery.provider_response)
	except Exception as e:
		return _error(f"Failed to send WhatsApp template: {str(e)}")


def _list_messages(kwargs: dict) -> str:
	if not frappe.db.exists("DocType", "WhatsApp Message"):
		return _error("frappe_whatsapp app is not installed or enabled")

	limit = int(kwargs.get("limit") or 20)
	filters = {}
	if kwargs.get("to"):
		filters["to"] = kwargs["to"]
	if kwargs.get("from"):
		filters["from"] = kwargs["from"]

	try:
		messages = frappe.get_all(
			"WhatsApp Message",
			filters=filters,
			fields=["name", "type", "from", "to", "message", "status", "creation"],
			order_by="creation desc",
			limit=limit,
		)
		return _success(messages)
	except Exception as e:
		return _error(f"Failed to fetch WhatsApp messages: {str(e)}")


def _get_account_info(kwargs: dict) -> str:
	phone_number_id, access_token = _get_whatsapp_credentials(kwargs)
	if not phone_number_id or not access_token:
		return _error("WhatsApp credentials not found")

	url = f"{META_GRAPH_URL}/{phone_number_id}"
	headers = {"Authorization": f"Bearer {access_token}"}

	try:
		res = requests.get(url, headers=headers, timeout=10)
		data = res.json()
		if res.status_code != 200 or "error" in data:
			return _error(f"WhatsApp API Error: {data.get('error', {}).get('message', res.text)}")
		return _success(data)
	except Exception as e:
		return _error(f"Failed to fetch WhatsApp account info: {str(e)}")
