"""Shared helpers for real-app channel tests (real Gateway + Channel Conversation, no network)."""

from __future__ import annotations

import frappe

from huf.ai.channels import conversation as conv


def make_gateway_conversation(handle: str | None = None):
	"""Insert a real WhatsApp Integration Settings + Gateway and a real Channel Conversation. Returns (gateway, conversation)."""
	sfx = frappe.generate_hash(length=6)
	phone = "555" + str(int(frappe.generate_hash(length=7), 16) % 10**8).zfill(8)
	settings = frappe.get_doc(
		{
			"doctype": "Integration Settings",
			"service": "whatsapp",
			"credentials": [
				{"key": "phone_number_id", "value": phone},
				{"key": "access_token", "value": "tok"},
				{"key": "webhook_verify_token", "value": "verify"},
				{"key": "app_secret", "value": "sec"},
			],
		}
	).insert(ignore_permissions=True)
	gw = frappe.get_doc(
		{
			"doctype": "Gateway",
			"gateway_name": f"Real {sfx}",
			"provider": "WhatsApp",
			"is_enabled": 1,
			"integration_settings": settings.name,
			"execution_user": "Administrator",
			"direct_policy": "Allow list",
			"handoff_message": "",
		}
	).insert(ignore_permissions=True)
	handle = handle or "555" + str(int(frappe.generate_hash(length=7), 16) % 10**8).zfill(8)
	return gw, conv.get_or_create_conversation(gw.name, handle)
