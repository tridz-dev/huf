# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Facebook Messenger and Instagram Direct integration tools for HUF agents.

Single consolidated tool that performs Facebook Messenger and Instagram Direct
actions via an `action` parameter.
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


def _get_messenger_credentials(kwargs: dict) -> tuple[str, str, str]:
	"""Get page_id, access_token, and platform from arguments or Integration Settings."""
	page_id = (kwargs.get("page_id") or "").strip()
	access_token = (kwargs.get("access_token") or "").strip()
	platform = (kwargs.get("platform") or "messenger").strip().lower()

	if page_id and access_token:
		return page_id, access_token, platform

	# Fallback to Messenger Settings
	if frappe.db.exists("DocType", "Messenger Settings"):
		try:
			doc = frappe.get_single("Messenger Settings")
			if platform == "instagram":
				page_id = page_id or doc.instagram_page_id or doc.page_id or ""
			else:
				page_id = page_id or doc.page_id or ""
			access_token = access_token or doc.get_password("access_token") or ""
		except Exception:
			pass

	return page_id, access_token, platform


def handle_action(action: str, **kwargs: Any) -> str:
	"""Handle Messenger/Instagram agent tool invocation."""
	action = (action or "").strip().lower()

	if action in ("send_message", "reply_message"):
		return _send_message(kwargs)
	elif action == "list_conversations":
		return _list_conversations(kwargs)
	elif action == "list_messages":
		return _list_messages(kwargs)
	else:
		return _error(f"Unknown action '{action}'. Supported actions: send_message, list_conversations, list_messages")


def _send_message(kwargs: dict) -> str:
	page_id, access_token, platform = _get_messenger_credentials(kwargs)
	recipient_id = (kwargs.get("recipient_id") or kwargs.get("to") or kwargs.get("psid") or "").strip()
	message = (kwargs.get("message") or kwargs.get("text") or "").strip()

	if not recipient_id:
		return _error("Recipient ID ('recipient_id') is required")
	if not message:
		return _error("Message text ('message') is required")
	if not access_token:
		return _error("Meta access_token not found in settings or arguments")

	url = f"{META_GRAPH_URL}/me/messages"
	params = {"access_token": access_token}
	payload = {
		"recipient": {"id": recipient_id},
		"message": {"text": message},
	}

	try:
		res = requests.post(url, json=payload, params=params, timeout=15)
		data = res.json()
		if res.status_code != 200 or "error" in data:
			return _error(f"Meta Graph API Error: {data.get('error', {}).get('message', res.text)}")

		msg_id = data.get("message_id")

		# Log in frappe_messenger if installed
		if frappe.db.exists("DocType", "Messenger Message"):
			try:
				frappe.get_doc({
					"doctype": "Messenger Message",
					"message_direction": "Outgoing",
					"sender_id": page_id or "page",
					"recipient_id": recipient_id,
					"message": message,
					"message_id": msg_id,
					"status": "Sent",
				}).insert(ignore_permissions=True)
			except Exception:
				pass

		return _success({"message_id": msg_id, "recipient_id": recipient_id, "platform": platform, "status": "sent"})
	except Exception as e:
		return _error(f"Failed to send {platform} message: {str(e)}")


def _list_conversations(kwargs: dict) -> str:
	if not frappe.db.exists("DocType", "Messenger Conversation"):
		return _error("frappe_messenger app is not installed or enabled")

	limit = int(kwargs.get("limit") or 20)
	platform = (kwargs.get("platform") or "").strip()

	filters = {}
	if platform:
		filters["platform"] = platform.capitalize()

	try:
		convos = frappe.get_all(
			"Messenger Conversation",
			filters=filters,
			fields=["name", "sender_id", "platform", "status", "last_message", "last_message_time"],
			order_by="modified desc",
			limit=limit,
		)
		return _success(convos)
	except Exception as e:
		return _error(f"Failed to list conversations: {str(e)}")


def _list_messages(kwargs: dict) -> str:
	if not frappe.db.exists("DocType", "Messenger Message"):
		return _error("frappe_messenger app is not installed or enabled")

	limit = int(kwargs.get("limit") or 20)
	conversation = (kwargs.get("conversation") or kwargs.get("conversation_id") or "").strip()

	filters = {}
	if conversation:
		filters["conversation"] = conversation

	try:
		messages = frappe.get_all(
			"Messenger Message",
			filters=filters,
			fields=["name", "message_direction", "sender_id", "recipient_id", "message", "status", "timestamp"],
			order_by="timestamp desc",
			limit=limit,
		)
		return _success(messages)
	except Exception as e:
		return _error(f"Failed to list messages: {str(e)}")
