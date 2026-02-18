"""
LlamaIndex-compatible VectorStore adapter for Zvec.

Wraps ZvecBackend as a LlamaIndex BasePydanticVectorStore, enabling
Zvec collections to be used in standard LlamaIndex index/query pipelines.

This is an optional integration layer — the primary path for Huf's
knowledge system is through the KnowledgeBackend ABC.
"""

from typing import Any, List, Optional, Dict

try:
	from llama_index.core.vector_stores.types import (
		BasePydanticVectorStore,
		VectorStoreQuery,
		VectorStoreQueryResult,
	)
	from llama_index.core.schema import BaseNode, TextNode
	from pydantic import ConfigDict

	LLAMAINDEX_AVAILABLE = True
except ImportError:
	LLAMAINDEX_AVAILABLE = False


def _check_llamaindex():
	if not LLAMAINDEX_AVAILABLE:
		raise ImportError(
			"llama-index-core is required for the LlamaIndex VectorStore adapter. "
			"Install it with: pip install llama-index-core"
		)


if LLAMAINDEX_AVAILABLE:

	class ZvecVectorStore(BasePydanticVectorStore):
		"""
		LlamaIndex VectorStore backed by Zvec.

		Usage:
			vector_store = ZvecVectorStore(
				db_path="/path/to/collection.zvec",
				dimension=1536,
				collection_name="my_knowledge",
			)
			index = VectorStoreIndex.from_vector_store(vector_store)
		"""

		model_config = ConfigDict(arbitrary_types_allowed=True)

		db_path: str
		dimension: int = 1536
		collection_name: str = "knowledge"
		vector_field: str = "embedding"

		_collection: Any = None

		def __init__(self, **kwargs):
			super().__init__(**kwargs)
			self._init_collection()

		def _init_collection(self):
			"""Initialize or open the zvec collection."""
			import zvec
			import os

			field_schemas = [
				zvec.FieldSchema("text", zvec.DataType.STRING),
				zvec.FieldSchema("ref_doc_id", zvec.DataType.STRING),
				zvec.FieldSchema("metadata_json", zvec.DataType.STRING),
			]

			vector_schema = zvec.VectorSchema(
				self.vector_field,
				zvec.DataType.VECTOR_FP32,
				self.dimension,
			)

			schema = zvec.CollectionSchema(
				name=self.collection_name,
				fields=field_schemas,
				vectors=vector_schema,
			)

			try:
				self._collection = zvec.create_and_open(path=self.db_path, schema=schema)
			except (RuntimeError, Exception):
				self._collection = zvec.open(self.db_path)

		@property
		def client(self) -> Any:
			"""Return the underlying zvec collection."""
			return self._collection

		def add(self, nodes: List[BaseNode], **kwargs: Any) -> List[str]:
			"""
			Add nodes to the vector store.

			Each node must have an embedding already set.
			"""
			import zvec
			import json

			docs = []
			ids = []

			for node in nodes:
				node_id = node.node_id
				embedding = node.get_embedding()
				text = node.get_content()
				metadata = node.metadata or {}
				ref_doc_id = node.ref_doc_id or ""

				doc = zvec.Doc(
					id=node_id,
					vectors={self.vector_field: embedding},
					fields={
						"text": text,
						"ref_doc_id": ref_doc_id,
						"metadata_json": json.dumps(metadata),
					},
				)
				docs.append(doc)
				ids.append(node_id)

			if docs:
				self._collection.upsert(docs)

			return ids

		def delete(self, ref_doc_id: str, **delete_kwargs: Any) -> None:
			"""Delete all nodes associated with a reference document ID."""
			self._collection.delete_by_filter(
				filter=f"ref_doc_id == '{ref_doc_id}'"
			)

		def query(
			self,
			query: VectorStoreQuery,
			**kwargs: Any,
		) -> VectorStoreQueryResult:
			"""
			Query the vector store with a VectorStoreQuery.

			Uses the query embedding to perform similarity search.
			"""
			import zvec
			import json

			if query.query_embedding is None:
				return VectorStoreQueryResult(nodes=[], similarities=[], ids=[])

			vector_query = zvec.VectorQuery(
				field_name=self.vector_field,
				vector=query.query_embedding,
			)

			topk = query.similarity_top_k or 5

			results = self._collection.query(
				vectors=vector_query,
				topk=topk,
				output_fields=["text", "ref_doc_id", "metadata_json"],
			)

			nodes = []
			similarities = []
			ids = []

			for doc in results:
				metadata = {}
				metadata_json = doc.fields.get("metadata_json", "{}")
				if metadata_json:
					try:
						metadata = json.loads(metadata_json)
					except (json.JSONDecodeError, TypeError):
						pass

				node = TextNode(
					id_=doc.id,
					text=doc.fields.get("text", ""),
					metadata=metadata,
				)
				nodes.append(node)
				similarities.append(doc.score if hasattr(doc, "score") else 0.0)
				ids.append(doc.id)

			return VectorStoreQueryResult(
				nodes=nodes,
				similarities=similarities,
				ids=ids,
			)

		def get_nodes(
			self,
			node_ids: Optional[List[str]] = None,
			filters: Optional[Any] = None,
		) -> List[BaseNode]:
			"""Retrieve nodes by ID. Limited implementation."""
			# Zvec doesn't support direct ID-based fetching easily,
			# so we return empty for now. Full implementation would need
			# per-ID vector queries or a separate lookup table.
			return []
