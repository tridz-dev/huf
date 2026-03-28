"""Memory Search Tool - Tool implementation for searching memories.

This module provides the memory_search tool that agents can call to search
for existing memory records based on query, filters, and scope.

Based on:
    - PRD Section 15: Retrieval Model (Tool-Only Mode)
    - CAPTURE_RETRIEVAL.md Section 3.3

Tool Type: Custom Function (App Provided)
Function Path: huf.memory.retrieval.memory_search_tool.memory_search

Dependencies:
    - E1: Memory Retrieval Service (COMPLETE)
"""

from typing import Dict, Any, Optional, List
import frappe
from frappe import _

from .retrieval_service import MemoryRetrievalService, RetrievalContext, RetrievalMode


def memory_search(
    query: Optional[str] = None,
    memory_type: Optional[str] = None,
    memory_types: Optional[List[str]] = None,
    scope_type: Optional[str] = None,
    tags: Optional[List[str]] = None,
    min_confidence: Optional[float] = None,
    min_importance: Optional[float] = None,
    limit: int = 10,
    offset: int = 0,
    agent: Optional[str] = None,
    conversation: Optional[str] = None,
    include_injected: bool = True,
) -> Dict[str, Any]:
    """Search for memory records.

    This tool allows agents to search for previously captured memories
    based on query text, memory type, scope, tags, and other filters.
    Results are ranked by relevance and importance.

    Args:
        query: Search query text to match against memory content
        memory_type: Filter by specific memory type
        memory_types: Filter by multiple memory types (list)
        scope_type: Filter by scope type (conversation, user, agent, namespace, global)
        tags: Filter by tags (memories must have all specified tags)
        min_confidence: Minimum confidence threshold (0.0-1.0)
        min_importance: Minimum importance threshold (0.0-1.0)
        limit: Maximum number of results to return (default: 10, max: 100)
        offset: Pagination offset for skipping results
        agent: Agent ID filter (auto-resolved from context if not provided)
        conversation: Conversation ID filter (auto-resolved from context)
        include_injected: Whether to include memories already injected in prompt

    Returns:
        Dict with:
            - success: bool
            - memories: List of matching memory records
            - total_found: Total number of matching records
            - query: The search query used
            - filters: Applied filters

    Example:
        >>> memory_search(
        ...     query="user preferences",
        ...     memory_type="preference",
        ...     limit=5
        ... )
        {
            "success": True,
            "memories": [
                {
                    "name": "MREC-2024-00001",
                    "title": "User Preference: Dark Mode",
                    "memory_type": "preference",
                    "summary": "User prefers dark mode interface",
                    "data": {"theme": "dark"},
                    "score": 0.95,
                    "confidence": 1.0,
                    "importance": 0.8
                }
            ],
            "total_found": 3,
            "query": "user preferences"
        }
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

        # Validate and limit
        limit = min(max(1, limit), 100)
        offset = max(0, offset)

        # Build filters
        filters = {}
        
        if memory_type:
            valid_types = [
                "profile", "session_state", "preference", "fact",
                "plan", "observation", "insight", "domain_object", "custom"
            ]
            if memory_type not in valid_types:
                return {
                    "success": False,
                    "error": f"Invalid memory_type: {memory_type}. Must be one of: {', '.join(valid_types)}"
                }
            filters["memory_type"] = memory_type
        
        if memory_types:
            valid_types = [
                "profile", "session_state", "preference", "fact",
                "plan", "observation", "insight", "domain_object", "custom"
            ]
            invalid = [t for t in memory_types if t not in valid_types]
            if invalid:
                return {
                    "success": False,
                    "error": f"Invalid memory_types: {', '.join(invalid)}"
                }
            filters["memory_type"] = ["in", memory_types]
        
        if scope_type:
            valid_scopes = ["conversation", "user", "agent", "namespace", "global"]
            if scope_type not in valid_scopes:
                return {
                    "success": False,
                    "error": f"Invalid scope_type: {scope_type}. Must be one of: {', '.join(valid_scopes)}"
                }
            filters["scope_type"] = scope_type
        
        if tags:
            # Tags filter requires special handling - memory must have ALL tags
            # This will be handled in the search query
            filters["tags"] = tags
        
        if min_confidence is not None:
            filters["confidence"] = [">=", max(0.0, min(1.0, min_confidence))]
        
        if min_importance is not None:
            filters["importance_score"] = [">=", max(0.0, min(1.0, min_importance))]

        # Create retrieval service
        service = MemoryRetrievalService()
        context = RetrievalContext(
            agent_name=agent,
            conversation_id=conversation,
            user_id=_get_current_user_from_context(),
        )

        # Execute search
        result = service.retrieve_for_tool(
            context=context,
            query=query,
            filters=filters,
            limit=limit,
            offset=offset,
        )

        # Format memories for response
        memories = []
        for memory in result.memories:
            memory_dict = {
                "name": memory.name,
                "title": memory.title,
                "memory_type": memory.memory_type,
                "summary": memory.summary_text,
                "data": memory.data_json,
                "score": round(memory.score, 3),
                "confidence": memory.confidence,
                "importance": memory.importance_score,
                "scope_type": memory.scope_type,
                "scope_key": memory.scope_key,
                "created_at": memory.created_at.isoformat() if memory.created_at else None,
                "tags": memory.tags,
            }
            memories.append(memory_dict)

        return {
            "success": True,
            "memories": memories,
            "total_found": result.total_found,
            "returned_count": len(memories),
            "query": query,
            "filters": {
                "memory_type": memory_type or memory_types,
                "scope_type": scope_type,
                "tags": tags,
                "min_confidence": min_confidence,
                "min_importance": min_importance,
            },
            "pagination": {
                "limit": limit,
                "offset": offset,
                "has_more": result.total_found > (offset + limit)
            }
        }

    except Exception as e:
        frappe.log_error(f"Memory search failed: {str(e)}", "Memory Search Tool")
        return {
            "success": False,
            "error": f"Failed to search memories: {str(e)}"
        }


def memory_get_recent(
    agent: Optional[str] = None,
    conversation: Optional[str] = None,
    memory_type: Optional[str] = None,
    limit: int = 5,
) -> Dict[str, Any]:
    """Get recent memories ordered by creation time.

    A convenience tool for retrieving the most recently created memories
    without needing a search query.

    Args:
        agent: Agent ID filter (auto-resolved from context)
        conversation: Conversation ID filter (auto-resolved from context)
        memory_type: Optional filter by memory type
        limit: Number of recent memories to retrieve (default: 5, max: 50)

    Returns:
        Dict with success status and list of recent memories
    """
    try:
        # Resolve agent from context
        if not agent:
            agent = _get_current_agent_from_context()
        
        if not agent:
            return {
                "success": False,
                "error": "Agent ID is required but not provided and could not be resolved from context"
            }

        conversation = conversation or _get_current_conversation_from_context()
        limit = min(max(1, limit), 50)

        # Build query
        filters = {
            "agent": agent,
            "status": "active",
        }
        
        if conversation:
            filters["conversation"] = conversation
        
        if memory_type:
            filters["memory_type"] = memory_type

        # Query recent memories
        records = frappe.get_all(
            "Memory Record",
            filters=filters,
            fields=[
                "name", "title", "memory_type", "summary_text", "data_json",
                "scope_type", "scope_key", "confidence", "importance_score", "creation"
            ],
            order_by="creation desc",
            limit=limit,
        )

        memories = []
        for r in records:
            memories.append({
                "name": r.name,
                "title": r.title,
                "memory_type": r.memory_type,
                "summary": r.summary_text,
                "data": frappe.parse_json(r.data_json or "{}"),
                "scope_type": r.scope_type,
                "scope_key": r.scope_key,
                "confidence": r.confidence,
                "importance": r.importance_score,
                "created_at": r.creation.isoformat() if r.creation else None,
            })

        return {
            "success": True,
            "memories": memories,
            "count": len(memories),
        }

    except Exception as e:
        frappe.log_error(f"Memory get_recent failed: {str(e)}", "Memory Search Tool")
        return {
            "success": False,
            "error": f"Failed to retrieve recent memories: {str(e)}"
        }


def memory_get_by_type(
    memory_type: str,
    agent: Optional[str] = None,
    conversation: Optional[str] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """Get memories filtered by type.

    A convenience tool for retrieving memories of a specific type.

    Args:
        memory_type: Type of memories to retrieve (required)
        agent: Agent ID filter (auto-resolved from context)
        conversation: Conversation ID filter (auto-resolved from context)
        limit: Maximum results (default: 10, max: 50)

    Returns:
        Dict with success status and list of memories
    """
    return memory_search(
        query=None,
        memory_type=memory_type,
        agent=agent,
        conversation=conversation,
        limit=limit,
    )


def memory_get_by_scope(
    scope_type: str,
    scope_key: Optional[str] = None,
    agent: Optional[str] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """Get memories filtered by scope.

    A convenience tool for retrieving memories within a specific scope.

    Args:
        scope_type: Scope type (conversation, user, agent, namespace, global)
        scope_key: Specific scope identifier (auto-resolved if not provided)
        agent: Agent ID filter (auto-resolved from context)
        limit: Maximum results (default: 10, max: 50)

    Returns:
        Dict with success status and list of memories
    """
    try:
        # Resolve agent from context
        if not agent:
            agent = _get_current_agent_from_context()
        
        if not agent:
            return {
                "success": False,
                "error": "Agent ID is required but not provided and could not be resolved from context"
            }

        # Resolve scope_key if not provided
        if not scope_key:
            if scope_type == "conversation":
                scope_key = _get_current_conversation_from_context() or "default"
            elif scope_type == "user":
                scope_key = _get_current_user_from_context() or "anonymous"
            elif scope_type == "agent":
                scope_key = agent
            else:
                scope_key = "default"

        limit = min(max(1, limit), 50)

        filters = {
            "agent": agent,
            "scope_type": scope_type,
            "scope_key": scope_key,
            "status": "active",
        }

        records = frappe.get_all(
            "Memory Record",
            filters=filters,
            fields=[
                "name", "title", "memory_type", "summary_text", "data_json",
                "confidence", "importance_score", "creation"
            ],
            order_by="importance_score desc, modified desc",
            limit=limit,
        )

        memories = []
        for r in records:
            memories.append({
                "name": r.name,
                "title": r.title,
                "memory_type": r.memory_type,
                "summary": r.summary_text,
                "data": frappe.parse_json(r.data_json or "{}"),
                "confidence": r.confidence,
                "importance": r.importance_score,
                "created_at": r.creation.isoformat() if r.creation else None,
            })

        return {
            "success": True,
            "memories": memories,
            "count": len(memories),
            "scope": {
                "type": scope_type,
                "key": scope_key,
            }
        }

    except Exception as e:
        frappe.log_error(f"Memory get_by_scope failed: {str(e)}", "Memory Search Tool")
        return {
            "success": False,
            "error": f"Failed to retrieve memories by scope: {str(e)}"
        }


# Helper functions

def _get_current_agent_from_context() -> Optional[str]:
    """Try to resolve current agent from execution context."""
    if hasattr(frappe.flags, "current_agent"):
        return frappe.flags.current_agent
    if hasattr(frappe.local, "agent_context"):
        return frappe.local.agent_context.get("agent")
    return None


def _get_current_conversation_from_context() -> Optional[str]:
    """Try to resolve current conversation from execution context."""
    if hasattr(frappe.flags, "current_conversation"):
        return frappe.flags.current_conversation
    if hasattr(frappe.local, "agent_context"):
        return frappe.local.agent_context.get("conversation")
    return None


def _get_current_user_from_context() -> Optional[str]:
    """Get current user from session."""
    user = frappe.session.user
    if user and user != "Guest":
        return user
    return None


# Whitelist the functions for agent tool execution
memory_search = frappe.whitelist(allow_guest=False)(memory_search)
memory_get_recent = frappe.whitelist(allow_guest=False)(memory_get_recent)
memory_get_by_type = frappe.whitelist(allow_guest=False)(memory_get_by_type)
memory_get_by_scope = frappe.whitelist(allow_guest=False)(memory_get_by_scope)
