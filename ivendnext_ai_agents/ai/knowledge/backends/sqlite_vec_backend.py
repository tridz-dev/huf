"""SQLite-vec backend for semantic vector search."""

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

import frappe
from frappe import _
from frappe.utils import get_files_path

from . import ChunkResult, KnowledgeBackend


def check_sqlite_vec_available() -> bool:
	"""Check if sqlite-vec extension can be loaded (pysqlite3 or Python with loadable extensions)."""
	try:
		import sqlite_vec  # type: ignore

		conn = sqlite3.connect(":memory:")
		if not hasattr(conn, "enable_load_extension"):
			conn.close()
			return False
		conn.enable_load_extension(True)
		conn.load_extension(sqlite_vec.loadable_path())
		conn.close()
		return True
	except Exception:
		return False


class SQLiteVecBackend(KnowledgeBackend):
	"""SQLite backend using sqlite-vec extension for vector similarity search."""

	SCHEMA = """
	CREATE TABLE IF NOT EXISTS chunks (
		chunk_id TEXT PRIMARY KEY,
		input_id TEXT NOT NULL,
		input_type TEXT NOT NULL,
		source_title TEXT,
		chunk_index INTEGER NOT NULL,
		text TEXT NOT NULL,
		char_start INTEGER,
		char_end INTEGER,
		metadata TEXT,
		created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
	);

	CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(
		embedding FLOAT[{dimension}]
	);

	CREATE INDEX IF NOT EXISTS idx_chunks_input_id ON chunks(input_id);
	"""

	PRAGMAS = {
		"journal_mode": "WAL",
		"synchronous": "NORMAL",
		"cache_size": -64000,
		"temp_store": "MEMORY",
	}

	def __init__(self):
		self.knowledge_source = None
		self.db_path = None
		self.dimension = 1536
		self._config = {}

	def initialize(self, knowledge_source: str, config: Dict[str, Any]) -> None:
		self.knowledge_source = knowledge_source
		self._config = config
		self.dimension = int(config.get("vector_dimension") or 1536)

		files_path = get_files_path(is_private=True)
		knowledge_dir = os.path.join(files_path, "knowledge")
		os.makedirs(knowledge_dir, exist_ok=True)

		safe_name = frappe.scrub(knowledge_source)
		self.db_path = os.path.join(knowledge_dir, f"{safe_name}.sqlite3")

		with self._get_connection() as conn:
			conn.executescript(self.SCHEMA.format(dimension=self.dimension))

	@contextmanager
	def _get_connection(self, readonly: bool = False):
		mode = "ro" if readonly else "rwc"
		uri = f"file:{self.db_path}?mode={mode}"
		conn = sqlite3.connect(uri, uri=True)
		conn.row_factory = sqlite3.Row

		try:
			for pragma, value in self.PRAGMAS.items():
				if isinstance(value, str):
					conn.execute(f"PRAGMA {pragma} = '{value}'")
				else:
					conn.execute(f"PRAGMA {pragma} = {value}")

			self._load_sqlite_vec(conn)
			yield conn

			if not readonly:
				conn.commit()
		except Exception:
			if not readonly:
				conn.rollback()
			raise
		finally:
			conn.close()

	def _load_sqlite_vec(self, conn: sqlite3.Connection) -> None:
		"""Load sqlite-vec extension for a connection."""
		try:
			import sqlite_vec  # type: ignore

			sqlite_vec.load(conn)
		except ImportError:
			frappe.throw(
				_("sqlite-vec package is required for sqlite_vec knowledge type. "
				  "Install it with: pip install sqlite-vec pysqlite3-binary")
			)
		except AttributeError as exc:
			if "load_extension" in str(exc) or "enable_load_extension" in str(exc):
				frappe.throw(
					_("Python's sqlite3 module does not support loadable extensions. "
					  "Install pysqlite3-binary: pip install pysqlite3-binary. "
					  "Or use sqlite_fts for keyword search without this requirement.")
				)
			raise
		except Exception as exc:
			frappe.throw(_("Failed to load sqlite-vec extension: {0}").format(exc))

	def add_chunks(self, chunks: List[Dict[str, Any]]) -> int:
		if not chunks:
			return 0

		embedding_model = self._config.get("embedding_model")
		if not embedding_model:
			frappe.throw("Embedding model is required for sqlite_vec backend")

		from ivendnext_ai_agents.ai.knowledge.embedding import get_embeddings, resolve_embedding_config

		texts = [chunk["text"] for chunk in chunks]
		embed_config = resolve_embedding_config(self.knowledge_source)
		embeddings = get_embeddings(
			texts=texts,
			model=embed_config["model"],
			api_key=embed_config.get("api_key"),
			api_base=embed_config.get("api_base"),
		)

		with self._get_connection() as conn:
			cursor = conn.cursor()

			for chunk, embedding in zip(chunks, embeddings):
				chunk_id = chunk.get("chunk_id") or str(uuid.uuid4())
				metadata = json.dumps(chunk.get("metadata", {}))

				existing_row = cursor.execute(
					"SELECT rowid FROM chunks WHERE chunk_id = ?",
					(chunk_id,),
				).fetchone()
				if existing_row:
					cursor.execute("DELETE FROM chunks_vec WHERE rowid = ?", (existing_row["rowid"],))

				cursor.execute(
					"""
					INSERT OR REPLACE INTO chunks
					(chunk_id, input_id, input_type, source_title, chunk_index,
					 text, char_start, char_end, metadata)
					VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
					""",
					(
						chunk_id,
						chunk["input_id"],
						chunk["input_type"],
						chunk.get("source_title"),
						chunk["chunk_index"],
						chunk["text"],
						chunk.get("char_start"),
						chunk.get("char_end"),
						metadata,
					),
				)

				chunk_rowid = cursor.execute(
					"SELECT rowid FROM chunks WHERE chunk_id = ?",
					(chunk_id,),
				).fetchone()["rowid"]
				cursor.execute(
					"INSERT INTO chunks_vec(rowid, embedding) VALUES (?, ?)",
					(chunk_rowid, json.dumps(embedding)),
				)

		return len(chunks)

	def delete_chunks(self, input_id: str) -> int:
		with self._get_connection() as conn:
			rows = conn.execute("SELECT rowid FROM chunks WHERE input_id = ?", (input_id,)).fetchall()
			for row in rows:
				conn.execute("DELETE FROM chunks_vec WHERE rowid = ?", (row["rowid"],))

			cursor = conn.execute("DELETE FROM chunks WHERE input_id = ?", (input_id,))
			return cursor.rowcount

	def search(
		self,
		query: str,
		top_k: int = 5,
		filters: Optional[Dict[str, Any]] = None,
	) -> List[ChunkResult]:
		if not query or not query.strip():
			return []

		from ivendnext_ai_agents.ai.knowledge.embedding import get_embedding, resolve_embedding_config

		embed_config = resolve_embedding_config(self.knowledge_source)
		query_embedding = get_embedding(
			text=query,
			model=embed_config["model"],
			api_key=embed_config.get("api_key"),
			api_base=embed_config.get("api_base"),
		)

		filter_clauses = []
		params: List[Any] = [json.dumps(query_embedding), top_k]

		if filters:
			for key, value in filters.items():
				filter_clauses.append(f"c.{key} = ?")
				params.append(value)

		where_sql = ""
		if filter_clauses:
			where_sql = " AND " + " AND ".join(filter_clauses)

		with self._get_connection(readonly=True) as conn:
			cursor = conn.execute(
				f"""
				SELECT
					c.chunk_id,
					c.text,
					c.source_title,
					c.input_id,
					c.metadata,
					v.distance
				FROM chunks_vec v
				JOIN chunks c ON c.rowid = v.rowid
				WHERE v.embedding MATCH ?
				AND k = ?
				{where_sql}
				ORDER BY v.distance ASC
				""",
				params,
			)

			results = []
			for row in cursor.fetchall():
				metadata = {}
				if row["metadata"]:
					try:
						metadata = json.loads(row["metadata"])
					except json.JSONDecodeError:
						pass

				score = 1.0 / (1.0 + float(row["distance"] or 0.0))
				results.append(
					ChunkResult(
						chunk_id=row["chunk_id"],
						text=row["text"],
						title=row["source_title"],
						score=score,
						source=row["input_id"],
						metadata=metadata,
					)
				)

			return results

	def clear(self) -> None:
		with self._get_connection() as conn:
			conn.execute("DELETE FROM chunks_vec")
			conn.execute("DELETE FROM chunks")

	def get_stats(self) -> Dict[str, Any]:
		stats = {
			"chunk_count": 0,
			"input_count": 0,
			"size_bytes": 0,
		}

		if not self.db_path or not os.path.exists(self.db_path):
			return stats

		stats["size_bytes"] = os.path.getsize(self.db_path)

		with self._get_connection(readonly=True) as conn:
			stats["chunk_count"] = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
			stats["input_count"] = conn.execute("SELECT COUNT(DISTINCT input_id) FROM chunks").fetchone()[0]

		return stats