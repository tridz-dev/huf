"""
Helpdesk integration tools for Frappe Helpdesk.
Uses direct Frappe DocType APIs – no external HTTP calls.
"""

import json
import frappe


def _helpdesk_installed():
    try:
        return "helpdesk" in frappe.get_installed_apps()
    except Exception:
        return False


def _error(msg):
    return json.dumps({"success": False, "error": msg}, default=str)


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------

def _handle_get_tickets(**kwargs) -> str:
    """List tickets with filters (status, priority, assigned_to, team, search)."""
    if not _helpdesk_installed():
        return _error("Frappe Helpdesk app is not installed.")

    try:
        filters = {}
        status = kwargs.get("status")
        priority = kwargs.get("priority")
        assigned_to = kwargs.get("assigned_to")
        team = kwargs.get("team")
        search = kwargs.get("search")
        limit = int(kwargs.get("limit", 20))
        offset = int(kwargs.get("offset", 0))

        if status:
            filters["status"] = status
        if priority:
            filters["priority"] = priority
        if team:
            filters["agent_group"] = team
        if assigned_to:
            # _assign stores JSON list of assigned users
            filters["_assign"] = ["like", f"%{assigned_to}%"]

        or_filters = []
        if search:
            or_filters = [
                ["HD Ticket", "subject", "like", f"%{search}%"],
                ["HD Ticket", "description", "like", f"%{search}%"],
                ["HD Ticket", "raised_by", "like", f"%{search}%"],
            ]

        fields = [
            "name",
            "subject",
            "raised_by",
            "status",
            "priority",
            "agent_group",
            "ticket_type",
            "customer",
            "contact",
            "modified",
        ]

        tickets = frappe.get_all(
            "HD Ticket",
            fields=fields,
            filters=filters,
            or_filters=or_filters or None,
            limit=limit,
            limit_start=offset,
            order_by="modified desc",
        )

        return json.dumps({"success": True, "count": len(tickets), "results": tickets}, default=str)
    except Exception as e:
        frappe.log_error(f"Helpdesk Get Tickets Error: {e}", "Helpdesk Tool")
        return _error(str(e))


def _handle_get_ticket(**kwargs) -> str:
    """Get single ticket details with comments."""
    if not _helpdesk_installed():
        return _error("Frappe Helpdesk app is not installed.")

    try:
        ticket_id = kwargs.get("ticket_id") or kwargs.get("name")
        if not ticket_id:
            return _error("ticket_id or name is required")
        if not frappe.db.exists("HD Ticket", ticket_id):
            return _error(f"Ticket {ticket_id} not found")

        doc = frappe.get_doc("HD Ticket", ticket_id)
        comments = frappe.get_all(
            "HD Ticket Comment",
            filters={"reference_ticket": ticket_id},
            fields=["name", "content", "commented_by", "creation", "is_pinned"],
            order_by="creation desc",
            limit=50,
        )

        result = doc.as_dict()
        result["comments"] = comments
        return json.dumps({"success": True, "results": result}, default=str)
    except Exception as e:
        frappe.log_error(f"Helpdesk Get Ticket Error: {e}", "Helpdesk Tool")
        return _error(str(e))


def _handle_create_ticket(**kwargs) -> str:
    """Create a support ticket."""
    if not _helpdesk_installed():
        return _error("Frappe Helpdesk app is not installed.")

    try:
        subject = kwargs.get("subject")
        if not subject:
            return _error("subject is required")

        doc = frappe.new_doc("HD Ticket")
        doc.subject = subject
        doc.description = kwargs.get("description", "")
        doc.customer = kwargs.get("customer", "")
        doc.priority = kwargs.get("priority", "")
        doc.ticket_type = kwargs.get("ticket_type") or kwargs.get("type", "")
        doc.agent_group = kwargs.get("team", "")
        doc.raised_by = kwargs.get("raised_by") or kwargs.get("email", frappe.session.user)
        doc.contact = kwargs.get("contact", "")
        doc.insert(ignore_permissions=True)

        return json.dumps({"success": True, "results": {"name": doc.name, "subject": doc.subject}}, default=str)
    except Exception as e:
        frappe.log_error(f"Helpdesk Create Ticket Error: {e}", "Helpdesk Tool")
        return _error(str(e))


def _handle_update_ticket(**kwargs) -> str:
    """Update ticket (status, priority, assigned_to, team)."""
    if not _helpdesk_installed():
        return _error("Frappe Helpdesk app is not installed.")

    try:
        ticket_id = kwargs.get("ticket_id") or kwargs.get("name")
        if not ticket_id:
            return _error("ticket_id or name is required")
        if not frappe.db.exists("HD Ticket", ticket_id):
            return _error(f"Ticket {ticket_id} not found")

        doc = frappe.get_doc("HD Ticket", ticket_id)

        if "status" in kwargs:
            doc.status = kwargs["status"]
        if "priority" in kwargs:
            doc.priority = kwargs["priority"]
        if "team" in kwargs:
            doc.agent_group = kwargs["team"]
        if "ticket_type" in kwargs:
            doc.ticket_type = kwargs["ticket_type"]
        if "type" in kwargs:
            doc.ticket_type = kwargs["type"]
        if "description" in kwargs:
            doc.description = kwargs["description"]
        if "resolution_details" in kwargs:
            doc.resolution_details = kwargs["resolution_details"]

        doc.save(ignore_permissions=True)

        assigned_to = kwargs.get("assigned_to")
        if assigned_to:
            if not frappe.db.exists("HD Agent", assigned_to):
                return _error(f"Agent {assigned_to} not found")
            doc.assign_agent(assigned_to)

        return json.dumps({"success": True, "results": {"name": doc.name, "subject": doc.subject}}, default=str)
    except Exception as e:
        frappe.log_error(f"Helpdesk Update Ticket Error: {e}", "Helpdesk Tool")
        return _error(str(e))


