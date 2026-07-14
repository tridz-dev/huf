"""
MCP Connection Resolver

URL-first MCP OAuth discovery for HUF.

Given only an MCP server URL and a callback URL, this module:
  1. Probes the MCP endpoint unauthenticated.
  2. Parses WWW-Authenticate challenges.
  3. Discovers Protected Resource Metadata (PRM).
  4. Discovers Authorization Server Metadata (OASM).
  5. Performs Dynamic Client Registration (DCR) when available.
  6. Returns normalized connection metadata ready for the OAuth flow.

The resolver keeps discovery and compatibility handling server-side so the UI
only needs the MCP server URL.
"""

import ipaddress
import json
import re
import secrets
import urllib.parse
from typing import Optional

import frappe
import requests
from frappe import _


DEFAULT_TIMEOUT = 15
USER_AGENT = "HUF-MCP-Client/1.0"


class MCPDiscoveryError(Exception):
    """Raised when MCP OAuth discovery fails."""

    def __init__(self, message: str, discovery_status: str = "Failed"):
        super().__init__(message)
        self.discovery_status = discovery_status


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #

@frappe.whitelist()
def resolve_mcp_connection(server_url: str, callback_url: str) -> dict:
    """
    Resolve MCP connection metadata from a server URL.

    Args:
        server_url: MCP server endpoint (e.g. https://mcp.higgsfield.ai/mcp).
        callback_url: OAuth redirect URI for this HUF installation.

    Returns:
        dict with keys:
          auth_type, resource, resource_metadata_url, authorization_server,
          authorization_endpoint, token_endpoint, registration_endpoint,
          scopes_supported, client_registration_method, client_id,
          discovery_status, discovery_error, metadata_json
    """
    try:
        server_url = _normalize_url(server_url)
        callback_url = _normalize_url(callback_url)

        if not _is_safe_url(server_url):
            return _error_result("Invalid or unsafe MCP server URL.")
        if not _is_safe_url(callback_url):
            return _error_result("Invalid or unsafe callback URL.")

        # 1. Probe the MCP endpoint
        probe = _probe_mcp_endpoint(server_url)

        if probe["status_code"] == 200:
            # Server appears public; still try metadata discovery in case
            # a 401 is returned on actual MCP POST operations.
            pass

        # 2. Discover Protected Resource Metadata
        resource_metadata = _discover_resource_metadata(server_url, probe)
        if not resource_metadata:
            return _error_result(
                "Could not discover Protected Resource Metadata. "
                "The server did not return a WWW-Authenticate challenge with resource_metadata."
            )

        # 3. Validate resource matches
        resource = resource_metadata.get("resource")
        if resource and _canonical_resource(resource) != _canonical_resource(server_url):
            # Some providers use the exact URL; tolerate trailing-slash differences.
            if not _resources_match(resource, server_url):
                return _error_result(
                    f"Protected resource mismatch: expected {server_url}, got {resource}."
                )

        authorization_servers = resource_metadata.get("authorization_servers") or []
        if not authorization_servers:
            return _error_result(
                "Protected Resource Metadata did not list any authorization_servers."
            )

        # 4. Discover Authorization Server Metadata
        auth_server_metadata = None
        auth_server_url = None
        for auth_server in authorization_servers:
            metadata = _discover_authorization_server(auth_server)
            if metadata:
                auth_server_metadata = metadata
                auth_server_url = auth_server
                break

        if not auth_server_metadata:
            return _error_result(
                "Could not discover Authorization Server Metadata from any advertised server."
            )

        # 5. Validate capabilities
        capabilities = _validate_capabilities(auth_server_metadata)
        if capabilities["error"]:
            return _error_result(capabilities["error"])

        # 6. Determine client registration method and obtain client_id
        client_id = None
        registration_method = "manual"
        registration_endpoint = auth_server_metadata.get("registration_endpoint")

        if registration_endpoint:
            registration = _register_client(
                registration_endpoint, callback_url, auth_server_metadata
            )
            if registration and registration.get("client_id"):
                client_id = registration["client_id"]
                registration_method = "dynamic_registration"

        if not client_id:
            return _error_result(
                "Dynamic Client Registration is not available and no manual client_id was provided."
            )

        return {
            "auth_type": "oauth",
            "resource": resource or server_url,
            "resource_metadata_url": resource_metadata.get("_source_url"),
            "authorization_server": auth_server_url,
            "authorization_endpoint": auth_server_metadata.get("authorization_endpoint"),
            "token_endpoint": auth_server_metadata.get("token_endpoint"),
            "registration_endpoint": registration_endpoint,
            "scopes_supported": auth_server_metadata.get("scopes_supported", []),
            "client_registration_method": registration_method,
            "client_id": client_id,
            "discovery_status": "Ready",
            "discovery_error": None,
            "metadata_json": json.dumps({
                "resource_metadata": resource_metadata,
                "authorization_server_metadata": auth_server_metadata,
                "client_registration": registration,
            }),
        }

    except MCPDiscoveryError as exc:
        frappe.log_error(f"MCP discovery error for {server_url}: {exc}", "MCP Discovery")
        return _error_result(str(exc), exc.discovery_status)
    except Exception as exc:
        frappe.log_error(f"MCP discovery unexpected error for {server_url}: {exc}", "MCP Discovery")
        return _error_result(str(exc))


