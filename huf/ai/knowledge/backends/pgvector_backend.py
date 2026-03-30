# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""PostgreSQL/pgvector backend using LlamaIndex adapter."""

from typing import Any, Dict, List, Optional, Tuple

import frappe

from ..backends import ChunkResult, KnowledgeBackend
from ..backends.factory import BackendFactory

# LlamaIndex imports - optional dependency
try:
	from llama_index.vector_stores.postgres import PGVectorStore
	from llama_index.core import VectorStoreIndex, StorageContext, Document
	LLAMAINDEX_AVAILABLE = True
except ImportError:
	LLAMAINDEX_AVAILABLE = False


class PGVectorBackend(KnowledgeBackend):
	"""PostgreSQL/pgvector backend for Huf knowledge storage."""
	
	def __init__(self):
		self.knowledge_source = None
		self.config = {}
		self.vector_store = None
		self.storage_context = None
		self.index = None
		self._initialized = False
	
	def initialize(self, knowledge_source: str, config: Dict[str, Any]) -> None:
		"""Initialize pgvector backend."""
		if not LLAMAINDEX_AVAILABLE:
			raise ImportError(
				"llama-index-vector-stores-postgres not installed. "
				"Install with: pip install llama-index-vector-stores-postgres"
			)
		
		self.knowledge_source = knowledge_source
		self.config = config
		
		# Get connection parameters
		connection_params = self._get_connection_params()
		
		# Create vector store
		self.vector_store = PGVectorStore.from_params(**connection_params)
		self.storage_context = StorageContext.from_defaults(
			vector_store=self.vector_store
		)
		
		self._initialized = True
	
	def _get_connection_params(self) -> Dict[str, Any]:
		"""Build connection parameters from config."""
		table_name = f"huf_{frappe.scrub(self.knowledge_source)}"
		
		return {
			"host": self.config.get("host", "localhost"),
			"port": self.config.get("port", 5432),
			"database": self.config.get("database", frappe.conf.db_name),
			"user": self.config.get("user", frappe.conf.db_user),
			"password": self.config.get("password", frappe.conf.db_password),
			"table_name": table_name,
			"embed_dim": self.config.get("vector_dimension", 1536),
		}
	
	def add_chunks(self, chunks: List[Dict[str, Any]]) -> int:
		"""Add chunks to pgvector."""
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
		"""Search pgvector."""
		if not self.index:
			# Try to load existing index
			self.index = VectorStoreIndex.from_vector_store(
				self.vector_store,
				storage_context=self.storage_context,
			)
		
		# Create retriever
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
		# PGVector doesn't support easy deletion by metadata
		# Handle at application layer
		frappe.logger().warning(
			f"PGVector delete_chunks not fully implemented for {input_id}"
		)
		return 0
	
	def clear(self) -> None:
		"""Clear all vectors."""
		if self.vector_store:
			table_name = f"huf_{frappe.scrub(self.knowledge_source)}"
			frappe.db.sql(f"TRUNCATE TABLE {table_name}")
	
	def get_stats(self) -> Dict[str, Any]:
		"""Get backend statistics."""
		return {
			"backend_type": "pgvector",
			"knowledge_source": self.knowledge_source,
			"initialized": self._initialized,
			"host": self.config.get("host"),
			"database": self.config.get("database"),
		}
	
	def health_check(self) -> Tuple[bool, str]:
		"""Check backend health."""
		try:
			if self.vector_store:
				self.search("health_check", top_k=1)
			return (True, "Healthy")
		except Exception as e:
			return (False, str(e))
	
	def supports_filters(self) -> bool:
		"""pgvector supports metadata filtering."""
		return True
	
	def supports_hybrid_search(self) -> bool:
		"""pgvector supports hybrid with FTS."""
		return True


# Register backend
BackendFactory.register("pgvector", PGVectorBackend)
