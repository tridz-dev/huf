# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""PostgreSQL/PGVector backend for HUF knowledge storage."""

import json
import re
import uuid
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

import frappe
from frappe import _

from . import ChunkResult, KnowledgeBackend

try:
	import psycopg
	from psycopg import sql
	PSYCOPG_AVAILABLE = True
except ImportError:
	PSYCOPG_AVAILABLE = False


VALID_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DISTANCE_OPERATORS = {
	"cosine": "<=>",
	"l2": "<->",
	"inner_product": "<#>",
}


class PGVectorBackend(KnowledgeBackend):
	"""PostgreSQL backend using the pgvector extension for semantic search."""

	def __init__(self):
		self.knowledge_source = None
		self.config = {}
		self.table_name = "huf_knowledge_vectors"
		self.dimension = 1536
		self.distance_metric = "cosine"
		self.connection_mode = "External PostgreSQL"
		self._initialized = False

	def initialize(self, knowledge_source: str, config: Dict[str, Any]) -> None:
		if not PSYCOPG_AVAILABLE:
			frappe.throw(
				_("psycopg is required for pgvector knowledge sources. "
				  "Install it with: pip install psycopg[binary]")
			)

		self.knowledge_source = knowledge_source
		self.config = config or {}
		self.table_name = self.config.get("table_name") or "huf_knowledge_vectors"
		self.dimension = int(self.config.get("vector_dimension") or 1536)
		self.distance_metric = self.config.get("distance_metric") or "cosine"
		self.connection_mode = self.config.get("connection_mode") or "External PostgreSQL"

		self._validate_config()
		self._ensure_schema()
		self._initialized = True

	def _validate_config(self) -> None:
		if not VALID_IDENTIFIER.match(self.table_name):
			frappe.throw(_("PGVector table name must be a valid PostgreSQL identifier"))

		if self.distance_metric not in DISTANCE_OPERATORS:
			frappe.throw(_("Unsupported PGVector distance metric: {0}").format(self.distance_metric))

		if self.dimension <= 0:
			frappe.throw(_("PGVector vector dimension must be positive"))

	@contextmanager
	def _get_connection(self):
		conn = psycopg.connect(**self._get_connection_params())
		try:
			yield conn
			conn.commit()
		except Exception:
			conn.rollback()
			raise
		finally:
			conn.close()

	def _get_connection_params(self) -> Dict[str, Any]:
		if self.connection_mode == "Site PostgreSQL":
			if frappe.conf.db_type != "postgres":
				frappe.throw(
					_("Site PostgreSQL mode requires a PostgreSQL-backed Frappe site. "
					  "Use External PostgreSQL for MariaDB-backed sites.")
				)
			return {
				"host": frappe.conf.db_host or "localhost",
				"port": int(frappe.conf.db_port or 5432),
				"dbname": frappe.conf.db_name,
				"user": frappe.conf.db_user,
				"password": frappe.conf.db_password,
			}

		params = {
			"host": self.config.get("host") or "localhost",
			"port": int(self.config.get("port") or 5432),
			"dbname": self.config.get("database"),
			"user": self.config.get("user"),
			"password": self.config.get("password"),
		}
		sslmode = self.config.get("sslmode")
		if sslmode:
			params["sslmode"] = sslmode
		return params

	def _ensure_schema(self) -> None:
		with self._get_connection() as conn:
			with conn.cursor() as cursor:
				cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
				cursor.execute(
					sql.SQL(
						"""
						CREATE TABLE IF NOT EXISTS {table} (
							id BIGSERIAL PRIMARY KEY,
							site_name TEXT NOT NULL,
							knowledge_source TEXT NOT NULL,
							input_id TEXT NOT NULL,
							input_type TEXT NOT NULL,
							chunk_id TEXT NOT NULL UNIQUE,
							source_title TEXT,
							chunk_index INTEGER,
							text TEXT NOT NULL,
							char_start INTEGER,
							char_end INTEGER,
							metadata JSONB DEFAULT '{{}}'::jsonb,
							embedding VECTOR({dimension}) NOT NULL,
							created_at TIMESTAMPTZ DEFAULT now(),
							updated_at TIMESTAMPTZ DEFAULT now()
						)
						"""
					).format(
						table=sql.Identifier(self.table_name),
						dimension=sql.SQL(str(self.dimension)),
					)
				)
				cursor.execute(
					sql.SQL(
						"CREATE INDEX IF NOT EXISTS {index} ON {table} (site_name, knowledge_source)"
					).format(
						index=sql.Identifier(f"idx_{self.table_name}_source"),
						table=sql.Identifier(self.table_name),
					)
				)
				cursor.execute(
					sql.SQL(
						"CREATE INDEX IF NOT EXISTS {index} ON {table} (site_name, knowledge_source, input_id)"
					).format(
						index=sql.Identifier(f"idx_{self.table_name}_input"),
						table=sql.Identifier(self.table_name),
					)
				)
				cursor.execute(
					sql.SQL(
						"CREATE INDEX IF NOT EXISTS {index} ON {table} USING GIN (metadata)"
					).format(
						index=sql.Identifier(f"idx_{self.table_name}_metadata"),
						table=sql.Identifier(self.table_name),
					)
				)

	def add_chunks(self, chunks: List[Dict[str, Any]]) -> int:
		if not chunks:
			return 0

		from huf.ai.knowledge.embedding import get_embeddings, resolve_embedding_config

		texts = [chunk["text"] for chunk in chunks]
		embed_config = resolve_embedding_config(self.knowledge_source)
		embeddings = get_embeddings(
			texts=texts,
			model=embed_config["model"],
			api_key=embed_config.get("api_key"),
			api_base=embed_config.get("api_base"),
		)

		with self._get_connection() as conn:
			with conn.cursor() as cursor:
				for chunk, embedding in zip(chunks, embeddings):
					chunk_id = chunk.get("chunk_id") or str(uuid.uuid4())
					metadata = json.dumps(chunk.get("metadata") or {})
					cursor.execute(
						sql.SQL(
							"""
							INSERT INTO {table}
							(site_name, knowledge_source, input_id, input_type, chunk_id, source_title,
							 chunk_index, text, char_start, char_end, metadata, embedding, updated_at)
							VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::vector, now())
							ON CONFLICT (chunk_id) DO UPDATE SET
								site_name = EXCLUDED.site_name,
								knowledge_source = EXCLUDED.knowledge_source,
								input_id = EXCLUDED.input_id,
								input_type = EXCLUDED.input_type,
								source_title = EXCLUDED.source_title,
								chunk_index = EXCLUDED.chunk_index,
								text = EXCLUDED.text,
								char_start = EXCLUDED.char_start,
								char_end = EXCLUDED.char_end,
								metadata = EXCLUDED.metadata,
								embedding = EXCLUDED.embedding,
								updated_at = now()
							"""
						).format(table=sql.Identifier(self.table_name)),
						(
							frappe.local.site,
							self.knowledge_source,
							chunk["input_id"],
							chunk["input_type"],
							chunk_id,
							chunk.get("source_title"),
							chunk.get("chunk_index"),
							chunk["text"],
							chunk.get("char_start"),
							chunk.get("char_end"),
							metadata,
							self._format_vector(embedding),
						),
					)
		return len(chunks)

	def delete_chunks(self, input_id: str) -> int:
		with self._get_connection() as conn:
			with conn.cursor() as cursor:
				cursor.execute(
					sql.SQL(
						"DELETE FROM {table} WHERE site_name = %s AND knowledge_source = %s AND input_id = %s"
					).format(table=sql.Identifier(self.table_name)),
					(frappe.local.site, self.knowledge_source, input_id),
				)
				return cursor.rowcount or 0

	def search(
		self,
		query: str,
		top_k: int = 5,
		filters: Optional[Dict[str, Any]] = None,
	) -> List[ChunkResult]:
		if not query or not query.strip():
			return []

		from huf.ai.knowledge.embedding import get_embedding, resolve_embedding_config

		embed_config = resolve_embedding_config(self.knowledge_source)
		query_embedding = get_embedding(
			text=query,
			model=embed_config["model"],
			api_key=embed_config.get("api_key"),
			api_base=embed_config.get("api_base"),
		)

		where_parts = [sql.SQL("site_name = %s"), sql.SQL("knowledge_source = %s")]
		params: List[Any] = [frappe.local.site, self.knowledge_source]
		if filters:
			for key, value in filters.items():
				where_parts.append(sql.SQL("metadata ->> %s = %s"))
				params.extend([key, str(value)])

		operator = sql.SQL(DISTANCE_OPERATORS[self.distance_metric])
		vector_text = self._format_vector(query_embedding)
		params.extend([vector_text, vector_text, int(top_k)])

		with self._get_connection() as conn:
			with conn.cursor() as cursor:
				cursor.execute(
					sql.SQL(
						"""
						SELECT chunk_id, text, source_title, input_id, metadata,
						       embedding {operator} %s::vector AS distance
						FROM {table}
						WHERE {where_sql}
						ORDER BY embedding {operator} %s::vector
						LIMIT %s
						"""
					).format(
						table=sql.Identifier(self.table_name),
						operator=operator,
						where_sql=sql.SQL(" AND ").join(where_parts),
					),
					params,
				)
				results = []
				for row in cursor.fetchall():
					chunk_id, text, title, input_id, metadata, distance = row
					results.append(
						ChunkResult(
							chunk_id=chunk_id,
							text=text,
							title=title,
							score=self._distance_to_score(distance),
							source=input_id,
							metadata=metadata or {},
						)
					)
				return results

	def clear(self) -> None:
		with self._get_connection() as conn:
			with conn.cursor() as cursor:
				cursor.execute(
					sql.SQL("DELETE FROM {table} WHERE site_name = %s AND knowledge_source = %s").format(
						table=sql.Identifier(self.table_name)
					),
					(frappe.local.site, self.knowledge_source),
				)

	def get_stats(self) -> Dict[str, Any]:
		stats = {
			"backend_type": "pgvector",
			"knowledge_source": self.knowledge_source,
			"table_name": self.table_name,
			"chunk_count": 0,
			"input_count": 0,
			"vector_dimension": self.dimension,
			"distance_metric": self.distance_metric,
		}
		with self._get_connection() as conn:
			with conn.cursor() as cursor:
				cursor.execute(
					sql.SQL(
						"""
						SELECT COUNT(*), COUNT(DISTINCT input_id)
						FROM {table}
						WHERE site_name = %s AND knowledge_source = %s
						"""
					).format(table=sql.Identifier(self.table_name)),
					(frappe.local.site, self.knowledge_source),
				)
				chunk_count, input_count = cursor.fetchone()
				stats["chunk_count"] = chunk_count or 0
				stats["input_count"] = input_count or 0
		return stats

	def health_check(self):
		try:
			with self._get_connection() as conn:
				with conn.cursor() as cursor:
					cursor.execute("SELECT 1")
			return (True, "Healthy")
		except Exception as exc:
			return (False, str(exc))

	def supports_filters(self) -> bool:
		return True

	def supports_hybrid_search(self) -> bool:
		return False

	def _format_vector(self, embedding: List[float]) -> str:
		if len(embedding) != self.dimension:
			frappe.throw(
				_("Embedding dimension mismatch. Expected {0}, got {1}").format(
					self.dimension, len(embedding)
				)
			)
		return "[" + ",".join(str(float(value)) for value in embedding) + "]"

	def _distance_to_score(self, distance) -> float:
		if distance is None:
			return 0.0
		distance = float(distance)
		if self.distance_metric == "cosine":
			return max(0.0, 1.0 - distance)
		return 1.0 / (1.0 + abs(distance))