@frappe.whitelist()
def discover_mcp_server(server_name: str) -> dict:
    """
    Resolve and persist discovery metadata for an existing MCP Server document.
    """
    if not frappe.has_permission("MCP Server", "write", server_name):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    try:
        server = frappe.get_doc("MCP Server", server_name)
        if not server.server_url:
            return {"error": "Server URL is not set."}

        callback_url = _get_redirect_uri(server)
        result = resolve_mcp_connection(server.server_url, callback_url)

        if result.get("discovery_status") != "Ready":
            server.oauth_discovery_status = result.get("discovery_status", "Failed")
            server.oauth_discovery_error = result.get("discovery_error")
            server.save(ignore_permissions=True)
            frappe.db.commit()
            return result

        # Persist discovered metadata
        server.oauth_discovery_status = "Ready"
        server.oauth_discovery_error = None
        server.oauth_resource_metadata_url = result.get("resource_metadata_url")
        server.oauth_authorization_server = result.get("authorization_server")
        server.oauth_client_registration_method = result.get("client_registration_method")
        server.oauth_metadata_json = result.get("metadata_json")
        server.oauth_last_discovered_at = frappe.utils.now_datetime()

        # Override manual fields only if they are empty (preserve admin overrides)
        if not server.oauth_authorization_endpoint:
            server.oauth_authorization_endpoint = result.get("authorization_endpoint")
        if not server.oauth_token_endpoint:
            server.oauth_token_endpoint = result.get("token_endpoint")
        if not server.oauth_registration_endpoint:
            server.oauth_registration_endpoint = result.get("registration_endpoint")
        if not server.oauth_client_id:
            server.oauth_client_id = result.get("client_id")
        if not server.oauth_scope and result.get("scopes_supported"):
            server.oauth_scope = " ".join(result["scopes_supported"])

        server.save(ignore_permissions=True)
        frappe.db.commit()

        # Return a sanitized version (no full metadata dump to frontend)
        return {
            "success": True,
            "discovery_status": "Ready",
            "authorization_server": result.get("authorization_server"),
            "client_registration_method": result.get("client_registration_method"),
        }

    except Exception as exc:
        frappe.log_error(f"MCP discovery persist error for {server_name}: {exc}", "MCP Discovery")
        return {"error": str(exc)}


# --------------------------------------------------------------------------- #
# Discovery helpers                                                            #
# --------------------------------------------------------------------------- #

