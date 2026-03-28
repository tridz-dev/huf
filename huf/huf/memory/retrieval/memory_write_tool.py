"""Memory Write Tool - Tool implementation for creating memory records.

This module provides the memory_write tool that agents can call to create
new memory records during conversation or execution.

Based on:
    - PRD Section 15: Retrieval Model
    - CAPTURE_RETRIEVAL.md Section 3.3 (Tool-Only Mode)

Tool Type: Custom Function (App Provided)
Function Path: huf.memory.retrieval.memory_write_tool.memory_write
"""

from typing import Dict, Any, Optional, List
import frappe
from frappe import _


def memory_write(
    title: str,
    memory_type: str,
    data: Dict[str, Any],
    agent: Optional[str] = None,
    conversation: Optional[str] = None,
    run: Optional[str] = None,
    scope_type: str = "conversation",
    scope_key: Optional[str] = None,
    visibility: str = "private",
    summary: Optional[str] = None,
    confidence: float = 1.0,
    importance: float = 0.5,
    tags: Optional[List[str]] = None,
    schema_name: Optional[str] = None,
    profile_name: Optional[str] = None,
    ttl_days: Optional[int] = None,
    effective_from: Optional[str] = None,
    effective_until: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new memory record.

    This tool allows agents to capture structured or semi-structured memories
    during conversation or execution. Memories are scoped and can be retrieved
    later based on scope, type, and relevance.

    Args:
        title: Human-readable title for the memory
        memory_type: Type of memory - one of:
            - profile: User/agent profile information
            - session_state: Current session context
            - preference: User preferences and settings
            - fact: Facts and knowledge
            - plan: Plans and goals
            - observation: Observations from interaction
            - insight: Derived insights and learnings
            - domain_object: Domain-specific objects
            - custom: Custom memory type
        data: Structured data payload (JSON-serializable dict)
        agent: Agent ID (auto-filled from context if not provided)
        conversation: Conversation ID (auto-filled from context if not provided)
        run: Agent Run ID (auto-filled from context if not provided)
        scope_type: Scope for memory retrieval:
            - conversation: Limited to current conversation
            - user: Scoped to user across conversations
            - agent: Scoped to agent across all usage
            - namespace: Scoped to a namespace
            - global: Global scope
        scope_key: Specific scope identifier (e.g., conversation_id, user_id)
        visibility: Sharing level - private, shared_with_agent, shared_with_namespace, global
        summary: Optional human-readable summary
        confidence: Confidence score 0.0-1.0 (default: 1.0)
        importance: Importance score 0.0-1.0 (default: 0.5)
        tags: Optional list of tag strings
        schema_name: Optional schema name for structured data
        profile_name: Optional Memory Profile used for capture
        ttl_days: Optional time-to-live in days
        effective_from: Optional effective start datetime (ISO format)
        effective_until: Optional effective end datetime (ISO format)

    Returns:
        Dict with:
            - success: bool
            - memory_record: Name of created record (if success)
            - message: Status message
            - error: Error details (if failed)

    Example:
        >>> memory_write(
        ...     title="User Preference: Dark Mode",
        ...     memory_type="preference",
        ...     data={"theme": "dark", "preference_source": "explicit"},
        ...     scope_type="user",
        ...     importance=0.8
        ... )
        {"success": True, "memory_record": "MEM-2024-00001", "message": "Memory created"}
    """
    try:
        # Resolve agent from context if not provided
        if not agent:
            agent = _get_current_agent_from_context()
        
        if not agent:
            return {
                "success": False,
                "error": "Agent ID is required but not provided and could not be resolved from context"
            }

        # Resolve conversation from context if not provided
        if not conversation:
            conversation = _get_current_conversation_from_context()

        # Resolve scope_key if not provided
        if not scope_key:
            scope_key = _resolve_scope_key(scope_type, conversation)

        # Validate memory_type
        valid_types = [
            "profile", "session_state", "preference", "fact",
            "plan", "observation", "insight", "domain_object", "custom"
        ]
        if memory_type not in valid_types:
            return {
                "success": False,
                "error": f"Invalid memory_type: {memory_type}. Must be one of: {', '.join(valid_types)}"
            }

        # Validate scope_type
        valid_scopes = ["conversation", "user", "agent", "namespace", "global"]
        if scope_type not in valid_scopes:
            return {
                "success": False,
                "error": f"Invalid scope_type: {scope_type}. Must be one of: {', '.join(valid_scopes)}"
            }

        # Validate visibility
        valid_visibility = ["private", "shared_with_agent", "shared_with_namespace", "global"]
        if visibility not in valid_visibility:
            return {
                "success": False,
                "error": f"Invalid visibility: {visibility}. Must be one of: {', '.join(valid_visibility)}"
            }

        # Build memory record document
        memory_doc = {
            "doctype": "Memory Record",
            "title": title,
            "agent": agent,
            "conversation": conversation,
            "run": run,
            "source_type": _determine_source_type(run),
            "producer_mode": "main_agent",  # Tool calls are from main agent
            "memory_type": memory_type,
            "schema_name": schema_name,
            "profile_name": profile_name,
            "data_json": frappe.as_json(data) if data else "{}",
            "summary_text": summary,
            "scope_type": scope_type,
            "scope_key": scope_key or "default",
            "visibility": visibility,
            "status": "active",
            "confidence": confidence,
            "importance_score": importance,
        }

        # Add optional fields
        if ttl_days:
            memory_doc["ttl_days"] = ttl_days
        if effective_from:
            memory_doc["effective_from"] = effective_from
        if effective_until:
            memory_doc["effective_until"] = effective_until

        # Create the document
        doc = frappe.get_doc(memory_doc)
        
        # Add tags if provided
        if tags:
            for tag in tags:
                doc.append("tags", {"tag": tag})

        doc.insert()

        # Update retrieval stats (last_retrieved_at = creation, retrieval_count = 0)
        # This will be updated on actual retrieval

        frappe.db.commit()

        return {
            "success": True,
            "memory_record": doc.name,
            "message": f"Memory record '{title}' created successfully",
            "details": {
                "name": doc.name,
                "title": title,
                "memory_type": memory_type,
                "scope_type": scope_type,
                "scope_key": scope_key,
                "created_at": str(doc.creation)
            }
        }

    except frappe.DoesNotExistError as e:
        frappe.log_error(f"Memory write failed - referenced document not found: {str(e)}", "Memory Write Tool")
        return {
            "success": False,
            "error": f"Referenced document not found: {str(e)}"
        }
    except Exception as e:
        frappe.log_error(f"Memory write failed: {str(e)}", "Memory Write Tool")
        return {
            "success": False,
            "error": f"Failed to create memory record: {str(e)}"
        }


def _get_current_agent_from_context() -> Optional[str]:
    """Try to resolve current agent from execution context."""
    # Check for agent in frappe flags (set during agent execution)
    if hasattr(frappe.flags, "current_agent"):
        return frappe.flags.current_agent
    
    # Check local context
    if hasattr(frappe.local, "agent_context"):
        return frappe.local.agent_context.get("agent")
    
    return None


def _get_current_conversation_from_context() -> Optional[str]:
    """Try to resolve current conversation from execution context."""
    # Check for conversation in frappe flags
    if hasattr(frappe.flags, "current_conversation"):
        return frappe.flags.current_conversation
    
    # Check local context
    if hasattr(frappe.local, "agent_context"):
        return frappe.local.agent_context.get("conversation")
    
    return None


def _resolve_scope_key(scope_type: str, conversation_id: Optional[str]) -> str:
    """Resolve scope key based on scope type and available context."""
    if scope_type == "conversation":
        return conversation_id or "default"
    
    elif scope_type == "user":
        # Try to get user from context
        user = frappe.session.user
        if user and user != "Guest":
            return user
        return "anonymous"
    
    elif scope_type == "agent":
        agent = _get_current_agent_from_context()
        if agent:
            return agent
        return "default"
    
    elif scope_type == "namespace":
        # Try to get namespace from context
        if hasattr(frappe.local, "agent_context"):
            ns = frappe.local.agent_context.get("namespace")
            if ns:
                return ns
        return "default"
    
    elif scope_type == "global":
        return "global"
    
    return "default"


def _determine_source_type(run_id: Optional[str]) -> str:
    """Determine source type based on run presence."""
    if run_id:
        return "run"
    if _get_current_conversation_from_context():
        return "conversation"
    return "manual"


# Whitelist the function for agent tool execution
memory_write = frappe.whitelist(allow_guest=False)(memory_write)
