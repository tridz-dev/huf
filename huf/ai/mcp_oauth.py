"""
MCP OAuth 2.1 + PKCE support for Huf's MCP client.

Implements:
  - Authorization Code flow with PKCE (S256)
  - Token storage in encrypted Password fields on MCP Server
  - Proactive token refresh (5-minute buffer)
  - Org-level tokens (one per MCP Server doc, not per Frappe user)

No CLI, no subprocesses, no vendor-specific code.
"""

import base64
import hashlib
import json
import os
import secrets
import urllib.parse
from datetime import timedelta
from typing import Optional

import frappe
import requests
from frappe import _
from frappe.utils import add_to_date, get_datetime, now_datetime


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #

@frappe.whitelist()
def start_oauth_flow(server_name: str) -> dict:
    """
    Build the OAuth authorization URL for the given MCP Server and return it.
    Stores the PKCE code_verifier and state in Redis (TTL 10 min) so the
    callback can validate and complete the exchange.

    Returns:
        {"auth_url": "<url>"}  on success
        {"error": "<message>"} on failure
    """
    if not frappe.has_permission("MCP Server", "write", server_name):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    try:
        server = frappe.get_doc("MCP Server", server_name)
        _require_oauth_config(server)

        code_verifier = _generate_code_verifier()
        code_challenge = _derive_code_challenge(code_verifier)
        state = secrets.token_urlsafe(32)

        # Persist verifier + state in Redis; callback retrieves by state
        cache_key = f"mcp_oauth_state:{state}"
        frappe.cache().set_value(
            cache_key,
            json.dumps({"server_name": server_name, "code_verifier": code_verifier}),
            expires_in_sec=600,
        )

        redirect_uri = _get_redirect_uri(server)

        params = {
            "response_type": "code",
            "client_id": server.oauth_client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        if server.oauth_scope:
            params["scope"] = server.oauth_scope
            
        if getattr(server, "oauth_extra_authorize_params", None):
            try:
                extra_params = json.loads(server.oauth_extra_authorize_params)
                if isinstance(extra_params, dict):
                    params.update(extra_params)
            except Exception as e:
                frappe.log_error(f"Invalid JSON in oauth_extra_authorize_params for {server_name}: {e}", "MCP OAuth")

        auth_url = server.oauth_authorization_endpoint + "?" + urllib.parse.urlencode(params)
        return {"auth_url": auth_url}

    except Exception as exc:
        frappe.log_error(f"MCP OAuth start_flow error for {server_name}: {exc}", "MCP OAuth")
        return {"error": str(exc)}


@frappe.whitelist(allow_guest=False)
def handle_oauth_callback(server_name: str, code: str, state: str) -> dict:
    """
    Exchange the authorization code for tokens and save them encrypted on the
    MCP Server doc. Called by the OAuth callback www page.

    Returns:
        {"success": True}  on success
        {"error": "<message>"} on failure
    """
    try:
        # Retrieve and validate state from Redis
        cache_key = f"mcp_oauth_state:{state}"
        cached_raw = frappe.cache().get_value(cache_key)
        if not cached_raw:
            return {"error": "OAuth state expired or invalid. Please try connecting again."}

        cached = json.loads(cached_raw)
        if cached.get("server_name") != server_name:
            return {"error": "OAuth state mismatch."}

        code_verifier = cached["code_verifier"]
        frappe.cache().delete_key(cache_key)  # One-time use

        server = frappe.get_doc("MCP Server", server_name)
        _require_oauth_config(server)

        redirect_uri = _get_redirect_uri(server)

        token_data = _exchange_code_for_tokens(server, code, code_verifier, redirect_uri)
        _save_tokens(server, token_data)

        return {"success": True}

    except Exception as exc:
        frappe.log_error(f"MCP OAuth callback error for {server_name}: {exc}", "MCP OAuth")
        return {"error": str(exc)}


@frappe.whitelist()
def disconnect_oauth(server_name: str) -> dict:
    """Clear OAuth tokens and reset status to Not Connected."""
    if not frappe.has_permission("MCP Server", "write", server_name):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    try:
        server = frappe.get_doc("MCP Server", server_name)
        server.oauth_access_token = ""
        server.oauth_refresh_token = ""
        server.oauth_token_expires_at = None
        server.oauth_status = "Not Connected"
        server.save(ignore_permissions=True)
        frappe.db.commit()
        return {"success": True}
    except Exception as exc:
        return {"error": str(exc)}


@frappe.whitelist()
def get_oauth_status(server_name: str) -> dict:
    """Return the current OAuth connection status (for form refresh)."""
    status = frappe.db.get_value("MCP Server", server_name, "oauth_status") or "Not Connected"
    return {"status": status}


def get_valid_access_token(server_name: str) -> str:
    """
    Return a valid access token for the given MCP Server.
    Refreshes automatically if the token expires within 5 minutes.
    Raises ValueError if not connected or refresh fails.

    Called from mcp_client._build_mcp_headers() — NOT whitelisted (internal).
    """
    server = frappe.get_doc("MCP Server", server_name)

    access_token = server.get_password("oauth_access_token")
    if not access_token:
        raise ValueError(
            f"MCP Server '{server_name}' is not connected via OAuth. "
            "Go to the MCP Server form and click 'Connect'."
        )

    # Proactively refresh if expiring within 5 minutes
    if _is_token_expiring_soon(server):
        try:
            access_token = refresh_oauth_token(server_name)
        except Exception as exc:
            frappe.log_error(f"MCP OAuth proactive refresh failed for {server_name}: {exc}", "MCP OAuth")
            # Return existing token — it may still work for a few minutes
            # (executor will get a 401 and retry once)

    return access_token


def refresh_oauth_token(server_name: str) -> str:
    """
    Use the stored refresh_token to get a new access token.
    Updates the stored tokens on success.
    Sets oauth_status = "Token Expired" on failure.
    Returns the new access token string.
    """
    server = frappe.get_doc("MCP Server", server_name)
    try:
        refresh_token = server.get_password("oauth_refresh_token")
    except Exception:
        refresh_token = None

    if not refresh_token:
        _set_expired_status(server)
        raise ValueError(f"No refresh token stored for MCP Server '{server_name}'.")

    try:
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": server.oauth_client_id,
        }
        client_secret = None
        try:
            client_secret = server.get_password("oauth_client_secret")
        except Exception:
            pass
        if client_secret:
            payload["client_secret"] = client_secret

        response = requests.post(
            server.oauth_token_endpoint,
            data=payload,
            headers={"Accept": "application/json"},
            timeout=15,
        )
        response.raise_for_status()
        token_data = response.json()

        if "error" in token_data:
            raise ValueError(token_data.get("error_description", token_data["error"]))

        _save_tokens(server, token_data)
        return server.get_password("oauth_access_token")

    except Exception as exc:
        _set_expired_status(server)
        raise


