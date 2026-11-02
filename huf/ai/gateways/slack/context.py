"""Shared helpers to reach a Slack gateway's credentials and Web API client.

Coordinator-owned: work packages import from here instead of re-implementing
credential lookup.
"""

from __future__ import annotations

import frappe

from huf.ai.gateways.slack.api import SlackApi


def get_gateway_credential(gateway, key: str) -> str:
	"""Return a credential value from the gateway's linked Integration Settings ("" if absent)."""
	if isinstance(gateway, str):
		# Callers such as the approvals notifier hold only the gateway name.
		name = frappe.db.get_value("Gateway", gateway, "integration_settings")
	else:
		name = getattr(gateway, "integration_settings", None)
	if not name:
		return ""
	settings = frappe.get_doc("Integration Settings", name)
	for row in settings.credentials or []:
		if row.key == key:
			return row.get_password("value") or ""
	return ""


def get_slack_api(gateway, *, http=None) -> SlackApi:
	"""Build a SlackApi for a gateway; raises ValueError (no secret in message) if no bot token."""
	token = get_gateway_credential(gateway, "token")
	if not token:
		raise ValueError("Slack gateway has no bot token configured")
	return SlackApi(token, http=http) if http else SlackApi(token)
