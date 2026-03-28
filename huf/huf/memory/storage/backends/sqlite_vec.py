"""
HUF Memory System - sqlite-vec Backend

Vector search backend using sqlite-vec extension.
"""

from __future__ import annotations

import json
import sqlite3
import struct
from datetime import datetime
from typing import TYPE_CHECKING, Optional

import frappe
from frappe.utils import get_site_path

from ..index_backend import (
    EmbeddingGenerator,
    IndexResult,
    MemoryIndexBackend,
    ScopeFilter,
    SearchResult,
)

if TYPE_CHECKING:
    from ..storage_service import MemoryRecord


class SqliteVecBackend(MemoryIndexBackend):
    """
    Vector search backend using sqlite-vec extension.
    
    This backend provides semantic similarity search over memory records
    using embeddings stored in a sqlite-vec virtual table.
    """
    
    DEFAULT_DIMENSION = 1536  # Default for OpenAI text-embedding-3-small
    
    def __init__(
        self,
        db_path: Optional[str] = None,
        embedding_generator: Optional[EmbeddingGenerator] = None,
        dimension: int = DEFAULT_DIMENSION
    ):
        super().__init__("sqlite_vec")
        self.db_path = db_path or self._get_default_db_path()
        self.table_name = "memory_vec_idx"
        self.embedding_generator = embedding_generator
        self.dimension = dimension
        self._conn: Optional[sqlite3.Connection] = None
    
    def _get_default_db_path(self) -> str:
        """Get the default SQLite database path."""
        site_path = get_site_path()
        return f"{site_path}/memory_vec.db"
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get or create SQLite connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            # Try to load sqlite-vec extension
            self._conn.enable_load_extension(True)
        return self._conn
    
    def _load_vec_extension(self) -> bool:
        """Attempt to load the sqlite-vec extension."""
        try:
            conn = self._get_connection()
            # Try common extension names/paths
            extension_paths = [
                "vec0",
                "libsqlite_vec",
                "sqlite_vec",
                "/usr/lib/sqlite3/vec0",
                "/usr/local/lib/sqlite3/vec0",
            ]
            
            for ext_path in extension_paths:
                try:
                    conn.load_extension(ext_path)
                    return True
                except sqlite3.OperationalError:
                    continue
            
            return False
        except Exception:
            return False
    
    async def initialize(self) -> bool:
        """Initialize the sqlite-vec virtual table."""
        try:
            # Check if extension is available
            if not self._load_vec_extension():
                frappe.log_error("sqlite-vec extension not available")
                return False
            
            conn = self._get_connection()
            
            # Create vec0 virtual table
            conn.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS {self.table_name} USING vec0(
                    record_id TEXT PRIMARY KEY,
                    embedding FLOAT[{self.dimension}]
                )
            """)
            
            # Create metadata table for efficient filtering
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.table_name}_meta (
                    record_id TEXT PRIMARY KEY,
                    scope_type TEXT,
                    scope_key TEXT,
                    memory_type TEXT,
                    agent TEXT,
                    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
            self._initialized = True
            return True
            
        except Exception as e:
            frappe.log_error(f"Vector backend initialization failed: {str(e)}")
            return False
    
    def _get_embedding(self, record: MemoryRecord) -> Optional[list[float]]:
        """
        Get embedding for a record.
        
        Uses the configured embedding generator if available,
        otherwise returns None (record can't be vector-indexed).
        """
        if self.embedding_generator:
            import asyncio
            text = self._get_embedding_text(record)
            try:
                return asyncio.run(self.embedding_generator.generate(text))
            except Exception as e:
                frappe.log_error(f"Embedding generation failed: {str(e)}")
                return None
        
        # Check if record has pre-computed embedding in metadata
        if record.metadata_json and "embedding" in record.metadata_json:
            return record.metadata_json["embedding"]
        
        return None
    
    def _get_embedding_text(self, record: MemoryRecord) -> str:
        """Extract text for embedding from a memory record."""
        if record.summary_text:
            return record.summary_text
        
        if record.data_json:
            return json.dumps(record.data_json, ensure_ascii=False, indent=None)
        
        return record.title
    
    def _serialize_embedding(self, embedding: list[float]) -> bytes:
        """Serialize embedding to bytes for sqlite-vec."""
        return struct.pack(f"{len(embedding)}f", *embedding)
    
    async def index(self, record: MemoryRecord) -> IndexResult:
        """Index a memory record to vector store."""
        try:
            embedding = self._get_embedding(record)
            
            if embedding is None:
                return IndexResult(
                    success=False,
                    record_id=record.name,
                    backend=self.backend_name,
                    indexed_at=datetime.now(),
                    error_message="No embedding available for record"
                )
            
            if len(embedding) != self.dimension:
                return IndexResult(
                    success=False,
                    record_id=record.name,
                    backend=self.backend_name,
                    indexed_at=datetime.now(),
                    error_message=f"Embedding dimension mismatch: {len(embedding)} != {self.dimension}"
                )
            
            conn = self._get_connection()
            
            # Insert into vector table
            conn.execute(f"""
                INSERT OR REPLACE INTO {self.table_name} (record_id, embedding)
                VALUES (?, ?)
            """, (record.name, self._serialize_embedding(embedding)))
            
            # Update metadata table
            conn.execute(f"""
                INSERT OR REPLACE INTO {self.table_name}_meta (
                    record_id, scope_type, scope_key, memory_type, agent, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                record.name,
                record.scope_type.value if record.scope_type else None,
                record.scope_key,
                record.memory_type.value if record.memory_type else None,
                record.agent,
                datetime.now().isoformat()
            ))
            
            conn.commit()
            
            return IndexResult(
                success=True,
                record_id=record.name,
                backend=self.backend_name,
                indexed_at=datetime.now(),
                embedding_dimension=self.dimension
            )
            
        except Exception as e:
            frappe.log_error(f"Vector index failed for {record.name}: {str(e)}")
            return IndexResult(
                success=False,
                record_id=record.name,
                backend=self.backend_name,
                indexed_at=datetime.now(),
                error_message=str(e)
            )
    
    async def search(
        self,
        query: str,
        scope: ScopeFilter,
        limit: int = 10
    ) -> list[SearchResult]:
        """Search using vector similarity."""
        try:
            # Generate query embedding
            if self.embedding_generator is None:
                return []
            
            import asyncio
            query_embedding = asyncio.run(self.embedding_generator.generate(query))
            
            if query_embedding is None:
                return []
            
            conn = self._get_connection()
            
            # Build scope filter conditions
            conditions = []
            params = []
            
            if scope.scope_type:
                conditions.append("m.scope_type = ?")
                params.append(scope.scope_type)
            
            if scope.scope_key:
                conditions.append("m.scope_key = ?")
                params.append(scope.scope_key)
            
            if scope.agent:
                conditions.append("m.agent = ?")
                params.append(scope.agent)
            
            if scope.memory_type:
                conditions.append("m.memory_type = ?")
                params.append(scope.memory_type)
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            # Execute vector similarity search
            # sqlite-vec uses vec_distance_L2 for L2 distance or vec_cosine_distance for cosine
            cursor = conn.execute(f"""
                SELECT 
                    v.record_id,
                    vec_distance_L2(v.embedding, ?) AS distance
                FROM {self.table_name} v
                JOIN {self.table_name}_meta m ON v.record_id = m.record_id
                WHERE {where_clause}
                ORDER BY distance
                LIMIT ?
            """, (self._serialize_embedding(query_embedding), *params, limit))
            
            results = []
            for row in cursor.fetchall():
                # Convert distance to similarity score (inverse, normalized)
                # L2 distance: lower is better, so invert
                distance = row["distance"]
                score = 1.0 / (1.0 + distance)  # Normalize to 0-1
                
                results.append(SearchResult(
                    record_id=row["record_id"],
                    score=score,
                    backend=self.backend_name
                ))
            
            return results
            
        except Exception as e:
            frappe.log_error(f"Vector search failed for query '{query}': {str(e)}")
            return []
    
    async def delete(self, record_id: str) -> bool:
        """Remove a record from the vector index."""
        try:
            conn = self._get_connection()
            
            conn.execute(
                f"DELETE FROM {self.table_name} WHERE record_id = ?",
                (record_id,)
            )
            conn.execute(
                f"DELETE FROM {self.table_name}_meta WHERE record_id = ?",
                (record_id,)
            )
            conn.commit()
            
            return True
            
        except Exception as e:
            frappe.log_error(f"Vector delete failed for {record_id}: {str(e)}")
            return False
    
    async def reindex(self, record: MemoryRecord) -> IndexResult:
        """Reindex a record (delete then insert)."""
        await self.delete(record.name)
        return await self.index(record)
    
    async def clear(self) -> bool:
        """Clear all records from the vector index."""
        try:
            conn = self._get_connection()
            conn.execute(f"DELETE FROM {self.table_name}")
            conn.execute(f"DELETE FROM {self.table_name}_meta")
            conn.commit()
            return True
        except Exception as e:
            frappe.log_error(f"Vector clear failed: {str(e)}")
            return False
    
    async def count(self) -> int:
        """Get the number of indexed records."""
        try:
            conn = self._get_connection()
            cursor = conn.execute(f"SELECT COUNT(*) FROM {self.table_name}")
            return cursor.fetchone()[0]
        except Exception:
            return 0
    
    def is_available(self) -> bool:
        """Check if sqlite-vec extension is available."""
        return self._load_vec_extension()
