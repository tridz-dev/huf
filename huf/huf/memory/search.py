"""Memory search functionality for HUF Memory System.

Implements memory search with filters and ranking as specified in:
- PRD Section 15: Retrieval Model
- CAPTURE_RETRIEVAL.md Section 3.5-3.6

Integration with existing HUF patterns:
- Mirrors knowledge/retriever.py::knowledge_search()
- Uses similar filter/ordering patterns
- Compatible with FTS and vector backends
"""

from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass
from datetime import datetime, timedelta
import math
import frappe
from frappe import _


@dataclass
class MemorySearchResult:
	"""Structured memory search result.
	
	Similar to ChunkResult in knowledge/backends/
	"""
	name: str
	title: str
	memory_type: str
	data_json: Dict[str, Any]
	summary_text: str
	score: float
	confidence: float
	importance_score: float
	created_at: datetime
	last_retrieved_at: Optional[datetime]
	retrieval_count: int
	scope_type: str
	scope_key: str
	agent: Optional[str]
	user: Optional[str]
	conversation: Optional[str]
	profile_name: Optional[str]
	tags: List[str]
	metadata: Dict[str, Any]


class MemoryFilterBuilder:
	"""Build database filters for memory search.
	
	Implements filter types from CAPTURE_RETRIEVAL.md Section 3.5:
	- scope_type, scope_key
	- agent, user, memory_type
	- profile_name, tags
	- status, min_confidence, min_importance
	- created_after, effective_date
	- source_type
	"""
	
	VALID_OPERATORS = {
		"=": "=",
		"!=": "!=",
		"<": "<",
		">": ">",
		"<=": "<=",
		">=": ">=",
		"in": "in",
		"not in": "not in",
		"like": "like",
		"not like": "not like",
	}
	
	def __init__(self):
		self.filters = {}
		self.conditions = []
	
	def add_filter(self, field: str, operator: str, value: Any):
		"""Add a filter condition."""
		if operator not in self.VALID_OPERATORS:
			raise ValueError(f"Invalid operator: {operator}")
		
		self.filters[field] = [operator, value]
		return self
	
	def add_scope_filter(
		self,
		scope_type: Optional[str] = None,
		scope_key: Optional[str] = None,
		conversation_id: Optional[str] = None,
		user_id: Optional[str] = None,
		agent_name: Optional[str] = None,
	) -> "MemoryFilterBuilder":
		"""Add scope-related filters.
		
		From PRD Section 13: Scope and Sharing Model
		Supported scopes: conversation, user, agent, namespace, global
		"""
		if scope_type:
			self.filters["scope_type"] = scope_type
		if scope_key:
			self.filters["scope_key"] = scope_key
		if conversation_id:
			self.filters["conversation"] = conversation_id
		if user_id:
			self.filters["user"] = user_id
		if agent_name:
			self.filters["agent"] = agent_name
		
		return self
	
	def add_type_filter(
		self,
		memory_type: Optional[str] = None,
		memory_types: Optional[List[str]] = None,
		profile_name: Optional[str] = None,
	) -> "MemoryFilterBuilder":
		"""Add memory type filters.
		
		Memory types from PRD Section 9.1:
		- profile, session_state, preference, fact, plan, observation, insight, domain_object, custom
		"""
		if memory_type:
			self.filters["memory_type"] = memory_type
		elif memory_types:
			self.filters["memory_type"] = ["in", memory_types]
		
		if profile_name:
			self.filters["profile_name"] = profile_name
		
		return self
	
	def add_status_filter(
		self,
		status: Optional[Union[str, List[str]]] = None,
		min_confidence: Optional[float] = None,
		min_importance: Optional[float] = None,
	) -> "MemoryFilterBuilder":
		"""Add status and quality filters."""
		if status:
			if isinstance(status, list):
				self.filters["status"] = ["in", status]
			else:
				self.filters["status"] = status
		
		if min_confidence is not None:
			self.filters["confidence"] [">=", min_confidence]
		
		if min_importance is not None:
			self.filters["importance_score"] [">=", min_importance]
		
		return self
	
	def add_recency_filter(
		self,
		created_after: Optional[datetime] = None,
		created_within_days: Optional[int] = None,
	) -> "MemoryFilterBuilder":
		"""Add recency filters."""
		if created_after:
			self.filters["creation"] [">=", created_after]
		elif created_within_days:
			cutoff = datetime.now() - timedelta(days=created_within_days)
			self.filters["creation"] [">=", cutoff]
		
		return self
	
	def add_tag_filter(self, tags: Optional[List[str]] = None, match_all: bool = False) -> "MemoryFilterBuilder":
		"""Add tag filters.
		
		Note: This requires parsing the tags field which may be JSON or comma-separated.
		"""
		if tags:
			# Tags stored as JSON array - handled in post-filtering
			self._tag_filter = {"tags": tags, "match_all": match_all}
		
		return self
	
	def build(self) -> Dict[str, Any]:
		"""Build and return the filter dictionary."""
		return self.filters.copy()


