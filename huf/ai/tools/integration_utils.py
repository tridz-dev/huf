# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Generic integration utilities: attach service tools to Agents."""

from typing import Optional

import frappe
from frappe import _


SERVICE_TOOL_TYPE_MAP = {
    "frappe_cloud": "Frappe Cloud",
}


def _service_to_tool_type(service: str) -> Optional[str]:
    """Map an Integration Service key to an Agent Tool Type name."""
    if not service:
        return None
    service = service.lower().strip()
    if service in SERVICE_TOOL_TYPE_MAP:
        return SERVICE_TOOL_TYPE_MAP[service]
    # Fallback: title-case the service key (e.g. "frappe_cloud" -> "Frappe Cloud")
    return " ".join(part.title() for part in service.replace("-", "_").split("_"))


def _get_tool_type_name(service: str) -> str:
    """Return the Agent Tool Type name for a service, raising if missing."""
    tool_type = _service_to_tool_type(service)
    if not tool_type or not frappe.db.exists("Agent Tool Type", tool_type):
        frappe.throw(_("No tools found for service '{0}'").format(service))
    return tool_type


def _get_tools_for_service(service: str) -> list[dict]:
    """Return Agent Tool Function docs that belong to the given service."""
    # Prefer the explicit service field; fall back to tool_type mapping.
    filters = [["service", "=", service]]
    tools_by_service = frappe.get_all(
        "Agent Tool Function",
        filters=filters,
        fields=["name", "tool_name", "description", "tool_type", "service"],
        order_by="tool_name",
    )
    if tools_by_service:
        return tools_by_service

    tool_type = _get_tool_type_name(service)
    return frappe.get_all(
        "Agent Tool Function",
        filters={"tool_type": tool_type},
        fields=["name", "tool_name", "description", "tool_type", "service"],
        order_by="tool_name",
    )


@frappe.whitelist()
def get_service_tools(service: str) -> dict:
    """Return tools that belong to an integration service."""
    if not service:
        frappe.throw(_("Service is required"))

    tools = _get_tools_for_service(service)
    return {"success": True, "tools": tools}


@frappe.whitelist()
def attach_service_tools(service: str, tool_names: list[str], agents: Optional[list[str]] = None):
    """
    Attach one or more Agent Tool Function docs (belonging to a service) to Agents.

    Args:
        service: Integration service key (e.g. "frappe_cloud").
        tool_names: List of tool_name values to attach.
        agents: List of Agent docnames to attach tools to.

    Returns:
        dict with attached_to_agents count and skipped count.
    """
    if not service:
        frappe.throw(_("Service is required"))
    if not tool_names:
        frappe.throw(_("At least one tool is required"))
    if not agents:
        return {"attached_to_agents": 0, "skipped": 0, "errors": []}

    tools = _get_tools_for_service(service)
    service_tool_names = {t["tool_name"] for t in tools}
    service_tool_by_name = {t["tool_name"]: t["name"] for t in tools}

    invalid = [name for name in tool_names if name not in service_tool_names]
    if invalid:
        frappe.throw(_("Tools not part of service '{0}': {1}").format(service, ", ".join(invalid)))

    attached = 0
    skipped = 0
    errors = []

    for agent_name in agents:
        try:
            if not frappe.db.exists("Agent", agent_name):
                errors.append(f"Agent '{agent_name}' not found")
                continue

            agent_doc = frappe.get_doc("Agent", agent_name)
            if not frappe.has_permission("Agent", "write", doc=agent_doc):
                errors.append(f"No write permission for Agent '{agent_name}'")
                continue

            existing_tools = {row.tool for row in agent_doc.agent_tool or []}
            changed = False

            for tool_name in tool_names:
                tool_docname = service_tool_by_name[tool_name]
                if tool_docname in existing_tools:
                    skipped += 1
                    continue
                agent_doc.append("agent_tool", {"tool": tool_docname})
                attached += 1
                changed = True

            if changed:
                agent_doc.save(ignore_permissions=True)

        except Exception as e:
            error_msg = str(e)
            frappe.log_error(
                f"attach_service_tools failed for agent {agent_name}: {error_msg}",
                "Attach Service Tools",
            )
            errors.append(f"Agent '{agent_name}': {error_msg}")
            continue

    if errors:
        frappe.log_error(
            "attach_service_tools completed with errors:\n" + "\n".join(errors),
            "Attach Service Tools",
        )

    return {"attached_to_agents": attached, "skipped": skipped, "errors": errors}
