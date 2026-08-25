"""Principal resolution for the Huf public developer API (v1).

`resolve_principal` is the single call site handlers rely on. Internally
it tries a chain of resolver functions, first match wins, so API-key and
OAuth support can be added later without changing the call site.
"""

from typing import Callable, Optional

import frappe

from huf.api.v1.context import AuthMode, RequestContext
from huf.api.v1.errors import AuthenticationError


def _resolve_session(request) -> Optional[RequestContext]:
	"""Resolve the principal from the current Frappe session cookie.

	Returns `None` (falls through to the next resolver) when there is no
	logged-in session; the caller is responsible for raising when no
	resolver in the chain finds a principal.
	"""
	user = frappe.session.user
	if not user or user == "Guest":
		return None
	return RequestContext(user=user, auth_mode=AuthMode.SESSION)


def _resolve_api_key(request) -> Optional[RequestContext]:
	"""Resolve the principal from an `X-Huf-Api-Key: <key>` header.

	Deliberately NOT `Authorization: Bearer ...`: Frappe's own
	`frappe.auth.validate_auth()` inspects any two-part `Authorization`
	header itself before our page_renderer ever runs, and hard-fails
	("Session Expired") if it doesn't parse as Frappe's own OAuth/API-key
	scheme (`token <key>:<secret>`). Confirmed live: a bearer-token
	credential in `Authorization` never reaches this resolver at all. A
	dedicated header sidesteps that collision entirely.

	Looks up and verifies the raw key against `Huf API Key` records (hash
	comparison only, never plaintext). Returns `None` (falls through to the
	next resolver) when there is no key header or the key does not verify,
	so a request with no API key still falls through to session auth
	instead of failing outright.

	Note: this resolves *identity* and attaches the key's `scopes` /
	`agent_restriction_mode` onto the returned context (as
	`credential_scopes` / `credential_agent_restriction`). Enforcing those
	restrictions against a specific request is handled by
	`huf.api.v1.scopes.require_scope` / `require_agent_allowed`, called
	from each endpoint handler - this resolver only carries the data.
	"""
	headers = getattr(request, "headers", None)
	if headers is None:
		headers = frappe.request.headers if frappe.request else {}

	raw_key = (headers.get("X-Huf-Api-Key") if headers else None) or ""
	raw_key = raw_key.strip()
	if not raw_key:
		return None

	from huf.huf.doctype.huf_api_key.huf_api_key import verify_key

	key_doc = verify_key(raw_key)
	if key_doc is None:
		return None

	return RequestContext(
		user=key_doc.owner,
		auth_mode=AuthMode.API_KEY,
		credential_scopes=key_doc._get_scopes_list(),
		credential_agent_restriction={
			"mode": key_doc.agent_restriction_mode,
			"agents": key_doc._get_restricted_agents_list(),
		},
	)


def _resolve_oauth(request) -> Optional[RequestContext]:
	"""Placeholder for future OAuth auth. Not implemented in Phase 1."""
	return None


# Chain of resolvers tried in order; first non-None result wins.
_RESOLVER_CHAIN: list[Callable] = [
	_resolve_api_key,
	_resolve_oauth,
	_resolve_session,
]


def resolve_principal(request=None) -> RequestContext:
	"""Resolve the authenticated principal for the current request.

	Raises `AuthenticationError` if no resolver in the chain matches
	(e.g. an unauthenticated Guest session with no API key or OAuth
	token present).
	"""
	for resolver in _RESOLVER_CHAIN:
		context = resolver(request)
		if context is not None:
			return context

	raise AuthenticationError()
