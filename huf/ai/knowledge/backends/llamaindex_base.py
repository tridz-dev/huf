# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""Shared LlamaIndex vector-store backend base class.

Backends that build on LlamaIndex vector-store adapters (Chroma, PGVector,
Weaviate, etc.) inherit from :class:`LlamaIndexBackend` to reuse the common
HUF-side machinery: chunk-to-Document conversion with HUF-generated embeddings,
VectorStoreQuery-based search, and metadata-filter scoping.
"""

import uuid
from abc import ABC, abstractmethod
from typing import Any

import frappe
from frappe import _

from . import ChunkResult, KnowledgeBackend

try:
	from llama_index.core import Document, StorageContext
	from llama_index.core.vector_stores import VectorStoreQuery
	from llama_index.core.vector_stores.types import ExactMatchFilter, MetadataFilters

	LLAMAINDEX_AVAILABLE = True
except ImportError:
	LLAMAINDEX_AVAILABLE = False


class LlamaIndexBackend(KnowledgeBackend, ABC):
	"""Base class for LlamaIndex vector-store backends.

	Subclasses provide backend-specific vector-store creation, configuration
	validation, and storage-engine plumbing. This base class owns the shared
	LlamaIndex-path behavior: embedding generation, Document conversion,
	VectorStoreQuery search, and result normalization.
	"""

	_backend_type: str = "llamaindex"

	def __init__(self):
		self.knowledge_source = None
		self.config = {}
		self.vector_store = None
		self.storage_context = None
		self._initialized = False

	# ------------------------------------------------------------------
	# Backend-specific hooks (must be implemented or overridden)
	# ------------------------------------------------------------------
	def _check_dependencies(self) -> None:
		"""Raise a clear error when required LlamaIndex packages are missing."""
		if not LLAMAINDEX_AVAILABLE:
			frappe.throw(
				_("llama-index-core is required for {0} knowledge sources.").format(self._backend_type)
			)

	@abstractmethod
	def _validate_config(self) -> None:
		"""Validate backend-specific configuration."""
		pass

	def _before_create_vector_store(self) -> None:
		"""Hook called before the vector store is created."""
		pass

	@abstractmethod
	def _create_vector_store(self) -> Any:
		"""Create and return the backend-specific vector store instance."""
		pass

	def _after_create_vector_store(self) -> None:
		"""Hook called after the vector store and storage context are ready."""
		pass

	# ------------------------------------------------------------------
	# Shared initialization
	# ------------------------------------------------------------------
	def initialize(self, knowledge_source: str, config: dict[str, Any]) -> None:
		self._check_dependencies()
		self.knowledge_source = knowledge_source
		self.config = config or {}
		self._validate_config()
		self._before_create_vector_store()
		self.vector_store = self._create_vector_store()
		self.storage_context = StorageContext.from_defaults(vector_store=self.vector_store)
		self._after_create_vector_store()
		self._initialized = True

	# ------------------------------------------------------------------
	# Chunk metadata / Document conversion
	# ------------------------------------------------------------------
	def _build_chunk_metadata(self, chunk: dict[str, Any], chunk_id: str) -> dict[str, Any]:
		"""Build metadata dict attached to each LlamaIndex Document.

		Backends may override to add per-backend scoping keys such as
		``site_name`` or ``char_start``/``char_end``.
		"""
		return {
			"knowledge_source": self.knowledge_source,
			"input_id": chunk["input_id"],
			"input_type": chunk["input_type"],
			"chunk_id": chunk_id,
			"source_title": chunk.get("source_title"),
			"chunk_index": chunk.get("chunk_index"),
			**(chunk.get("metadata") or {}),
		}

	def add_chunks(self, chunks: list[dict[str, Any]]) -> int:
		if not chunks:
			return 0
		if not self._initialized:
			raise RuntimeError("Backend not initialized. Call initialize() first.")

		from huf.ai.knowledge.embedding import get_embeddings, resolve_embedding_config

		texts = [chunk["text"] for chunk in chunks]
		embed_config = resolve_embedding_config(self.knowledge_source)
		embeddings = get_embeddings(
			texts=texts,
			model=embed_config["model"],
			api_key=embed_config.get("api_key"),
			api_base=embed_config.get("api_base"),
		)

		documents = []
		for chunk, embedding in zip(chunks, embeddings, strict=True):
			chunk_id = chunk.get("chunk_id") or str(uuid.uuid4())
			documents.append(
				Document(
					text=chunk["text"],
					id_=chunk_id,
					embedding=embedding,
					metadata=self._build_chunk_metadata(chunk, chunk_id),
				)
			)

		if documents:
			self.vector_store.add(documents)

		return len(chunks)

	# ------------------------------------------------------------------
	# Search
	# ------------------------------------------------------------------
	@property
	def _result_source_field(self) -> str:
		"""Metadata key used as ``ChunkResult.source``."""
		return "input_id"

	@property
	def _excluded_metadata_keys(self) -> set[str]:
		"""Metadata keys stripped from ``ChunkResult.metadata``."""
		return {"chunk_id", "source_title", "knowledge_source", "site_name"}

	def _build_search_filters(self, filters: dict[str, Any] | None) -> MetadataFilters | None:
		"""Build LlamaIndex metadata filters for a search query.

		The default implementation applies only the caller-supplied filters.
		Backends that scope by ``site_name``/``knowledge_source`` should
		override this method to add those mandatory filters.
		"""
		llama_filters = []
		if filters:
			llama_filters.extend(ExactMatchFilter(key=key, value=value) for key, value in filters.items())
		return MetadataFilters(filters=llama_filters) if llama_filters else None

	def _node_to_chunk_result(self, node, result: Any, index: int) -> ChunkResult:
		"""Convert a single LlamaIndex node to a HUF ChunkResult."""
		score = 0.0
		if result.similarities and index < len(result.similarities):
			score = float(result.similarities[index])

		metadata = dict(node.metadata or {})
		return ChunkResult(
			chunk_id=metadata.get("chunk_id", node.id_ or ""),
			text=node.text,
			title=metadata.get("source_title"),
			score=score,
			source=metadata.get(self._result_source_field),
			metadata={k: v for k, v in metadata.items() if k not in self._excluded_metadata_keys},
		)

	def search(
		self,
		query: str,
		top_k: int = 5,
		filters: dict[str, Any] | None = None,
	) -> list[ChunkResult]:
		if not query or not query.strip():
			return []
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

		query_kwargs: dict[str, Any] = {
			"query_embedding": query_embedding,
			"similarity_top_k": top_k,
			"mode": "default",
		}

		llama_filters = self._build_search_filters(filters)
		if llama_filters:
			query_kwargs["filters"] = llama_filters

		query_obj = VectorStoreQuery(**query_kwargs)
		result = self.vector_store.query(query_obj)

		results = []
		if result.nodes:
			for index, node in enumerate(result.nodes):
				results.append(self._node_to_chunk_result(node, result, index))

		return results

	# ------------------------------------------------------------------
	# Maintenance / stats
	# ------------------------------------------------------------------
	def health_check(self) -> tuple[bool, str]:
		try:
			if not self._initialized:
				return (False, "Backend not initialized")
			self.get_stats()
			return (True, "Healthy")
		except Exception as exc:
			return (False, str(exc))

	def supports_filters(self) -> bool:
		return True

	def supports_hybrid_search(self) -> bool:
		return False
