# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""PostgreSQL/PGVector backend using the LlamaIndex adapter."""

import re
import uuid
from typing import Any

import frappe
from frappe import _

from . import ChunkResult, KnowledgeBackend

try:
	from llama_index.core import Document, StorageContext
	from llama_index.core.vector_stores import VectorStoreQuery
	from llama_index.core.vector_stores.types import ExactMatchFilter, MetadataFilters
	from llama_index.vector_stores.postgres import PGVectorStore
	from sqlalchemy import create_engine, text

	LLAMAINDEX_PGVECTOR_AVAILABLE = True
except ImportError:
	LLAMAINDEX_PGVECTOR_AVAILABLE = False


VALID_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class PGVectorBackend(KnowledgeBackend):
	"""PostgreSQL/pgvector backend for HUF knowledge storage.

	This mirrors the Chroma backend pattern: HUF resolves and generates
	embeddings, while LlamaIndex owns the vector-store adapter behavior.
	"""

	PGVECTOR_DISTANCE_TO_OPS = {
		"cosine": "vector_cosine_ops",
		"l2": "vector_l2_ops",
		"inner_product": "vector_ip_ops",
	}

	def __init__(self):
		self.knowledge_source = None
		self.config = {}
		self.table_name = "huf_knowledge_vectors"
		self.dimension = 1536
		self.connection_mode = "External PostgreSQL"
		self.vector_store = None
		self.storage_context = None
		self._initialized = False

	@classmethod
	def get_advanced_config_schema(cls) -> list[dict[str, Any]]:
		return [
			{
				"key": "hnsw_m",
				"label": "HNSW M",
				"type": "number",
				"default": 16,
				"min": 4,
				"max": 200,
				"help_text": "Max connections per node in the HNSW graph. Higher values improve recall at the cost of more memory and slower index builds.",
				"visible_when": {"pgvector_index_type": "hnsw"},
			},
			{
				"key": "hnsw_ef_construction",
				"label": "HNSW EF Construction",
				"type": "number",
				"default": 64,
				"min": 4,
				"max": 1000,
				"help_text": "Size of the dynamic candidate list used during HNSW index construction. Higher values improve index quality at the cost of build time.",
				"visible_when": {"pgvector_index_type": "hnsw"},
			},
			{
				"key": "hnsw_ef_search",
				"label": "HNSW EF Search",
				"type": "number",
				"default": 40,
				"min": 1,
				"max": 1000,
				"help_text": "Size of the dynamic candidate list used during HNSW search. Higher values improve recall at the cost of search speed.",
				"visible_when": {"pgvector_index_type": "hnsw"},
			},
			{
				"key": "hybrid_search",
				"label": "Hybrid Search",
				"type": "boolean",
				"default": False,
				"help_text": "Combine vector similarity with full-text keyword search when supported by the backend.",
			},
		]

	def initialize(self, knowledge_source: str, config: dict[str, Any]) -> None:
		if not LLAMAINDEX_PGVECTOR_AVAILABLE:
			frappe.throw(
				_(
					"llama-index-vector-stores-postgres is required for pgvector knowledge sources. "
					"Install it with: pip install llama-index-vector-stores-postgres"
				)
			)

		self.knowledge_source = knowledge_source
		self.config = config or {}
		self.table_name = self.config.get("table_name") or "huf_knowledge_vectors"
		self.dimension = int(self.config.get("vector_dimension") or 1536)
		self.connection_mode = self.config.get("connection_mode") or "External PostgreSQL"

		self._validate_config()
		self._ensure_pgvector_extension()
		self.vector_store = PGVectorStore.from_params(**self._get_connection_params())
		self.storage_context = StorageContext.from_defaults(vector_store=self.vector_store)
		self._initialized = True

	def _validate_config(self) -> None:
		if not VALID_IDENTIFIER.match(self.table_name):
			frappe.throw(_("PGVector table name must be a valid PostgreSQL identifier"))
		if self.dimension <= 0:
			frappe.throw(_("PGVector vector dimension must be positive"))

	def _get_connection_params(self) -> dict[str, Any]:
		params = {
			"table_name": self.table_name,
			"embed_dim": self.dimension,
			"use_jsonb": True,
			"hybrid_search": bool(self.config.get("hybrid_search")),
		}

		index_type = self.config.get("index_type")
		if index_type == "hnsw":
			hnsw_kwargs = {
				"hnsw_m": int(self.config.get("hnsw_m") or 16),
				"hnsw_ef_construction": int(self.config.get("hnsw_ef_construction") or 64),
				"hnsw_ef_search": int(self.config.get("hnsw_ef_search") or 40),
			}

			distance_metric = self.config.get("distance_metric") or "cosine"
			hnsw_dist_method = self.PGVECTOR_DISTANCE_TO_OPS.get(distance_metric)
			if hnsw_dist_method:
				hnsw_kwargs["hnsw_dist_method"] = hnsw_dist_method

			params["hnsw_kwargs"] = hnsw_kwargs

		params.update(self._get_database_params())
		# PGVectorStore.from_params does not accept sslmode; it is handled via
		# the SQLAlchemy URL used for direct pgvector-extension checks.
		params.pop("sslmode", None)
		return params

	def _get_database_params(self) -> dict[str, Any]:
		if self.connection_mode == "Site PostgreSQL":
			if frappe.conf.db_type != "postgres":
				frappe.throw(
					_(
						"Site PostgreSQL mode requires a PostgreSQL-backed Frappe site. "
						"Use External PostgreSQL for MariaDB-backed sites."
					)
				)
			return {
				"host": frappe.conf.db_host or "localhost",
				"port": int(frappe.conf.db_port or 5432),
				"database": frappe.conf.db_name,
				"user": frappe.conf.db_user,
				"password": frappe.conf.db_password,
			}

		params = {
			"host": self.config.get("host") or "localhost",
			"port": int(self.config.get("port") or 5432),
			"database": self.config.get("database"),
			"user": self.config.get("user"),
			"password": self.config.get("password"),
		}
		sslmode = self.config.get("sslmode")
		if sslmode:
			params["sslmode"] = sslmode
		return params

	def _get_sqlalchemy_url(self) -> str:
		params = self._get_database_params()
		sslmode = params.get("sslmode")
		url = (
			f"postgresql+psycopg://{params.get('user')}:{params.get('password') or ''}"
			f"@{params.get('host')}:{params.get('port')}/{params.get('database')}"
		)
		if sslmode:
			url += f"?sslmode={sslmode}"
		return url

	def _get_sql_table_name(self) -> str:
		return f"data_{self.table_name}"

	def _ensure_pgvector_extension(self) -> None:
		try:
			engine = create_engine(self._get_sqlalchemy_url())
			with engine.begin() as conn:
				conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
		except Exception as exc:
			frappe.throw(
				_(
					"Unable to ensure PostgreSQL pgvector extension. "
					"Create it manually with `CREATE EXTENSION IF NOT EXISTS vector;` "
					"or grant the database user permission. Error: {0}"
				).format(str(exc))
			)

	def _count_by_filters(
		self, extra_where: str = "", params: dict[str, Any] | None = None
	) -> tuple[int, int]:
		params = params or {}
		query = f"""
			SELECT COUNT(*) AS chunk_count,
			       COUNT(DISTINCT metadata_->>'input_id') AS input_count
			FROM {self._get_sql_table_name()}
			WHERE metadata_->>'site_name' = :site_name
			  AND metadata_->>'knowledge_source' = :knowledge_source
			  {extra_where}
		"""
		try:
			engine = create_engine(self._get_sqlalchemy_url())
			with engine.begin() as conn:
				row = conn.execute(
					text(query),
					{
						"site_name": frappe.local.site,
						"knowledge_source": self.knowledge_source,
						**params,
					},
				).fetchone()
				return (int(row[0] or 0), int(row[1] or 0))
		except Exception as exc:
			frappe.logger().warning(f"PGVector count failed for {self.knowledge_source}: {exc!s}")
			return (0, 0)

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
					metadata={
						"site_name": frappe.local.site,
						"knowledge_source": self.knowledge_source,
						"input_id": chunk["input_id"],
						"input_type": chunk["input_type"],
						"chunk_id": chunk_id,
						"source_title": chunk.get("source_title"),
						"chunk_index": chunk.get("chunk_index"),
						"char_start": chunk.get("char_start"),
						"char_end": chunk.get("char_end"),
						**(chunk.get("metadata") or {}),
					},
				)
			)

		if documents:
			self.vector_store.add(documents)

		return len(chunks)

	def delete_chunks(self, input_id: str) -> int:
		if not self._initialized:
			raise RuntimeError("Backend not initialized. Call initialize() first.")

		count_before, _ = self._count_by_filters(
			extra_where="AND metadata_->>'input_id' = :input_id",
			params={"input_id": input_id},
		)
		filters = MetadataFilters(
			filters=[
				ExactMatchFilter(key="site_name", value=frappe.local.site),
				ExactMatchFilter(key="knowledge_source", value=self.knowledge_source),
				ExactMatchFilter(key="input_id", value=input_id),
			]
		)
		try:
			self.vector_store.delete_nodes(filters=filters)
		except Exception as exc:
			frappe.logger().warning(f"PGVector delete_chunks error for {input_id}: {exc!s}")
			return 0
		return count_before

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

		llama_filters = [
			ExactMatchFilter(key="site_name", value=frappe.local.site),
			ExactMatchFilter(key="knowledge_source", value=self.knowledge_source),
		]
		if filters:
			llama_filters.extend(ExactMatchFilter(key=key, value=value) for key, value in filters.items())

		query_obj = VectorStoreQuery(
			query_embedding=query_embedding,
			similarity_top_k=top_k,
			mode="default",
			filters=MetadataFilters(filters=llama_filters),
		)
		result = self.vector_store.query(query_obj)

		results = []
		if result.nodes:
			for index, node in enumerate(result.nodes):
				score = 0.0
				if result.similarities and index < len(result.similarities):
					score = float(result.similarities[index])

				metadata = dict(node.metadata or {})
				results.append(
					ChunkResult(
						chunk_id=metadata.get("chunk_id", node.id_ or ""),
						text=node.text,
						title=metadata.get("source_title"),
						score=score,
						source=metadata.get("input_id"),
						metadata={
							k: v
							for k, v in metadata.items()
							if k not in ["chunk_id", "source_title", "knowledge_source", "site_name"]
						},
					)
				)

		return results

	def clear(self) -> None:
		if not self._initialized:
			raise RuntimeError("Backend not initialized. Call initialize() first.")

		filters = MetadataFilters(
			filters=[
				ExactMatchFilter(key="site_name", value=frappe.local.site),
				ExactMatchFilter(key="knowledge_source", value=self.knowledge_source),
			]
		)
		try:
			self.vector_store.delete_nodes(filters=filters)
		except Exception as exc:
			frappe.logger().warning(f"PGVector clear error for {self.knowledge_source}: {exc!s}")
			raise

	def get_stats(self) -> dict[str, Any]:
		chunk_count, input_count = self._count_by_filters()
		return {
			"backend_type": "pgvector",
			"knowledge_source": self.knowledge_source,
			"table_name": self.table_name,
			"initialized": self._initialized,
			"vector_dimension": self.dimension,
			"chunk_count": chunk_count,
			"input_count": input_count,
			"size_bytes": 0,
		}

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
		return bool(self.config.get("hybrid_search"))
