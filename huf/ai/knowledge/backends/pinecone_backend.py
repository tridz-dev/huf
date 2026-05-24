# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""Pinecone backend using LlamaIndex adapter."""

import os
import re
from typing import Any, Dict, List, Optional, Tuple

import frappe

from ..backends import ChunkResult, KnowledgeBackend
from ..backends.factory import BackendFactory

# LlamaIndex imports - optional dependency
try:
	from llama_index.vector_stores.pinecone import PineconeVectorStore
	from llama_index.core import VectorStoreIndex, StorageContext, Document
	LLAMAINDEX_AVAILABLE = True
except ImportError:
	LLAMAINDEX_AVAILABLE = False


def _sanitize_index_name(name: str) -> str:
	"""Sanitize knowledge source name for Pinecone index.
	
	Pinecone index names must:
	- Be lowercase alphanumeric or hyphen
	- Start and end with alphanumeric
	- Be between 1-45 characters
	"""
	# Convert to lowercase and replace invalid characters with hyphens
	sanitized = re.sub(r'[^a-z0-9-]+', '-', name.lower())
	# Remove leading/trailing hyphens
	sanitized = sanitized.strip('-')
	# Limit to 45 characters
	sanitized = sanitized[:45]
	# Ensure not empty
	if not sanitized:
		sanitized = 'huf-knowledge'
	return sanitized


