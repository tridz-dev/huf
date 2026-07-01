# MCP OAuth 2.1 Support — Implementation Plan

**Branch:** `feat/mcp-oauth-support`  
**Feature:** Add standard OAuth 2.1 + PKCE flow to the `MCP Server` DocType so Huf agents can use any OAuth-protected HTTP MCP server (Higgsfield, GitHub Copilot, Notion, Shopify, etc.) without CLI tools, environment variables, or manual token entry.

---

## 1. Goals & Non-Goals

### Goals
- Admin clicks **Connect** on an `MCP Server` form → a new browser tab opens at the OAuth provider → user authorises → tab shows a success page → MCP Server shows "Connected" → agents use tools immediately.
- Access token is refreshed silently before expiry — zero user interaction after initial connect.
- Existing `none / api_key / bearer_token / custom_header` auth modes are completely unmodified.
- Org-level auth: one Huf site, one set of tokens per MCP Server document. (Per-user is a future concern.)
- No Node.js, no CLI binary, no shell subprocess, no Playwright required anywhere in this flow.
- No hard-coded vendor logic — any OAuth 2.1-compliant MCP server works by filling in the OAuth config fields.

### Non-Goals
- Per-user token binding (each Frappe user has their own OAuth session). Future phase.
- SSE transport OAuth (SSE is handled identically at the header level; same token injection works).
- OAuth Dynamic Client Registration (RFC 7591). Admin registers the app manually and fills in client_id/secret.
- Automatic discovery of authorization/token endpoints from `/.well-known` (admin can fill these in; auto-discovery is a nice-to-have for Phase 2).

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                   MCP Server DocType                │
│  auth_type = "oauth"                                │
│  oauth_* config fields (client_id, endpoints…)     │
│  oauth_access_token / oauth_refresh_token (Password)│
│  oauth_token_expires_at (Datetime)                  │
│  oauth_status (Select: Not Connected/Connected/…)   │
└──────────────┬──────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────┐
│              huf/ai/mcp_oauth.py                    │
│  start_oauth_flow()   → builds PKCE auth URL        │
│  handle_oauth_callback() → exchanges code→tokens    │
│  get_valid_access_token() → refresh if near expiry  │
│  refresh_oauth_token() → uses refresh_token         │
│  auto_refresh_oauth_tokens() → scheduler job        │
│  disconnect_oauth()   → clears tokens               │
└──────────────┬──────────────────────────────────────┘
               │ called by
               ▼
┌─────────────────────────────────────────────────────┐
│         huf/ai/mcp_client.py (modified)             │
│  _build_mcp_headers():                              │
│    elif auth_type == "oauth":                       │
│      token = get_valid_access_token(server_name)   │
│      headers["Authorization"] = f"Bearer {token}"  │
│  _execute_mcp_tool_http(): retry once on 401        │
└──────────────┬──────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────┐
│        huf/www/mcp_oauth_callback.py + .html        │
│  Receives ?code=&state= from OAuth provider         │
│  Validates state (from Redis cache)                 │
│  Calls handle_oauth_callback() → saves tokens       │
│  Renders success or error page (no redirect needed) │
└─────────────────────────────────────────────────────┘
```

**State/PKCE storage:** `frappe.cache().set_value(key, value, expires_in_sec=600)` — Redis, TTL 10 min, no new DocType needed.

---

## 3. File-by-File Reference

### 3.1 Modified: `huf/huf/doctype/mcp_server/mcp_server.json`

**What changes:** Add `oauth` to the `auth_type` Select options; add an `OAuth Configuration` section with the config and token fields.

**Fields to add (in order after `auth_header_value`):**

```json
// Extend auth_type options:
"options": "none\napi_key\nbearer_token\ncustom_header\noauth"

