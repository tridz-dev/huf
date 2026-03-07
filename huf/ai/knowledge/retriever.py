"""Knowledge retrieval system."""

from typing import List, Dict, Any, Optional
import frappe
from frappe import _

from .backends import get_backend, ChunkResult


def get_search_diagnostics(source_names: List[str]) -> List[Dict[str, Any]]:
	"""
	Return diagnostic info for why sources were skipped during search.
	Used when search returns empty to provide actionable feedback.
	"""
	diagnostics = []
	for source_name in source_names:
		try:
			source = frappe.get_doc("Knowledge Source", source_name)
			reason = None
			if source.status != "Ready":
				reason = _("status is {0} (index not ready). Run 'Rebuild Index' or ensure Knowledge Inputs are processed.").format(
					source.status
				)
			elif source.disabled:
				reason = _("knowledge source is disabled")
			elif not frappe.has_permission("Knowledge Source", "read", source_name):
				reason = _("permission denied (requires read access to Knowledge Source)")
			else:
				reason = _("index may be empty (no chunks)")
			diagnostics.append({
				"source": source_name,
				"status": source.status,
				"reason": reason,
			})
		except (frappe.DoesNotExistError, frappe.ValidationError):
			diagnostics.append({"source": source_name, "status": None, "reason": _("source does not exist")})
		except Exception as e:
			diagnostics.append({"source": source_name, "status": None, "reason": str(e)})
	return diagnostics


@frappe.whitelist()
def knowledge_search(
	query: str,
	knowledge_source: Optional[str] = None,
	knowledge_sources: Optional[List[str]] = None,
	top_k: int = 5,
	filters: Optional[Dict[str, Any]] = None,
	ignore_permissions: bool = False,
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
		ignore_permissions: When True (e.g. from agent context), skip permission check

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

			# Ensure user has access to this Knowledge Source (unless agent context)
			if not ignore_permissions and not frappe.has_permission("Knowledge Source", "read", source_name):
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
				
		except (frappe.DoesNotExistError, frappe.ValidationError):
			# Source doesn't exist or is invalid, just skip
			continue
			
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
