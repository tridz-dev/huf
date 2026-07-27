"""Gateway Guided Onboarding & Pairing Tools for Huf Agents and Hub Chat.

Provides tools for AI agents and users to set up, configure, probe,
and approve channel gateway pairings directly via chat or API.
"""

from __future__ import annotations

import json
import secrets
from typing import Any

import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime


def setup_gateway(
	provider: str,
	gateway_name: str,
	credentials: dict[str, str],
	*,
	default_target_type: str = "Agent",
	default_agent: str | None = None,
	default_flow: str | None = None,
	direct_policy: str = "Pairing",
	room_policy: str = "Allow list",
	room_sender_policy: str = "Allow list",
	mention_required: bool = True,
	execution_user: str | None = None,
) -> dict[str, Any]:
	"""Set up or update a channel Gateway and its connected credentials seamlessly.

	Args:
		provider: Channel provider name (e.g. "Telegram", "WhatsApp", "Discord", "Slack", "Email", "SMS", "Google Chat", "Microsoft Teams")
		gateway_name: Unique name for this Gateway instance (e.g. "Telegram Sales Bot")
		credentials: Dictionary of credential key-value pairs required by the adapter schema
		default_target_type: "Agent" or "Flow"
		default_agent: Name of the default Agent document to route incoming messages to
		default_flow: Name of the default Flow document
		direct_policy: "Pairing", "Allow list", "Open", or "Disabled"
		room_policy: "Allow list", "Open", or "Disabled"
		room_sender_policy: "Allow list" or "Open"
		mention_required: Whether group messages require explicit @mentioning the bot
		execution_user: User account to run agent/flow under (defaults to current session user)

	Returns:
		Dict containing setup result, webhook URL, and status details.
	"""
	if not provider or not gateway_name or not credentials:
		return {"success": False, "error": "Provider, gateway_name, and credentials are required."}

	# 1. Validate adapter credentials and test probe
	from huf.ai.gateway_webhook import _adapter_class_for_provider

	try:
		adapter_cls = _adapter_class_for_provider(provider)
	except Exception as exc:
		return {"success": False, "error": f"Unsupported or uninstalled channel provider '{provider}': {exc}"}

	try:
		adapter = adapter_cls(credentials)
	except ValueError as exc:
		return {"success": False, "error": f"Credential validation failed for {provider}: {exc}"}

	# 2. Save Integration Settings
	integration_name = f"Integration-{gateway_name}"
	if frappe.db.exists("Integration Settings", integration_name):
		int_doc = frappe.get_doc("Integration Settings", integration_name)
		int_doc.service = provider.lower().replace(" ", "_")
		int_doc.is_enabled = 1
		int_doc.credentials = []
	else:
		int_doc = frappe.get_doc(
			{
				"doctype": "Integration Settings",
				"integration_name": integration_name,
				"service": provider.lower().replace(" ", "_"),
				"is_enabled": 1,
			}
		)

	for key, val in credentials.items():
		int_doc.append("credentials", {"key": key, "value": val})

	int_doc.save(ignore_permissions=True)

	# 3. Save Gateway document
	if frappe.db.exists("Gateway", gateway_name):
		gw_doc = frappe.get_doc("Gateway", gateway_name)
	else:
		gw_doc = frappe.get_doc(
			{
				"doctype": "Gateway",
				"gateway_name": gateway_name,
			}
		)

	gw_doc.provider = provider
	gw_doc.is_enabled = 1
	gw_doc.integration_settings = int_doc.name
	gw_doc.execution_user = execution_user or frappe.session.user or "Administrator"
	gw_doc.direct_policy = direct_policy
	gw_doc.room_policy = room_policy
	gw_doc.room_sender_policy = room_sender_policy
	gw_doc.mention_required = 1 if mention_required else 0
	gw_doc.default_target_type = default_target_type
	if default_agent:
		gw_doc.default_agent = default_agent
	if default_flow:
		gw_doc.default_flow = default_flow

	gw_doc.save(ignore_permissions=True)

	# 4. Generate webhook URL
	host_url = frappe.utils.get_url()
	webhook_url = f"{host_url.rstrip('/')}/api/method/huf.ai.gateway_webhook.handle_gateway_webhook?gateway_name={frappe.utils.quoted(gateway_name)}"

	# 5. Provider-specific auto-registration (e.g. Telegram setWebhook)
	auto_webhook_status = "Not applicable"
	if provider == "Telegram" and "bot_token" in credentials:
		try:
			import requests

			res = requests.post(
				f"https://api.telegram.org/bot{credentials['bot_token']}/setWebhook",
				json={"url": webhook_url},
				timeout=10,
			)
			res_data = res.json()
			if res_data.get("ok"):
				auto_webhook_status = "Auto-configured with Telegram API"
			else:
				auto_webhook_status = f"Telegram setWebhook notice: {res_data.get('description')}"
		except Exception as e:
			auto_webhook_status = f"Webhook auto-set attempted: {e}"

	return {
		"success": True,
		"gateway_name": gw_doc.name,
		"provider": provider,
		"status": "Active & Enabled",
		"webhook_url": webhook_url,
		"auto_webhook_status": auto_webhook_status,
		"direct_policy": direct_policy,
		"default_target": default_agent or default_flow or "None",
		"message": f"Gateway '{gateway_name}' for {provider} configured successfully!",
	}


