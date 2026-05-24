# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""FAISS backend using LlamaIndex adapter."""

import os
from typing import Any, Dict, List, Optional, Tuple

import frappe

from ..backends import ChunkResult, KnowledgeBackend
from ..backends.factory import BackendFactory

# LlamaIndex imports - optional dependency
try:
	from llama_index.vector_stores.faiss import FaissVectorStore
	from llama_index.core import VectorStoreIndex, StorageContext, Document
	LLAMAINDEX_AVAILABLE = True
except ImportError:
	LLAMAINDEX_AVAILABLE = False


class FAISSBackend(KnowledgeBackend):
	"""FAISS backend for Huf knowledge storage.
	
	FAISS is an in-memory vector store that requires manual persistence.
	Best for: Research, development, small datasets.
	Limitations: No built-in metadata filtering, no native persistence.
	"""
	
	def __init__(self):
		super().__init__()
		self.vector_store: Optional[FaissVectorStore] = None
		self.storage_context: Optional[StorageContext] = None
		self.index: Optional[VectorStoreIndex] = None
		self._initialized = False
		self._index_path: Optional[str] = None
		self._dimension: int = 1536
	
	def initialize(self, knowledge_source: str, config: Dict[str, Any]) -> None:
		"""Initialize FAISS backend.
		
		Config options:
			- index_path: Path to save/load FAISS index (default: frappe private files)
			- vector_dimension: Dimension of embeddings (default: 1536)
		"""
		if not LLAMAINDEX_AVAILABLE:
			raise ImportError(
				"llama-index-vector-stores-faiss not installed. "
				"Install with: pip install llama-index-vector-stores-faiss"
			)
		
		self.knowledge_source = knowledge_source
		self.config = config
		self._dimension = config.get("vector_dimension", 1536)
		
		# Set up index path for persistence
		self._index_path = self._get_index_path()
		
		# Load existing index if available, otherwise create new
		if os.path.exists(self._index_path):
			self._load_index()
		else:
			self._create_new_index()
		
		self._initialized = True
	
	def _get_index_path(self) -> str:
		"""Get the path for storing FAISS index."""
		# Use configured path or default to frappe private files
		if "index_path" in self.config:
			return self.config["index_path"]
		
		# Default: store in site's private files
		site_path = frappe.get_site_path()
		index_dir = os.path.join(site_path, "private", "files", "huf_faiss_indexes")
		os.makedirs(index_dir, exist_ok=True)
		
		# Use sanitized knowledge source as filename
		safe_name = frappe.scrub(self.knowledge_source)
		return os.path.join(index_dir, f"{safe_name}.faiss")
	
	def _create_new_index(self) -> None:
		"""Create a new FAISS index."""
		self.vector_store = FaissVectorStore(
			faiss_index=None,  # Will create new index
			dim=self._dimension,
		)
		self.storage_context = StorageContext.from_defaults(
			vector_store=self.vector_store
		)
		self.index = None  # Will be created when first documents are added
		
		# Save the empty index
		self._save_index()
	
	def _load_index(self) -> None:
		"""Load existing FAISS index from disk."""
		try:
			self.vector_store = FaissVectorStore.from_persist_path(
				persist_path=self._index_path
			)
			self.storage_context = StorageContext.from_defaults(
				vector_store=self.vector_store
			)
			# Try to load the index
			self.index = VectorStoreIndex.from_vector_store(
				vector_store=self.vector_store,
				storage_context=self.storage_context,
			)
		except Exception as e:
			frappe.logger().warning(f"Failed to load FAISS index, creating new: {e}")
			self._create_new_index()
	
	def _save_index(self) -> None:
		"""Save FAISS index to disk."""
		if self.vector_store:
			try:
				self.vector_store.persist(persist_path=self._index_path)
			except Exception as e:
				frappe.logger().error(f"Failed to save FAISS index: {e}")
	
	def add_chunks(self, chunks: List[Dict[str, Any]]) -> int:
		"""Add chunks to FAISS index.
		
		Note: FAISS doesn't support incremental updates well, so we rebuild
		the index when adding new chunks. For production use with large
		datasets, consider using pgvector instead.
		"""
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
		if self.index is None:
			# First time adding documents
			self.index = VectorStoreIndex.from_documents(
				documents,
				storage_context=self.storage_context,
			)
		else:
			# Add to existing index
			for doc in documents:
				self.index.insert(doc)
		
		# Persist to disk
		self._save_index()
		
		return len(chunks)
	
	def search(
		self,
		query: str,
		top_k: int = 5,
		filters: Optional[Dict] = None
	) -> List[ChunkResult]:
		"""Search FAISS index.
		
		Note: filters parameter is ignored as FAISS doesn't support
		metadata filtering in basic usage.
		"""
		if not self.index:
			# Try to load existing index
			if os.path.exists(self._index_path):
				self._load_index()
			else:
				return []
		
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
		"""Delete chunks by input_id.
		
		FAISS Limitation: Basic FAISS doesn't support deletion by metadata.
		This would require either:
		1. Rebuilding the entire index without the deleted chunks
		2. Using a more complex FAISS index type with ID mapping
		3. Marking as deleted and filtering at application layer
		
		For now, we log a warning and return 0. Consider using pgvector
		for use cases requiring frequent deletions.
		"""
		frappe.logger().warning(
			f"FAISS delete_chunks not implemented - FAISS doesn't support "
			f"easy deletion by metadata. Consider rebuilding the index or "
			f"using pgvector backend for {input_id}"
		)
		return 0
	
	def clear(self) -> None:
		"""Clear all vectors and reset the index."""
		# Remove the index file if it exists
		if self._index_path and os.path.exists(self._index_path):
			try:
				os.remove(self._index_path)
			except Exception as e:
				frappe.logger().error(f"Failed to remove FAISS index file: {e}")
		
		# Reset in-memory state
		self._create_new_index()
		
		frappe.logger().info(f"Cleared FAISS index for {self.knowledge_source}")
	
	def get_stats(self) -> Dict[str, Any]:
		"""Get backend statistics."""
		stats = {
			"backend_type": "faiss",
			"knowledge_source": self.knowledge_source,
			"initialized": self._initialized,
			"index_path": self._index_path,
			"dimension": self._dimension,
		}
		
		# Add index file info if available
		if self._index_path and os.path.exists(self._index_path):
			stats["index_file_size_bytes"] = os.path.getsize(self._index_path)
			stats["index_exists"] = True
		else:
			stats["index_exists"] = False
		
		# Add FAISS index stats if loaded
		if self.vector_store and hasattr(self.vector_store, '_faiss_index'):
			faiss_index = self.vector_store._faiss_index
			if faiss_index is not None:
				stats["faiss_ntotal"] = faiss_index.ntotal
		
		return stats
	
	def health_check(self) -> Tuple[bool, str]:
		"""Check backend health."""
		try:
			if not self._initialized:
				return (False, "Backend not initialized")
			
			if self.vector_store is None:
				return (False, "Vector store not created")
			
			# Try a simple search to verify index is working
			self.search("health_check", top_k=1)
			
			return (True, "Healthy")
		except Exception as e:
			return (False, str(e))
	
	def supports_filters(self) -> bool:
		"""FAISS doesn't support metadata filtering in basic usage."""
		return False
	
	def supports_hybrid_search(self) -> bool:
		"""FAISS doesn't support hybrid search natively."""
		return False


# Register backend
BackendFactory.register("faiss", FAISSBackend)
