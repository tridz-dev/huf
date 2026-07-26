"""SQLite FTS5 Backend for Knowledge System."""

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from typing import Any, ClassVar

import frappe
from frappe.utils import get_files_path

from . import ChunkResult, KnowledgeBackend


class SQLiteFTSBackend(KnowledgeBackend):
	"""SQLite FTS5 backend for keyword search."""

	SCHEMA_TEMPLATE = """
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

	CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
		text,
		source_title,
		content='chunks',
		content_rowid='rowid',
		tokenize='{tokenizer}'
	);

	CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
		INSERT INTO chunks_fts(rowid, text, source_title)
		VALUES (new.rowid, new.text, new.source_title);
	END;

	CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
		INSERT INTO chunks_fts(chunks_fts, rowid, text, source_title)
		VALUES ('delete', old.rowid, old.text, old.source_title);
	END;

	CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
		INSERT INTO chunks_fts(chunks_fts, rowid, text, source_title)
		VALUES ('delete', old.rowid, old.text, old.source_title);
		INSERT INTO chunks_fts(rowid, text, source_title)
		VALUES (new.rowid, new.text, new.source_title);
	END;

	CREATE INDEX IF NOT EXISTS idx_chunks_input_id ON chunks(input_id);
	"""

	FTS_TOKENIZERS: ClassVar[list[str]] = [
		"porter unicode61",
		"unicode61",
		"ascii",
		"porter ascii",
		"trigram",
	]
	DEFAULT_FTS_TOKENIZER = "porter unicode61"

	@classmethod
	def get_advanced_config_schema(cls) -> list[dict[str, Any]]:
		"""Return schema for SQLite FTS5 backend advanced configuration."""
		return [
			{
				"key": "fts_tokenizer",
				"label": "FTS Tokenizer",
				"type": "select",
				"default": cls.DEFAULT_FTS_TOKENIZER,
				"options": cls.FTS_TOKENIZERS,
				"help_text": (
					"Tokenizer used by the FTS5 index. 'porter' tokenizers add English stemming "
					"(matches 'run' to 'running'), plain 'unicode61'/'ascii' tokenize without "
					"stemming (ascii also folds accents), and 'trigram' enables substring "
					"matching. Only applies to newly created sources."
				),
			},
			{
				"key": "fts_bm25_text_weight",
				"label": "BM25 Text Weight",
				"type": "number",
				"default": 1.0,
				"min": 0,
				"max": 10,
				"help_text": (
					"BM25 ranking weight applied to matches in the chunk body text. "
					"Raise it to rank chunks more strongly by their main content."
				),
			},
			{
				"key": "fts_bm25_title_weight",
				"label": "BM25 Title Weight",
				"type": "number",
				"default": 0.75,
				"min": 0,
				"max": 10,
				"help_text": (
					"BM25 ranking weight applied to matches in the source title. "
					"Raise it to favor chunks whose source title matches the query."
				),
			},
		]

	@property
	def _schema(self) -> str:
		"""Schema SQL with the configured FTS5 tokenizer.

		The tokenizer is validated against FTS_TOKENIZERS (falling back to the
		default) before interpolation, so unvalidated config never reaches SQL.
		Note: FTS5 fixes the tokenizer at virtual-table creation time
		(CREATE VIRTUAL TABLE IF NOT EXISTS), so changing it only affects a
		newly-created source's DB file, not existing ones.
		"""
		tokenizer = self._config.get("fts_tokenizer")
		if tokenizer not in self.FTS_TOKENIZERS:
			tokenizer = self.DEFAULT_FTS_TOKENIZER
		return self.SCHEMA_TEMPLATE.format(tokenizer=tokenizer)

	PRAGMAS: ClassVar[dict[str, Any]] = {
		"journal_mode": "WAL",
		"synchronous": "NORMAL",
		"cache_size": -64000,
		"temp_store": "MEMORY",
	}

	def __init__(self):
		self.knowledge_source = None
		self.db_path = None
		self._config = {}

	def initialize(self, knowledge_source: str, config: dict[str, Any]) -> None:
		"""Initialize SQLite database for knowledge source."""
		self.knowledge_source = knowledge_source
		self._config = config

		# Determine database path
		files_path = get_files_path(is_private=True)
		knowledge_dir = os.path.join(files_path, "knowledge")
		os.makedirs(knowledge_dir, exist_ok=True)

		# Sanitize name for filesystem
		safe_name = frappe.scrub(knowledge_source)
		self.db_path = os.path.join(knowledge_dir, f"{safe_name}.sqlite3")

		# Create database and schema
		with self._get_connection() as conn:
			conn.executescript(self._schema)

	@contextmanager
	def _get_connection(self, readonly: bool = False):
		"""Get SQLite connection with proper settings."""
		mode = "ro" if readonly else "rwc"
		uri = f"file:{self.db_path}?mode={mode}"

		conn = sqlite3.connect(uri, uri=True)
		conn.row_factory = sqlite3.Row

		try:
			# Apply pragmas
			for pragma, value in self.PRAGMAS.items():
				if isinstance(value, str):
					conn.execute(f"PRAGMA {pragma} = '{value}'")
				else:
					conn.execute(f"PRAGMA {pragma} = {value}")

			yield conn

			if not readonly:
				conn.commit()
		except Exception:
			if not readonly:
				conn.rollback()
			raise
		finally:
			conn.close()

	def add_chunks(self, chunks: list[dict[str, Any]]) -> int:
		"""Add chunks to the database."""
		if not chunks:
			return 0

		with self._get_connection() as conn:
			cursor = conn.cursor()

			for chunk in chunks:
				chunk_id = chunk.get("chunk_id") or str(uuid.uuid4())
				metadata = json.dumps(chunk.get("metadata", {}))

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

			return len(chunks)

	def delete_chunks(self, input_id: str) -> int:
		"""Delete all chunks for an input."""
		with self._get_connection() as conn:
			cursor = conn.execute("DELETE FROM chunks WHERE input_id = ?", (input_id,))
			return cursor.rowcount

	def search(self, query: str, top_k: int = 5, filters: dict[str, Any] | None = None) -> list[ChunkResult]:
		"""Search using FTS5 with BM25 ranking."""
		if not query or not query.strip():
			return []

		# Escape special FTS5 characters
		safe_query = self._escape_fts_query(query)

		# BM25 column weights from config, cast to float so they are safe to
		# interpolate as numeric literals (never raw config strings).
		text_weight = float(self._config.get("fts_bm25_text_weight", 1.0))
		title_weight = float(self._config.get("fts_bm25_title_weight", 0.75))

		with self._get_connection(readonly=True) as conn:
			cursor = conn.execute(
				f"""
				SELECT
					c.chunk_id,
					c.text,
					c.source_title,
					c.input_id,
					c.metadata,
					bm25(chunks_fts, {text_weight}, {title_weight}) AS score
				FROM chunks_fts
				JOIN chunks c ON chunks_fts.rowid = c.rowid
				WHERE chunks_fts MATCH ?
				ORDER BY score
				LIMIT ?
			""",
				(safe_query, top_k),
			)

			results = []
			for row in cursor.fetchall():
				metadata = {}
				if row["metadata"]:
					try:
						metadata = json.loads(row["metadata"])
					except json.JSONDecodeError:
						pass

				results.append(
					ChunkResult(
						chunk_id=row["chunk_id"],
						text=row["text"],
						title=row["source_title"],
						score=abs(row["score"]),  # BM25 returns negative scores
						source=row["input_id"],
						metadata=metadata,
					)
				)

			return results

	def _escape_fts_query(self, query: str) -> str:
		"""Escape special characters for FTS5 query."""
		# Remove problematic characters
		special_chars = ['"', "'", "(", ")", "*", ":", "^", "-", "+"]
		result = query
		for char in special_chars:
			result = result.replace(char, " ")

		# Split into terms and wrap in quotes for phrase-like matching
		terms = result.split()
		if len(terms) > 1:
			return " OR ".join(f'"{term}"' for term in terms if term)
		return result

	def clear(self) -> None:
		"""Clear all chunks from the database."""
		with self._get_connection() as conn:
			conn.execute("DELETE FROM chunks")
			conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")

	def get_stats(self) -> dict[str, Any]:
		"""Get database statistics."""
		stats = {
			"chunk_count": 0,
			"input_count": 0,
			"size_bytes": 0,
		}

		if not os.path.exists(self.db_path):
			return stats

		stats["size_bytes"] = os.path.getsize(self.db_path)

		with self._get_connection(readonly=True) as conn:
			cursor = conn.execute("SELECT COUNT(*) FROM chunks")
			stats["chunk_count"] = cursor.fetchone()[0]

			cursor = conn.execute("SELECT COUNT(DISTINCT input_id) FROM chunks")
			stats["input_count"] = cursor.fetchone()[0]

		return stats
