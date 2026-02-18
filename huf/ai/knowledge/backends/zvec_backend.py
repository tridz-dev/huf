"""
Zvec Vector Database Backend for Knowledge System.

Provides semantic (vector similarity) search using Zvec, an in-process
vector database built on Alibaba's Proxima engine. Stores embeddings
alongside text and metadata as a portable .zvec collection file.
"""

import os
import uuid
from typing import List, Dict, Any, Optional

import frappe
from frappe.utils import get_files_path

from . import KnowledgeBackend, ChunkResult


class ZvecBackend(KnowledgeBackend):
	"""Zvec vector database backend for semantic search."""

	# Default vector field name in the zvec collection
	DEFAULT_VECTOR_FIELD = "embedding"

	# Scalar fields stored alongside each chunk
	SCALAR_FIELDS = [
		("text", str),
		("source_title", str),
		("input_id", str),
		("input_type", str),
		("chunk_index", int),
		("metadata_json", str),
	]

	def __init__(self):
		self.collection = None
		self.knowledge_source = None
		self.db_path = None
		self.vector_field = self.DEFAULT_VECTOR_FIELD
		self.dimension = None
		self._config = {}

	def initialize(self, knowledge_source: str, config: Dict[str, Any]) -> None:
		"""Initialize Zvec collection for knowledge source."""
		import zvec

		self.knowledge_source = knowledge_source
		self._config = config
		self.dimension = config.get("vector_dimension") or 1536
		self.vector_field = self.DEFAULT_VECTOR_FIELD

		# Determine database path
		files_path = get_files_path(is_private=True)
		knowledge_dir = os.path.join(files_path, "knowledge")
		os.makedirs(knowledge_dir, exist_ok=True)

		safe_name = frappe.scrub(knowledge_source)
		self.db_path = os.path.join(knowledge_dir, f"{safe_name}.zvec")

		# Build schema: scalar fields + one dense vector field
		field_schemas = [
			zvec.FieldSchema(name, zvec.DataType.STRING if dtype is str else zvec.DataType.INT64)
			for name, dtype in self.SCALAR_FIELDS
		]

		vector_schema = zvec.VectorSchema(
			self.vector_field,
			zvec.DataType.VECTOR_FP32,
			self.dimension,
		)

		schema = zvec.CollectionSchema(
			name=knowledge_source,
			fields=field_schemas,
			vectors=vector_schema,
		)

		# Create or open collection
		try:
			self.collection = zvec.create_and_open(path=self.db_path, schema=schema)
		except (RuntimeError, Exception):
			# Collection already exists — open it
			self.collection = zvec.open(self.db_path)

	def add_chunks(self, chunks: List[Dict[str, Any]]) -> int:
		"""
		Add chunks to the Zvec collection.

		Generates embeddings for each chunk text and stores them alongside
		the original text and metadata as zvec documents.
		"""
		import zvec
		import json

		if not chunks:
			return 0

		# Get embedding configuration
		embedding_model = self._config.get("embedding_model")
		if not embedding_model:
			frappe.throw("Embedding model is required for zvec backend")

		# Gather texts for batch embedding
		texts = [chunk["text"] for chunk in chunks]

		# Generate embeddings in batch
		from huf.ai.knowledge.embedding import get_embeddings, resolve_embedding_config

		embed_config = resolve_embedding_config(self.knowledge_source)
		vectors = get_embeddings(
			texts=texts,
			model=embed_config["model"],
			api_key=embed_config.get("api_key"),
			api_base=embed_config.get("api_base"),
		)

		# Build zvec documents
		docs = []
		for chunk, vector in zip(chunks, vectors):
			chunk_id = chunk.get("chunk_id") or str(uuid.uuid4())
			metadata = chunk.get("metadata", {})

			doc = zvec.Doc(
				id=chunk_id,
				vectors={self.vector_field: vector},
				fields={
					"text": chunk["text"],
					"source_title": chunk.get("source_title") or "",
					"input_id": chunk["input_id"],
					"input_type": chunk.get("input_type", ""),
					"chunk_index": chunk["chunk_index"],
					"metadata_json": json.dumps(metadata) if metadata else "{}",
				},
			)
			docs.append(doc)

		# Insert documents (use upsert, to handle re-indexing gracefully)
		result = self.collection.upsert(docs)

		# Count successes
		if isinstance(result, list):
			return sum(1 for status in result if status.ok())
		# Single doc result
		return 1 if result.ok() else 0

	def delete_chunks(self, input_id: str) -> int:
		"""Delete all chunks for a given input_id."""
		try:
			self.collection.delete_by_filter(filter=f"input_id == '{input_id}'")
			# delete_by_filter doesn't return count in all zvec versions,
			# so we can't reliably report count
			return 0
		except Exception as e:
			frappe.log_error(
				f"Zvec delete_chunks error for input_id={input_id}",
				str(e),
			)
			return 0

	def search(
		self,
		query: str,
		top_k: int = 5,
		filters: Optional[Dict[str, Any]] = None,
	) -> List[ChunkResult]:
		"""
		Search for relevant chunks using vector similarity.

		Embeds the query text, then performs approximate nearest-neighbor
		search against the stored chunk embeddings.
		"""
		import zvec
		import json

		if not query or not query.strip():
			return []

		# Embed the query
		from huf.ai.knowledge.embedding import get_embedding, resolve_embedding_config

		embed_config = resolve_embedding_config(self.knowledge_source)
		query_vector = get_embedding(
			text=query,
			model=embed_config["model"],
			api_key=embed_config.get("api_key"),
			api_base=embed_config.get("api_base"),
		)

		# Build vector query
		vector_query = zvec.VectorQuery(
			field_name=self.vector_field,
			vector=query_vector,
		)

		# Build optional filter expression
		filter_expr = None
		if filters:
			clauses = []
			for key, value in filters.items():
				if isinstance(value, str):
					clauses.append(f"{key} == '{value}'")
				else:
					clauses.append(f"{key} == {value}")
			filter_expr = " AND ".join(clauses)

		# Execute query
		query_kwargs = {
			"vectors": vector_query,
			"topk": top_k,
			"output_fields": ["text", "source_title", "input_id", "chunk_index", "metadata_json"],
		}
		if filter_expr:
			query_kwargs["filter"] = filter_expr

		results = self.collection.query(**query_kwargs)

		# Convert to ChunkResult objects
		chunk_results = []
		for doc in results:
			metadata = {}
			metadata_json = doc.fields.get("metadata_json", "{}")
			if metadata_json:
				try:
					metadata = json.loads(metadata_json)
				except (json.JSONDecodeError, TypeError):
					pass

			chunk_index = doc.fields.get("chunk_index")
			if chunk_index is not None:
				metadata["chunk_index"] = chunk_index

			chunk_results.append(
				ChunkResult(
					chunk_id=doc.id,
					text=doc.fields.get("text", ""),
					title=doc.fields.get("source_title"),
					score=doc.score if hasattr(doc, "score") else 0.0,
					source=doc.fields.get("input_id"),
					metadata=metadata,
				)
			)

		return chunk_results

	def clear(self) -> None:
		"""Clear all documents from the collection."""
		import zvec

		if self.collection is None:
			return

		# Close current collection, remove files, recreate
		try:
			self.collection.close()
		except Exception:
			pass

		# Remove the zvec directory/file and reinitialize
		import shutil

		if os.path.exists(self.db_path):
			if os.path.isdir(self.db_path):
				shutil.rmtree(self.db_path)
			else:
				os.remove(self.db_path)

		# Reinitialize with same config
		self.initialize(self.knowledge_source, self._config)

	def get_stats(self) -> Dict[str, Any]:
		"""Get collection statistics."""
		stats = {
			"chunk_count": 0,
			"input_count": 0,
			"size_bytes": 0,
		}

		if not self.db_path or not os.path.exists(self.db_path):
			return stats

		# Calculate size (zvec may store data in a directory)
		if os.path.isdir(self.db_path):
			total_size = 0
			for dirpath, _dirnames, filenames in os.walk(self.db_path):
				for f in filenames:
					fp = os.path.join(dirpath, f)
					total_size += os.path.getsize(fp)
			stats["size_bytes"] = total_size
		else:
			stats["size_bytes"] = os.path.getsize(self.db_path)

		# Try to get document count from collection stats
		if self.collection:
			try:
				collection_stats = self.collection.stats()
				stats["chunk_count"] = getattr(collection_stats, "doc_count", 0)
			except Exception:
				pass

		return stats