def _probe_mcp_endpoint(server_url: str) -> dict:
    """
    Make an unauthenticated request to the MCP endpoint and capture status + challenges.
    """
    try:
        response = requests.get(
            server_url,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            timeout=DEFAULT_TIMEOUT,
            allow_redirects=True,
        )
    except requests.exceptions.Timeout:
        raise MCPDiscoveryError("Connection to MCP server timed out.")
    except requests.exceptions.ConnectionError as exc:
        raise MCPDiscoveryError(f"Could not connect to MCP server: {exc}")
    except requests.exceptions.RequestException as exc:
        raise MCPDiscoveryError(f"Request to MCP server failed: {exc}")

    challenges = []
    www_auth = response.headers.get("WWW-Authenticate") or ""
    if www_auth:
        challenges = _parse_www_authenticate(www_auth)

    return {
        "status_code": response.status_code,
        "headers": dict(response.headers),
        "challenges": challenges,
    }


def _parse_www_authenticate(header: str) -> list[dict]:
    """
    Parse WWW-Authenticate header into challenge dicts.

    Handles quoted values and multiple challenges. RFC 7235-style.
    """
    tokens = _tokenize_www_authenticate(header)
    challenges = []
    current_scheme = None
    current_params = {}

    def flush():
        nonlocal current_scheme, current_params
        if current_scheme:
            challenges.append({"scheme": current_scheme, **current_params})
            current_scheme = None
            current_params = {}

    for token in tokens:
        if "=" not in token:
            # New challenge scheme
            flush()
            current_scheme = token
            continue

        key, _, value = token.partition("=")
        key = key.strip().lower()
        value = value.strip()
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        current_params[key] = value

    flush()
    return challenges


def _tokenize_www_authenticate(header: str) -> list[str]:
    """Tokenize a WWW-Authenticate header, preserving quoted strings."""
    tokens = []
    i = 0
    n = len(header)
    while i < n:
        # Skip separators
        if header[i] in " \t,":
            i += 1
            continue

        if header[i] == '"':
            # Quoted string
            j = i + 1
            while j < n and header[j] != '"':
                if header[j] == "\\" and j + 1 < n:
                    j += 2
                else:
                    j += 1
            tokens.append(header[i : j + 1])
            i = j + 1
            continue

        # Unquoted token
        j = i
        while j < n and header[j] not in " \t,":
            j += 1
        token = header[i:j]
        if token:
            tokens.append(token)
        i = j

    return tokens