class MemoryRanker:
	"""Ranking algorithm for memory search results.
	
	Implements Phase 1 ranking from CAPTURE_RETRIEVAL.md Section 3.6:
	
	Base Score:
	score = importance_score × 0.4 + 
	        recency_weight × 0.3 + 
	        scope_relevance × 0.2 + 
	        (1 / (1 + retrieval_count)) × 0.1
	
	Components:
	- importance_score: 0.0-1.0, explicit or derived
	- recency_weight: exponential decay from creation date
	- scope_relevance: exact match = 1.0, parent scope = 0.8, global = 0.5
	- retrieval_count_decay: penalize over-fetched items
	"""
	
	def __init__(
		self,
		importance_weight: float = 0.4,
		recency_weight: float = 0.3,
		scope_weight: float = 0.2,
		retrieval_decay_weight: float = 0.1,
		recency_half_life_days: float = 30.0,
	):
		self.importance_weight = importance_weight
		self.recency_weight = recency_weight
		self.scope_weight = scope_weight
		self.retrieval_decay_weight = retrieval_decay_weight
		self.recency_half_life_days = recency_half_life_days
	
	def calculate_recency_weight(self, created_at: datetime) -> float:
		"""Calculate recency weight using exponential decay.
		
		weight = exp(-ln(2) × days_old / half_life)
		"""
		if not created_at:
			return 0.5
		
		days_old = (datetime.now() - created_at).days
		decay = math.exp(-math.log(2) * days_old / self.recency_half_life_days)
		
		# Normalize to 0-1 range, with fresh items > 0.5
		return max(0.0, min(1.0, decay))
	
	def calculate_scope_relevance(
		self,
		memory_scope: str,
		target_scope: str,
	) -> float:
		"""Calculate scope relevance score.
		
		From spec:
		- exact match = 1.0
		- parent scope = 0.8
		- global = 0.5
		"""
		if memory_scope == target_scope:
			return 1.0
		if memory_scope == "global":
			return 0.5
		# Parent scope check could be expanded
		return 0.8
	
	def calculate_retrieval_decay(self, retrieval_count: int) -> float:
		"""Calculate retrieval count decay.
		
		Formula: 1 / (1 + retrieval_count)
		"""
		return 1.0 / (1.0 + retrieval_count)
	
	def rank(
		self,
		memories: List[Dict[str, Any]],
		target_scope: Optional[str] = None,
		query: Optional[str] = None,
	) -> List[Dict[str, Any]]:
		"""Rank memories by relevance score.
		
		Args:
			memories: List of memory records (dict format)
			target_scope: The scope we're searching from
			query: Optional query for semantic relevance
			
		Returns:
			List of memories with 'relevance_score' added
		"""
		scored_memories = []
		
		for memory in memories:
			# Get base scores
			importance = memory.get("importance_score", 0.5) or 0.5
			
			# Parse creation time
			created_at = memory.get("creation") or memory.get("created_at")
			if isinstance(created_at, str):
				try:
					created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
				except:
					created_at = None
			
			recency = self.calculate_recency_weight(created_at)
			
			# Scope relevance
			memory_scope = memory.get("scope_type", "conversation")
			scope_rel = self.calculate_scope_relevance(
				memory_scope,
				target_scope or "conversation"
			)
			
			# Retrieval decay
			retrieval_count = memory.get("retrieval_count", 0) or 0
			retrieval_decay = self.calculate_retrieval_decay(retrieval_count)
			
			# Calculate composite score
			composite_score = (
				importance * self.importance_weight +
				recency * self.recency_weight +
				scope_rel * self.scope_weight +
				retrieval_decay * self.retrieval_decay_weight
			)
			
			# Add backend relevance if available
			backend_score = memory.get("_backend_score", 0)
			if backend_score > 0:
				# Blend backend score (e.g., FTS BM25 or vector similarity)
				composite_score = 0.7 * composite_score + 0.3 * backend_score
			
			memory["relevance_score"] = round(composite_score, 4)
			memory["_ranking_debug"] = {
				"importance_component": round(importance * self.importance_weight, 4),
				"recency_component": round(recency * self.recency_weight, 4),
				"scope_component": round(scope_rel * self.scope_weight, 4),
				"retrieval_decay_component": round(retrieval_decay * self.retrieval_decay_weight, 4),
			}
			
			scored_memories.append(memory)
		
		# Sort by relevance score descending
		scored_memories.sort(key=lambda x: x["relevance_score"], reverse=True)
		
		return scored_memories


