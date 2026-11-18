"""Narrow Gateway scoping for OTP senders.

The generic Gateway ``has_permission`` hook (``has_permission_gateway_family``) passes only System
Manager, because Gateway carries credentials. OTP senders therefore cannot be scoped through
``frappe.has_permission``; this module checks the sender role and a Gateway User Permission directly.
Deny by default: a sender without a matching Gateway User Permission is refused.
"""

import frappe

OTP_SENDER_ROLE = "HUF OTP Sender"


def sender_may_use_gateway(user: str, gateway: str) -> bool:
	roles = set(frappe.get_roles(user) or [])
	if "System Manager" in roles:
		return True
	if OTP_SENDER_ROLE not in roles:
		return False
	perms = frappe.permissions.get_user_permissions(user) or {}
	return any(
		(row.get("doc") if isinstance(row, dict) else row) == gateway
		for row in perms.get("Gateway") or []
	)
