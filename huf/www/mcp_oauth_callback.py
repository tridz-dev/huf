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