class MemorySearcher:
	"""Main memory search interface.
	
	Similar to knowledge/retriever.py::knowledge_search()
	Provides unified search across all memory records.
	"""
	
	def __init__(self):
		self.ranker = MemoryRanker()
	
	def search(
		self,
		query: Optional[str] = None,
		filters: Optional[Dict[str, Any]] = None,
		limit: int = 10,
		order_by: Optional[List[str]] = None,
		use_ranking: bool = True,
		ignore_permissions: bool = False,
	) -> List[Dict[str, Any]]:
		"""Search memory records.
		
		Args:
			query: Search query text (for FTS/vector search)
			filters: Filter conditions (from MemoryFilterBuilder or dict)
			limit: Maximum results to return
			order_by: Sort order (e.g., ["-importance_score", "-created_at"])
			use_ranking: Whether to apply relevance ranking
			ignore_permissions: Skip permission check (for agent context)
			
		Returns:
			List of memory records with relevance scores
		"""
		# Build base query
		doctype = "Memory Record"
		
		# Check permissions unless in agent context
		if not ignore_permissions and not frappe.has_permission(doctype, "read"):
			return []
		
		# Build filter conditions
		filter_conditions = filters or {}
		
		# Execute query
		try:
			results = frappe.get_all(
				doctype,
				filters=filter_conditions,
				fields=[
					"name",
					"title",
					"memory_type",
					"data_json",
					"summary_text",
					"confidence",
					"importance_score",
					"creation",
					"last_retrieved_at",
					"retrieval_count",
					"scope_type",
					"scope_key",
					"agent",
					"user",
					"conversation",
					"profile_name",
					"tags",
					"source_type",
					"status",
				],
				limit=limit * 3 if use_ranking else limit,  # Get more for ranking
				order_by=order_by or "modified desc",
			)
		except Exception as e:
			frappe.log_error(
				f"Memory search error: {str(e)}",
				"Memory Search Error"
			)
			return []
		
		if not results:
			return []
		
		# Apply ranking if enabled
		if use_ranking:
			results = self.ranker.rank(results, query=query)
			results = results[:limit]
		else:
			results = results[:limit]
		
		# Parse JSON fields
		for result in results:
			if result.get("data_json") and isinstance(result["data_json"], str):
				try:
					result["data_json"] = frappe.parse_json(result["data_json"])
				except:
					result["data_json"] = {}
			if result.get("tags") and isinstance(result["tags"], str):
				try:
					result["tags"] = frappe.parse_json(result["tags"])
				except:
					result["tags"] = []
		
		return results
	
	def search_by_similarity(
		self,
		query_embedding: List[float],
		filters: Optional[Dict[str, Any]] = None,
		limit: int = 10,
		min_similarity: float = 0.7,
	) -> List[Dict[str, Any]]:
		"""Search by vector similarity (for vector-capable backends).
		
		Placeholder for future vector search integration.
		"""
		# TODO: Implement when sqlite_vec or other vector backends are available
		# For now, fall back to regular search
		return self.search(filters=filters, limit=limit)
	
	def get_memory_by_id(self, memory_id: str, ignore_permissions: bool = False) -> Optional[Dict[str, Any]]:
		"""Get a single memory record by ID."""
		try:
			if not ignore_permissions and not frappe.has_permission("Memory Record", "read", memory_id):
				return None
			
			memory = frappe.get_doc("Memory Record", memory_id)
			
			# Update retrieval count
			try:
				memory.db_set("retrieval_count", (memory.retrieval_count or 0) + 1, update_modified=False)
				memory.db_set("last_retrieved_at", datetime.now(), update_modified=False)
			except:
				pass
			
			return memory.as_dict()
		except frappe.DoesNotExistError:
			return None


