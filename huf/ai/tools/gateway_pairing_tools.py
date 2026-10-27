"""Gateway Guided Onboarding & Pairing Tools for Huf Agents and Hub Chat.

Provides tools for AI agents and users to set up, configure, probe,
and approve channel gateway pairings directly via chat or API.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import now_datetime

from huf.ai.gateway_adapters.provider_ids import provider_to_service_id


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
	#
	# Integration Settings autonames as "{service}-####" (no field named
	# "integration_name", no "is_enabled" — those don't exist on this
	# doctype). It also isn't keyed one-to-one by gateway: re-running setup
	# for an existing gateway must reuse the Integration Settings already
	# linked to it (via Gateway.integration_settings), not fabricate a name
	# to look up, which would never match the real autoname and silently
	# create a fresh duplicate on every call.
	existing_gateway = frappe.db.get_value("Gateway", gateway_name, "integration_settings")
	if existing_gateway and frappe.db.exists("Integration Settings", existing_gateway):
		int_doc = frappe.get_doc("Integration Settings", existing_gateway)
		int_doc.service = provider_to_service_id(provider)
		int_doc.is_active = 1
		int_doc.credentials = []
	else:
		int_doc = frappe.get_doc(
			{
				"doctype": "Integration Settings",
				"service": provider_to_service_id(provider),
				"is_active": 1,
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
	# Gateway.validate() throws if default_target_type is set without its
	# matching default_agent/default_flow. default_target_type defaults to
	# "Agent" above so setup would otherwise fail whenever a caller sets up
	# a channel without picking a target yet — clear it in that case rather
	# than force a target pick during onboarding; otherwise respect the
	# caller's explicit choice.
	if default_target_type == "Agent" and not default_agent:
		default_target_type = None
	elif default_target_type == "Flow" and not default_flow:
		default_target_type = None
	gw_doc.default_target_type = default_target_type
	if default_agent:
		gw_doc.default_agent = default_agent
	if default_flow:
		gw_doc.default_flow = default_flow

	gw_doc.save(ignore_permissions=True)

	# 4. Generate webhook URL
	from huf.ai.telegram_public_url import public_base_url

	host_url = public_base_url() if provider == "Telegram" else frappe.utils.get_url()
	webhook_url = f"{host_url.rstrip('/')}/api/method/huf.ai.gateway_webhook.handle_gateway_webhook?gateway_name={frappe.utils.quoted(gateway_name)}"

	# 5. Provider-specific auto-registration (e.g. Telegram setWebhook)
	auto_webhook_status = "Not applicable"
	if provider == "Telegram" and "token" in credentials:
		try:
			import requests

			from huf.ai.gateway_adapters.telegram_client import bot_api_url

			res = requests.post(
				bot_api_url(
					credentials["token"], "setWebhook", test_environment=bool(gw_doc.get("telegram_test_environment"))
				),
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
	"""List active (unexpired) pending DM/Room pairing access requests.

	Admin-only: pairing codes are approval credentials.

	Args:
		gateway_name: Optional gateway filter name

	Returns:
		List of pending pairing request dictionaries
	"""
	from huf.ai.gateway_service import _mask_code, _require_gateway_admin

	_require_gateway_admin()
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

	now = now_datetime()
	results = []
	for entry in entries:
		if entry.get("expires_at") and entry["expires_at"] < now:
			continue
		results.append(
			{
				"entry_id": entry["name"],
				"gateway": entry["gateway"],
				"provider": entry["provider"],
				"entry_type": entry["entry_type"],
				"external_id": entry["external_id"],
				"pairing_code": _mask_code(entry["pairing_code"]) if entry.get("pairing_code") else "N/A",
				"expires_at": str(entry.get("expires_at") or ""),
				"created_at": str(entry["creation"]),
			}
		)

	return results


def approve_pairing_code(
	pairing_code_or_id: str, notes: str | None = None, gateway_name: str | None = None
) -> dict[str, Any]:
	"""Approve a pending pairing request using its pairing code or entry ID.

	Thin wrapper over ``gateway_service.approve_gateway_pairing`` (the single
	canonical approval path): admin-only, gateway-scoped, brute-force limited.

	Args:
		pairing_code_or_id: The pairing code (e.g. "PAIR-7A9KXM4Q") or entry ID
		notes: Optional notes regarding the approval
		gateway_name: Gateway the code belongs to (required when using a code)

	Returns:
		Dict with approval status and sender details
	"""
	if not pairing_code_or_id:
		return {"success": False, "error": "pairing_code_or_id is required."}

	from huf.ai.gateway_service import approve_gateway_pairing

	try:
		result = approve_gateway_pairing(pairing_code_or_id, notes=notes, gateway=gateway_name)
	except (frappe.ValidationError, frappe.PermissionError, frappe.TooManyRequestsError) as exc:
		return {"success": False, "error": str(exc)}

	return {
		"success": True,
		"entry_id": result["name"],
		"gateway": result["gateway"],
		"provider": result["provider"],
		"external_id": result["external_id"],
		"state": "Approved",
		"notification_status": result["notification_status"],
		"message": f"Pairing request '{pairing_code_or_id}' for {result['provider']} user {result['external_id']} approved successfully!",
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
