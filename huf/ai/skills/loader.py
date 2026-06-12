"""Runtime skill loader for the Huf Skills system.

This module turns Skill definitions attached to an Agent into concrete runtime
capabilities: FunctionTool instances, mandatory knowledge source configs,
MCP server names, and system prompt additions.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import frappe
from agents import FunctionTool


# Map of standard tool types to their handler function paths.
# Mirrors the mapping in huf.ai.sdk_tools.create_agent_tools.
_STANDARD_TOOL_PATHS = {
    "Get List": "huf.ai.sdk_tools.handle_get_list",
    "Get Document": "huf.ai.sdk_tools.handle_get_document",
    "Update Document": "huf.ai.sdk_tools.handle_update_document",
    "Create Document": "huf.ai.sdk_tools.handle_create_document",
    "Delete Document": "huf.ai.sdk_tools.handle_delete_document",
    "Get Multiple Documents": "huf.ai.sdk_tools.handle_get_documents",
    "Create Multiple Documents": "huf.ai.sdk_tools.handle_create_documents",
    "Update Multiple Documents": "huf.ai.sdk_tools.handle_update_documents",
    "Delete Multiple Documents": "huf.ai.sdk_tools.handle_delete_documents",
    "Submit Document": "huf.ai.sdk_tools.handle_submit_document",
    "Cancel Document": "huf.ai.sdk_tools.handle_cancel_document",
    "Get Value": "huf.ai.sdk_tools.handle_get_value",
    "Set Value": "huf.ai.sdk_tools.handle_set_value",
    "Get Report Result": "huf.ai.sdk_tools.handle_get_report_result",
    "GET": "huf.ai.http_handler.handle_get_request",
    "POST": "huf.ai.http_handler.handle_post_request",
    "Run Agent": "huf.ai.sdk_tools.handle_run_agent",
    "Attach File to Document": "huf.ai.sdk_tools.handle_attach_file_to_document",
    "Get Conversation Data": "huf.ai.sdk_tools.handle_get_conversation_data",
    "Set Conversation Data": "huf.ai.sdk_tools.handle_set_conversation_data",
    "Load Conversation Data": "huf.ai.sdk_tools.handle_load_conversation_data",
}


def _skill_doctypes_exist() -> bool:
    """Return True if the Skill DocTypes have been installed."""
    try:
        return frappe.db.exists("DocType", "Skill") and frappe.db.exists("DocType", "Agent Skill")
    except Exception:
        return False


def get_agent_skills(agent_name: str, mode: Optional[str] = None):
    """Return Skill docs attached to an agent, optionally filtered by mode.

    Only skills with status "Active" are returned.
    """
    if not _skill_doctypes_exist():
        return []

    try:
        agent = frappe.get_doc("Agent", agent_name)
    except Exception:
        return []

    skills = []
    for row in agent.get("agent_skill", []):
        if mode and getattr(row, "mode", None) != mode:
            continue
        try:
            skill = frappe.get_doc("Skill", row.skill)
            if getattr(skill, "status", "Active") != "Active":
                continue
            skills.append(skill)
        except Exception:
            continue

    return skills


def get_agent_skill_mcp_servers(agent_name: str) -> list[str]:
    """Return enabled MCP server names from all attached skills."""
    servers = []
    seen = set()

    for skill in get_agent_skills(agent_name):
        for row in skill.get("skill_mcp_servers", []):
            if not getattr(row, "enabled", 1):
                continue
            name = getattr(row, "mcp_server", None)
            if name and name not in seen:
                seen.add(name)
                servers.append(name)

    return servers


def _resolve_tool_function_path(tool_doc) -> Optional[str]:
    """Resolve the handler function path for an Agent Tool Function doc."""
    tool_type = tool_doc.types

    if tool_type in ("Custom Function", "App Provided"):
        return tool_doc.function_path or None

    if tool_type == "Client Side Tool":
        if not tool_doc.function_name:
            return None
        return "huf.ai.cilent_side_tool.client_side_function"

    return _STANDARD_TOOL_PATHS.get(tool_type)


def _build_tool_parameters(tool_doc) -> dict:
    """Build the parameter schema for a tool from its doc."""
    params = {}

    # Prefer the computed function definition, fall back to raw params JSON.
    raw = getattr(tool_doc, "function_definition", None) or getattr(tool_doc, "params", None)
    if raw:
        try:
            params = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except Exception:
            params = {}

    if not isinstance(params, dict):
        params = {}

    if "additionalProperties" in params:
        del params["additionalProperties"]

    return params


def _build_extra_args(tool_doc, skill_tool_row=None) -> dict:
    """Build extra arguments passed to the tool handler at runtime."""
    extra_args = {}
    tool_type = tool_doc.types

    if tool_type == "Attach File to Document" and tool_doc.reference_doctype:
        extra_args["reference_doctype"] = tool_doc.reference_doctype

    elif (
        tool_type
        in {
            "Get Document",
            "Get Multiple Documents",
            "Get List",
            "Create Document",
            "Create Multiple Documents",
            "Update Document",
            "Update Multiple Documents",
            "Delete Document",
            "Delete Multiple Documents",
        }
        and tool_doc.reference_doctype
    ):
        extra_args["reference_doctype"] = tool_doc.reference_doctype

    elif tool_type == "Client Side Tool" and tool_doc.function_name:
        extra_args["function_name"] = tool_doc.function_name

    elif tool_type == "Run Agent" and tool_doc.agent:
        extra_args["target_agent_name"] = tool_doc.agent

    return extra_args


def load_all_skill_tools(agent_doc, user: str) -> list[FunctionTool]:
    """Return FunctionTool instances from all tools declared by attached skills.

    Both Mandatory and Optional skills are loaded at agent construction time.
    Tools are filtered by the user's permissions.
    """
    tools: list[FunctionTool] = []

    # Lazy imports to avoid circular dependencies between sdk_tools and loader.
    from huf.ai.sdk_tools import create_function_tool
    from huf.ai.tool_registry import PermissionAwareToolRegistry

    if not _skill_doctypes_exist():
        return tools

    agent_name = getattr(agent_doc, "agent_name", None)
    if not agent_name:
        return tools

    seen_names: set[str] = set()

    for skill in get_agent_skills(agent_name):
        for skill_tool in skill.get("skill_tools", []):
            try:
                tool_doc = frappe.get_doc("Agent Tool Function", skill_tool.tool)
            except Exception:
                continue

            if not PermissionAwareToolRegistry._can_use_tool(tool_doc, user):
                continue

            function_path = _resolve_tool_function_path(tool_doc)
            if not function_path:
                continue

            name = tool_doc.tool_name
            if not name or name in seen_names:
                continue

            description = getattr(skill_tool, "description", None) or tool_doc.description or ""
            params = _build_tool_parameters(tool_doc)
            extra_args = _build_extra_args(tool_doc, skill_tool)

            try:
                tool = create_function_tool(
                    name=name,
                    description=description,
                    tool_name=function_path,
                    parameters=params,
                    extra_args=extra_args,
                    tool_type=tool_doc.types,
                    allowed_for_guest=bool(getattr(tool_doc, "allowed_for_guest", False)),
                )
            except Exception as e:
                frappe.log_error(
                    f"Error creating skill tool '{name}' from skill '{skill.name}': {e!s}",
                    "Skill Tool Loading Error",
                )
                continue

            if tool:
                tools.append(tool)
                seen_names.add(name)

    return tools


def get_mandatory_skill_knowledge(agent_name: str) -> list[dict[str, Any]]:
    """Return mandatory knowledge source configs from attached skills.

    The returned dicts are compatible with huf.ai.knowledge.context_builder.build_knowledge_context.
    """
    sources = []
    seen: set[str] = set()

    for skill in get_agent_skills(agent_name):
        for row in skill.get("skill_knowledge", []):
            if getattr(row, "mode", "Mandatory") != "Mandatory":
                continue

            source_name = getattr(row, "knowledge_source", None)
            if not source_name or source_name in seen:
                continue

            seen.add(source_name)
            sources.append({
                "knowledge_source": source_name,
                "priority": getattr(row, "priority", 0) or 0,
                "max_chunks": getattr(row, "max_chunks", 5) or 5,
                "token_budget": getattr(row, "token_budget", 2000) or 2000,
            })

    # Sort by priority (higher first) to align with agent-level knowledge handling.
    sources.sort(key=lambda x: x["priority"], reverse=True)
    return sources


def get_skill_instructions(agent_name: str) -> str:
    """Concatenate instructions from all attached skills."""
    parts = []

    for skill in get_agent_skills(agent_name):
        instructions = getattr(skill, "instructions", None)
        if instructions and instructions.strip():
            parts.append(instructions.strip())

    if not parts:
        return ""

    return "\n\n".join(parts)


def get_optional_skills_preamble(agent_name: str) -> str:
    """Return a system prompt section listing optional skills."""
    optional_skills = []

    for skill in get_agent_skills(agent_name, mode="Optional"):
        description = getattr(skill, "description", None) or ""
        optional_skills.append(f"- {skill.skill_name}: {description}".strip())

    if not optional_skills:
        return ""

    return (
        "\n\nOptional skills available. "
        "Only use an optional skill when the user's request clearly matches its description:\n"
        + "\n".join(optional_skills)
    )


def handle_list_skills(agent_name: str, **kwargs) -> str:
    """Handler for the runtime list_skills tool."""
    skills = []

    for skill in get_agent_skills(agent_name):
        description = getattr(skill, "description", None) or ""
        skills.append(f"- {skill.skill_name}: {description}".strip())

    if not skills:
        return "No skills are attached to this agent."

    return "Skills available to this agent:\n" + "\n".join(skills)


def create_list_skills_tool(agent_name: str) -> Optional[FunctionTool]:
    """Build a runtime list_skills tool for the given agent."""
    if not _skill_doctypes_exist():
        return None

    if not get_agent_skills(agent_name):
        return None

    # Lazy import to avoid circular dependency.
    from huf.ai.sdk_tools import create_function_tool

    try:
        return create_function_tool(
            name="list_skills",
            description="List all skills attached to this agent.",
            tool_name="huf.ai.skills.loader.handle_list_skills",
            parameters={"type": "object", "properties": {}, "required": []},
            extra_args={"agent_name": agent_name},
        )
    except Exception as e:
        frappe.log_error(
            f"Error creating list_skills tool for agent '{agent_name}': {e!s}",
            "Skill Tool Loading Error",
        )
        return None
