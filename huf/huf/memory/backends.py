"""
HUF Memory System - Index Backends

Concrete implementations of the MemoryIndexBackend abstraction:
- SQLiteFTSBackend: Full-text search using SQLite FTS5
- SqliteVecBackend: Vector search using sqlite-vec extension
- HybridBackend: Combines multiple backends with RRF fusion
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

import frappe
from frappe.utils import get_site_path

from .indexing import (
    EmbeddingGenerator,
    IndexResult,
    MemoryIndexBackend,
    ScopeFilter,
    SearchResult,
)

if TYPE_CHECKING:
    from .storage import MemoryRecord


# ============================================================================
# SQLite FTS5 Backend
# ============================================================================

class SQLiteFTSBackend(MemoryIndexBackend):
    """
    Full-text search backend using SQLite FTS5 virtual tables.
    
    This backend provides keyword and phrase search over memory records
    using Porter stemming and unicode61 tokenization.
    """
    
    def __init__(self, db_path: Optional[str] = None):
        super().__init__("sqlite_fts")
        self.db_path = db_path or self._get_default_db_path()
        self.table_name = "memory_fts_idx"
        self._conn: Optional[sqlite3.Connection] = None
    
    def _get_default_db_path(self) -> str:
        """Get the default SQLite database path."""
        site_path = get_site_path()
        return f"{site_path}/memory_fts.db"
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get or create SQLite connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            # Enable FTS5
            self._conn.enable_load_extension(True)
            try:
                self._conn.load_extension("fts5")
            except sqlite3.OperationalError:
                # FTS5 might be built-in
                pass
        return self._conn
    
    async def initialize(self) -> bool:
        """Initialize the FTS5 virtual table."""
        try:
            conn = self._get_connection()
            
            # Create FTS5 virtual table (contentless design)
            conn.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS {self.table_name} USING fts5(
                    record_id UNINDEXED,
                    title,
                    summary_text,
                    data_json,
                    tags,
                    scope_type UNINDEXED,
                    scope_key UNINDEXED,
                    memory_type UNINDEXED,
                    agent UNINDEXED,
                    tokenize='porter unicode61'
                )
            """)
            
            # Create auxiliary tables for efficient metadata queries
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
            frappe.log_error(f"FTS backend initialization failed: {str(e)}")
            return False
    
    async def index(self, record: MemoryRecord) -> IndexResult:
        """Index a memory record to FTS5."""
        try:
            conn = self._get_connection()
            
            # Serialize data_json for text search
            data_json_text = json.dumps(record.data_json, ensure_ascii=False) if record.data_json else ""
            tags_text = ",".join(record.tags) if record.tags else ""
            
            # Insert into FTS table
            conn.execute(f"""
                INSERT OR REPLACE INTO {self.table_name} (
                    record_id, title, summary_text, data_json, tags,
                    scope_type, scope_key, memory_type, agent
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.name,
                record.title or "",
                record.summary_text or "",
                data_json_text,
                tags_text,
                record.scope_type.value if record.scope_type else "",
                record.scope_key or "",
                record.memory_type.value if record.memory_type else "",
                record.agent or ""
            ))
            
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
                indexed_at=datetime.now()
            )
            
        except Exception as e:
            frappe.log_error(f"FTS index failed for {record.name}: {str(e)}")
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
        """Search using FTS5 match syntax."""
        try:
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
            
            # Execute FTS query with snippet generation
            cursor = conn.execute(f"""
                SELECT 
                    f.record_id,
                    f.title,
                    f.summary_text,
                    f.tags,
                    rank AS score,
                    snippet({self.table_name}, 2, '<mark>', '</mark>', '...', 32) AS snippet
                FROM {self.table_name} f
                JOIN {self.table_name}_meta m ON f.record_id = m.record_id
                WHERE {self.table_name} MATCH ? AND {where_clause}
                ORDER BY rank
                LIMIT ?
            """, (query, *params, limit))
            
            results = []
            for row in cursor.fetchall():
                results.append(SearchResult(
                    record_id=row["record_id"],
                    score=row["score"],
                    backend=self.backend_name,
                    matched_fields=self._extract_matched_fields(row),
                    snippet=row["snippet"]
                ))
            
            return results
            
        except Exception as e:
            frappe.log_error(f"FTS search failed for query '{query}': {str(e)}")
            return []
    
    def _extract_matched_fields(self, row: sqlite3.Row) -> list[str]:
        """Determine which fields matched based on content."""
        fields = []
        # This is a simplified version - in practice, you'd use FTS5 aux functions
        # to determine which columns matched
        if row["title"]:
            fields.append("title")
        if row["summary_text"]:
            fields.append("summary_text")
        if row["tags"]:
            fields.append("tags")
        return fields
    
    async def delete(self, record_id: str) -> bool:
        """Remove a record from the FTS index."""
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
            frappe.log_error(f"FTS delete failed for {record_id}: {str(e)}")
            return False
    
    async def reindex(self, record: MemoryRecord) -> IndexResult:
        """Reindex a record (delete then insert)."""
        await self.delete(record.name)
        return await self.index(record)
    
    async def clear(self) -> bool:
        """Clear all records from the FTS index."""
        try:
            conn = self._get_connection()
            conn.execute(f"DELETE FROM {self.table_name}")
            conn.execute(f"DELETE FROM {self.table_name}_meta")
            conn.commit()
            return True
        except Exception as e:
            frappe.log_error(f"FTS clear failed: {str(e)}")
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
        """Check if FTS5 is available."""
        try:
            conn = self._get_connection()
            cursor = conn.execute("SELECT sqlite_compileoption_used('ENABLE_FTS5')")
            result = cursor.fetchone()[0]
            return result == 1 or self._initialized
        except Exception:
            return False


# ============================================================================
# SQLite-vec Backend
# ============================================================================

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
        import struct
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


# ============================================================================
# Hybrid Backend
# ============================================================================

class HybridBackend(MemoryIndexBackend):
    """
    Hybrid backend that combines results from multiple backends using RRF.
    
    This backend wraps multiple index backends and provides unified search
    with Reciprocal Rank Fusion for combining results.
    """
    
    def __init__(
        self,
        backends: list[MemoryIndexBackend],
        rrf_k: int = 60,
        weights: Optional[dict[str, float]] = None
    ):
        super().__init__("hybrid")
        self.backends = backends
        self.rrf_k = rrf_k
        self.weights = weights or {}
        
        # Default equal weights for unweighted backends
        default_weight = 1.0 / len(backends) if backends else 1.0
        for backend in backends:
            if backend.backend_name not in self.weights:
                self.weights[backend.backend_name] = default_weight
    
    async def initialize(self) -> bool:
        """Initialize all wrapped backends."""
        results = []
        for backend in self.backends:
            results.append(await backend.initialize())
        
        self._initialized = all(results)
        return self._initialized
    
    async def index(self, record: MemoryRecord) -> IndexResult:
        """
        Index a record to all backends.
        
        Returns the first successful result or first failure if all fail.
        """
        results = []
        
        for backend in self.backends:
            try:
                result = await backend.index(record)
                results.append(result)
            except Exception as e:
                results.append(IndexResult(
                    success=False,
                    record_id=record.name,
                    backend=backend.backend_name,
                    indexed_at=datetime.now(),
                    error_message=str(e)
                ))
        
        # Return first success, or first failure if all failed
        for result in results:
            if result.success:
                return result
        
        return results[0] if results else IndexResult(
            success=False,
            record_id=record.name,
            backend=self.backend_name,
            indexed_at=datetime.now(),
            error_message="No backends available"
        )
    
    async def search(
        self,
        query: str,
        scope: ScopeFilter,
        limit: int = 10
    ) -> list[SearchResult]:
        """
        Search across all backends and fuse results using RRF.
        
        Reciprocal Rank Fusion (RRF) formula:
            score = Σ weight_i / (k + rank_i) for each backend i
        """
        all_results: list[list[SearchResult]] = []
        
        # Query all backends
        for backend in self.backends:
            if not backend.is_available():
                continue
            
            try:
                results = await backend.search(query, scope, limit * 2)
                
                # Assign ranks within each backend's results
                for i, result in enumerate(results):
                    result.rank = i + 1
                
                all_results.append(results)
            except Exception as e:
                frappe.log_error(f"Hybrid search failed for {backend.backend_name}: {str(e)}")
        
        # Fuse results using weighted RRF
        return self._fuse_results(all_results, limit)
    
    def _fuse_results(
        self,
        result_lists: list[list[SearchResult]],
        limit: int
    ) -> list[SearchResult]:
        """
        Fuse results from multiple backends using weighted RRF.
        """
        scores: dict[str, float] = {}
        record_map: dict[str, SearchResult] = {}
        
        for results in result_lists:
            for result in results:
                backend_name = result.backend
                weight = self.weights.get(backend_name, 1.0)
                
                if result.record_id not in scores:
                    scores[result.record_id] = 0.0
                    record_map[result.record_id] = result
                
                # Weighted RRF score contribution
                scores[result.record_id] += weight / (self.rrf_k + result.rank)
        
        # Sort by fused score
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        
        # Build final results
        fused_results = []
        for record_id in sorted_ids[:limit]:
            result = record_map[record_id]
            result.score = scores[record_id]
            fused_results.append(result)
        
        return fused_results
    
    async def delete(self, record_id: str) -> bool:
        """Delete a record from all backends."""
        results = []
        
        for backend in self.backends:
            try:
                results.append(await backend.delete(record_id))
            except Exception:
                results.append(False)
        
        return any(results)  # Success if any backend succeeded
    
    async def reindex(self, record: MemoryRecord) -> IndexResult:
        """Reindex a record in all backends."""
        return await self.index(record)
    
    async def clear(self) -> bool:
        """Clear all backends."""
        results = []
        
        for backend in self.backends:
            try:
                results.append(await backend.clear())
            except Exception:
                results.append(False)
        
        return all(results)
    
    async def count(self) -> int:
        """Return the maximum count across all backends."""
        counts = []
        
        for backend in self.backends:
            try:
                counts.append(await backend.count())
            except Exception:
                pass
        
        return max(counts) if counts else 0
    
    def is_available(self) -> bool:
        """Check if any backend is available."""
        return any(backend.is_available() for backend in self.backends)
    
    def get_backend_stats(self) -> dict[str, Any]:
        """Get statistics for all wrapped backends."""
        return {
            backend.backend_name: {
                "available": backend.is_available(),
                "weight": self.weights.get(backend.backend_name, 1.0)
            }
            for backend in self.backends
        }


# ============================================================================
# Utility Functions
# ============================================================================

def get_backend_for_policy(
    enable_fts: bool = True,
    enable_vector: bool = False,
    vector_backend_type: str = "sqlite_vec"
) -> MemoryIndexBackend:
    """
    Factory function to get appropriate backend based on policy.
    
    Args:
        enable_fts: Whether to enable FTS indexing
        enable_vector: Whether to enable vector indexing
        vector_backend_type: Type of vector backend
        
    Returns:
        Configured MemoryIndexBackend (single or hybrid)
    """
    backends = []
    
    if enable_fts:
        fts_backend = SQLiteFTSBackend()
        if fts_backend.is_available():
            backends.append(fts_backend)
    
    if enable_vector:
        if vector_backend_type == "sqlite_vec":
            vec_backend = SqliteVecBackend()
            if vec_backend.is_available():
                backends.append(vec_backend)
        # Add pgvector support here when implemented
    
    if len(backends) == 0:
        from .indexing import NoOpBackend
        return NoOpBackend()
    
    if len(backends) == 1:
        return backends[0]
    
    return HybridBackend(backends)
