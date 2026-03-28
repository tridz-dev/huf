"""Memory retrieval system - Retrieval modes for HUF Memory System.

This module implements the three retrieval modes specified in the HUF Memory PRD:
- inject: Memory auto-injected into system prompt
- tool_only: Agent must call tool to query memory  
- hybrid: Top-K memory injected + full search via tool

Integration with existing HUF knowledge retrieval patterns:
- Mirrors knowledge/retriever.py patterns
- Uses similar search diagnostics
- Compatible with context_builder.py patterns
"""

from typing import List, Dict, Any, Optional, Literal
from enum import Enum
import frappe
from frappe import _


class RetrievalMode(str, Enum):
	"""Supported memory retrieval modes."""
	INJECT = "inject"
	TOOL_ONLY = "tool_only"
	HYBRID = "hybrid"


class MemoryRetrievalConfig:
	"""Configuration for memory retrieval.
	
	Based on PRD Section 15: Retrieval Model
	"""
	
	def __init__(
		self,
		mode: RetrievalMode = RetrievalMode.HYBRID,
		inject_max_items: int = 5,
		inject_max_tokens: int = 2000,
		tool_enabled: bool = True,
		tool_default_limit: int = 10,
		tool_max_limit: int = 100,
		default_status: List[str] = None,
		default_scope: str = "inherit_from_conversation",
		order_by: List[str] = None,
		filters: Optional[Dict[str, Any]] = None,
	):
		self.mode = mode
		self.inject_max_items = inject_max_items
		self.inject_max_tokens = inject_max_tokens
		self.tool_enabled = tool_enabled
		self.tool_default_limit = tool_default_limit
		self.tool_max_limit = tool_max_limit
		self.default_status = default_status or ["active"]
		self.default_scope = default_scope
		self.order_by = order_by or ["-importance_score", "-created_at"]
		self.filters = filters or {}


class MemoryRetrievalMode:
	"""Base class for memory retrieval mode implementations.
	
	Following the pattern of knowledge/retriever.py for consistency.
	"""
	
	def __init__(self, config: MemoryRetrievalConfig):
		self.config = config
	
	def retrieve(
		self,
		query: Optional[str] = None,
		agent_name: Optional[str] = None,
		conversation_id: Optional[str] = None,
		user_id: Optional[str] = None,
		filters: Optional[Dict[str, Any]] = None,
	) -> Dict[str, Any]:
		"""Retrieve memory based on mode-specific logic.
		
		Args:
			query: Optional search query for relevance ranking
			agent_name: Agent context for scoping
			conversation_id: Conversation context for scoping
			user_id: User context for scoping
			filters: Additional filters to apply
			
		Returns:
			Dict with retrieval results and metadata
		"""
		raise NotImplementedError


