# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""Weaviate backend using LlamaIndex adapter."""

import re
from typing import Any, Dict, List, Optional, Tuple

import frappe

from ..backends import ChunkResult, KnowledgeBackend
from ..backends.factory import BackendFactory

# LlamaIndex imports - optional dependency
try:
	from llama_index.vector_stores.weaviate import WeaviateVectorStore
	from llama_index.core import VectorStoreIndex, StorageContext, Document
	LLAMAINDEX_AVAILABLE = True
except ImportError:
	LLAMAINDEX_AVAILABLE = False


class WeaviateBackend(KnowledgeBackend):
	"""Weaviate vector backend for Huf knowledge storage.
	
	Supports both self-hosted (Docker) and Weaviate Cloud deployments.
	Features best-in-class hybrid search combining vector similarity with BM25.
	"""
	
	def __init__(self):
		self.knowledge_source = None
		self.config = {}
		self.vector_store = None
		self.storage_context = None
		self.index = None
		self._initialized = False
		self._weaviate_client = None
	
	def initialize(self, knowledge_source: str, config: Dict[str, Any]) -> None:
		"""Initialize Weaviate backend."""
		if not LLAMAINDEX_AVAILABLE:
			raise ImportError(
				"llama-index-vector-stores-weaviate not installed. "
				"Install with: pip install llama-index-vector-stores-weaviate"
			)
		
		self.knowledge_source = knowledge_source
		self.config = config
		
		# Get connection parameters
		connection_params = self._get_connection_params()
		
		# Create vector store
		self.vector_store = WeaviateVectorStore(**connection_params)
		self.storage_context = StorageContext.from_defaults(
			vector_store=self.vector_store
		)
		
		self._initialized = True
	
	def _get_connection_params(self) -> Dict[str, Any]:
		"""Build connection parameters from config."""
		# Sanitize class name - Weaviate class names must start with uppercase letter
		# and contain only alphanumeric characters
		sanitized = frappe.scrub(self.knowledge_source)
		class_name = f"Huf_{sanitized}"
		# Ensure starts with uppercase and only alphanumeric
		class_name = re.sub(r'[^a-zA-Z0-9]', '_', class_name)
		if class_name[0].isdigit():
			class_name = f"Class_{class_name}"
		class_name = class_name[0].upper() + class_name[1:]
		
		params = {
			"class_name": class_name,
		}
		
		# Handle different connection modes
		if self.config.get("weaviate_cloud_url"):
			# Weaviate Cloud
			params["url"] = self.config["weaviate_cloud_url"]
			if self.config.get("api_key"):
				params["api_key"] = self.config["api_key"]
		else:
			# Self-hosted
			host = self.config.get("host", "localhost")
			port = self.config.get("port", 8080)
			params["url"] = f"http://{host}:{port}"
		
		return params
	
	def add_chunks(self, chunks: List[Dict[str, Any]]) -> int:
		"""Add chunks to Weaviate."""
		if not chunks:
			return 0
		
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
		filters: Optional[Dict] = None,
		use_hybrid: bool = True
	) -> List[ChunkResult]:
		"""Search Weaviate using hybrid search (vector + BM25).
		
		Args:
			query: Search query string
			top_k: Number of results to return
			filters: Optional metadata filters
			use_hybrid: If True, use hybrid search (vector + keyword). 
				If False, use pure vector search.
		"""
		if not self.index:
			# Try to load existing index
			self.index = VectorStoreIndex.from_vector_store(
				self.vector_store,
				storage_context=self.storage_context,
			)
		
		# Create retriever with hybrid search if enabled
		if use_hybrid and self.supports_hybrid_search():
			retriever = self.index.as_retriever(
				similarity_top_k=top_k,
				vector_store_kwargs={
					"alpha": 0.7,  # Balance between vector (1.0) and BM25 (0.0)
					"fusion_type": "relative_score",
				}
			)
		else:
			retriever = self.index.as_retriever(similarity_top_k=top_k)
		
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
		"""Delete chunks by input_id."""
		try:
			# Weaviate supports deletion by metadata filter
			# Using where filter to delete objects with matching input_id
			from weaviate.classes.query import Filter
			
			collection = self.vector_store._collection
			collection.data.delete_many(
				where=Filter.by_property("input_id").equal(input_id)
			)
			return 1  # Weaviate doesn't return count, assume success
		except Exception as e:
			frappe.logger().warning(
				f"Weaviate delete_chunks failed for {input_id}: {str(e)}"
			)
			return 0
	
	def clear(self) -> None:
		"""Clear all vectors from the class."""
		try:
			if self.vector_store:
				# Get the Weaviate client from vector store
				client = self.vector_store._client
				class_name = self._get_connection_params()["class_name"]
				
				# Delete all objects in the class
				client.collections.delete(class_name)
				
				# Re-initialize to recreate the schema
				connection_params = self._get_connection_params()
				self.vector_store = WeaviateVectorStore(**connection_params)
				self.storage_context = StorageContext.from_defaults(
					vector_store=self.vector_store
				)
				self.index = None
		except Exception as e:
			frappe.logger().error(f"Weaviate clear failed: {str(e)}")
			raise
	
	def get_stats(self) -> Dict[str, Any]:
		"""Get backend statistics."""
		stats = {
			"backend_type": "weaviate",
			"knowledge_source": self.knowledge_source,
			"initialized": self._initialized,
			"class_name": self._get_connection_params().get("class_name"),
			"url": self._get_connection_params().get("url"),
		}
		
		# Try to get object count
		try:
			if self.vector_store:
				collection = self.vector_store._collection
				# Get aggregate count
				result = collection.aggregate.over_all(total_count=True)
				stats["object_count"] = result.total_count
		except Exception as e:
			stats["object_count"] = None
			stats["count_error"] = str(e)
		
		return stats
	
	def health_check(self) -> Tuple[bool, str]:
		"""Check backend health."""
		try:
			if self.vector_store:
				# Test connection with a simple query
				client = self.vector_store._client
				client.get_meta()
			return (True, "Healthy")
		except Exception as e:
			return (False, str(e))
	
	def supports_filters(self) -> bool:
		"""Weaviate supports metadata filtering."""
		return True
	
	def supports_hybrid_search(self) -> bool:
		"""Weaviate supports hybrid search (vector + BM25)."""
		return True
	
	def get_class_name(self) -> str:
		"""Get the Weaviate class name for this knowledge source."""
		return self._get_connection_params().get("class_name", "")


# Register backend
BackendFactory.register("weaviate", WeaviateBackend)
