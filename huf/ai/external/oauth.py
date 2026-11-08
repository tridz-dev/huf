"""OAuth discovery for the MCP gateway.

Frappe already provides the OAuth server (authorization, token with PKCE, dynamic client
registration, bearer validation). This module adds only what MCP clients need to find it: a
protected-resource metadata document whose ``resource`` is the gateway URL itself, and a
``WWW-Authenticate`` challenge on 401 responses from the gateway that points at that document.
"""

from __future__ import annotations

import frappe

RESOURCE_PATH = "/api/method/huf.ai.external.gateway.mcp"
METADATA_PATH = "/api/method/huf.ai.external.oauth.protected_resource"
RESOURCE_NAME = "Huf MCP gateway"


def resource_url(base: str) -> str:
	return base.rstrip("/") + RESOURCE_PATH


def metadata_url(base: str) -> str:
	return base.rstrip("/") + METADATA_PATH


def challenge_header(base: str) -> str:
	return f'Bearer resource_metadata="{metadata_url(base)}"'


def build_metadata(base: str, scopes: list[str] | None = None) -> dict:
	"""Protected-resource metadata (RFC 9728) for the gateway. The site is its own authorization server."""
	doc = {
		"resource": resource_url(base),
		"authorization_servers": [base.rstrip("/")],
		"bearer_methods_supported": ["header"],
		"resource_name": RESOURCE_NAME,
	}
	if scopes:
		doc["scopes_supported"] = scopes
	return doc


def _configured_scopes() -> list[str]:
	raw = frappe.get_cached_value("OAuth Settings", "OAuth Settings", "scopes_supported") or ""
	return [line.strip() for line in raw.splitlines() if line.strip()]


@frappe.whitelist(allow_guest=True, methods=["GET"])
def protected_resource() -> None:
	"""Serve the gateway's protected-resource metadata as the whole response body."""
	frappe.local.allow_cors = "*"
	frappe.local.response.update(build_metadata(frappe.utils.get_url(), _configured_scopes()))


def add_auth_challenge(response=None, request=None) -> None:
	"""after_request hook: advertise the metadata document on 401 answers from the gateway (Guest 403 becomes 401)."""
	if request is None or response is None or request.path.rstrip("/") != RESOURCE_PATH:
		return
	if response.status_code == 403 and frappe.session.user == "Guest":
		# Frappe answers a Guest calling a non-guest method with 403; MCP clients need 401 to start login.
		response.status_code = 401
	if response.status_code != 401:
		return
	frappe.local.response_headers.set("WWW-Authenticate", challenge_header(frappe.utils.get_url()))