class InjectRetrievalMode(MemoryRetrievalMode):
	"""Inject mode: Memory auto-injected into system prompt.
	
	From CAPTURE_RETRIEVAL.md Section 3.2:
	- Query memory store at conversation start and/or before each run
	- Format results as structured context block
	- Prepend to system prompt (before knowledge, after core instructions)
	"""
	
	def retrieve(
		self,
		query: Optional[str] = None,
		agent_name: Optional[str] = None,
		conversation_id: Optional[str] = None,
		user_id: Optional[str] = None,
		filters: Optional[Dict[str, Any]] = None,
	) -> Dict[str, Any]:
		"""Retrieve memories for prompt injection.
		
		Query Construction (from spec):
		- scope_type: policy.scope_type
		- scope_key: resolve_scope_key(policy, conversation)
		- memory_type: policy.memory_types or None
		- status: active
		- effective_date: <= now
		"""
		from .search import MemorySearcher
		
		searcher = MemorySearcher()
		
		# Build injection-specific filters
		inject_filters = {
			"status": ["in", self.config.default_status],
		}
		
		# Add scope resolution
		if conversation_id:
			inject_filters["conversation"] = conversation_id
		if user_id:
			inject_filters["user"] = user_id
		if agent_name:
			inject_filters["agent"] = agent_name
		
		# Merge with provided filters
		if filters:
			inject_filters.update(filters)
		
		# Search with ranking
		results = searcher.search(
			query=query or "",  # Empty query returns most relevant by score
			filters=inject_filters,
			limit=self.config.inject_max_items,
			order_by=self.config.order_by,
		)
		
		# Apply token budget filtering
		filtered_results = self._apply_token_budget(results)
		
		return {
			"mode": RetrievalMode.INJECT,
			"results": filtered_results,
			"total_found": len(results),
			"injected_count": len(filtered_results),
			"estimated_tokens": self._estimate_tokens(filtered_results),
		}
	
	def _apply_token_budget(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
		"""Filter results to fit within token budget."""
		filtered = []
		total_tokens = 0
		
		for result in results:
			# Rough token estimation (4 chars per token)
			content = result.get("summary_text", "") or str(result.get("data_json", ""))
			tokens = len(content) // 4
			
			if total_tokens + tokens > self.config.inject_max_tokens:
				break
			
			filtered.append(result)
			total_tokens += tokens
		
		return filtered
	
	def _estimate_tokens(self, results: List[Dict[str, Any]]) -> int:
		"""Estimate total tokens for results."""
		total = 0
		for result in results:
			content = result.get("summary_text", "") or str(result.get("data_json", ""))
			total += len(content) // 4
		return total


class ToolOnlyRetrievalMode(MemoryRetrievalMode):
	"""Tool-only mode: Agent must call tool to query memory.
	
	From CAPTURE_RETRIEVAL.md Section 3.3:
	- No automatic injection
	- Memory search tool available to agent
	- Agent explicitly queries when needed
	"""
	
	def retrieve(
		self,
		query: Optional[str] = None,
		agent_name: Optional[str] = None,
		conversation_id: Optional[str] = None,
		user_id: Optional[str] = None,
		filters: Optional[Dict[str, Any]] = None,
		limit: Optional[int] = None,
	) -> Dict[str, Any]:
		"""Retrieve memories via tool search.
		
		Note: This is typically called when the agent invokes the memory_search tool.
		"""
		from .search import MemorySearcher
		
		searcher = MemorySearcher()
		
		# Build tool-specific filters
		tool_filters = {
			"status": ["in", self.config.default_status],
		}
		
		if conversation_id:
			tool_filters["conversation"] = conversation_id
		if user_id:
			tool_filters["user"] = user_id
		if agent_name:
			tool_filters["agent"] = agent_name
		
		if filters:
			tool_filters.update(filters)
		
		# Use provided limit or default
		search_limit = limit or self.config.tool_default_limit
		search_limit = min(search_limit, self.config.tool_max_limit)
		
		results = searcher.search(
			query=query or "",
			filters=tool_filters,
			limit=search_limit,
			order_by=self.config.order_by,
		)
		
		return {
			"mode": RetrievalMode.TOOL_ONLY,
			"results": results,
			"total_found": len(results),
			"query": query,
		}


class HybridRetrievalMode(MemoryRetrievalMode):
	"""Hybrid mode: Top-K memory injected + full search via tool.
	
	From CAPTURE_RETRIEVAL.md Section 3.4:
	- Top-K high-priority memory auto-injected
	- Full memory search tool also available
	- Injected memory marked to avoid double-retrieval
	"""
	
	def __init__(self, config: MemoryRetrievalConfig):
		super().__init__(config)
		self.inject_mode = InjectRetrievalMode(config)
		self.tool_mode = ToolOnlyRetrievalMode(config)
	
	def retrieve(
		self,
		query: Optional[str] = None,
		agent_name: Optional[str] = None,
		conversation_id: Optional[str] = None,
		user_id: Optional[str] = None,
		filters: Optional[Dict[str, Any]] = None,
		exclude_injected: bool = True,
	) -> Dict[str, Any]:
		"""Retrieve memories using hybrid approach.
		
		Returns both injected memories and tool-available memories,
		with optional deduplication.
		"""
		# Get injected memories
		injected = self.inject_mode.retrieve(
			query=query,
			agent_name=agent_name,
			conversation_id=conversation_id,
			user_id=user_id,
			filters=filters,
		)
		
		injected_ids = {r.get("name") for r in injected["results"]}
		
		# Get tool-available memories (potentially excluding injected)
		tool_filters = dict(filters) if filters else {}
		if exclude_injected and injected_ids:
			tool_filters["name"] = ["not in", list(injected_ids)]
		
		tool_results = self.tool_mode.retrieve(
			query=query,
			agent_name=agent_name,
			conversation_id=conversation_id,
			user_id=user_id,
			filters=tool_filters,
		)
		
		return {
			"mode": RetrievalMode.HYBRID,
			"injected": injected["results"],
			"injected_count": len(injected["results"]),
			"tool_available": tool_results["results"],
			"tool_count": len(tool_results["results"]),
			"total_unique": len(injected["results"]) + len(tool_results["results"]),
			"injected_ids": list(injected_ids),
		}


def get_retrieval_mode(
	mode: Literal["inject", "tool_only", "hybrid"],
	config: Optional[MemoryRetrievalConfig] = None,
) -> MemoryRetrievalMode:
	"""Factory function to get the appropriate retrieval mode implementation.
	
	Args:
		mode: The retrieval mode identifier
		config: Optional configuration (uses defaults if not provided)
		
	Returns:
		MemoryRetrievalMode instance for the specified mode
		
	Example:
		>>> mode = get_retrieval_mode("hybrid")
		>>> results = mode.retrieve(agent_name="MyAgent", conversation_id="conv_123")
	"""
	config = config or MemoryRetrievalConfig()
	
	mode_map = {
		RetrievalMode.INJECT: InjectRetrievalMode,
		RetrievalMode.TOOL_ONLY: ToolOnlyRetrievalMode,
		RetrievalMode.HYBRID: HybridRetrievalMode,
	}
	
	mode_enum = RetrievalMode(mode)
	mode_class = mode_map[mode_enum]
	
	return mode_class(config)


def resolve_retrieval_mode_for_agent(agent_name: str) -> RetrievalMode:
	"""Resolve the retrieval mode for a given agent.
	
	Checks agent configuration and returns the appropriate mode.
	Falls back to hybrid if not configured.
	"""
	try:
		agent = frappe.get_doc("Agent", agent_name)
		mode = agent.get("memory_retrieval_mode", "hybrid")
		return RetrievalMode(mode)
	except Exception:
		return RetrievalMode.HYBRID


# Whitelist functions for API access

@frappe.whitelist()
def get_retrieval_modes() -> List[Dict[str, str]]:
	"""Get available retrieval modes with descriptions."""
	return [
		{
			"id": RetrievalMode.INJECT,
			"name": "Inject",
			"description": "Memory auto-injected into system prompt. Best for high-priority profile data.",
		},
		{
			"id": RetrievalMode.TOOL_ONLY,
			"name": "Tool Only",
			"description": "Agent must call tool to query memory. Best for large corpora or secondary knowledge.",
		},
		{
			"id": RetrievalMode.HYBRID,
			"name": "Hybrid",
			"description": "Top-K memory injected + full search via tool. Best general-purpose configuration.",
		},
	]


@frappe.whitelist()
def test_retrieval(
	mode: str,
	agent_name: str,
	query: Optional[str] = None,
	conversation_id: Optional[str] = None,
) -> Dict[str, Any]:
	"""Test memory retrieval with specified mode.
	
	Similar to knowledge_source.py::test_search() for diagnostic purposes.
	"""
	try:
		retrieval_config = MemoryRetrievalConfig(mode=RetrievalMode(mode))
		retrieval = get_retrieval_mode(mode, retrieval_config)
		
		results = retrieval.retrieve(
			query=query,
			agent_name=agent_name,
			conversation_id=conversation_id,
		)
		
		return {
			"success": True,
			"mode": mode,
			"results": results,
		}
	except Exception as e:
		frappe.log_error(
			f"Memory retrieval test error: {str(e)}",
			"Memory Retrieval Test Error"
		)
		return {
			"success": False,
			"error": str(e),
		}
