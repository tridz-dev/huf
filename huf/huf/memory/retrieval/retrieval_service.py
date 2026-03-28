"""Memory Retrieval Service - Unified service layer for memory retrieval.

This module provides a high-level service interface for retrieving memories
with support for different retrieval modes (inject, tool_only, hybrid) and
scope-aware filtering.

Based on:
    - PRD Section 15: Retrieval Model
    - CAPTURE_RETRIEVAL.md Section 3: Retrieval Modes

Dependencies:
    - A1: Memory Record DocType (COMPLETE)
    - D1: Canonical Storage Service (COMPLETE)
"""

from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field
from datetime import datetime
import frappe
from frappe import _

from ..retrieval import (
    RetrievalMode,
    MemoryRetrievalConfig,
    get_retrieval_mode,
    InjectRetrievalMode,
    ToolOnlyRetrievalMode,
    HybridRetrievalMode,
)
from ..search import MemorySearcher, MemoryFilterBuilder, MemorySearchResult


@dataclass
class RetrievalContext:
    """Context for memory retrieval operations.
    
    Encapsulates all context needed to scope memory retrieval:
    - agent_name: The agent requesting memories
    - conversation_id: Current conversation (if any)
    - user_id: Current user
    - run_id: Current agent run (if any)
    - namespace: Optional namespace scope
    """
    agent_name: str
    conversation_id: Optional[str] = None
    user_id: Optional[str] = None
    run_id: Optional[str] = None
    namespace: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary for serialization."""
        return {
            "agent_name": self.agent_name,
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "run_id": self.run_id,
            "namespace": self.namespace,
        }


@dataclass
class RetrievalResult:
    """Result of a memory retrieval operation.
    
    Provides a standardized result structure regardless of retrieval mode.
    """
    mode: RetrievalMode
    memories: List[MemorySearchResult]
    total_found: int
    injected_count: int = 0
    tool_count: int = 0
    estimated_tokens: int = 0
    query: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for API responses."""
        return {
            "mode": self.mode.value,
            "memories": [
                {
                    "name": m.name,
                    "title": m.title,
                    "memory_type": m.memory_type,
                    "summary": m.summary_text,
                    "data": m.data_json,
                    "score": m.score,
                    "confidence": m.confidence,
                    "importance": m.importance_score,
                    "scope_type": m.scope_type,
                    "scope_key": m.scope_key,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in self.memories
            ],
            "total_found": self.total_found,
            "injected_count": self.injected_count,
            "tool_count": self.tool_count,
            "estimated_tokens": self.estimated_tokens,
            "query": self.query,
            "metadata": self.metadata,
        }


class MemoryRetrievalService:
    """Service layer for memory retrieval operations.
    
    Provides a unified interface for retrieving memories with support for:
    - Multiple retrieval modes (inject, tool_only, hybrid)
    - Scope-aware filtering (conversation, user, agent, namespace, global)
    - Token budgeting for prompt injection
    - Relevance ranking and scoring
    
    Usage:
        service = MemoryRetrievalService()
        context = RetrievalContext(agent_name="MyAgent", conversation_id="CONV-001")
        result = service.retrieve_for_injection(context)
    """
    
    def __init__(self, config: Optional[MemoryRetrievalConfig] = None):
        """Initialize the retrieval service.
        
        Args:
            config: Optional retrieval configuration. Uses defaults if not provided.
        """
        self.config = config or MemoryRetrievalConfig()
        self.searcher = MemorySearcher()
    
    def retrieve_for_injection(
        self,
        context: RetrievalContext,
        query: Optional[str] = None,
        max_items: Optional[int] = None,
        max_tokens: Optional[int] = None,
    ) -> RetrievalResult:
        """Retrieve memories for prompt injection.
        
        This is the primary method for getting memories to inject into
        agent prompts. It applies token budgeting and returns the most
        relevant memories that fit within the budget.
        
        Args:
            context: Retrieval context (agent, conversation, user, etc.)
            query: Optional query for relevance ranking
            max_items: Maximum items to retrieve (overrides config)
            max_tokens: Maximum tokens for content (overrides config)
        
        Returns:
            RetrievalResult with memories formatted for injection
        """
        max_items = max_items or self.config.inject_max_items
        max_tokens = max_tokens or self.config.inject_max_tokens
        
        # Build filters for injection
        builder = MemoryFilterBuilder()
        builder.add_scope_filter(
            agent_name=context.agent_name,
            conversation_id=context.conversation_id,
            user_id=context.user_id,
        )
        builder.add_status_filter(status="active")
        
        # Add effective date filter (memories valid now)
        builder.add_temporal_filter(effective_now=True)
        
        # Execute search
        memories = self.searcher.search(
            query=query or "",
            filters=builder.build(),
            limit=max_items * 2,  # Get extra for token filtering
            order_by=["-importance_score", "-modified"],
        )
        
        # Apply token budget
        filtered_memories, token_count = self._apply_token_budget(
            memories, max_tokens
        )
        
        # Limit to max_items
        filtered_memories = filtered_memories[:max_items]
        
        # Update retrieval stats for fetched memories
        self._update_retrieval_stats([m.name for m in filtered_memories])
        
        return RetrievalResult(
            mode=RetrievalMode.INJECT,
            memories=filtered_memories,
            total_found=len(memories),
            injected_count=len(filtered_memories),
            estimated_tokens=token_count,
            query=query,
        )
    
    def retrieve_for_tool(
        self,
        context: RetrievalContext,
        query: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> RetrievalResult:
        """Retrieve memories for tool-based search.
        
        This method is called when the agent invokes the memory_search tool.
        It provides flexible search with filtering and pagination.
        
        Args:
            context: Retrieval context
            query: Search query string
            filters: Additional filters (memory_type, tags, etc.)
            limit: Maximum results to return
            offset: Pagination offset
        
        Returns:
            RetrievalResult with search results
        """
        limit = limit or self.config.tool_default_limit
        limit = min(limit, self.config.tool_max_limit)
        
        # Build filters
        builder = MemoryFilterBuilder()
        builder.add_scope_filter(
            agent_name=context.agent_name,
            conversation_id=context.conversation_id,
            user_id=context.user_id,
        )
        builder.add_status_filter(status="active")
        
        if filters:
            # Merge provided filters
            for key, value in filters.items():
                if isinstance(value, list) and len(value) == 2 and value[0] in ["=", "!=", "in", "not in", ">", "<", ">=", "<="]:
                    builder.add_filter(key, value[0], value[1])
                else:
                    builder.add_filter(key, "=", value)
        
        # Execute search
        memories = self.searcher.search(
            query=query or "",
            filters=builder.build(),
            limit=limit,
            offset=offset,
            order_by=["-importance_score", "-modified"],
        )
        
        # Update retrieval stats
        self._update_retrieval_stats([m.name for m in memories])
        
        return RetrievalResult(
            mode=RetrievalMode.TOOL_ONLY,
            memories=memories,
            total_found=len(memories),
            tool_count=len(memories),
            query=query,
        )
    
    def retrieve_hybrid(
        self,
        context: RetrievalContext,
        query: Optional[str] = None,
        inject_max_items: Optional[int] = None,
        inject_max_tokens: Optional[int] = None,
        tool_limit: Optional[int] = None,
    ) -> RetrievalResult:
        """Retrieve memories using hybrid mode.
        
        Combines injected memories (high-priority, token-budgeted) with
        additional memories available via tool search.
        
        Args:
            context: Retrieval context
            query: Search query for relevance ranking
            inject_max_items: Max items for injection
            inject_max_tokens: Max tokens for injection
            tool_limit: Max additional items for tool search
        
        Returns:
            RetrievalResult with both injected and tool-available memories
        """
        # Get injected memories
        injected_result = self.retrieve_for_injection(
            context=context,
            query=query,
            max_items=inject_max_items,
            max_tokens=inject_max_tokens,
        )
        
        injected_ids = {m.name for m in injected_result.memories}
        
        # Get additional memories for tool (excluding injected)
        tool_limit = tool_limit or self.config.tool_default_limit
        
        builder = MemoryFilterBuilder()
        builder.add_scope_filter(
            agent_name=context.agent_name,
            conversation_id=context.conversation_id,
            user_id=context.user_id,
        )
        builder.add_status_filter(status="active")
        
        # Exclude already injected memories
        if injected_ids:
            builder.add_filter("name", "not in", list(injected_ids))
        
        tool_memories = self.searcher.search(
            query=query or "",
            filters=builder.build(),
            limit=tool_limit,
            order_by=["-importance_score", "-modified"],
        )
        
        # Update retrieval stats
        self._update_retrieval_stats([m.name for m in tool_memories])
        
        # Combine results
        all_memories = injected_result.memories + tool_memories
        
        return RetrievalResult(
            mode=RetrievalMode.HYBRID,
            memories=all_memories,
            total_found=len(all_memories),
            injected_count=len(injected_result.memories),
            tool_count=len(tool_memories),
            estimated_tokens=injected_result.estimated_tokens,
            query=query,
            metadata={
                "injected_ids": list(injected_ids),
            }
        )
    
    def retrieve_by_mode(
        self,
        mode: RetrievalMode,
        context: RetrievalContext,
        query: Optional[str] = None,
        **kwargs
    ) -> RetrievalResult:
        """Retrieve memories using specified mode.
        
        Unified entry point that delegates to the appropriate retrieval method
        based on the specified mode.
        
        Args:
            mode: RetrievalMode to use (inject, tool_only, hybrid)
            context: Retrieval context
            query: Optional search query
            **kwargs: Additional mode-specific arguments
        
        Returns:
            RetrievalResult
        """
        if mode == RetrievalMode.INJECT:
            return self.retrieve_for_injection(
                context=context,
                query=query,
                max_items=kwargs.get("max_items"),
                max_tokens=kwargs.get("max_tokens"),
            )
        elif mode == RetrievalMode.TOOL_ONLY:
            return self.retrieve_for_tool(
                context=context,
                query=query,
                filters=kwargs.get("filters"),
                limit=kwargs.get("limit"),
                offset=kwargs.get("offset", 0),
            )
        elif mode == RetrievalMode.HYBRID:
            return self.retrieve_hybrid(
                context=context,
                query=query,
                inject_max_items=kwargs.get("inject_max_items"),
                inject_max_tokens=kwargs.get("inject_max_tokens"),
                tool_limit=kwargs.get("tool_limit"),
            )
        else:
            raise ValueError(f"Unknown retrieval mode: {mode}")
    
    def get_memory_by_id(self, memory_id: str) -> Optional[MemorySearchResult]:
        """Get a specific memory by ID.
        
        Args:
            memory_id: Name/ID of the memory record
        
        Returns:
            MemorySearchResult if found, None otherwise
        """
        try:
            doc = frappe.get_doc("Memory Record", memory_id)
            
            # Update retrieval stats
            self._update_retrieval_stats([memory_id])
            
            return MemorySearchResult(
                name=doc.name,
                title=doc.title,
                memory_type=doc.memory_type,
                data_json=frappe.parse_json(doc.data_json or "{}"),
                summary_text=doc.summary_text or "",
                score=1.0,
                confidence=doc.confidence or 1.0,
                importance_score=doc.importance_score or 0.5,
                created_at=doc.creation,
                last_retrieved_at=doc.last_retrieved_at,
                retrieval_count=(doc.retrieval_count or 0) + 1,
                scope_type=doc.scope_type,
                scope_key=doc.scope_key,
                agent=doc.agent,
                user=None,  # User field not in current schema
                conversation=doc.conversation,
                profile_name=doc.profile_name,
                tags=[t.tag for t in doc.tags] if hasattr(doc, "tags") else [],
                metadata=frappe.parse_json(doc.metadata_json or "{}"),
            )
        except frappe.DoesNotExistError:
            return None
    
    def _apply_token_budget(
        self,
        memories: List[MemorySearchResult],
        max_tokens: int,
    ) -> tuple[List[MemorySearchResult], int]:
        """Filter memories to fit within token budget.
        
        Args:
            memories: List of memories to filter
            max_tokens: Maximum allowed tokens
        
        Returns:
            Tuple of (filtered_memories, total_tokens)
        """
        filtered = []
        total_tokens = 0
        
        for memory in memories:
            # Estimate tokens (rough approximation: 4 chars per token)
            content = memory.summary_text or str(memory.data_json)
            tokens = len(content) // 4
            
            if total_tokens + tokens > max_tokens:
                break
            
            filtered.append(memory)
            total_tokens += tokens
        
        return filtered, total_tokens
    
    def _update_retrieval_stats(self, memory_ids: List[str]):
        """Update retrieval statistics for accessed memories.
        
        Args:
            memory_ids: List of memory record IDs to update
        """
        if not memory_ids:
            return
        
        now = datetime.now()
        
        for memory_id in memory_ids:
            try:
                frappe.db.sql("""
                    UPDATE `tabMemory Record`
                    SET last_retrieved_at = %s,
                        retrieval_count = COALESCE(retrieval_count, 0) + 1
                    WHERE name = %s
                """, (now, memory_id))
            except Exception as e:
                frappe.logger().debug(f"Failed to update retrieval stats for {memory_id}: {e}")
        
        frappe.db.commit()


# Whitelist functions for API access

@frappe.whitelist()
def retrieve_memories(
    agent_name: str,
    mode: str = "hybrid",
    query: Optional[str] = None,
    conversation_id: Optional[str] = None,
    user_id: Optional[str] = None,
    max_items: Optional[int] = None,
) -> Dict[str, Any]:
    """API endpoint for memory retrieval.
    
    Args:
        agent_name: Name of the agent
        mode: Retrieval mode (inject, tool_only, hybrid)
        query: Optional search query
        conversation_id: Optional conversation ID
        user_id: Optional user ID
        max_items: Maximum items to retrieve
    
    Returns:
        Dict with retrieval results
    """
    try:
        service = MemoryRetrievalService()
        context = RetrievalContext(
            agent_name=agent_name,
            conversation_id=conversation_id,
            user_id=user_id,
        )
        
        mode_enum = RetrievalMode(mode)
        result = service.retrieve_by_mode(
            mode=mode_enum,
            context=context,
            query=query,
            inject_max_items=max_items,
        )
        
        return {
            "success": True,
            **result.to_dict()
        }
    except Exception as e:
        frappe.log_error(f"Memory retrieval failed: {str(e)}", "Memory Retrieval Service")
        return {
            "success": False,
            "error": str(e),
        }


@frappe.whitelist()
def get_memory_by_id(memory_id: str) -> Dict[str, Any]:
    """API endpoint to get a specific memory by ID.
    
    Args:
        memory_id: Memory record name/ID
    
    Returns:
        Dict with memory details or error
    """
    try:
        service = MemoryRetrievalService()
        result = service.get_memory_by_id(memory_id)
        
        if result:
            return {
                "success": True,
                "memory": {
                    "name": result.name,
                    "title": result.title,
                    "memory_type": result.memory_type,
                    "summary": result.summary_text,
                    "data": result.data_json,
                    "confidence": result.confidence,
                    "importance": result.importance_score,
                    "scope_type": result.scope_type,
                    "scope_key": result.scope_key,
                }
            }
        else:
            return {
                "success": False,
                "error": f"Memory record '{memory_id}' not found"
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
