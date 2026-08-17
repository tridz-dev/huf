# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""
Whitelisted API endpoints for HUF Projects and pinned conversations.

Provides REST-style APIs for:
- HUF Project CRUD (list, get, create, update, archive)
- Conversation Pin lifecycle (pin, unpin, list pinned)
- Moving an existing Agent Conversation in/out of a Project

Security note: every method resolves "the current user" from
``frappe.session.user`` and enforces permissions via
``frappe.has_permission`` / a document's own ``has_permission`` check.
A ``user`` value supplied by the client is never trusted for
permission-sensitive operations.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now_datetime

logger = frappe.logger("huf")

# Fields on HUF Project that a client is allowed to mutate via update_project.
_PROJECT_UPDATABLE_FIELDS = ("project_name", "description", "instructions", "default_agent", "status")

_PROJECT_LIST_FIELDS = [
    "name",
    "project_name",
    "description",
    "default_agent",
    "status",
    "last_activity",
    "modified",
]


# ---------------------------------------------------------------------------
# HUF Project APIs
# ---------------------------------------------------------------------------


@frappe.whitelist()
def list_projects(status: str | None = None) -> list[dict]:
    """
    List HUF Projects visible to the current user.

    Args:
        status: Optional status filter ("Open" / "Archived").

    Returns:
        list of dicts with project summary fields.
    """
    if not frappe.has_permission("HUF Project", "read"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    filters = {}
    if status:
        filters["status"] = status

    return frappe.get_list(
        "HUF Project",
        filters=filters,
        fields=_PROJECT_LIST_FIELDS,
        order_by="modified desc",
    )


@frappe.whitelist()
def get_project(project: str) -> dict:
    """
    Get a single HUF Project.

    Args:
        project: HUF Project name.

    Returns:
        dict of the project's fields.
    """
    doc = frappe.get_doc("HUF Project", project)
    if not doc.has_permission("read"):
        frappe.throw(_("You do not have permission to view this project."), frappe.PermissionError)

    return doc.as_dict()


@frappe.whitelist()
def create_project(
    project_name: str,
    description: str | None = None,
    instructions: str | None = None,
    default_agent: str | None = None,
) -> dict:
    """
    Create a new HUF Project.

    Args:
        project_name: Human-readable project name (required).
        description: Optional short description.
        instructions: Optional project-level context/instructions.
        default_agent: Optional default Agent for new project chats.
            Ownership is not implied; the Agent must still be usable by
            the current user under normal chat-availability rules.

    Returns:
        dict of the created project's fields.
    """
    if not frappe.has_permission("HUF Project", "create"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    if not project_name or not project_name.strip():
        frappe.throw(_("Project name is required"))

    if default_agent:
        _validate_agent_access(default_agent)

    doc = frappe.get_doc(
        {
            "doctype": "HUF Project",
            "project_name": project_name.strip(),
            "description": description,
            "instructions": instructions,
            "default_agent": default_agent,
            "status": "Open",
            "last_activity": now_datetime(),
        }
    )
    doc.insert()

    return doc.as_dict()


@frappe.whitelist()
def update_project(
    project: str,
    project_name: str | None = None,
    description: str | None = None,
    instructions: str | None = None,
    default_agent: str | None = None,
    status: str | None = None,
) -> dict:
    """
    Update an existing HUF Project. Only known, explicit fields are
    accepted -- arbitrary client-supplied field mutation is not allowed.

    Args:
        project: HUF Project name.
        project_name: New project name, if changing.
        description: New description, if changing.
        instructions: New instructions, if changing.
        default_agent: New default Agent, if changing (empty string clears it).
        status: New status ("Open" / "Archived"), if changing.

    Returns:
        dict of the updated project's fields.
    """
    doc = frappe.get_doc("HUF Project", project)
    if not doc.has_permission("write"):
        frappe.throw(_("You do not have permission to edit this project."), frappe.PermissionError)

    updates = {
        "project_name": project_name,
        "description": description,
        "instructions": instructions,
        "default_agent": default_agent,
        "status": status,
    }

    changed = False
    for fieldname in _PROJECT_UPDATABLE_FIELDS:
        value = updates[fieldname]
        if value is None:
            continue
        if fieldname == "default_agent" and value:
            _validate_agent_access(value)
        doc.set(fieldname, value)
        changed = True

    if changed:
        doc.save()

    return doc.as_dict()


@frappe.whitelist()
def archive_project(project: str) -> dict:
    """
    Archive a HUF Project (status transition, not a destructive delete).

    Args:
        project: HUF Project name.

    Returns:
        dict of the archived project's fields.
    """
    doc = frappe.get_doc("HUF Project", project)
    if not doc.has_permission("write"):
        frappe.throw(_("You do not have permission to archive this project."), frappe.PermissionError)

    doc.status = "Archived"
    doc.save()

    return doc.as_dict()


def _validate_agent_access(agent: str) -> None:
    """Raise if `agent` does not exist or is not usable by the current user."""
    if not frappe.db.exists("Agent", agent):
        frappe.throw(_("Agent {0} does not exist").format(agent))

    from huf.ai.agent_integration import _is_user_allowed

    agent_doc = frappe.get_cached_doc("Agent", agent)
    if not _is_user_allowed(agent_doc, frappe.session.user):
        frappe.throw(_("You do not have access to agent {0}").format(agent), frappe.PermissionError)


# ---------------------------------------------------------------------------
# Conversation Pin APIs
# ---------------------------------------------------------------------------


@frappe.whitelist()
def pin_conversation(conversation: str) -> dict:
    """
    Pin a conversation for the current user. Idempotent: pinning an
    already-pinned conversation returns the existing pin rather than
    raising.

    Args:
        conversation: Agent Conversation name.

    Returns:
        dict with pin metadata (name, user, conversation, pinned_at).
    """
    if not frappe.has_permission("Agent Conversation", "read", doc=conversation):
        frappe.throw(_("You do not have permission to pin this conversation."), frappe.PermissionError)

    user = frappe.session.user

    existing = frappe.db.get_value(
        "Conversation Pin",
        {"user": user, "conversation": conversation},
        ["name", "user", "conversation", "pinned_at"],
        as_dict=True,
    )
    if existing:
        return existing

    doc = frappe.get_doc(
        {
            "doctype": "Conversation Pin",
            "user": user,
            "conversation": conversation,
            "pinned_at": now_datetime(),
        }
    )
    doc.insert(ignore_permissions=True)

    return {"name": doc.name, "user": doc.user, "conversation": doc.conversation, "pinned_at": doc.pinned_at}


@frappe.whitelist()
def unpin_conversation(conversation: str) -> dict:
    """
    Unpin a conversation for the current user. Idempotent: returns
    success even if no pin existed.

    Args:
        conversation: Agent Conversation name.

    Returns:
        dict with {"success": True}.
    """
    user = frappe.session.user

    pin_name = frappe.db.get_value("Conversation Pin", {"user": user, "conversation": conversation}, "name")
    if pin_name:
        frappe.delete_doc("Conversation Pin", pin_name, ignore_permissions=True)

    return {"success": True}


@frappe.whitelist()
def get_pinned_conversations(project: str | None = None) -> list[dict]:
    """
    List the current user's pinned conversations, most recently pinned
    first, optionally scoped to a Project.

    Args:
        project: Optional HUF Project name to filter to.

    Returns:
        list of dicts with conversation summary fields plus `pinned_at`.
    """
    user = frappe.session.user

    Pin = frappe.qb.DocType("Conversation Pin")
    Conv = frappe.qb.DocType("Agent Conversation")

    query = (
        frappe.qb.from_(Pin)
        .inner_join(Conv)
        .on(Pin.conversation == Conv.name)
        .where(Pin.user == user)
        .select(Pin.conversation, Pin.pinned_at)
        .orderby(Pin.pinned_at, order=frappe.qb.desc)
        # Pinned is a small, deliberate set rather than a paginated list, but
        # this still caps the query so a user with an unusually large pin
        # history can't turn it into an unbounded fetch. Matches useChatList's
        # page size. The join+filter on project happens before this limit is
        # applied, so a project with fewer than 20 pins isn't starved by pins
        # in other projects.
        .limit(20)
    )
    if project:
        query = query.where(Conv.project == project)

    pins = query.run(as_dict=True)
    if not pins:
        return []

    pinned_at_by_conversation = {p.conversation: p.pinned_at for p in pins}
    conversation_names = list(pinned_at_by_conversation.keys())

    conversations = frappe.get_list(
        "Agent Conversation",
        filters={"name": ["in", conversation_names]},
        fields=["name", "title", "agent", "project", "model", "last_activity", "channel"],
    )

    for conv in conversations:
        conv["pinned_at"] = pinned_at_by_conversation.get(conv["name"])

    conversations.sort(key=lambda c: c["pinned_at"] or "", reverse=True)

    return conversations


# ---------------------------------------------------------------------------
# Conversation <-> Project association
# ---------------------------------------------------------------------------


@frappe.whitelist()
def set_conversation_project(conversation: str, project: str | None = None) -> dict:
    """
    Move an existing Agent Conversation in or out of a Project.

    The Agent on the conversation is never changed; only the `project`
    link is updated. Passing `project=None` (or an empty string) clears
    the conversation's project.

    Args:
        conversation: Agent Conversation name.
        project: HUF Project name to attach, or None/"" to clear.

    Returns:
        dict with {"conversation": ..., "project": ...}.
    """
    doc = frappe.get_doc("Agent Conversation", conversation)
    if not doc.has_permission("write"):
        frappe.throw(_("You do not have permission to modify this conversation."), frappe.PermissionError)

    project = project or None
    if project:
        project_doc = frappe.get_doc("HUF Project", project)
        if not project_doc.has_permission("read"):
            frappe.throw(_("You do not have permission to use this project."), frappe.PermissionError)

    doc.db_set("project", project)

    return {"conversation": doc.name, "project": project}
