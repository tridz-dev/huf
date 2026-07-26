"""SQLite FTS5 Backend for Knowledge System."""

import os
import sqlite3
import json
import uuid
from typing import List, Dict, Any, Optional
from contextlib import contextmanager

import frappe
from frappe.utils import get_files_path

from . import KnowledgeBackend, ChunkResult


class SQLiteFTSBackend(KnowledgeBackend):
	"""SQLite FTS5 backend for keyword search."""
	
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
	
	CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
		text,
		source_title,
		content='chunks',
		content_rowid='rowid',
		tokenize='porter unicode61'
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
	
	PRAGMAS = {
		"journal_mode": "WAL",
		"synchronous": "NORMAL",
		"cache_size": -64000,
		"temp_store": "MEMORY",
	}
	
	def __init__(self):
		self.knowledge_source = None
		self.db_path = None
		self._config = {}
	
	def initialize(self, knowledge_source: str, config: Dict[str, Any]) -> None:
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
			conn.executescript(self.SCHEMA)
	
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
	
	def add_chunks(self, chunks: List[Dict[str, Any]]) -> int:
		"""Add chunks to the database."""
		if not chunks:
			return 0
		
		with self._get_connection() as conn:
			cursor = conn.cursor()
			
			for chunk in chunks:
				chunk_id = chunk.get("chunk_id") or str(uuid.uuid4())
				metadata = json.dumps(chunk.get("metadata", {}))
				
				cursor.execute("""
					INSERT OR REPLACE INTO chunks 
					(chunk_id, input_id, input_type, source_title, chunk_index, 
					 text, char_start, char_end, metadata)
					VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
				""", (
					chunk_id,
					chunk["input_id"],
					chunk["input_type"],
					chunk.get("source_title"),
					chunk["chunk_index"],
					chunk["text"],
					chunk.get("char_start"),
					chunk.get("char_end"),
					metadata,
				))
			
			return len(chunks)
	
	def delete_chunks(self, input_id: str) -> int:
		"""Delete all chunks for an input."""
		with self._get_connection() as conn:
			cursor = conn.execute(
				"DELETE FROM chunks WHERE input_id = ?",
				(input_id,)
			)
			return cursor.rowcount
	
	def search(
		self,
		query: str,
		top_k: int = 5,
		filters: Optional[Dict[str, Any]] = None
	) -> List[ChunkResult]:
		"""Search using FTS5 with BM25 ranking."""
		if not query or not query.strip():
			return []
		
		# Escape special FTS5 characters
		safe_query = self._escape_fts_query(query)
		
		with self._get_connection(readonly=True) as conn:
			cursor = conn.execute("""
				SELECT 
					c.chunk_id,
					c.text,
					c.source_title,
					c.input_id,
					c.metadata,
					bm25(chunks_fts, 1.0, 0.75) AS score
				FROM chunks_fts
				JOIN chunks c ON chunks_fts.rowid = c.rowid
				WHERE chunks_fts MATCH ?
				ORDER BY score
				LIMIT ?
			""", (safe_query, top_k))
			
			results = []
			for row in cursor.fetchall():
				metadata = {}
				if row["metadata"]:
					try:
						metadata = json.loads(row["metadata"])
					except json.JSONDecodeError:
						pass
				
				results.append(ChunkResult(
					chunk_id=row["chunk_id"],
					text=row["text"],
					title=row["source_title"],
					score=abs(row["score"]),  # BM25 returns negative scores
					source=row["input_id"],
					metadata=metadata,
				))
			
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
	
	def get_stats(self) -> Dict[str, Any]:
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