# Convenience functions for API access

@frappe.whitelist()
def memory_search(
	query: Optional[str] = None,
	filters: Optional[Dict[str, Any]] = None,
	limit: int = 10,
	agent_name: Optional[str] = None,
	conversation_id: Optional[str] = None,
	user_id: Optional[str] = None,
	memory_type: Optional[str] = None,
	status: Optional[str] = None,
	min_confidence: Optional[float] = None,
	min_importance: Optional[float] = None,
	created_within_days: Optional[int] = None,
	ignore_permissions: bool = False,
) -> List[Dict[str, Any]]:
	"""Public API for memory search.
	
	Similar interface to knowledge/retriever.py::knowledge_search()
	
	Args:
		query: Search query text
		filters: Additional filter dict
		limit: Max results (default: 10)
		agent_name: Filter by agent
		conversation_id: Filter by conversation
		user_id: Filter by user
		memory_type: Filter by memory type
		status: Filter by status
		min_confidence: Minimum confidence threshold
		min_importance: Minimum importance threshold
		created_within_days: Only memories created within N days
		ignore_permissions: Skip permission check (agent context)
		
	Returns:
		List of memory records with relevance scores
	"""
	# Build filters
	builder = MemoryFilterBuilder()
	
	if agent_name or conversation_id or user_id:
		builder.add_scope_filter(
			agent_name=agent_name,
			conversation_id=conversation_id,
			user_id=user_id,
		)
	
	if memory_type:
		builder.add_type_filter(memory_type=memory_type)
	
	builder.add_status_filter(
		status=status or "active",
		min_confidence=min_confidence,
		min_importance=min_importance,
	)
	
	if created_within_days:
		builder.add_recency_filter(created_within_days=created_within_days)
	
	# Merge with provided filters
	final_filters = builder.build()
	if filters:
		final_filters.update(filters)
	
	# Execute search
	searcher = MemorySearcher()
	return searcher.search(
		query=query,
		filters=final_filters,
		limit=limit,
		ignore_permissions=ignore_permissions,
	)


@frappe.whitelist()
def get_recent_memories(
	limit: int = 10,
	memory_type: Optional[str] = None,
	agent_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
	"""Get most recently created memories."""
	filters = {"status": "active"}
	if memory_type:
		filters["memory_type"] = memory_type
	if agent_name:
		filters["agent"] = agent_name
	
	searcher = MemorySearcher()
	return searcher.search(
		filters=filters,
		limit=limit,
		order_by=["-creation"],
		use_ranking=False,
	)


@frappe.whitelist()
def get_high_importance_memories(
	limit: int = 10,
	min_importance: float = 0.8,
) -> List[Dict[str, Any]]:
	"""Get high-importance memories."""
	filters = {
		"status": "active",
		"importance_score": [">=", min_importance],
	}
	
	searcher = MemorySearcher()
	return searcher.search(
		filters=filters,
		limit=limit,
		order_by=["-importance_score"],
		use_ranking=False,
	)