// --- New section break ---
{
  "fieldname": "oauth_section",
  "fieldtype": "Section Break",
  "label": "OAuth 2.1 Configuration",
  "depends_on": "eval:doc.auth_type === 'oauth'",
  "collapsible": 0
},
{
  "fieldname": "oauth_status",
  "fieldtype": "Select",
  "label": "OAuth Status",
  "options": "Not Connected\nConnected\nToken Expired",
  "default": "Not Connected",
  "read_only": 1,
  "in_list_view": 0,
  "bold": 1
},
{
  "fieldname": "oauth_connect_button",
  "fieldtype": "Button",
  "label": "Connect",
  "depends_on": "eval:doc.auth_type === 'oauth' && doc.oauth_status !== 'Connected'"
},
{
  "fieldname": "oauth_disconnect_button",
  "fieldtype": "Button",
  "label": "Disconnect",
  "depends_on": "eval:doc.auth_type === 'oauth' && doc.oauth_status === 'Connected'"
},
{
  "fieldname": "column_break_oauth",
  "fieldtype": "Column Break"
},
{
  "fieldname": "oauth_scope",
  "fieldtype": "Small Text",
  "label": "OAuth Scope",
  "description": "Space-separated OAuth scopes (e.g. 'read write'). Leave blank for provider default.",
  "depends_on": "eval:doc.auth_type === 'oauth'"
},
// --- OAuth endpoints sub-section ---
{
  "fieldname": "oauth_endpoints_section",
  "fieldtype": "Section Break",
  "label": "OAuth Endpoints",
  "depends_on": "eval:doc.auth_type === 'oauth'",
  "collapsible": 1,
  "collapsed": 1
},
{
  "fieldname": "oauth_authorization_endpoint",
  "fieldtype": "Data",
  "label": "Authorization Endpoint",
  "description": "e.g. https://higgsfield.ai/oauth/authorize",
  "depends_on": "eval:doc.auth_type === 'oauth'"
},
{
  "fieldname": "oauth_token_endpoint",
  "fieldtype": "Data",
  "label": "Token Endpoint",
  "description": "e.g. https://higgsfield.ai/oauth/token",
  "depends_on": "eval:doc.auth_type === 'oauth'"
},
{
  "fieldname": "oauth_client_id",
  "fieldtype": "Data",
  "label": "Client ID",
  "depends_on": "eval:doc.auth_type === 'oauth'"
},
{
  "fieldname": "oauth_client_secret",
  "fieldtype": "Password",
  "label": "Client Secret",
  "depends_on": "eval:doc.auth_type === 'oauth'",
  "description": "Stored encrypted. Leave blank if using PKCE-only public client."
},
// --- Token storage (read-only, collapsed) ---
{
  "fieldname": "oauth_tokens_section",
  "fieldtype": "Section Break",
  "label": "Stored Tokens",
  "depends_on": "eval:doc.auth_type === 'oauth'",
  "collapsible": 1,
  "collapsed": 1
},
{
  "fieldname": "oauth_access_token",
  "fieldtype": "Password",
  "label": "Access Token",
  "read_only": 1,
  "description": "Set automatically after OAuth flow. Stored encrypted."
},
{
  "fieldname": "oauth_refresh_token",
  "fieldtype": "Password",
  "label": "Refresh Token",
  "read_only": 1,
  "description": "Set automatically after OAuth flow. Stored encrypted."
},
{
  "fieldname": "oauth_token_expires_at",
  "fieldtype": "Datetime",
  "label": "Token Expires At",
  "read_only": 1
}
```

**`field_order` insertion point:** Insert the new section after `auth_header_value` and before `custom_headers_section`.

---

### 3.2 Modified: `huf/huf/doctype/mcp_server/mcp_server.js`

**What changes:** Add handlers for the OAuth Connect/Disconnect buttons and a status indicator. Keep all existing handlers (Sync Tools, Test Connection, auth_type) unchanged.

**New code to add inside `frappe.ui.form.on("MCP Server", { ... })`:**

```javascript
// --- Existing refresh() handler: add at end ---
refresh(frm) {
    // ... existing code unchanged ...

    // OAuth: show Connect/Disconnect and status badge
    if (frm.doc.auth_type === "oauth" && !frm.is_new()) {
        frm.events.render_oauth_status(frm);
    }
},

render_oauth_status(frm) {
    const status = frm.doc.oauth_status || "Not Connected";
    const colours = { "Connected": "green", "Token Expired": "orange", "Not Connected": "red" };
    const colour = colours[status] || "red";
    frm.get_field("oauth_status").$wrapper
        .find(".control-value")
        .html(`<span class="indicator-pill ${colour}">${status}</span>`);
},