class PineconeBackend(KnowledgeBackend):
	"""Pinecone backend for Huf knowledge storage."""
	
	def __init__(self):
		self.knowledge_source = None
		self.config = {}
		self.vector_store = None
		self.storage_context = None
		self.index = None
		self._initialized = False
		self._namespace = None
		self._index_name = None
	
	def initialize(self, knowledge_source: str, config: Dict[str, Any]) -> None:
		"""Initialize Pinecone backend.
		
		Args:
			knowledge_source: Name of the knowledge source
			config: Backend configuration containing:
				- api_key: Pinecone API key (or from PINECONE_API_KEY env var)
				- index_name: Pinecone index name (optional, defaults to sanitized knowledge_source)
				- namespace: Namespace for multi-tenancy (optional)
				- vector_dimension: Embedding dimension (default: 1536)
		"""
		if not LLAMAINDEX_AVAILABLE:
			raise ImportError(
				"llama-index-vector-stores-pinecone not installed. "
				"Install with: pip install llama-index-vector-stores-pinecone"
			)
		
		self.knowledge_source = knowledge_source
		self.config = config
		
		# Get API key from config or environment
		api_key = config.get("api_key") or os.environ.get("PINECONE_API_KEY")
		if not api_key:
			raise ValueError(
				"Pinecone API key required. Provide in config or set PINECONE_API_KEY environment variable."
			)
		
		# Get index name (sanitized knowledge source or explicit config)
		self._index_name = config.get("index_name") or _sanitize_index_name(knowledge_source)
		
		# Get namespace for multi-tenancy
		self._namespace = config.get("namespace")
		
		# Create vector store
		self.vector_store = PineconeVectorStore(
			api_key=api_key,
			index_name=self._index_name,
			namespace=self._namespace,
		)
		
		self.storage_context = StorageContext.from_defaults(
			vector_store=self.vector_store
		)
		
		self._initialized = True
		
		frappe.logger().info(
			f"Pinecone backend initialized: index={self._index_name}, "
			f"namespace={self._namespace or 'default'}"
		)
	
	def add_chunks(self, chunks: List[Dict[str, Any]]) -> int:
		"""Add chunks to Pinecone.
		
		Args:
			chunks: List of chunk dictionaries with text, metadata, etc.
			
		Returns:
			Number of chunks added
		"""
		if not chunks:
			return 0
		
		if not self._initialized:
			raise RuntimeError("Backend not initialized. Call initialize() first.")
		
		# Convert to LlamaIndex Documents
		documents = []
		for chunk in chunks:
			doc = Document(
				text=chunk["text"],
				metadata={
					"input_id": chunk["input_id"],
					"input_type": chunk["input_type"],
					"chunk_id": chunk.get("chunk_id"),
					"source_title": chunk.get("source_title"),
					"knowledge_source": self.knowledge_source,
				}
			)
			documents.append(doc)
		
		# Create/update index
		self.index = VectorStoreIndex.from_documents(
			documents,
			storage_context=self.storage_context,
		)
		
		return len(chunks)
	
	def search(
		self,
		query: str,
		top_k: int = 5,
		filters: Optional[Dict] = None
	) -> List[ChunkResult]:
		"""Search Pinecone.
		
		Args:
			query: Search query string
			top_k: Number of results to return
			filters: Optional metadata filters
			
		Returns:
			List of ChunkResult objects
		"""
		if not self._initialized:
			raise RuntimeError("Backend not initialized. Call initialize() first.")
		
		if not self.index:
			# Try to load existing index
			self.index = VectorStoreIndex.from_vector_store(
				self.vector_store,
				storage_context=self.storage_context,
			)
		
		# Create retriever with optional filters
		retriever_kwargs = {"similarity_top_k": top_k}
		if filters:
			retriever_kwargs["filters"] = filters
		
		retriever = self.index.as_retriever(**retriever_kwargs)
		
		# Search
		nodes = retriever.retrieve(query)
		
		# Convert to ChunkResult
		results = []
		for node in nodes:
			result = ChunkResult(
				chunk_id=node.metadata.get("chunk_id", ""),
				text=node.text,
				title=node.metadata.get("source_title"),
				score=float(node.score) if hasattr(node, "score") else 0.0,
				source=node.metadata.get("knowledge_source"),
				metadata=node.metadata,
			)
			results.append(result)
		
		return results
	
	def delete_chunks(self, input_id: str) -> int:
		"""Delete chunks by input_id.
		
		Pinecone supports deletion by metadata filter.
		
		Args:
			input_id: ID of the input to delete
			
		Returns:
			Number of chunks deleted (approximate)
		"""
		if not self._initialized:
			raise RuntimeError("Backend not initialized. Call initialize() first.")
		
		try:
			# Pinecone supports deletion by filter
			# Note: This requires the Pinecone client directly
			if hasattr(self.vector_store, '_pinecone_index'):
				# Delete all vectors with matching input_id in metadata
				filter_dict = {"input_id": {"$eq": input_id}}
				self.vector_store._pinecone_index.delete(
					filter=filter_dict,
					namespace=self._namespace
				)
				return 1  # Pinecone doesn't return delete count
			else:
				frappe.logger().warning(
					"Pinecone delete_chunks: direct client access not available"
				)
				return 0
		except Exception as e:
			frappe.logger().error(f"Pinecone delete_chunks error: {e}")
			return 0
	
	def clear(self) -> None:
		"""Clear all vectors from the namespace."""
		if not self._initialized:
			raise RuntimeError("Backend not initialized. Call initialize() first.")
		
		try:
			if hasattr(self.vector_store, '_pinecone_index'):
				# Delete all vectors in the namespace
				self.vector_store._pinecone_index.delete(
					delete_all=True,
					namespace=self._namespace
				)
				frappe.logger().info(
					f"Pinecone cleared: index={self._index_name}, "
					f"namespace={self._namespace or 'default'}"
				)
		except Exception as e:
			frappe.logger().error(f"Pinecone clear error: {e}")
			raise
	
	def get_stats(self) -> Dict[str, Any]:
		"""Get backend statistics.
		
		Returns:
			Dictionary with backend statistics
		"""
		stats = {
			"backend_type": "pinecone",
			"knowledge_source": self.knowledge_source,
			"initialized": self._initialized,
			"index_name": self._index_name,
			"namespace": self._namespace,
		}
		
		# Try to get index stats from Pinecone
		if self._initialized and hasattr(self.vector_store, '_pinecone_index'):
			try:
				index_stats = self.vector_store._pinecone_index.describe_index_stats()
				stats["vector_count"] = index_stats.total_vector_count
				if self._namespace and self._namespace in index_stats.namespaces:
					stats["namespace_count"] = index_stats.namespaces[self._namespace].vector_count
				stats["dimension"] = index_stats.dimension
			except Exception as e:
				stats["stats_error"] = str(e)
		
		return stats
	
	def health_check(self) -> Tuple[bool, str]:
		"""Check backend health.
		
		Returns:
			Tuple of (is_healthy, message)
		"""
		try:
			if not self._initialized:
				return (False, "Backend not initialized")
			
			if not hasattr(self.vector_store, '_pinecone_index'):
				return (False, "Pinecone client not available")
			
			# Check connection by describing index stats
			self.vector_store._pinecone_index.describe_index_stats()
			return (True, "Healthy")
		except Exception as e:
			return (False, str(e))
	
	def supports_filters(self) -> bool:
		"""Pinecone supports metadata filtering.
		
		Returns:
			True
		"""
		return True
	
	def supports_hybrid_search(self) -> bool:
		"""Pinecone supports sparse-dense hybrid search.
		
		Returns:
			True
		"""
		return True


# Register backend
BackendFactory.register("pinecone", PineconeBackend)
