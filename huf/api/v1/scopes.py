"""Scope and agent-restriction enforcement for the Huf public developer API (v1).

The critical rule for this platform: an API key can only ever REDUCE the
authority of the caller, never increase it. `huf.api.v1.auth._resolve_api_key`
resolves WHO is calling and attaches the key's `credential_scopes` /
`credential_agent_restriction` onto the `RequestContext`; this module
enforces WHAT that key is allowed to do, on top of (never instead of) the
normal Huf/Frappe capability and ownership checks each handler already
performs.

Session (and OAuth, once implemented) auth leaves `credential_scopes` /
`credential_agent_restriction` as `None` on the context - those requests
are unrestricted by credential scope, governed only by the underlying
capability/ownership checks, same as before this module existed.
"""

from huf.api.v1.context import RequestContext
from huf.api.v1.errors import AuthorizationError

# Endpoint action -> required scope. Deliberately small and defensible:
# every v1 handler maps to exactly one scope from `ALLOWED_SCOPES` in
# huf.huf.doctype.huf_api_key.huf_api_key.
ACTION_SCOPES = {
	"agents:list": "agents:read",
	"agents:get": "agents:read",
	"conversations:list": "conversations:read",
	"conversations:create": "conversations:write",
	"conversations:get": "conversations:read",
	"conversations:messages": "conversations:read",
	"responses:create": "agents:run",
	"responses:stream": "agents:run",
	"runs:get": "conversations:read",
}


def require_scope(context: RequestContext, scope: str) -> None:
	"""Raise `AuthorizationError` unless `context`'s credential permits `scope`.

	Session/OAuth auth (`context.credential_scopes is None`) is unrestricted
	by credential scope - normal capability checks elsewhere still apply.
	"""
	if context.credential_scopes is None:
		return

	if scope not in context.credential_scopes:
		raise AuthorizationError(f"This API key does not have the '{scope}' scope.")


def require_agent_allowed(context: RequestContext, agent_id: str) -> None:
	"""Raise `AuthorizationError` unless `context`'s credential permits `agent_id`.

	`context.credential_agent_restriction is None` means no restriction is
	in effect (session/OAuth auth). Mode "all" always passes; mode
	"selected" requires `agent_id` to be in the restricted agent list.
	"""
	restriction = context.credential_agent_restriction
	if restriction is None:
		return

	if restriction.get("mode") == "selected" and agent_id not in (restriction.get("agents") or []):
		raise AuthorizationError(f"This API key is not permitted to use agent '{agent_id}'.")
