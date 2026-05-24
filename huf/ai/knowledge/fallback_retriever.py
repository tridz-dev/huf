"""Fallback retriever for knowledge search with automatic backend failover."""

from typing import List, Dict, Any, Optional
import frappe

from .retriever import ChunkResult
from .health_monitor import get_health_monitor, check_backend_health


class FallbackRetriever:
	"""
	Knowledge retriever with automatic fallback to secondary backends.
	
	If the primary backend fails or returns no results, automatically
	switches to the configured fallback backend.
	"""
	
	def __init__(self, knowledge_source: str):
		"""
		Initialize retriever for a knowledge source.
		
		Args:
			knowledge_source: Name of the Knowledge Source document
		"""
		self.knowledge_source = knowledge_source
		self._monitor = get_health_monitor()
		self._primary_backend = None
		self._fallback_backend = None
		self._backend_config = {}
		
		self._load_backend_config()
	
	def _load_backend_config(self):
		"""Load backend configuration from the knowledge source."""
		try:
			source = frappe.get_doc("Knowledge Source", self.knowledge_source)
			self._primary_backend = source.get("knowledge_type", "sqlite_fts")
			self._fallback_backend = source.get("fallback_knowledge_type")
			
			if hasattr(source, "backend_config") and source.backend_config:
				try:
					self._backend_config = frappe.parse_json(source.backend_config)
				except Exception:
					self._backend_config = {}
					
		except frappe.DoesNotExistError:
			frappe.log_error(
				f"Knowledge source not found: {self.knowledge_source}",
				"Fallback Retriever"
			)
			self._primary_backend = None
		except Exception as e:
			frappe.log_error(
				f"Error loading backend config for {self.knowledge_source}: {e}",
				"Fallback Retriever"
			)
	
	def search(
		self,
		query: str,
		top_k: int = 5,
		filters: Optional[Dict[str, Any]] = None,
		use_fallback: bool = True
	) -> List[Dict[str, Any]]:
		"""
		Search with automatic fallback logic.
		
		First attempts to search using the primary backend. If that fails
		or returns no results, and fallback is enabled, tries the fallback backend.
		
		Args:
			query: Search query string
			top_k: Maximum number of results to return
			filters: Optional filters to apply
			use_fallback: Whether to attempt fallback if primary fails
		
		Returns:
			List of search results with source information
		"""
		if not query or not query.strip():
			return []
		
		if not self._primary_backend:
			return []
		
		results = []
		fallback_used = False
		
		# Check primary backend health
		health = self._monitor.check_health(self.knowledge_source)
		primary_healthy = (
			health.primary_backend and health.primary_backend.is_healthy
		)
		
		# Try primary backend if healthy
		if primary_healthy:
			try:
				results = self._search_primary(query, top_k, filters)
			except Exception as e:
				frappe.log_error(
					f"Primary backend search failed for {self.knowledge_source}: {e}",
					"Fallback Retriever"
				)
				results = []
		
		# Determine if we should use fallback
		should_fallback = (
			use_fallback and
			self._fallback_backend and
			(len(results) == 0 or not primary_healthy)
		)
		
		# Check if fallback is healthy
		fallback_healthy = (
			health.fallback_backend and health.fallback_backend.is_healthy
		)
		
		if should_fallback and fallback_healthy:
			try:
				fallback_results = self._search_fallback(query, top_k, filters)
				if fallback_results:
					results = fallback_results
					fallback_used = True
			except Exception as e:
				frappe.log_error(
					f"Fallback backend search failed for {self.knowledge_source}: {e}",
					"Fallback Retriever"
				)
		
		# Add metadata to results
		for result in results:
			result["_search_metadata"] = {
				"knowledge_source": self.knowledge_source,
				"fallback_used": fallback_used,
				"primary_backend": self._primary_backend,
				"fallback_backend": self._fallback_backend if fallback_used else None,
			}
		
		return results
	
	def _search_primary(
		self,
		query: str,
		top_k: int,
		filters: Optional[Dict[str, Any]]
	) -> List[Dict[str, Any]]:
		"""
		Search using the primary backend.
		
		Args:
			query: Search query
			top_k: Maximum results
			filters: Optional filters
		
		Returns:
			List of results from primary backend
		"""
		from .backends import get_backend
		
		backend_class = get_backend(self._primary_backend)
		backend = backend_class()
		backend.initialize(self.knowledge_source, self._backend_config)
		
		chunk_results = backend.search(query, top_k=top_k, filters=filters)
		
		return self._format_results(chunk_results)
	
	def _search_fallback(
		self,
		query: str,
		top_k: int,
		filters: Optional[Dict[str, Any]]
	) -> List[Dict[str, Any]]:
		"""
		Search using the fallback backend.
		
		Args:
			query: Search query
			top_k: Maximum results
			filters: Optional filters
		
		Returns:
			List of results from fallback backend
		"""
		from .backends import get_backend
		
		backend_class = get_backend(self._fallback_backend)
		backend = backend_class()
		backend.initialize(self.knowledge_source, self._backend_config)
		
		chunk_results = backend.search(query, top_k=top_k, filters=filters)
		
		return self._format_results(chunk_results)
	
	def _format_results(self, chunk_results: List[ChunkResult]) -> List[Dict[str, Any]]:
		"""Format ChunkResult objects to standard dict format."""
		results = []
		for result in chunk_results:
			results.append({
				"text": result.text,
				"title": result.title,
				"score": result.score,
				"chunk_id": result.chunk_id,
				"source": result.source,
				"metadata": result.metadata or {},
			})
		return results
	
	def get_backend_info(self) -> Dict[str, Any]:
		"""
		Get information about configured backends and their health.
		
		Returns:
			Dict with primary_backend, fallback_backend, and health status
		"""
		health = self._monitor.check_health(self.knowledge_source)
		
		return {
			"knowledge_source": self.knowledge_source,
			"primary_backend": self._primary_backend,
			"fallback_backend": self._fallback_backend,
			"primary_healthy": (
				health.primary_backend.is_healthy 
				if health.primary_backend else False
			),
			"fallback_healthy": (
				health.fallback_backend.is_healthy
				if health.fallback_backend else False
			),
		}
