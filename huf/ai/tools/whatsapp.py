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

META_GRAPH_URL = "https://graph.facebook.com/v18.0"


def _error(msg: str) -> str:
	return json.dumps({"success": False, "error": msg}, default=str)


def _success(data: Any) -> str:
	return json.dumps({"success": True, "data": data}, default=str)


def _get_whatsapp_credentials(kwargs: dict) -> tuple[str, str]:
	"""Get phone_number_id and access_token from arguments or Integration Settings."""
	phone_number_id = (kwargs.get("phone_number_id") or "").strip()
	access_token = (kwargs.get("access_token") or "").strip()

	if phone_number_id and access_token:
		return phone_number_id, access_token

	# Fallback to Integration Settings or WhatsApp Account DocType
	if frappe.db.exists("DocType", "WhatsApp Account"):
		accounts = frappe.get_all("WhatsApp Account", fields=["name", "phone_number_id"], limit=1)
		if accounts:
			doc = frappe.get_doc("WhatsApp Account", accounts[0].name)
			phone_number_id = phone_number_id or doc.phone_number_id or ""
			access_token = access_token or doc.get_password("token") or ""

	if not phone_number_id or not access_token:
		# Check Integration Settings
		settings_list = frappe.get_all("Integration Settings", filters={"service": "whatsapp", "is_active": 1}, limit=1)
		if settings_list:
			doc = frappe.get_doc("Integration Settings", settings_list[0].name)
			phone_number_id = phone_number_id or doc.get("phone_number_id") or ""
			for row in doc.credentials or []:
				if row.key == "access_token":
					access_token = access_token or row.get_password("value") or ""

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

	url = f"{META_GRAPH_URL}/{phone_number_id}/messages"
	headers = {
		"Authorization": f"Bearer {access_token}",
		"Content-Type": "application/json",
	}
	payload = {
		"messaging_product": "whatsapp",
		"recipient_type": "individual",
		"to": recipient,
		"type": "text",
		"text": {"preview_url": False, "body": message},
	}

	try:
		res = requests.post(url, json=payload, headers=headers, timeout=15)
		data = res.json()
		if res.status_code != 200 or "error" in data:
			return _error(f"WhatsApp API Error: {data.get('error', {}).get('message', res.text)}")

		msg_id = data.get("messages", [{}])[0].get("id")

		# Log in frappe_whatsapp if installed
		if frappe.db.exists("DocType", "WhatsApp Message"):
			try:
				frappe.get_doc({
					"doctype": "WhatsApp Message",
					"type": "Outgoing",
					"from": phone_number_id,
					"to": recipient,
					"message": message,
					"message_id": msg_id,
					"status": "Sent",
				}).insert(ignore_permissions=True)
			except Exception:
				pass

		return _success({"message_id": msg_id, "recipient": recipient, "status": "sent"})
	except Exception as e:
		return _error(f"Failed to send WhatsApp message: {str(e)}")


def _send_template(kwargs: dict) -> str:
	phone_number_id, access_token = _get_whatsapp_credentials(kwargs)
	recipient = (kwargs.get("to") or kwargs.get("recipient") or "").strip()
	template_name = (kwargs.get("template_name") or "").strip()
	language_code = (kwargs.get("language_code") or "en").strip()

	if not recipient or not template_name:
		return _error("Recipient ('to') and 'template_name' are required")
	if not phone_number_id or not access_token:
		return _error("WhatsApp credentials not found")

	url = f"{META_GRAPH_URL}/{phone_number_id}/messages"
	headers = {
		"Authorization": f"Bearer {access_token}",
		"Content-Type": "application/json",
	}
	payload = {
		"messaging_product": "whatsapp",
		"recipient_type": "individual",
		"to": recipient,
		"type": "template",
		"template": {
			"name": template_name,
			"language": {"code": language_code},
		},
	}

	try:
		res = requests.post(url, json=payload, headers=headers, timeout=15)
		data = res.json()
		if res.status_code != 200 or "error" in data:
			return _error(f"WhatsApp API Error: {data.get('error', {}).get('message', res.text)}")

		return _success(data)
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
		return _success(res.json())
	except Exception as e:
		return _error(f"Failed to fetch WhatsApp account info: {str(e)}")
