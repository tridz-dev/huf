"""Identity endpoint for the Huf public developer API (v1).

Exposes the authenticated user's identity, role, and capabilities.
"""

from huf.api.v1.context import RequestContext
from huf.permissions import get_me


def handle_me(context: RequestContext) -> dict:
	"""GET /huf/api/v1/me - authenticated user identity and capabilities.

	Wraps huf.permissions.get_me() and returns a public-shaped dict.

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
	identity = get_me()

	return {
		"user": identity["user"],
		"display_name": identity["full_name"],
		"huf_role": identity["huf_role"],
		"capabilities": identity["capabilities"],
		"auth_type": context.auth_mode.value,
	}