def list_pairing_requests(gateway_name: str | None = None) -> list[dict[str, Any]]:
	"""List pending DM/Room pairing access requests.

	Args:
		gateway_name: Optional gateway filter name

	Returns:
		List of pending pairing request dictionaries
	"""
	filters: dict[str, Any] = {"state": "Pending"}
	if gateway_name:
		filters["gateway"] = gateway_name

	entries = frappe.get_all(
		"Gateway Access Entry",
		filters=filters,
		fields=[
			"name",
			"gateway",
			"provider",
			"entry_type",
			"external_id",
			"pairing_code",
			"state",
			"expires_at",
			"display_label",
			"creation",
		],
		order_by="creation desc",
	)

	results = []
	for entry in entries:
		results.append(
			{
				"entry_id": entry["name"],
				"gateway": entry["gateway"],
				"provider": entry["provider"],
				"entry_type": entry["entry_type"],
				"external_id": entry["external_id"],
				"pairing_code": entry.get("pairing_code") or "N/A",
				"expires_at": str(entry.get("expires_at") or ""),
				"created_at": str(entry["creation"]),
			}
		)

	return results


def approve_pairing_code(pairing_code_or_id: str, notes: str | None = None) -> dict[str, Any]:
	"""Approve a pending pairing request using its 8-character pairing code or entry ID.

	Args:
		pairing_code_or_id: The pairing code (e.g. "PAIR-7A9K") or entry ID
		notes: Optional notes regarding the approval

	Returns:
		Dict with approval status and sender details
	"""
	if not pairing_code_or_id:
		return {"success": False, "error": "pairing_code_or_id is required."}

	code_clean = pairing_code_or_id.strip().upper()

	# Match by pairing_code first, then by name or external_id
	entries = frappe.get_all(
		"Gateway Access Entry",
		filters=[
			["state", "=", "Pending"],
			[
				"pairing_code",
				"=",
				code_clean,
			],
		],
		fields=["name", "gateway", "provider", "external_id", "entry_type"],
		limit_page_length=1,
	)

	if not entries:
		entries = frappe.get_all(
			"Gateway Access Entry",
			filters={
				"name": pairing_code_or_id.strip(),
				"state": "Pending",
			},
			fields=["name", "gateway", "provider", "external_id", "entry_type"],
			limit_page_length=1,
		)

	if not entries:
		return {"success": False, "error": f"No pending pairing request found matching '{pairing_code_or_id}'."}

	entry = entries[0]
	doc = frappe.get_doc("Gateway Access Entry", entry["name"])
	doc.state = "Approved"
	doc.approved_by = frappe.session.user if frappe.session.user != "Guest" else "Administrator"
	doc.approved_at = now_datetime()
	if notes:
		doc.notes = notes
	doc.save(ignore_permissions=True)

	# Notify approved sender on external platform
	notification_status = "Not attempted"
	try:
		gw_doc = frappe.get_doc("Gateway", doc.gateway)
		if gw_doc.integration_settings:
			int_doc = frappe.get_doc("Integration Settings", gw_doc.integration_settings)
			creds = {}
			for row in getattr(int_doc, "credentials", []):
				creds[row.key] = row.get_password("value") if hasattr(row, "get_password") else row.value

			from huf.ai.gateway_webhook import _adapter_class_for_provider
			from huf.ai.gateway_adapters.types import GatewayReply

			adapter_cls = _adapter_class_for_provider(gw_doc.provider)
			adapter = adapter_cls(creds)

			welcome_text = (
				f"🎉 Your access pairing request has been approved!\n\n"
				f"You can now interact directly with this assistant."
			)
			adapter.send_reply(GatewayReply(conversation_id=doc.external_id, text=welcome_text))
			notification_status = "Welcome message sent to sender"
	except Exception as exc:
		notification_status = f"Approval saved, welcome message notice: {exc}"

	return {
		"success": True,
		"entry_id": doc.name,
		"gateway": doc.gateway,
		"provider": doc.provider,
		"external_id": doc.external_id,
		"state": "Approved",
		"notification_status": notification_status,
		"message": f"Pairing request '{pairing_code_or_id}' for {doc.provider} user {doc.external_id} approved successfully!",
	}


def test_gateway_health(gateway_name: str) -> dict[str, Any]:
	"""Run health probe and diagnostic check on a Gateway.

	Args:
		gateway_name: Name of the Gateway document to inspect

	Returns:
		Health diagnostic report
	"""
	if not frappe.db.exists("Gateway", gateway_name):
		return {"success": False, "error": f"Gateway '{gateway_name}' does not exist."}

	gw_doc = frappe.get_doc("Gateway", gateway_name)

	report = {
		"gateway_name": gw_doc.name,
		"provider": gw_doc.provider,
		"is_enabled": bool(gw_doc.is_enabled),
		"direct_policy": gw_doc.direct_policy,
		"room_policy": gw_doc.room_policy,
		"last_event_at": str(gw_doc.last_event_at or "Never"),
		"last_error": gw_doc.last_error or "None",
		"adapter_probe": "Untested",
	}

	if gw_doc.integration_settings:
		try:
			int_doc = frappe.get_doc("Integration Settings", gw_doc.integration_settings)
			creds = {}
			for row in getattr(int_doc, "credentials", []):
				creds[row.key] = row.get_password("value") if hasattr(row, "get_password") else row.value

			from huf.ai.gateway_webhook import _adapter_class_for_provider

			adapter_cls = _adapter_class_for_provider(gw_doc.provider)
			adapter = adapter_cls(creds)
			report["adapter_probe"] = "Adapter credentials verified & instantiated cleanly"
		except Exception as exc:
			report["adapter_probe"] = f"Adapter initialization error: {exc}"

	return {"success": True, "report": report}
