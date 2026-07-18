# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""Redis Vector backend using LlamaIndex adapter."""

from typing import Any, Dict, List, Optional, Tuple

import frappe

from ..backends import ChunkResult, KnowledgeBackend

# LlamaIndex imports - optional dependency
try:
	from llama_index.vector_stores.redis import RedisVectorStore
	from llama_index.core import StorageContext, Document
	from llama_index.core.vector_stores.types import (
		VectorStoreQuery,
		MetadataFilters,
		ExactMatchFilter,
	)
	LLAMAINDEX_AVAILABLE = True
except ImportError:
	RedisVectorStore = None
	StorageContext = None
	VectorStoreQuery = None
	MetadataFilters = None
	ExactMatchFilter = None

	class Document:
		"""Minimal Document stand-in used only when llama-index is unavailable."""

		def __init__(self, text=None, id_=None, embedding=None, metadata=None):
			self.text = text
			self.id_ = id_
			self.embedding = embedding
			self.metadata = metadata or {}

	LLAMAINDEX_AVAILABLE = False


class RedisBackend(KnowledgeBackend):
	"""Redis Vector backend for Huf knowledge storage.

	Uses a modern llama-index-vector-stores-redis RedisVectorStore that expects
	a redis.Redis client and an IndexSchema describing the index. Embeddings are
	computed explicitly by Huf's embedding module and attached to Documents before
	add(), matching the chroma backend pattern.
	"""

	def __init__(self):
		self.knowledge_source = None
		self.config = {}
		self.vector_store = None
		self.storage_context = None
		self.index = None
		self._initialized = False
		self._redis_client = None

	def initialize(self, knowledge_source: str, config: Dict[str, Any]) -> None:
		"""Initialize Redis backend.

		Config options:
		- host: Redis server host (default: localhost)
		- port: Redis server port (default: 6379)
		- username: Optional Redis username
		- password: Optional Redis password
		- index_prefix: Key/index prefix (default: huf)
		- vector_dimension: Embedding dimension (default: 1536)
		"""
		if not LLAMAINDEX_AVAILABLE:
			raise ImportError(
				"llama-index-vector-stores-redis not installed. "
				"Install with: pip install llama-index-vector-stores-redis"
			)

		self.knowledge_source = knowledge_source
		self.config = config

		self._init_redis_client()
		self._init_vector_store()

		self._initialized = True

	def _init_redis_client(self) -> None:
		"""Create the redis.Redis client from config."""
		import redis

		connection_kwargs = {
			"host": self.config.get("host", "localhost"),
			"port": self.config.get("port", 6379),
		}

		if self.config.get("username"):
			connection_kwargs["username"] = self.config.get("username")
		if self.config.get("password"):
			connection_kwargs["password"] = self.config.get("password")

		self._redis_client = redis.Redis(**connection_kwargs)

	def _init_vector_store(self) -> None:
		"""Build RedisVectorStore with an explicit IndexSchema.

		We construct the schema via redisvl IndexSchema.from_dict so we can set
		the index name, key prefix, vector dimension, and metadata tag fields
		(input_id, input_type, etc.) that search/delete filters rely on.
		"""
		from redisvl.schema import IndexSchema

		index_prefix = self.config.get("index_prefix", "huf")
		index_name = f"{index_prefix}_{frappe.scrub(self.knowledge_source)}"
		vector_dimension = self.config.get("vector_dimension", 1536)

		schema = IndexSchema.from_dict({
			"index": {
				"name": index_name,
				"prefix": f"{index_name}/vector",
				"key_separator": "_",
			},
			"fields": [
				{"type": "tag", "name": "id", "attrs": {"sortable": False}},
				{"type": "tag", "name": "doc_id", "attrs": {"sortable": False}},
				{"type": "text", "name": "text", "attrs": {"weight": 1.0}},
				{"type": "tag", "name": "input_id", "attrs": {"sortable": False}},
				{"type": "tag", "name": "input_type", "attrs": {"sortable": False}},
				{"type": "tag", "name": "chunk_id", "attrs": {"sortable": False}},
				{"type": "tag", "name": "source_title", "attrs": {"sortable": False}},
				{"type": "tag", "name": "knowledge_source", "attrs": {"sortable": False}},
				{
					"type": "vector",
					"name": "vector",
					"attrs": {
						"dims": vector_dimension,
						"algorithm": "flat",
						"distance_metric": "cosine",
					},
				},
			],
		})

		self.vector_store = RedisVectorStore(
			redis_client=self._redis_client,
			schema=schema,
		)
		self.storage_context = StorageContext.from_defaults(
			vector_store=self.vector_store
		)

	def add_chunks(self, chunks: List[Dict[str, Any]]) -> int:
		"""Add chunks to Redis Vector Store.

		Args:
			chunks: List of chunk dictionaries with keys:
				- text: The chunk text content
				- input_id: Source input ID
				- input_type: Type of input (e.g., 'document', 'web_page')
				- chunk_id: Unique chunk identifier
				- source_title: Title of the source
				- chunk_index: Index of the chunk within the source
				- metadata: Additional metadata dict

		Returns:
			Number of chunks added
		"""
		if not chunks:
			return 0

		if not self._initialized:
			raise RuntimeError("Backend not initialized. Call initialize() first.")

		from huf.ai.knowledge.embedding import get_embeddings, resolve_embedding_config
		import uuid

		texts = [chunk["text"] for chunk in chunks]
		embed_config = resolve_embedding_config(self.knowledge_source)
		embeddings = get_embeddings(
			texts=texts,
			model=embed_config["model"],
			api_key=embed_config.get("api_key"),
			api_base=embed_config.get("api_base"),
		)

		documents = []
		for chunk, embedding in zip(chunks, embeddings):
			chunk_id = chunk.get("chunk_id") or str(uuid.uuid4())
			doc = Document(
				text=chunk["text"],
				id_=chunk_id,
				embedding=embedding,
				metadata={
					"input_id": chunk["input_id"],
					"input_type": chunk["input_type"],
					"chunk_id": chunk_id,
					"source_title": chunk.get("source_title"),
					"chunk_index": chunk.get("chunk_index"),
					"knowledge_source": self.knowledge_source,
					**(chunk.get("metadata") or {})
				}
			)
			documents.append(doc)

		if documents:
			self.vector_store.add(documents)

		return len(chunks)

	def search(
		self,
		query: str,
		top_k: int = 5,
		filters: Optional[Dict[str, Any]] = None
	) -> List[ChunkResult]:
		"""Search Redis Vector Store for relevant chunks.

		Args:
			query: Search query text
			top_k: Maximum number of results
			filters: Optional metadata filters (e.g., {"input_type": "document"})

		Returns:
			List of ChunkResult objects
		"""
		if not self._initialized:
			raise RuntimeError("Backend not initialized. Call initialize() first.")

		from huf.ai.knowledge.embedding import get_embedding, resolve_embedding_config

		embed_config = resolve_embedding_config(self.knowledge_source)
		query_embedding = get_embedding(
			text=query,
			model=embed_config["model"],
			api_key=embed_config.get("api_key"),
			api_base=embed_config.get("api_base"),
		)

		query_kwargs = {
			"query_embedding": query_embedding,
			"similarity_top_k": top_k,
			"mode": "default",
		}

		if filters:
			llama_filters = [
				ExactMatchFilter(key=key, value=value)
				for key, value in filters.items()
			]
			query_kwargs["filters"] = MetadataFilters(filters=llama_filters)

		query_obj = VectorStoreQuery(**query_kwargs)

		# Search directly on vector store to use our custom embedding
		result = self.vector_store.query(query_obj)

		# Convert to ChunkResult
		results = []
		if result.nodes:
			for i, node in enumerate(result.nodes):
				score = 0.0
				if result.similarities and i < len(result.similarities):
					score = float(result.similarities[i])

				res = ChunkResult(
					chunk_id=node.metadata.get("chunk_id", ""),
					text=node.text,
					title=node.metadata.get("source_title"),
					score=score,
					source=node.metadata.get("knowledge_source"),
					metadata={k: v for k, v in node.metadata.items() if k not in [
						"chunk_id", "source_title", "knowledge_source"
					]}
				)
				results.append(res)

		return results

	def delete_chunks(self, input_id: str) -> int:
		"""Delete all chunks for an input.

		Uses RedisVectorStore.delete_nodes with a metadata filter on input_id.
		The schema declares input_id as a tag field so this filter is indexed.

		Args:
			input_id: The input ID to delete chunks for

		Returns:
			Number of chunks deleted
		"""
		if not self._initialized or not self.vector_store:
			raise RuntimeError("Backend not initialized. Call initialize() first.")

		try:
			# Count matching documents before deleting
			count_query = VectorStoreQuery(
				filters=MetadataFilters(filters=[
					ExactMatchFilter(key="input_id", value=input_id)
				]),
				similarity_top_k=10000,
			)
			count_result = self.vector_store.query(count_query)
			count = len(count_result.nodes) if count_result.nodes else 0

			# Delete matching documents
			self.vector_store.delete_nodes(
				filters=MetadataFilters(filters=[
					ExactMatchFilter(key="input_id", value=input_id)
				])
			)

			return count
		except Exception as e:
			frappe.logger().warning(f"Redis delete_chunks error for {input_id}: {str(e)}")
			return 0

	def clear(self) -> None:
		"""Clear all chunks from the Redis index."""
		if not self._initialized or not self.vector_store:
			raise RuntimeError("Backend not initialized. Call initialize() first.")

		try:
			index_name = self.vector_store.index_name
			self.vector_store.client.ft(index_name).dropindex(delete_documents=True)
		except Exception as e:
			frappe.logger().warning(f"Redis clear dropindex error: {str(e)}")

		# Rebuild vector store so the index exists for subsequent operations
		self._init_vector_store()
		self.index = None

	def get_stats(self) -> Dict[str, Any]:
		"""Get backend statistics.

		Returns:
			Dict with backend statistics
		"""
		stats = {
			"backend_type": "redis",
			"knowledge_source": self.knowledge_source,
			"initialized": self._initialized,
			"host": self.config.get("host", "localhost"),
			"port": self.config.get("port", 6379),
			"index_name": self.vector_store.index_name if self.vector_store else None,
			"chunk_count": 0,
		}

		if self.vector_store:
			try:
				info = self.vector_store.client.ft(
					self.vector_store.index_name
				).info()
				stats["chunk_count"] = info.get("num_docs", 0)
			except Exception as e:
				frappe.logger().warning(f"Redis get_stats count error: {str(e)}")

		return stats

	def health_check(self) -> Tuple[bool, str]:
		"""Check backend health.

		Returns:
			Tuple of (is_healthy, message)
		"""
		try:
			if not self._initialized:
				return (False, "Backend not initialized")

			if not self.vector_store:
				return (False, "Redis vector store not available")

			# Ping Redis server
			self.vector_store.client.ping()

			return (True, "Healthy")
		except Exception as e:
			return (False, str(e))

	def supports_filters(self) -> bool:
		"""Redis supports metadata filtering via RediSearch."""
		return True

	def supports_hybrid_search(self) -> bool:
		"""Redis hybrid search is not enabled in this backend."""
		return False
