"""Knowledge retrieval system."""

from typing import List, Dict, Any, Optional
import frappe
from frappe import _

from .backends import get_backend, ChunkResult


@frappe.whitelist()
def knowledge_search(
	query: str,
	knowledge_source: Optional[str] = None,
	knowledge_sources: Optional[List[str]] = None,
	top_k: int = 5,
	filters: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
	"""
	Search for relevant knowledge chunks.
	
	This is the main retrieval contract used by agents.
	
	Args:
		query: The search query
		knowledge_source: Single knowledge source to search
		knowledge_sources: Multiple knowledge sources to search
		top_k: Maximum results per source
		filters: Additional filters (reserved for future use)
	
	Returns:
		List of chunk results with text, title, score, and source
	"""
	if not query or not query.strip():
		return []
	
	# Determine sources to search
	sources = []
	if knowledge_source:
		sources = [knowledge_source]
	elif knowledge_sources:
		sources = knowledge_sources
	else:
		frappe.throw(_("Either knowledge_source or knowledge_sources is required"))
	
	# Collect results from all sources
	all_results = []
	
	for source_name in sources:
		try:
			source = frappe.get_doc("Knowledge Source", source_name)
			
			# Check if source is ready
			if source.status != "Ready":
				continue
			
			if source.disabled:
				continue
			
			# Initialize backend
			backend_class = get_backend(source.knowledge_type)
			backend = backend_class()
			backend.initialize(source_name, {})
			
			# Search
			results = backend.search(query, top_k=top_k, filters=filters)
			
			# Add source information
			for result in results:
				all_results.append({
					"text": result.text,
					"title": result.title,
					"score": result.score,
					"chunk_id": result.chunk_id,
					"source": source_name,
					"metadata": result.metadata,
				})
				
		except Exception as e:
			frappe.log_error(
				f"Knowledge search error for {source_name}",
				frappe.get_traceback()
			)
			continue
	
	# Sort by score across all sources
	all_results.sort(key=lambda x: x["score"], reverse=True)
	
	# Limit to top_k total
	return all_results[:top_k]


def get_mandatory_knowledge(agent_name: str) -> List[Dict[str, Any]]:
	"""
	Get mandatory knowledge sources for an agent.
	
	Returns list of knowledge source configurations with mode='Mandatory'.
	"""
	agent = frappe.get_doc("Agent", agent_name)
	
	mandatory_sources = []
	for ak in agent.get("agent_knowledge", []):
		if ak.mode == "Mandatory":
			mandatory_sources.append({
				"knowledge_source": ak.knowledge_source,
				"priority": ak.priority or 0,
				"max_chunks": ak.max_chunks or 5,
				"token_budget": ak.token_budget or 2000,
			})
	
	# Sort by priority (higher first)
	mandatory_sources.sort(key=lambda x: x["priority"], reverse=True)
	
	return mandatory_sources


def get_optional_knowledge(agent_name: str) -> List[Dict[str, Any]]:
	"""
	Get optional knowledge sources for an agent.
	
	Returns list of knowledge source configurations with mode='Optional'.
	"""
	agent = frappe.get_doc("Agent", agent_name)
	
	optional_sources = []
	for ak in agent.get("agent_knowledge", []):
		if ak.mode == "Optional":
			optional_sources.append({
				"knowledge_source": ak.knowledge_source,
				"priority": ak.priority or 0,
				"max_chunks": ak.max_chunks or 5,
				"token_budget": ak.token_budget or 2000,
			})
	
	return optional_sources