def _discover_resource_metadata(server_url: str, probe: dict) -> Optional[dict]:
    """
    Discover Protected Resource Metadata (RFC 9728).

    First from WWW-Authenticate resource_metadata, then well-known fallbacks.
    """
    parsed = urllib.parse.urlparse(server_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path or "/"

    candidate_urls = []

    # From challenge
    for challenge in probe.get("challenges", []):
        if challenge.get("scheme", "").lower() == "bearer":
            resource_metadata_url = challenge.get("resource_metadata") or challenge.get("resource")
            if resource_metadata_url:
                candidate_urls.append(resource_metadata_url)

    # Well-known fallbacks
    candidate_urls.extend([
        f"{origin}/.well-known/oauth-protected-resource{path}",
        f"{origin}/.well-known/oauth-protected-resource",
    ])

    for url in candidate_urls:
        if not _is_safe_url(url):
            continue
        metadata = _fetch_json(url)
        if metadata and isinstance(metadata, dict):
            metadata["_source_url"] = url
            return metadata

    return None


def _discover_authorization_server(auth_server_url: str) -> Optional[dict]:
    """
    Discover Authorization Server Metadata (RFC 8414) or OpenID Discovery.
    """
    parsed = urllib.parse.urlparse(auth_server_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    candidate_urls = [
        f"{origin}/.well-known/oauth-authorization-server{parsed.path or ''}",
        f"{origin}/.well-known/oauth-authorization-server",
        f"{origin}/.well-known/openid-configuration{parsed.path or ''}",
        f"{origin}/.well-known/openid-configuration",
    ]

    for url in candidate_urls:
        if not _is_safe_url(url):
            continue
        metadata = _fetch_json(url)
        if metadata and isinstance(metadata, dict):
            if metadata.get("authorization_endpoint") and metadata.get("token_endpoint"):
                return metadata

    return None


def _validate_capabilities(metadata: dict) -> dict:
    """
    Validate that the authorization server supports what we need.
    """
    grant_types = metadata.get("grant_types_supported", ["authorization_code"])
    if "authorization_code" not in grant_types:
        return {"error": "Authorization server does not support authorization_code grant."}

    code_methods = metadata.get("code_challenge_methods_supported", [])
    if "S256" not in code_methods:
        return {"error": "Authorization server does not support PKCE S256."}

    response_types = metadata.get("response_types_supported", ["code"])
    if "code" not in response_types:
        return {"error": "Authorization server does not support response_type=code."}

    return {"error": None}


def _register_client(registration_endpoint: str, callback_url: str, auth_server_metadata: dict) -> Optional[dict]:
    """
    Perform Dynamic Client Registration (RFC 7591).

    Returns registration response dict or None on failure.
    """
    if not _is_safe_url(registration_endpoint):
        return None

    payload = {
        "client_name": "HUF",
        "redirect_uris": [callback_url],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": " ".join(auth_server_metadata.get("scopes_supported", [])),
    }

    try:
        response = requests.post(
            registration_endpoint,
            json=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        frappe.log_error(f"MCP DCR failed at {registration_endpoint}: {exc}", "MCP DCR")
        return None


# --------------------------------------------------------------------------- #
# URL safety                                                                   #
# --------------------------------------------------------------------------- #

def _normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        return url
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme:
        url = "https://" + url
        parsed = urllib.parse.urlparse(url)
    return urllib.parse.urlunparse(parsed)


def _is_safe_url(url: str) -> bool:
    """
    Reject non-HTTP(S) URLs and private/internal addresses.
    Allow localhost only for development.
    """
    if not url:
        return False
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    # Allow localhost for development
    if hostname.lower() in ("localhost", "127.0.0.1", "::1"):
        return True

    try:
        ip = ipaddress.ip_address(hostname)
        # Reject private, loopback, link-local, multicast, reserved
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            return False
    except ValueError:
        # hostname is not an IP, that's fine
        pass

    return True


def _canonical_resource(url: str) -> str:
    """Normalize resource URL for comparison."""
    parsed = urllib.parse.urlparse(url.rstrip("/"))
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".lower()


def _resources_match(a: str, b: str) -> bool:
    """Allow exact or trailing-slash-only differences."""
    return _canonical_resource(a) == _canonical_resource(b)


# --------------------------------------------------------------------------- #
# HTTP helpers                                                                 #
# --------------------------------------------------------------------------- #

def _fetch_json(url: str) -> Optional[dict]:
    """Fetch JSON from a safe URL. Returns None on any failure."""
    if not _is_safe_url(url):
        return None
    try:
        response = requests.get(
            url,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            timeout=DEFAULT_TIMEOUT,
            allow_redirects=True,
        )
        if response.status_code != 200:
            return None
        return response.json()
    except Exception:
        return None


def _error_result(message: str, status: str = "Failed") -> dict:
    return {
        "auth_type": None,
        "resource": None,
        "resource_metadata_url": None,
        "authorization_server": None,
        "authorization_endpoint": None,
        "token_endpoint": None,
        "registration_endpoint": None,
        "scopes_supported": [],
        "client_registration_method": None,
        "client_id": None,
        "discovery_status": status,
        "discovery_error": message,
        "metadata_json": None,
    }


def _get_redirect_uri(server=None) -> str:
    """Build the absolute OAuth callback URL for this site."""
    if server and getattr(server, "oauth_redirect_uri", None):
        return server.oauth_redirect_uri

    site_url = frappe.utils.get_url()
    parsed = urllib.parse.urlparse(site_url)
    if parsed.port:
        site_url = f"{parsed.scheme}://{parsed.hostname}"

    return f"{site_url}/mcp-oauth-callback"