def auto_refresh_oauth_tokens():
    """
    Scheduled job (hourly) — refresh tokens that expire within the next hour.
    Registered in hooks.py under scheduler_events.hourly.
    """
    servers = frappe.get_all(
        "MCP Server",
        filters={"enabled": 1, "auth_type": "oauth", "oauth_status": "Connected"},
        fields=["name", "oauth_token_expires_at"],
    )
    for s in servers:
        if _is_token_expiring_soon(s, buffer_minutes=65):
            try:
                refresh_oauth_token(s.name)
            except Exception as exc:
                frappe.log_error(f"Auto refresh failed for {s.name}: {exc}", "MCP OAuth Auto Refresh")


# --------------------------------------------------------------------------- #
# Private helpers                                                              #
# --------------------------------------------------------------------------- #

def _generate_code_verifier() -> str:
    """Generate a 64-byte URL-safe code verifier per RFC 7636."""
    return base64.urlsafe_b64encode(os.urandom(64)).rstrip(b"=").decode()


def _derive_code_challenge(verifier: str) -> str:
    """Derive S256 code challenge from verifier."""
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _get_redirect_uri(server=None) -> str:
    """Build the absolute OAuth callback URL for this site, or use a custom one if configured."""
    if server and getattr(server, "oauth_redirect_uri", None):
        return server.oauth_redirect_uri

    site_url = frappe.utils.get_url()
    
    # Strip internal frappe ports (like :8703) to match public callback URLs
    parsed = urllib.parse.urlparse(site_url)
    if parsed.port:
        site_url = f"{parsed.scheme}://{parsed.hostname}"
        
    return f"{site_url}/mcp-oauth-callback"


def _exchange_code_for_tokens(server, code: str, code_verifier: str, redirect_uri: str) -> dict:
    """POST to token endpoint to exchange authorization code for tokens."""
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": server.oauth_client_id,
        "code_verifier": code_verifier,
    }
    client_secret = None
    try:
        client_secret = server.get_password("oauth_client_secret")
    except Exception:
        pass
    if client_secret:
        payload["client_secret"] = client_secret

    response = requests.post(
        server.oauth_token_endpoint,
        data=payload,
        headers={"Accept": "application/json"},
        timeout=15,
    )
    
    if not response.ok:
        frappe.log_error(f"OAuth Token Error Response: {response.text}", "MCP OAuth")
        raise ValueError(f"Token error HTTP {response.status_code}: {response.text}")
        
    data = response.json()

    if "error" in data:
        raise ValueError(f"Token error: {data.get('error_description', data['error'])}")
    if "access_token" not in data:
        raise ValueError("Token endpoint did not return an access_token.")

    return data


def _save_tokens(server, token_data: dict):
    """Persist access_token, refresh_token, expiry and status to the server doc."""
    expires_in = token_data.get("expires_in")
    expires_at = add_to_date(now_datetime(), seconds=int(expires_in)) if expires_in else None
    
    # Support custom token paths (e.g. authed_user.access_token) if configured
    token_path = getattr(server, "oauth_token_response_path", None) or "access_token"
    
    access_token = token_data
    for key in token_path.split("."):
        if isinstance(access_token, dict) and key in access_token:
            access_token = access_token.get(key)
        else:
            access_token = None
            break
            
    # Fallback to standard root access_token if path extraction failed
    if not access_token:
        access_token = token_data.get("access_token")

    server.oauth_access_token = access_token
    if token_data.get("refresh_token"):
        server.oauth_refresh_token = token_data["refresh_token"]
    server.oauth_token_expires_at = expires_at
    server.oauth_status = "Connected"
    server.save(ignore_permissions=True)
    frappe.db.commit()


def _is_token_expiring_soon(server_or_row, buffer_minutes: int = 5) -> bool:
    """Return True if the token expires within buffer_minutes."""
    expires_at = getattr(server_or_row, "oauth_token_expires_at", None)
    if not expires_at:
        return False
    threshold = add_to_date(now_datetime(), minutes=buffer_minutes)
    return get_datetime(expires_at) <= get_datetime(threshold)


def _set_expired_status(server):
    try:
        server.oauth_status = "Token Expired"
        server.save(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        pass


def _require_oauth_config(server):
    """Raise a descriptive error if mandatory OAuth fields are missing."""
    missing = []
    if not server.oauth_authorization_endpoint:
        missing.append("Authorization Endpoint")
    if not server.oauth_token_endpoint:
        missing.append("Token Endpoint")
    if not server.oauth_client_id:
        missing.append("Client ID")
    if missing:
        raise ValueError(f"Missing OAuth configuration: {', '.join(missing)}")
