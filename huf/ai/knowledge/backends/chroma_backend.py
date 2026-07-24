# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""ChromaDB backend using LlamaIndex adapter."""

from typing import Any

import frappe

from . import ChunkResult, KnowledgeBackend
from .llamaindex_base import LLAMAINDEX_AVAILABLE, LlamaIndexBackend

try:
	import chromadb
	from llama_index.vector_stores.chroma import ChromaVectorStore

	CHROMA_DEPS_AVAILABLE = True
except ImportError:
	CHROMA_DEPS_AVAILABLE = False


class ChromaBackend(LlamaIndexBackend, KnowledgeBackend):
	"""ChromaDB backend for Huf knowledge storage.

	Supports both local file-based storage (PersistentClient) and
	remote server mode (HttpClient).
	"""

	_backend_type = "chroma"

	@classmethod
	def get_advanced_config_schema(cls) -> list[dict[str, Any]]:
		return [
			{
				"key": "chroma_hnsw_space",
				"label": "HNSW Space",
				"type": "select",
				"default": "cosine",
				"options": ["cosine", "l2", "ip"],
				"help_text": "Distance function used by the HNSW index. Choose the metric that matches your embedding model (cosine is the most common).",
			},
			{
				"key": "chroma_hnsw_m",
				"label": "HNSW M",
				"type": "number",
				"default": 16,
				"min": 4,
				"max": 200,
				"help_text": "Max connections per node in the HNSW graph. Higher values improve recall at the cost of more memory and slower index builds.",
			},
			{
				"key": "chroma_hnsw_construction_ef",
				"label": "HNSW Construction EF",
				"type": "number",
				"default": 100,
				"min": 4,
				"max": 1000,
				"help_text": "Size of the dynamic candidate list used during HNSW index construction. Higher values improve index quality at the cost of build time.",
			},
			{
				"key": "chroma_hnsw_search_ef",
				"label": "HNSW Search EF",
				"type": "number",
				"default": 100,
				"min": 1,
				"max": 1000,
				"help_text": "Size of the dynamic candidate list used during HNSW search. Higher values improve recall at the cost of search speed.",
			},
		]

	def __init__(self):
		super().__init__()
		self.client = None
		self.collection = None
		self.index = None

	def _check_dependencies(self) -> None:
		if not LLAMAINDEX_AVAILABLE or not CHROMA_DEPS_AVAILABLE:
			raise ImportError(
				"llama-index-vector-stores-chroma and chromadb not installed. "
				"Install with: pip install llama-index-vector-stores-chroma chromadb"
			)

	def _validate_config(self) -> None:
		# Chroma has no mandatory validation; connection details are resolved
		# lazily in _create_vector_store.
		pass

	def _create_vector_store(self) -> Any:
		"""Create Chroma client, collection, and vector store."""
		persist_directory = self.config.get("persist_directory")

		if persist_directory:
			self.client = chromadb.PersistentClient(path=persist_directory)
		else:
			host = self.config.get("host", "localhost")
			port = self.config.get("port", 8000)
			ssl = self.config.get("ssl", False)
			self.client = chromadb.HttpClient(host=host, port=port, ssl=ssl)

		collection_name = self.config.get("collection_name") or f"huf_{frappe.scrub(self.knowledge_source)}"
		metadata = {"knowledge_source": self.knowledge_source}
		# Only include HNSW knobs the user explicitly set, so unset values fall
		# back to Chroma's own defaults. get_or_create_collection applies this
		# metadata only on CREATE — existing collections keep their HNSW config.
		hnsw_key_map = {
			"chroma_hnsw_space": "hnsw:space",
			"chroma_hnsw_m": "hnsw:M",
			"chroma_hnsw_construction_ef": "hnsw:construction_ef",
			"chroma_hnsw_search_ef": "hnsw:search_ef",
		}
		for config_key, metadata_key in hnsw_key_map.items():
			value = self.config.get(config_key)
			if value is not None:
				metadata[metadata_key] = value if metadata_key == "hnsw:space" else int(value)
		self.collection = self.client.get_or_create_collection(
			name=collection_name,
			metadata=metadata,
		)

		return ChromaVectorStore(chroma_collection=self.collection)

	@property
	def _result_source_field(self) -> str:
		return "knowledge_source"

	@property
	def _excluded_metadata_keys(self) -> set[str]:
		return {"chunk_id", "source_title", "knowledge_source"}

	def delete_chunks(self, input_id: str) -> int:
		if not self._initialized or not self.collection:
			raise RuntimeError("Backend not initialized. Call initialize() first.")

		try:
			results = self.collection.get(where={"input_id": input_id}, include=[])
			ids_to_delete = results.get("ids", [])
			if ids_to_delete:
				self.collection.delete(ids=ids_to_delete)
			return len(ids_to_delete)
		except Exception as exc:
			frappe.logger().warning(f"Chroma delete_chunks error for {input_id}: {exc!s}")
			return 0

	def clear(self) -> None:
		if not self._initialized or not self.collection:
			raise RuntimeError("Backend not initialized. Call initialize() first.")

		try:
			self.collection.delete(where={})
		except Exception:
			try:
				results = self.collection.get(include=[])
				ids = results.get("ids", [])
				if ids:
					self.collection.delete(ids=ids)
			except Exception as exc:
				frappe.logger().error(f"Chroma clear error: {exc!s}")
				raise

		self.index = None

	def get_stats(self) -> dict[str, Any]:
		stats = {
			"backend_type": "chroma",
			"knowledge_source": self.knowledge_source,
			"initialized": self._initialized,
			"host": self.config.get(
				"host", "localhost" if not self.config.get("persist_directory") else None
			),
			"port": self.config.get("port", 8000 if not self.config.get("persist_directory") else None),
			"persist_directory": self.config.get("persist_directory"),
			"collection_name": self.collection.name if self.collection else None,
			"chunk_count": 0,
		}

		if self.collection:
			try:
				stats["chunk_count"] = self.collection.count()
			except Exception as exc:
				frappe.logger().warning(f"Chroma get_stats count error: {exc!s}")

		return stats

	def health_check(self) -> tuple[bool, str]:
		try:
			if not self._initialized:
				return (False, "Backend not initialized")
			if not self.client:
				return (False, "Chroma client not available")
			self.client.list_collections()
			return (True, "Healthy")
		except Exception as exc:
			return (False, str(exc))
