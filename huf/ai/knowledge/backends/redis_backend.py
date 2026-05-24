# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""Redis Vector backend using LlamaIndex adapter."""

from typing import Any, Dict, List, Optional, Tuple

import frappe

from ..backends import ChunkResult, KnowledgeBackend
from ..backends.factory import BackendFactory

# LlamaIndex imports - optional dependency
try:
	from llama_index.vector_stores.redis import RedisVectorStore
	from llama_index.core import VectorStoreIndex, StorageContext, Document
	LLAMAINDEX_AVAILABLE = True
except ImportError:
	LLAMAINDEX_AVAILABLE = False


class RedisBackend(KnowledgeBackend):
	"""Redis Vector backend for Huf knowledge storage."""
	
	def __init__(self):
		self.knowledge_source = None
		self.config = {}
		self.vector_store = None
		self.storage_context = None
		self.index = None
		self._initialized = False
		self._redis_client = None
	
	def initialize(self, knowledge_source: str, config: Dict[str, Any]) -> None:
		"""Initialize Redis backend."""
		if not LLAMAINDEX_AVAILABLE:
			raise ImportError(
				"llama-index-vector-stores-redis not installed. "
				"Install with: pip install llama-index-vector-stores-redis"
			)
		
		self.knowledge_source = knowledge_source
		self.config = config
		
		# Get connection parameters
		connection_params = self._get_connection_params()
		
		# Create vector store
		self.vector_store = RedisVectorStore(**connection_params)
		self.storage_context = StorageContext.from_defaults(
			vector_store=self.vector_store
		)
		
		# Store redis client for direct operations
		self._redis_client = self.vector_store._redis_client
		
		self._initialized = True
	
	def _get_connection_params(self) -> Dict[str, Any]:
		"""Build connection parameters from config."""
		index_prefix = self.config.get("index_prefix", "huf")
		index_name = f"{index_prefix}_{frappe.scrub(self.knowledge_source)}"
		
		params = {
			"index_name": index_name,
			"index_prefix": index_prefix,
			"host": self.config.get("host", "localhost"),
			"port": self.config.get("port", 6379),
			"dim": self.config.get("vector_dimension", 1536),
		}
		
		# Optional authentication
		if self.config.get("password"):
			params["password"] = self.config.get("password")
		
		if self.config.get("username"):
			params["username"] = self.config.get("username")
		
		return params
	
	def add_chunks(self, chunks: List[Dict[str, Any]]) -> int:
		"""Add chunks to Redis Vector Store."""
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
		filters: Optional[Dict] = None
	) -> List[ChunkResult]:
		"""Search Redis Vector Store."""
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
		"""Delete chunks by input_id using Redis hash tagging."""
		if not self._redis_client:
			return 0
		
		try:
			# Redis Vector Store stores documents with metadata
			# We'll search for keys matching the input_id pattern and delete them
			index_name = self.config.get("index_name", f"huf_{frappe.scrub(self.knowledge_source)}")
			
			# Use FT.SEARCH to find documents by input_id
			query = f"@input_id:{{{input_id}}}"
			results = self._redis_client.ft(index_name).search(query)
			
			deleted_count = 0
			if results and results.docs:
				for doc in results.docs:
					# Delete the document from Redis
					self._redis_client.delete(doc.id)
					deleted_count += 1
			
			return deleted_count
		except Exception as e:
			frappe.logger().warning(f"Redis delete_chunks error for {input_id}: {str(e)}")
			return 0
	
	def clear(self) -> None:
		"""Clear all vectors from the Redis index."""
		if self._redis_client and self.vector_store:
			try:
				index_name = self.config.get("index_name", f"huf_{frappe.scrub(self.knowledge_source)}")
				
				# Drop the search index
				try:
					self._redis_client.ft(index_name).dropindex(delete_documents=True)
				except Exception:
					# Index might not exist
					pass
				
				# Re-initialize the vector store
				connection_params = self._get_connection_params()
				self.vector_store = RedisVectorStore(**connection_params)
				self.storage_context = StorageContext.from_defaults(
					vector_store=self.vector_store
				)
				self._redis_client = self.vector_store._redis_client
				self.index = None
				
			except Exception as e:
				frappe.logger().warning(f"Redis clear error: {str(e)}")
	
	def get_stats(self) -> Dict[str, Any]:
		"""Get backend statistics."""
		stats = {
			"backend_type": "redis",
			"knowledge_source": self.knowledge_source,
			"initialized": self._initialized,
			"host": self.config.get("host", "localhost"),
			"port": self.config.get("port", 6379),
		}
		
		# Try to get Redis index info
		if self._redis_client:
			try:
				index_name = self.config.get("index_name", f"huf_{frappe.scrub(self.knowledge_source)}")
				info = self._redis_client.ft(index_name).info()
				stats["index_name"] = index_name
				stats["num_docs"] = info.get("num_docs", 0)
				stats["indexing"] = info.get("indexing", False)
			except Exception:
				# Index might not exist yet
				stats["index_exists"] = False
		
		return stats
	
	def health_check(self) -> Tuple[bool, str]:
		"""Check backend health by pinging Redis."""
		try:
			if self._redis_client:
				# Ping Redis server
				response = self._redis_client.ping()
				if response:
					return (True, "Healthy - Redis server responding")
				else:
					return (False, "Redis ping failed")
			else:
				return (False, "Redis client not initialized")
		except Exception as e:
			return (False, f"Redis health check failed: {str(e)}")
	
	def supports_filters(self) -> bool:
		"""Redis supports metadata filtering via RediSearch."""
		return True
	
	def supports_hybrid_search(self) -> bool:
		"""Redis hybrid search is possible but complex to implement.
		
		For now, return False. Can be enhanced later with
		Redisearch hybrid query support.
		"""
		return False


# Register backend
BackendFactory.register("redis", RedisBackend)
