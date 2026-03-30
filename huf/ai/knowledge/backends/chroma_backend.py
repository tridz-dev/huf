# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""ChromaDB backend using LlamaIndex adapter."""

from typing import Any, Dict, List, Optional, Tuple

import frappe

from ..backends import ChunkResult, KnowledgeBackend

# LlamaIndex imports - optional dependency
try:
	from llama_index.vector_stores.chroma import ChromaVectorStore
	from llama_index.core import VectorStoreIndex, StorageContext, Document
	import chromadb
	from chromadb.config import Settings
	LLAMAINDEX_AVAILABLE = True
except ImportError:
	LLAMAINDEX_AVAILABLE = False


class ChromaBackend(KnowledgeBackend):
	"""ChromaDB backend for Huf knowledge storage.
	
	Supports both local file-based storage (PersistentClient) and
	remote server mode (HttpClient).
	"""
	
	def __init__(self):
		self.knowledge_source = None
		self.config = {}
		self.client = None
		self.collection = None
		self.vector_store = None
		self.storage_context = None
		self.index = None
		self._initialized = False
	
	def initialize(self, knowledge_source: str, config: Dict[str, Any]) -> None:
		"""Initialize Chroma backend.
		
		Config options:
		- host: Chroma server host (default: localhost)
		- port: Chroma server port (default: 8000)
		- persist_directory: Directory for file-based storage
		- collection_name: Override collection name (default: derived from knowledge_source)
		- vector_dimension: Embedding dimension (default: 1536)
		"""
		if not LLAMAINDEX_AVAILABLE:
			raise ImportError(
				"llama-index-vector-stores-chroma and chromadb not installed. "
				"Install with: pip install llama-index-vector-stores-chroma chromadb"
			)
		
		self.knowledge_source = knowledge_source
		self.config = config
		
		# Determine connection mode: server or persistent
		persist_directory = config.get("persist_directory")
		
		if persist_directory:
			# File-based persistent client
			self.client = chromadb.PersistentClient(
				path=persist_directory,
				settings=Settings(
					anonymized_telemetry=False,
				)
			)
		else:
			# HTTP client for Chroma server
			host = config.get("host", "localhost")
			port = config.get("port", 8000)
			ssl = config.get("ssl", False)
			
			self.client = chromadb.HttpClient(
				host=host,
				port=port,
				ssl=ssl,
				settings=Settings(
					anonymized_telemetry=False,
				)
			)
		
		# Get or create collection
		collection_name = config.get("collection_name") or f"huf_{frappe.scrub(knowledge_source)}"
		self.collection = self.client.get_or_create_collection(
			name=collection_name,
			metadata={"knowledge_source": knowledge_source}
		)
		
		# Create vector store
		self.vector_store = ChromaVectorStore(chroma_collection=self.collection)
		self.storage_context = StorageContext.from_defaults(
			vector_store=self.vector_store
		)
		
		self._initialized = True
	
	def add_chunks(self, chunks: List[Dict[str, Any]]) -> int:
		"""Add chunks to ChromaDB.
		
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
		
		# Convert to LlamaIndex Documents
		documents = []
		for chunk in chunks:
			doc = Document(
				text=chunk["text"],
				id_=chunk.get("chunk_id"),
				metadata={
					"input_id": chunk["input_id"],
					"input_type": chunk["input_type"],
					"chunk_id": chunk.get("chunk_id"),
					"source_title": chunk.get("source_title"),
					"chunk_index": chunk.get("chunk_index"),
					"knowledge_source": self.knowledge_source,
					**(chunk.get("metadata") or {})
				}
			)
			documents.append(doc)
		
		# Add documents to vector store
		for doc in documents:
			self.vector_store.add([doc])
		
		# Update index reference
		self.index = VectorStoreIndex.from_vector_store(
			self.vector_store,
			storage_context=self.storage_context,
		)
		
		return len(chunks)
	
	def search(
		self,
		query: str,
		top_k: int = 5,
		filters: Optional[Dict[str, Any]] = None
	) -> List[ChunkResult]:
		"""Search ChromaDB for relevant chunks.
		
		Args:
			query: Search query text
			top_k: Maximum number of results
			filters: Optional metadata filters (e.g., {"input_type": "document"})
		
		Returns:
			List of ChunkResult objects
		"""
		if not self._initialized:
			raise RuntimeError("Backend not initialized. Call initialize() first.")
		
		# Build/load index
		if not self.index:
			self.index = VectorStoreIndex.from_vector_store(
				self.vector_store,
				storage_context=self.storage_context,
			)
		
		# Create retriever with optional filters
		retriever_kwargs = {"similarity_top_k": top_k}
		
		# Chroma supports metadata filtering through LlamaIndex
		if filters:
			from llama_index.core.vector_stores.types import MetadataFilters, ExactMatchFilter
			llama_filters = [
				ExactMatchFilter(key=key, value=value)
				for key, value in filters.items()
			]
			retriever_kwargs["filters"] = MetadataFilters(filters=llama_filters)
		
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
				score=float(node.score) if hasattr(node, "score") and node.score is not None else 0.0,
				source=node.metadata.get("knowledge_source"),
				metadata={k: v for k, v in node.metadata.items() if k not in [
					"chunk_id", "source_title", "knowledge_source"
				]}
			)
			results.append(result)
		
		return results
	
	def delete_chunks(self, input_id: str) -> int:
		"""Delete all chunks for an input.
		
		Chroma supports deletion by metadata filter.
		
		Args:
			input_id: The input ID to delete chunks for
		
		Returns:
			Number of chunks deleted
		"""
		if not self._initialized or not self.collection:
			raise RuntimeError("Backend not initialized. Call initialize() first.")
		
		try:
			# Get IDs of documents to delete
			results = self.collection.get(
				where={"input_id": input_id},
				include=[]
			)
			
			ids_to_delete = results.get("ids", [])
			
			if ids_to_delete:
				self.collection.delete(ids=ids_to_delete)
			
			return len(ids_to_delete)
		except Exception as e:
			frappe.logger().warning(f"Chroma delete_chunks error for {input_id}: {str(e)}")
			return 0
	
	def clear(self) -> None:
		"""Clear all chunks from the collection."""
		if not self._initialized or not self.collection:
			raise RuntimeError("Backend not initialized. Call initialize() first.")
		
		# Delete all documents in the collection
		try:
			self.collection.delete(where={})
		except Exception:
			# If delete with empty where fails, try to get all IDs and delete
			try:
				results = self.collection.get(include=[])
				ids = results.get("ids", [])
				if ids:
					self.collection.delete(ids=ids)
			except Exception as e:
				frappe.logger().error(f"Chroma clear error: {str(e)}")
				raise
		
		# Reset index
		self.index = None
	
	def get_stats(self) -> Dict[str, Any]:
		"""Get backend statistics.
		
		Returns:
			Dict with backend statistics
		"""
		stats = {
			"backend_type": "chroma",
			"knowledge_source": self.knowledge_source,
			"initialized": self._initialized,
			"host": self.config.get("host", "localhost" if not self.config.get("persist_directory") else None),
			"port": self.config.get("port", 8000 if not self.config.get("persist_directory") else None),
			"persist_directory": self.config.get("persist_directory"),
			"collection_name": self.collection.name if self.collection else None,
			"chunk_count": 0,
		}
		
		if self.collection:
			try:
				# Get count from collection
				count_result = self.collection.count()
				stats["chunk_count"] = count_result
			except Exception as e:
				frappe.logger().warning(f"Chroma get_stats count error: {str(e)}")
		
		return stats
	
	def health_check(self) -> Tuple[bool, str]:
		"""Check backend health.
		
		Returns:
			Tuple of (is_healthy, message)
		"""
		try:
			if not self._initialized:
				return (False, "Backend not initialized")
			
			if not self.client:
				return (False, "Chroma client not available")
			
			# Try to list collections (lightweight operation)
			self.client.list_collections()
			
			return (True, "Healthy")
		except Exception as e:
			return (False, str(e))
	
	def supports_filters(self) -> bool:
		"""Chroma supports metadata filtering."""
		return True
	
	def supports_hybrid_search(self) -> bool:
		"""Chroma does not support built-in hybrid search."""
		return False
