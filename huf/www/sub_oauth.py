import frappe
from frappe import _
from huf.ai.providers.adapters import get_adapter


def get_context(context):
    context.no_cache = 1
    context.title = "Subscription OAuth Callback"

    code = frappe.request.args.get("code")
    state = frappe.request.args.get("state")
    error = frappe.request.args.get("error")
    error_description = frappe.request.args.get("error_description")

    # Manual-paste fallback: user submits the full callback URL via form.
    pasted_url = None
    if frappe.request.method == "POST":
        pasted_url = frappe.form_dict.get("pasted_url") or frappe.request.get_json(silent=True) or {}
        if isinstance(pasted_url, dict):
            pasted_url = pasted_url.get("pasted_url")

    if error:
        context.status = "error"
        context.message = f"{error}: {error_description or 'OAuth provider returned an error.'}"
        return context

    if not code and not pasted_url:
        # Show manual-paste form when no code is present.
        context.status = "form"
        context.message = (
            "If your OAuth flow redirected to localhost and showed a connection error, "
            "copy the full URL from your browser's address bar and paste it below."
        )
        return context

    if not code and pasted_url:
        # Resolve the connection first by state so we can use the correct adapter.
        connection_doc = _resolve_connection_by_pasted_url(pasted_url)
        if not connection_doc:
            context.status = "error"
            context.message = "Could not find a matching pending subscription connection. Please start the connection flow again."
            return context

        try:
            adapter = get_adapter(connection_doc.adapter_type)
            redirect_uri = frappe.utils.get_url("/huf/sub_oauth")
            result = adapter.complete_authorization(
                connection_doc,
                {"pasted_url": pasted_url, "redirect_uri": redirect_uri},
            )
            connection_doc.save(ignore_permissions=True)
            context.status = "success"
            context.message = _(
                "Successfully connected {0}. You can close this window and return to HUF."
            ).format(connection_doc.connection_name)
            context.connection = connection_doc.connection_name
            context.result = result
        except Exception as e:
            frappe.log_error(
                frappe.get_traceback(),
                "Subscription OAuth Callback Error",
            )
            context.status = "error"
            context.message = f"Failed to complete authorization: {str(e)}"
        return context

    # Standard redirect flow with explicit code + state.
    connections = frappe.get_all(
        "AI Provider Connection",
        filters={"auth_status": "Pending Authorization", "is_active": 1},
        fields=["name"],
    )

    connection_doc = None
    for row in connections:
        doc = frappe.get_doc("AI Provider Connection", row.name)
        metadata = doc.get_decrypted_auth_payload() or {}
        if metadata.get("oauth_state") == state:
            connection_doc = doc
            break

    if not connection_doc:
        context.status = "error"
        context.message = "Could not find a matching pending subscription connection. Please start the connection flow again."
        return context

    try:
        adapter = get_adapter(connection_doc.adapter_type)
        redirect_uri = frappe.utils.get_url("/huf/sub_oauth")
        result = adapter.complete_authorization(
            connection_doc,
            {"code": code, "state": state, "redirect_uri": redirect_uri},
        )
        connection_doc.save(ignore_permissions=True)
        context.status = "success"
        context.message = _(
            "Successfully connected {0}. You can close this window and return to HUF."
        ).format(connection_doc.connection_name)
        context.connection = connection_doc.connection_name
        context.result = result
    except Exception as e:
        frappe.log_error(
            frappe.get_traceback(),
            "Subscription OAuth Callback Error",
        )
        context.status = "error"
        context.message = f"Failed to complete authorization: {str(e)}"

    return context


def _resolve_connection_by_pasted_url(pasted_url: str):
    """Try to find the pending connection by parsing the state out of a pasted URL."""
    try:
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(pasted_url)
        params = parse_qs(parsed.query)
        state = params.get("state", [None])[0]
    except Exception:
        state = None

    if not state:
        return None

    connections = frappe.get_all(
        "AI Provider Connection",
        filters={"auth_status": "Pending Authorization", "is_active": 1},
        fields=["name"],
    )
    for row in connections:
        doc = frappe.get_doc("AI Provider Connection", row.name)
        metadata = doc.get_decrypted_auth_payload() or {}
        if metadata.get("oauth_state") == state:
            return doc
    return None
