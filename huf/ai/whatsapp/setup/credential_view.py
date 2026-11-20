# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Read-only views of a gateway's Integration Settings credentials (moved out of management.py unchanged)."""

from __future__ import annotations

import frappe

_PRESENCE_KEYS = ("app_secret", "webhook_verify_token", "access_token", "phone_number_id", "app_id")


def _credential_presence(integration_settings: str | None) -> dict[str, bool]:
	"""Report which credential keys are set, never their values."""
	presence = dict.fromkeys(_PRESENCE_KEYS, False)
	if not integration_settings:
		return presence
	settings = frappe.get_doc("Integration Settings", integration_settings)
	for row in settings.credentials or []:
		if row.key in presence:
			presence[row.key] = bool(row.get_password("value") or "")
	return presence


def _credential_app_id(integration_settings: str | None) -> str:
	"""Meta app id from an optional ``app_id`` credential (not a secret; used for dashboard links)."""
	if not integration_settings:
		return ""
	settings = frappe.get_doc("Integration Settings", integration_settings)
	for row in settings.credentials or []:
		if row.key == "app_id":
			return str(row.get_password("value") or "").strip()
	return ""


def _credential_phone_number_id(integration_settings: str | None) -> str:
	"""The gateway credential's phone_number_id (not a secret; it is in the webhook payload)."""
	if not integration_settings:
		return ""
	settings = frappe.get_doc("Integration Settings", integration_settings)
	for row in settings.credentials or []:
		if row.key == "phone_number_id":
			return str(row.get_password("value") or "").strip()
	return ""