oauth_connect_button(frm) {
    if (!frm.doc.oauth_authorization_endpoint || !frm.doc.oauth_token_endpoint || !frm.doc.oauth_client_id) {
        frappe.msgprint({
            title: __("Missing Configuration"),
            message: __("Please fill in Authorization Endpoint, Token Endpoint, and Client ID before connecting."),
            indicator: "orange"
        });
        return;
    }
    frappe.call({
        method: "huf.ai.mcp_oauth.start_oauth_flow",
        args: { server_name: frm.doc.name },
        freeze: true,
        freeze_message: __("Preparing OAuth flow…"),
        callback(r) {
            if (r.message && r.message.auth_url) {
                const win = window.open(r.message.auth_url, "_blank", "width=600,height=700");
                // Poll for the window to close, then refresh form
                const poll = setInterval(() => {
                    if (!win || win.closed) {
                        clearInterval(poll);
                        frm.reload_doc();
                    }
                }, 1000);
            } else {
                frappe.msgprint({ title: __("Error"), message: r.message?.error || __("Could not start OAuth flow."), indicator: "red" });
            }
        }
    });
},

oauth_disconnect_button(frm) {
    frappe.confirm(__("Disconnect this MCP Server from OAuth? Tokens will be deleted."), () => {
        frappe.call({
            method: "huf.ai.mcp_oauth.disconnect_oauth",
            args: { server_name: frm.doc.name },
            freeze: true,
            callback(r) {
                if (r.message?.success) {
                    frappe.show_alert({ message: __("Disconnected"), indicator: "green" });
                    frm.reload_doc();
                } else {
                    frappe.msgprint({ title: __("Error"), message: r.message?.error, indicator: "red" });
                }
            }
        });
    });
},
```

---

### 3.3 New file: `huf/ai/mcp_oauth.py`

This is the central OAuth logic module. Zero vendor-specific code — works with any OAuth 2.1 provider.

```python
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

        redirect_uri = _get_redirect_uri()

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

        redirect_uri = _get_redirect_uri()

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
    refresh_token = server.get_password("oauth_refresh_token")

    if not refresh_token:
        _set_expired_status(server)
        raise ValueError(f"No refresh token stored for MCP Server '{server_name}'.")

    try:
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": server.oauth_client_id,
        }
        client_secret = server.get_password("oauth_client_secret")
        if client_secret:
            payload["client_secret"] = client_secret

        response = requests.post(
            server.oauth_token_endpoint,
            data=payload,
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


def _get_redirect_uri() -> str:
    """Build the absolute OAuth callback URL for this site."""
    site_url = frappe.utils.get_url()
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
    client_secret = server.get_password("oauth_client_secret")
    if client_secret:
        payload["client_secret"] = client_secret

    response = requests.post(
        server.oauth_token_endpoint,
        data=payload,
        timeout=15,
    )
    response.raise_for_status()
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

    server.oauth_access_token = token_data["access_token"]
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
```

---

### 3.4 Modified: `huf/ai/mcp_client.py`

**Two changes only — no restructuring:**

**Change 1: `_build_mcp_headers()`** — add `oauth` branch after the existing `if mcp_server.auth_type` block:

```python
# Replace this block in _build_mcp_headers():

if mcp_server.auth_type and mcp_server.auth_type != "none":
    if mcp_server.auth_type == "oauth":
        # Delegate to mcp_oauth — handles proactive refresh
        from huf.ai.mcp_oauth import get_valid_access_token
        try:
            token = get_valid_access_token(mcp_server.name)
            headers["Authorization"] = f"Bearer {token}"
        except ValueError as exc:
            frappe.log_error(str(exc), "MCP OAuth Header Error")
            # Proceed without auth header; server will return 401
    else:
        auth_value = mcp_server.get_password("auth_header_value")
        if auth_value and mcp_server.auth_header_name:
            if mcp_server.auth_type == "bearer_token":
                headers[mcp_server.auth_header_name] = f"Bearer {auth_value}"
            else:
                headers[mcp_server.auth_header_name] = auth_value
```

**Change 2: `_execute_mcp_tool_http()`** — add a single 401-retry-with-refresh:

```python
# At the bottom of the async with session.post(...) block, before returning result:
if response.status == 401 and mcp_server.auth_type == "oauth":
    # Token may have just expired; refresh and retry once
    from huf.ai.mcp_oauth import refresh_oauth_token
    try:
        refresh_oauth_token(mcp_server.name)
        headers = _build_mcp_headers(mcp_server)
        async with session.post(url, json=payload, headers=headers) as retry_response:
            if retry_response.status == 200:
                result = await retry_response.json()
                if "error" in result:
                    return {"error": result["error"].get("message", "Unknown MCP error"), "success": False}
                return result.get("result", result)
    except Exception as refresh_exc:
        frappe.log_error(f"OAuth retry failed: {refresh_exc}", "MCP OAuth Retry")
    return {"error": "OAuth token invalid or expired. Reconnect via the MCP Server form.", "success": False}
```

---

### 3.5 New file: `huf/www/mcp_oauth_callback.py`

This is the Frappe web page controller that receives the OAuth provider redirect.  
Route: `/mcp-oauth-callback`

```python
"""
OAuth 2.1 callback handler for MCP Server OAuth connections.

This page is opened by the OAuth provider redirect after user authorization.
It calls mcp_oauth.handle_oauth_callback(), then renders a success or error page.

No login required from the OAuth provider — Frappe session must already exist
(the Connect button is clicked while the admin is logged in).
"""

import frappe
from frappe import _

no_cache = 1


def get_context(context):
    code = frappe.form_dict.get("code")
    state = frappe.form_dict.get("state")
    error = frappe.form_dict.get("error")
    error_description = frappe.form_dict.get("error_description", "")

    context.success = False
    context.error_message = ""
    context.server_name = ""

    if error:
        context.error_message = f"{error}: {error_description}" if error_description else error
        return context

    if not code or not state:
        context.error_message = "Missing code or state parameter."
        return context

    # Recover server_name from Redis state
    import json
    cache_key = f"mcp_oauth_state:{state}"
    cached_raw = frappe.cache().get_value(cache_key)
    if not cached_raw:
        context.error_message = "OAuth session expired or invalid. Please try again."
        return context

    cached = json.loads(cached_raw)
    server_name = cached.get("server_name", "")
    context.server_name = server_name

    from huf.ai.mcp_oauth import handle_oauth_callback
    result = handle_oauth_callback(server_name=server_name, code=code, state=state)

    if result.get("success"):
        context.success = True
    else:
        context.error_message = result.get("error", "Unknown error during token exchange.")

    return context
```

---

### 3.6 New file: `huf/www/mcp_oauth_callback.html`

Minimal Jinja template for the callback page. No external dependencies — just inline styles.

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>MCP OAuth — {{ "Connected" if success else "Error" }}</title>
  <style>
    body { font-family: system-ui, sans-serif; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; background: #f4f5f6; }
    .card { background: #fff; border-radius: 12px; padding: 48px 40px; max-width: 420px; text-align: center; box-shadow: 0 4px 24px rgba(0,0,0,.08); }
    .icon { font-size: 48px; margin-bottom: 16px; }
    h2 { margin: 0 0 8px; color: #1f2329; }
    p { color: #6b7280; margin: 0 0 24px; }
    .close-hint { font-size: 13px; color: #9ca3af; }
  </style>
  {% if success %}
  <script>
    // Auto-close; parent tab poll will reload the form
    setTimeout(() => window.close(), 2000);
  </script>
  {% endif %}
</head>
<body>
  <div class="card">
    {% if success %}
      <div class="icon">✅</div>
      <h2>Connected!</h2>
      <p>MCP Server <strong>{{ server_name }}</strong> is now connected.<br>This tab will close automatically.</p>
      <p class="close-hint">You can also close this tab manually.</p>
    {% else %}
      <div class="icon">❌</div>
      <h2>Connection Failed</h2>
      <p>{{ error_message }}</p>
      <p class="close-hint">Close this tab and try again from the MCP Server form.</p>
    {% endif %}
  </div>
</body>
</html>
```

---

### 3.7 Modified: `huf/hooks.py`

**Two additions — no removals:**

**Addition 1: Website route rule** (add to `website_route_rules` list):
```python
{"from_route": "/mcp-oauth-callback", "to_route": "mcp_oauth_callback"},
```

**Addition 2: Hourly scheduler** (add to `scheduler_events["hourly"]` list):
```python
"huf.ai.mcp_oauth.auto_refresh_oauth_tokens"
```

---

## 4. Data Flow: Connect Flow (Admin)

```
Admin opens MCP Server form (auth_type = "oauth")
  │
  ├─ Fills: auth_endpoint, token_endpoint, client_id, [client_secret], [scope]
  ├─ Saves document
  │
  └─ Clicks "Connect" button
       │
       ▼
  mcp_server.js:oauth_connect_button()
       │  frappe.call → huf.ai.mcp_oauth.start_oauth_flow(server_name)
       ▼
  mcp_oauth.start_oauth_flow()
       │  Generates: code_verifier (random 64 bytes)
       │  Derives:   code_challenge = SHA-256(verifier) → base64url
       │  Generates: state = random 32 bytes
       │  Stores in Redis (TTL 10 min):
       │    mcp_oauth_state:{state} → {server_name, code_verifier}
       │  Builds authorization URL with PKCE params
       │  Returns: {auth_url: "https://provider.com/oauth/authorize?..."}
       ▼
  JS opens auth_url in popup window (600×700)
  User authenticates and authorises at provider
  Provider redirects to: https://{site}/mcp-oauth-callback?code=XXX&state=YYY
       ▼
  mcp_oauth_callback.py:get_context()
       │  Reads state from Redis → {server_name, code_verifier}
       │  Calls mcp_oauth.handle_oauth_callback(server_name, code, state)
       ▼
  mcp_oauth.handle_oauth_callback()
       │  Validates state (Redis lookup + server_name match)
       │  Deletes state from Redis (one-time use)
       │  POSTs to token_endpoint: {grant_type, code, redirect_uri, client_id, code_verifier, [client_secret]}
       │  Receives: {access_token, refresh_token, expires_in, ...}
       │  Saves encrypted to MCP Server doc:
       │    oauth_access_token, oauth_refresh_token, oauth_token_expires_at, oauth_status="Connected"
       ▼
  mcp_oauth_callback.html renders "✅ Connected! This tab will close automatically."
  JS popup auto-closes after 2s
  Parent window poll detects popup closed → frm.reload_doc()
  Form shows "Connected" status badge + "Disconnect" button
```

---

## 5. Data Flow: Agent Tool Execution

```
Agent runs a tool from an OAuth MCP Server
  │
  ▼
mcp_client.create_mcp_tools() → builds FunctionTool list (unchanged)
  │
  ▼
on_invoke_tool() → execute_mcp_tool(server_name, tool_name, arguments)
  │
  ▼
_execute_mcp_tool_http()
  │  calls _build_mcp_headers(mcp_server)
  │       └─ auth_type == "oauth":
  │            get_valid_access_token(server_name)
  │                 ├─ reads oauth_access_token (decrypted Password)
  │                 ├─ checks expiry: if expires < now+5min → refresh_oauth_token()
  │                 └─ returns token string
  │       └─ headers["Authorization"] = "Bearer {token}"
  │
  ├─ POST to MCP server with Bearer token → tool result → return
  │
  └─ (if 401 returned)
       │  refresh_oauth_token() → get new token → retry POST once
       └─ (if still 401) → return {error: "OAuth token invalid…"}
```

---

## 6. Acceptance Criteria

| # | Criterion | How Verified |
|---|-----------|-------------|
| AC-1 | Admin saves MCP Server with `auth_type = oauth` and the OAuth endpoint/client fields | Form saves without error; new fields visible |
| AC-2 | Clicking Connect opens a new browser tab/popup with the OAuth provider's auth page | Inspect the URL; PKCE params (`code_challenge`, `code_challenge_method=S256`, `state`) present |
| AC-3 | After authorizing at the provider, the popup shows "Connected!" and auto-closes | Visual verification |
| AC-4 | MCP Server form refreshes and shows "Connected" status badge after popup closes | Visual verification |
| AC-5 | `oauth_access_token` and `oauth_refresh_token` are stored encrypted (not visible in the form) | Only Password fieldtype renders masked; raw DB value is encrypted |
| AC-6 | An agent linked to the OAuth MCP Server successfully calls tools (e.g. `tools/list` returns results) | Agent conversation log shows tool outputs |
| AC-7 | When the access token is near expiry (< 5 min), it is refreshed automatically before the agent call | Set `oauth_token_expires_at` to now+3min; run tool; check new expiry |
| AC-8 | When the access token receives a 401, the client retries once with a refreshed token | Mock server returning 401 then 200; confirm single retry |
| AC-9 | Clicking Disconnect clears all tokens and sets status to "Not Connected" | DB check + form UI |
| AC-10 | Existing `bearer_token`, `api_key`, `none`, `custom_header` auth modes are completely unaffected | Run existing `test_mcp_connection` on a non-OAuth server; should pass |
| AC-11 | No CLI, no subprocess, no Node.js required anywhere in the flow | Code review: no `subprocess`, `os.system`, `shutil.which` calls |
| AC-12 | Redis state expires after 10 minutes if callback never arrives | Wait 11 min; callback returns "state expired" error |
| AC-13 | The hourly scheduler refreshes tokens expiring within 65 minutes | Set expiry to now+30min; run scheduler; confirm new expiry |
| AC-14 | `auto_refresh_oauth_tokens` sets `oauth_status = "Token Expired"` when refresh_token is also invalid | Mock token endpoint returning `{"error": "invalid_grant"}`; check DB status |

---

## 7. What is NOT Changed

- `huf/ai/mcp_client.py` — only `_build_mcp_headers()` and `_execute_mcp_tool_http()` are touched. All other functions unchanged.
- `huf/ai/tool_registry.py`, `sdk_tools.py`, `app_seeding/` — zero changes.
- Agent DocType, Agent Tool Function DocType — zero changes.
- Permissions model — OAuth admin operations require `write` on MCP Server (already gated to System Manager and Huf Manager via existing permissions). No new roles.
- No new Python package dependencies beyond what Frappe already ships (`requests` is available; `hashlib`, `secrets`, `base64`, `os`, `urllib.parse` are stdlib).

---

## 8. Implementation Order for Kimi

Execute in this sequence to avoid forward-reference errors:

1. **DocType JSON** — `mcp_server.json`: add the OAuth fields and options. (Run `bench migrate` after.)
2. **`mcp_oauth.py`** — create new file `huf/ai/mcp_oauth.py` with the full module.
3. **`mcp_client.py`** — apply the two targeted edits to `_build_mcp_headers()` and `_execute_mcp_tool_http()`.
4. **`mcp_oauth_callback.py`** — create `huf/www/mcp_oauth_callback.py`.
5. **`mcp_oauth_callback.html`** — create `huf/www/mcp_oauth_callback.html`.
6. **`mcp_server.js`** — add the four new event handlers inside the existing `frappe.ui.form.on` block.
7. **`hooks.py`** — add route rule and hourly scheduler entry.
8. **Verify** — `bench migrate && bench build` — no import errors, form loads, callback route resolves.

---

## 9. Open Questions (Resolve Before Coding)

| # | Question | Default Assumption |
|---|----------|--------------------|
| Q1 | Does Higgsfield's `/oauth/token` endpoint accept `code_verifier` in the request body, or does it require Basic Auth for confidential clients? | Assume PKCE public client (no client_secret required for Higgsfield; field is optional in the DocType). |
| Q2 | Does `frappe.cache().set_value()` accept `expires_in_sec` as a keyword argument in the installed Frappe version? | Yes — this is the standard Frappe Redis cache API. Verify with `bench --site … console` if unsure. |
| Q3 | Does the Frappe site URL returned by `frappe.utils.get_url()` match the redirect URI registered in Higgsfield's OAuth app? | Admin must register `{site_url}/mcp-oauth-callback` in Higgsfield's developer portal. |
| Q4 | Should the callback page require the user to be logged in (`allow_guest=False` on the page)? | Yes — the page reads from Redis and calls internal APIs. Frappe session cookie is present because the admin opened the popup from the Frappe desk. |

---

## 10. Future Phases (Out of Scope Now)

- **Auto-discovery:** `GET /.well-known/oauth-authorization-server` to pre-fill `oauth_authorization_endpoint` and `oauth_token_endpoint`.
- **Per-user OAuth:** `MCP User Token` DocType keyed by `(mcp_server, owner)`. Requires refactoring `_build_mcp_headers()` to accept a user parameter.
- **Token revocation:** call provider's `revocation_endpoint` on Disconnect.
- **Seed record for Higgsfield:** a fixture JSON that pre-fills all Higgsfield OAuth endpoints so admins only need to enter client_id/secret.
