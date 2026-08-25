"""Identity endpoint for the Huf public developer API (v1).

Exposes the authenticated user's identity, role, and capabilities.
"""

import frappe

from huf.api.v1.context import RequestContext
from huf.permissions import get_user_capabilities, get_user_huf_role


def handle_me(context: RequestContext) -> dict:
	"""GET /huf/api/v1/me - authenticated user identity and capabilities.

	Deliberately does NOT call huf.permissions.get_me(): that function reads
	frappe.session.user directly, which for API-key/OAuth auth stays "Guest"
	(the v1 router resolves the principal itself without changing the
	ambient Frappe session) - it would silently report the wrong identity.
	Uses get_user_huf_role()/get_user_capabilities() instead, both of which
	already accept an explicit user, and looks up full_name directly for
	`context.user`. Confirmed live: get_me() returned "Guest"/no
	capabilities for a request correctly authenticated via API key before
	this fix.

	Args:
		context: RequestContext containing the authenticated user and auth mode.

	Returns:
		dict with keys:
			- user: user email/username
			- display_name: full name (or user if not set)
			- huf_role: assigned Huf Role name (e.g., "Huf Manager")
			- capabilities: list of capability strings (e.g., ["agent.use", "chat.use"])
			- auth_type: authentication mode (e.g., "session", "api_key", "oauth")
	"""
	full_name = frappe.db.get_value("User", context.user, "full_name") or context.user

	return {
		"user": context.user,
		"display_name": full_name,
		"huf_role": get_user_huf_role(context.user),
		"capabilities": get_user_capabilities(context.user),
		"auth_type": context.auth_mode.value,
	}
