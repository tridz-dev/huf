"""
Raven integration tools for Frappe Raven.
Uses direct Frappe DocType APIs – no external HTTP calls.
"""

import json
import frappe


def _raven_installed():
    try:
        return "raven" in frappe.get_installed_apps()
    except Exception:
        return False


def _error(msg):
    return json.dumps({"success": False, "error": msg})


def _resolve_channel_id(channel_id=None, channel_name=None):
    if channel_id and frappe.db.exists("Raven Channel", channel_id):
        return channel_id
    if channel_name:
        cid = frappe.db.get_value("Raven Channel", {"channel_name": channel_name}, "name")
        if cid:
            return cid
    return None


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

def handle_send_message(**kwargs) -> str:
    """Send a message to a Raven channel."""
    if not _raven_installed():
        return _error("Frappe Raven app is not installed.")

    try:
        channel_id = _resolve_channel_id(
            kwargs.get("channel_id"), kwargs.get("channel_name")
        )
        text = kwargs.get("text")
        if not channel_id:
            return _error("channel_id or channel_name is required and must exist")
        if not text:
            return _error("text is required")

        doc = frappe.new_doc("Raven Message")
        doc.channel_id = channel_id
        doc.text = text
        doc.message_type = kwargs.get("message_type", "Text")
        doc.insert(ignore_permissions=True)

        return json.dumps({"success": True, "results": {"name": doc.name, "channel_id": channel_id}})
    except Exception as e:
        frappe.log_error(f"Raven Send Message Error: {e}", "Raven Tool")
        return _error(str(e))


def handle_get_messages(**kwargs) -> str:
    """Get recent messages from a channel."""
    if not _raven_installed():
        return _error("Frappe Raven app is not installed.")

    try:
        channel_id = _resolve_channel_id(
            kwargs.get("channel_id"), kwargs.get("channel_name")
        )
        if not channel_id:
            return _error("channel_id or channel_name is required and must exist")

        limit = int(kwargs.get("limit", 50))
        before_message_id = kwargs.get("before_message_id")

        filters = {"channel_id": channel_id}
        if before_message_id:
            creation = frappe.db.get_value("Raven Message", before_message_id, "creation")
            if creation:
                filters["creation"] = ["<", creation]

        messages = frappe.get_all(
            "Raven Message",
            fields=[
                "name",
                "text",
                "content",
                "message_type",
                "owner",
                "creation",
                "channel_id",
                "file",
                "is_reply",
                "linked_message",
                "is_edited",
                "is_forwarded",
                "is_thread",
            ],
            filters=filters,
            limit=limit,
            order_by="creation desc",
        )

        return json.dumps({"success": True, "count": len(messages), "results": messages})
    except Exception as e:
        frappe.log_error(f"Raven Get Messages Error: {e}", "Raven Tool")
        return _error(str(e))


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------

def handle_list_channels(**kwargs) -> str:
    """List all channels (optionally filter by type: public/private/open)."""
    if not _raven_installed():
        return _error("Frappe Raven app is not installed.")

    try:
        filters = {"is_archived": 0}
        channel_type = kwargs.get("channel_type") or kwargs.get("type")
        if channel_type:
            filters["type"] = channel_type.capitalize()

        limit = int(kwargs.get("limit", 50))

        channels = frappe.get_all(
            "Raven Channel",
            fields=[
                "name",
                "channel_name",
                "type",
                "channel_description",
                "is_direct_message",
                "is_archived",
                "workspace",
                "creation",
                "modified",
            ],
            filters=filters,
            limit=limit,
            order_by="modified desc",
        )

        return json.dumps({"success": True, "count": len(channels), "results": channels})
    except Exception as e:
        frappe.log_error(f"Raven List Channels Error: {e}", "Raven Tool")
        return _error(str(e))


def handle_get_channel_members(**kwargs) -> str:
    """Get members of a channel."""
    if not _raven_installed():
        return _error("Frappe Raven app is not installed.")

    try:
        channel_id = _resolve_channel_id(
            kwargs.get("channel_id"), kwargs.get("channel_name")
        )
        if not channel_id:
            return _error("channel_id or channel_name is required and must exist")

        members = frappe.get_all(
            "Raven Channel Member",
            filters={"channel_id": channel_id},
            fields=["name", "user_id", "is_admin", "last_visit", "allow_notifications"],
            order_by="creation asc",
        )

        return json.dumps({"success": True, "count": len(members), "results": members})
    except Exception as e:
        frappe.log_error(f"Raven Get Channel Members Error: {e}", "Raven Tool")
        return _error(str(e))


def handle_create_channel(**kwargs) -> str:
    """Create a new channel."""
    if not _raven_installed():
        return _error("Frappe Raven app is not installed.")

    try:
        channel_name = kwargs.get("channel_name")
        channel_type = kwargs.get("type", "Public")
        if not channel_name:
            return _error("channel_name is required")

        valid_types = {"Private", "Public", "Open"}
        ctype = channel_type.capitalize()
        if ctype not in valid_types:
            return _error("type must be one of: Private, Public, Open")

        workspace = kwargs.get("workspace")
        if not workspace:
            workspaces = frappe.get_all("Raven Workspace", fields=["name"], limit=1)
            if workspaces:
                workspace = workspaces[0].name

        if not workspace:
            return _error("No Raven workspace found. Please specify workspace.")

        doc = frappe.new_doc("Raven Channel")
        doc.channel_name = channel_name
        doc.type = ctype
        doc.workspace = workspace
        doc.channel_description = kwargs.get("channel_description", "")
        doc.insert(ignore_permissions=True)

        members = kwargs.get("members", [])
        if isinstance(members, str):
            try:
                members = json.loads(members)
            except Exception:
                members = []

        for user_id in members:
            if not frappe.db.exists("Raven Channel Member", {"channel_id": doc.name, "user_id": user_id}):
                member = frappe.new_doc("Raven Channel Member")
                member.channel_id = doc.name
                member.user_id = user_id
                member.insert(ignore_permissions=True)

        return json.dumps({"success": True, "results": {"name": doc.name, "channel_name": doc.channel_name}})
    except Exception as e:
        frappe.log_error(f"Raven Create Channel Error: {e}", "Raven Tool")
        return _error(str(e))


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def handle_search_messages(**kwargs) -> str:
    """Search messages across channels or within a specific channel."""
    if not _raven_installed():
        return _error("Frappe Raven app is not installed.")

    try:
        query = kwargs.get("query")
        if not query:
            return _error("query is required")

        channel_id = _resolve_channel_id(
            kwargs.get("channel_id"), kwargs.get("channel_name")
        )
        limit = int(kwargs.get("limit", 50))

        filters = {"text": ["like", f"%{query}%"]}
        if channel_id:
            filters["channel_id"] = channel_id

        messages = frappe.get_all(
            "Raven Message",
            fields=[
                "name",
                "text",
                "content",
                "message_type",
                "owner",
                "creation",
                "channel_id",
                "file",
                "is_reply",
                "linked_message",
            ],
            filters=filters,
            limit=limit,
            order_by="creation desc",
        )

        return json.dumps({"success": True, "count": len(messages), "results": messages})
    except Exception as e:
        frappe.log_error(f"Raven Search Messages Error: {e}", "Raven Tool")
        return _error(str(e))