def _handle_add_comment(**kwargs) -> str:
    """Add a comment/reply to a ticket."""
    if not _helpdesk_installed():
        return _error("Frappe Helpdesk app is not installed.")

    try:
        ticket_id = kwargs.get("ticket_id")
        content = kwargs.get("content")
        if not all([ticket_id, content]):
            return _error("ticket_id and content are required")
        if not frappe.db.exists("HD Ticket", ticket_id):
            return _error(f"Ticket {ticket_id} not found")

        comment = frappe.new_doc("HD Ticket Comment")
        comment.reference_ticket = ticket_id
        comment.content = content
        comment.commented_by = kwargs.get("commented_by", frappe.session.user)
        comment.insert(ignore_permissions=True)

        return json.dumps({"success": True, "results": {"name": comment.name}}, default=str)
    except Exception as e:
        frappe.log_error(f"Helpdesk Add Comment Error: {e}", "Helpdesk Tool")
        return _error(str(e))


# ---------------------------------------------------------------------------
# Agents & Teams
# ---------------------------------------------------------------------------

def _handle_get_agents(**kwargs) -> str:
    """List helpdesk agents."""
    if not _helpdesk_installed():
        return _error("Frappe Helpdesk app is not installed.")

    try:
        limit = int(kwargs.get("limit", 50))
        offset = int(kwargs.get("offset", 0))
        filters = {}
        is_active = kwargs.get("is_active")
        if is_active is not None:
            filters["is_active"] = int(is_active)

        search = kwargs.get("search")
        or_filters = []
        if search:
            or_filters = [
                ["HD Agent", "agent_name", "like", f"%{search}%"],
                ["HD Agent", "user", "like", f"%{search}%"],
            ]

        agents = frappe.get_all(
            "HD Agent",
            fields=["name", "agent_name", "user", "is_active"],
            filters=filters,
            or_filters=or_filters or None,
            limit=limit,
            limit_start=offset,
            order_by="modified desc",
        )
        return json.dumps({"success": True, "count": len(agents), "results": agents}, default=str)
    except Exception as e:
        frappe.log_error(f"Helpdesk Get Agents Error: {e}", "Helpdesk Tool")
        return _error(str(e))


def _handle_get_teams(**kwargs) -> str:
    """List helpdesk teams."""
    if not _helpdesk_installed():
        return _error("Frappe Helpdesk app is not installed.")

    try:
        limit = int(kwargs.get("limit", 50))
        offset = int(kwargs.get("offset", 0))
        search = kwargs.get("search")
        or_filters = []
        if search:
            or_filters = [
                ["HD Team", "team_name", "like", f"%{search}%"],
            ]

        teams = frappe.get_all(
            "HD Team",
            fields=["name", "team_name", "ignore_restrictions", "assignment_rule"],
            or_filters=or_filters or None,
            limit=limit,
            limit_start=offset,
            order_by="modified desc",
        )
        return json.dumps({"success": True, "count": len(teams), "results": teams}, default=str)
    except Exception as e:
        frappe.log_error(f"Helpdesk Get Teams Error: {e}", "Helpdesk Tool")
        return _error(str(e))


def _handle_assign_ticket(**kwargs) -> str:
    """Assign ticket to an agent."""
    if not _helpdesk_installed():
        return _error("Frappe Helpdesk app is not installed.")

    try:
        ticket_id = kwargs.get("ticket_id")
        agent_id = kwargs.get("agent_id") or frappe.session.user
        if not ticket_id:
            return _error("ticket_id is required")
        if not frappe.db.exists("HD Ticket", ticket_id):
            return _error(f"Ticket {ticket_id} not found")
        if not frappe.db.exists("HD Agent", agent_id):
            return _error(f"Agent {agent_id} not found")

        doc = frappe.get_doc("HD Ticket", ticket_id)
        doc.assign_agent(agent_id)

        return json.dumps({"success": True, "results": {"name": doc.name, "assigned_to": agent_id}}, default=str)
    except Exception as e:
        frappe.log_error(f"Helpdesk Assign Ticket Error: {e}", "Helpdesk Tool")
        return _error(str(e))


def handle_action(**kwargs) -> str:
    action = kwargs.get("action", "").strip().lower()
    dispatch = {
        "list_tickets": _handle_get_tickets,
        "get_ticket": _handle_get_ticket,
        "create_ticket": _handle_create_ticket,
        "update_ticket": _handle_update_ticket,
        "add_comment": _handle_add_comment,
        "list_agents": _handle_get_agents,
        "list_teams": _handle_get_teams,
        "assign_ticket": _handle_assign_ticket,
    }
    handler = dispatch.get(action)
    if not handler:
        valid = ", ".join(sorted(dispatch.keys()))
        return json.dumps({"success": False, "error": f"Unknown action '{action}'. Valid: {valid}"}, default=str)
    return handler(**kwargs)
