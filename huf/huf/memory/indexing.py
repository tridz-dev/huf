"""
HUF Memory System - Indexing Layer

FTS (Full-Text Search) and vector indexing with backend abstraction.
This module provides the abstract interface and base implementations
for indexing Memory Records across different backends.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal, Optional, Union

import frappe

if TYPE_CHECKING:
    from .storage import MemoryRecord


class SearchResult:
    """Result from an index search operation."""
    
    def __init__(
        self,
        record_id: str,
        score: float,
        backend: str,
        rank: int = 0,
        matched_fields: Optional[list[str]] = None,
        snippet: Optional[str] = None
    ):
        self.record_id = record_id
        self.score = score
        self.backend = backend
        self.rank = rank
        self.matched_fields = matched_fields or []
        self.snippet = snippet
    
    def __repr__(self) -> str:
        return f"SearchResult(record_id={self.record_id}, score={self.score:.4f}, backend={self.backend})"


@dataclass
class IndexResult:
    """Result from an index operation."""
    
    success: bool
    record_id: str
    backend: str
    indexed_at: datetime
    error_message: Optional[str] = None
    embedding_dimension: Optional[int] = None
    tokens_used: Optional[int] = None


class ScopeFilter:
    """Filter parameters for scoped memory search."""
    
    def __init__(
        self,
        scope_type: Optional[str] = None,
        scope_key: Optional[str] = None,
        agent: Optional[str] = None,
        memory_type: Optional[str] = None,
        visibility: Optional[str] = None,
        status: str = "active",
        tags: Optional[list[str]] = None,
        min_confidence: float = 0.0,
        min_importance: float = 0.0,
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None
    ):
        self.scope_type = scope_type
        self.scope_key = scope_key
        self.agent = agent
        self.memory_type = memory_type
        self.visibility = visibility
        self.status = status
        self.tags = tags
        self.min_confidence = min_confidence
        self.min_importance = min_importance
        self.created_after = created_after
        self.created_before = created_before
    
    def to_sql_conditions(self, table_alias: str = "") -> tuple[str, list]:
        """Convert filter to SQL WHERE clause and parameters."""
        conditions = []
        params = []
        prefix = f"{table_alias}." if table_alias else ""
        
        if self.scope_type:
            conditions.append(f"{prefix}scope_type = %s")
            params.append(self.scope_type)
        
        if self.scope_key:
            conditions.append(f"{prefix}scope_key = %s")
            params.append(self.scope_key)
        
        if self.agent:
            conditions.append(f"{prefix}agent = %s")
            params.append(self.agent)
        
        if self.memory_type:
            conditions.append(f"{prefix}memory_type = %s")
            params.append(self.memory_type)
        
        if self.visibility:
            conditions.append(f"{prefix}visibility = %s")
            params.append(self.visibility)
        
        conditions.append(f"{prefix}status = %s")
        params.append(self.status)
        
        if self.min_confidence > 0:
            conditions.append(f"{prefix}confidence >= %s")
            params.append(self.min_confidence)
        
        if self.min_importance > 0:
            conditions.append(f"{prefix}importance_score >= %s")
            params.append(self.min_importance)
        
        if self.created_after:
            conditions.append(f"{prefix}creation >= %s")
            params.append(self.created_after)
        
        if self.created_before:
            conditions.append(f"{prefix}creation <= %s")
            params.append(self.created_before)
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        return where_clause, params


class MemoryIndexBackend(ABC):
    """
    Abstract interface for memory indexing backends.
    
    This ABC defines the uniform interface that all indexing backends
    must implement, regardless of underlying storage technology.
    """
    
    def __init__(self, backend_name: str):
        self.backend_name = backend_name
        self._initialized = False
    
    @abstractmethod
    async def initialize(self) -> bool:
        """
        Initialize the backend (create tables, load extensions, etc.).
        
        Returns:
            True if initialization successful
        """
        pass
    
    @abstractmethod
    async def index(self, record: MemoryRecord) -> IndexResult:
        """
        Index a memory record for retrieval.
        
        Args:
            record: The MemoryRecord to index
            
        Returns:
            IndexResult with success status and metadata
        """
        pass
    
    @abstractmethod
    async def search(
        self,
        query: str,
        scope: ScopeFilter,
        limit: int = 10
    ) -> list[SearchResult]:
        """
        Search indexed memories.
        
        Args:
            query: The search query string
            scope: ScopeFilter for filtering results
            limit: Maximum results to return
            
        Returns:
            List of SearchResult objects ranked by relevance
        """
        pass
    
    @abstractmethod
    async def delete(self, record_id: str) -> bool:
        """
        Remove a record from the index.
        
        Args:
            record_id: The record ID to remove
            
        Returns:
            True if deleted or not found, False on error
        """
        pass
    
    @abstractmethod
    async def reindex(self, record: MemoryRecord) -> IndexResult:
        """
        Update an existing indexed record.
        
        Args:
            record: The MemoryRecord with updated values
            
        Returns:
            IndexResult with success status and metadata
        """
        pass
    
    @abstractmethod
    async def clear(self) -> bool:
        """
        Clear all records from this index.
        
        Returns:
            True if cleared successfully
        """
        pass
    
    @abstractmethod
    async def count(self) -> int:
        """
        Get the number of indexed records.
        
        Returns:
            Count of indexed records
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if the backend is available/ready.
        
        Returns:
            True if the backend can be used
        """
        pass
    
    async def health_check(self) -> dict[str, Any]:
        """
        Perform a health check on the backend.
        
        Returns:
            Dict with health status information
        """
        return {
            "backend": self.backend_name,
            "available": self.is_available(),
            "initialized": self._initialized,
            "record_count": await self.count() if self.is_available() else 0
        }
    
    def _get_embedding_text(self, record: MemoryRecord) -> str:
        """
        Extract text for embedding from a memory record.
        
        Uses summary_text if available, otherwise falls back to
        a serialized representation of the data.
        """
        if record.summary_text:
            return record.summary_text
        
        # Serialize data_json for embedding
        if record.data_json:
            return json.dumps(record.data_json, ensure_ascii=False, indent=None)
        
        return record.title


class NoOpBackend(MemoryIndexBackend):
    """
    No-op backend for when no indexing is configured.
    
    This backend silently accepts all operations but does nothing,
    allowing the system to function without indexing.
    """
    
    def __init__(self):
        super().__init__("noop")
    
    async def initialize(self) -> bool:
        self._initialized = True
        return True
    
    async def index(self, record: MemoryRecord) -> IndexResult:
        return IndexResult(
            success=True,
            record_id=record.name,
            backend=self.backend_name,
            indexed_at=datetime.now()
        )
    
    async def search(
        self,
        query: str,
        scope: ScopeFilter,
        limit: int = 10
    ) -> list[SearchResult]:
        return []
    
    async def delete(self, record_id: str) -> bool:
        return True
    
    async def reindex(self, record: MemoryRecord) -> IndexResult:
        return await self.index(record)
    
    async def clear(self) -> bool:
        return True
    
    async def count(self) -> int:
        return 0
    
    def is_available(self) -> bool:
        return True


class EmbeddingGenerator(ABC):
    """
    Abstract interface for embedding generation.
    
    This allows pluggable embedding providers (OpenAI, local models, etc.)
    """
    
    @abstractmethod
    async def generate(self, text: str) -> list[float]:
        """
        Generate embedding vector for text.
        
        Args:
            text: The text to embed
            
        Returns:
            List of float values (the embedding vector)
        """
        pass
    
    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the dimension of embeddings produced."""
        pass


class MemoryIndexingService:
    """
    High-level service for coordinating memory indexing operations.
    
    This service manages the interaction between canonical storage
    and optional index backends, handling policy decisions and
    fallback behaviors.
    """
    
    def __init__(
        self,
        fts_backend: Optional[MemoryIndexBackend] = None,
        vector_backend: Optional[MemoryIndexBackend] = None
    ):
        self.fts_backend = fts_backend
        self.vector_backend = vector_backend
        self._initialized = False
    
    async def initialize(self) -> bool:
        """Initialize all configured backends."""
        results = []
        
        if self.fts_backend:
            results.append(await self.fts_backend.initialize())
        
        if self.vector_backend:
            results.append(await self.vector_backend.initialize())
        
        self._initialized = all(results) if results else True
        return self._initialized
    
    async def index_record(self, record: MemoryRecord) -> dict[str, IndexResult]:
        """
        Index a record according to its policy settings.
        
        Args:
            record: The MemoryRecord to index
            
        Returns:
            Dict mapping backend name to IndexResult
        """
        results = {}
        
        if not record.can_index():
            return results
        
        # Index to FTS if enabled
        if record.enable_fts_index and self.fts_backend:
            try:
                result = await self.fts_backend.index(record)
                results["fts"] = result
                
                if result.success:
                    record.fts_indexed = True
            except Exception as e:
                results["fts"] = IndexResult(
                    success=False,
                    record_id=record.name,
                    backend="fts",
                    indexed_at=datetime.now(),
                    error_message=str(e)
                )
        
        # Index to vector if enabled
        if record.enable_vector_index and self.vector_backend:
            try:
                result = await self.vector_backend.index(record)
                results["vector"] = result
                
                if result.success:
                    record.vector_indexed = True
            except Exception as e:
                results["vector"] = IndexResult(
                    success=False,
                    record_id=record.name,
                    backend="vector",
                    indexed_at=datetime.now(),
                    error_message=str(e)
                )
        
        # Update record index metadata
        if any(r.success for r in results.values()):
            record.last_indexed_at = datetime.now()
        
        return results
    
    async def search(
        self,
        query: str,
        scope: Optional[ScopeFilter] = None,
        limit: int = 10,
        use_fts: bool = True,
        use_vector: bool = True,
        hybrid_fusion: bool = True,
        rrf_k: int = 60
    ) -> list[SearchResult]:
        """
        Search across configured backends.
        
        Args:
            query: The search query
            scope: Optional scope filter
            limit: Maximum results
            use_fts: Whether to use FTS backend
            use_vector: Whether to use vector backend
            hybrid_fusion: Whether to use RRF for hybrid search
            rrf_k: RRF fusion parameter
            
        Returns:
            Combined and ranked search results
        """
        scope = scope or ScopeFilter()
        all_results: list[list[SearchResult]] = []
        
        # Query FTS backend
        if use_fts and self.fts_backend and self.fts_backend.is_available():
            try:
                fts_results = await self.fts_backend.search(query, scope, limit * 2)
                for i, r in enumerate(fts_results):
                    r.rank = i + 1
                all_results.append(fts_results)
            except Exception as e:
                frappe.log_error(f"FTS search failed: {str(e)}")
        
        # Query vector backend
        if use_vector and self.vector_backend and self.vector_backend.is_available():
            try:
                vec_results = await self.vector_backend.search(query, scope, limit * 2)
                for i, r in enumerate(vec_results):
                    r.rank = i + 1
                all_results.append(vec_results)
            except Exception as e:
                frappe.log_error(f"Vector search failed: {str(e)}")
        
        # If only one backend returned results, return directly
        if len(all_results) == 1:
            return all_results[0][:limit]
        
        # If multiple backends, fuse results
        if len(all_results) > 1 and hybrid_fusion:
            return self._fuse_results(all_results, limit, rrf_k)
        
        # Fallback: concatenate and deduplicate
        combined = []
        seen = set()
        for results in all_results:
            for r in results:
                if r.record_id not in seen:
                    seen.add(r.record_id)
                    combined.append(r)
        
        return combined[:limit]
    
    def _fuse_results(
        self,
        result_lists: list[list[SearchResult]],
        limit: int,
        k: int = 60
    ) -> list[SearchResult]:
        """
        Fuse results from multiple backends using Reciprocal Rank Fusion.
        
        RRF formula: score = Σ 1 / (k + rank_i) for each backend i
        """
        # Collect all scores by record_id
        scores: dict[str, float] = {}
        record_map: dict[str, SearchResult] = {}
        
        for results in result_lists:
            for result in results:
                if result.record_id not in scores:
                    scores[result.record_id] = 0.0
                    record_map[result.record_id] = result
                
                # RRF score contribution from this backend
                scores[result.record_id] += 1.0 / (k + result.rank)
        
        # Sort by fused score (descending)
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        
        # Build final results with fused scores
        fused_results = []
        for record_id in sorted_ids[:limit]:
            result = record_map[record_id]
            result.score = scores[record_id]
            fused_results.append(result)
        
        return fused_results
    
    async def delete_record(self, record_id: str) -> dict[str, bool]:
        """
        Delete a record from all indexes.
        
        Args:
            record_id: The record ID to delete
            
        Returns:
            Dict mapping backend name to success status
        """
        results = {}
        
        if self.fts_backend:
            try:
                results["fts"] = await self.fts_backend.delete(record_id)
            except Exception as e:
                frappe.log_error(f"FTS delete failed for {record_id}: {str(e)}")
                results["fts"] = False
        
        if self.vector_backend:
            try:
                results["vector"] = await self.vector_backend.delete(record_id)
            except Exception as e:
                frappe.log_error(f"Vector delete failed for {record_id}: {str(e)}")
                results["vector"] = False
        
        return results
    
    async def reindex_record(self, record: MemoryRecord) -> dict[str, IndexResult]:
        """
        Reindex a record (update existing index entries).
        
        Args:
            record: The MemoryRecord to reindex
            
        Returns:
            Dict mapping backend name to IndexResult
        """
        results = {}
        
        # Reindex FTS if enabled
        if record.enable_fts_index and self.fts_backend:
            try:
                result = await self.fts_backend.reindex(record)
                results["fts"] = result
                
                if result.success:
                    record.fts_indexed = True
            except Exception as e:
                results["fts"] = IndexResult(
                    success=False,
                    record_id=record.name,
                    backend="fts",
                    indexed_at=datetime.now(),
                    error_message=str(e)
                )
        
        # Reindex vector if enabled
        if record.enable_vector_index and self.vector_backend:
            try:
                result = await self.vector_backend.reindex(record)
                results["vector"] = result
                
                if result.success:
                    record.vector_indexed = True
            except Exception as e:
                results["vector"] = IndexResult(
                    success=False,
                    record_id=record.name,
                    backend="vector",
                    indexed_at=datetime.now(),
                    error_message=str(e)
                )
        
        if any(r.success for r in results.values()):
            record.last_indexed_at = datetime.now()
        
        return results
    
    async def rebuild_index(
        self,
        batch_size: int = 100,
        filters: Optional[dict] = None
    ) -> dict[str, Any]:
        """
        Rebuild indexes from canonical storage.
        
        Args:
            batch_size: Number of records to process per batch
            filters: Optional filters for which records to reindex
            
        Returns:
            Statistics about the rebuild operation
        """
        # Clear existing indexes
        if self.fts_backend:
            await self.fts_backend.clear()
        
        if self.vector_backend:
            await self.vector_backend.clear()
        
        # Query all active records
        base_filters = {"status": "active"}
        if filters:
            base_filters.update(filters)
        
        records = frappe.get_all(
            "Memory Record",
            filters=base_filters,
            fields=["name"],
            limit_page_length=0
        )
        
        stats = {
            "total": len(records),
            "indexed": 0,
            "failed": 0,
            "by_backend": {"fts": 0, "vector": 0}
        }
        
        # Process in batches
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            
            for record_ref in batch:
                try:
                    doc = frappe.get_doc("Memory Record", record_ref.name)
                    from .storage import MemoryRecord
                    record = MemoryRecord.from_doc(doc)
                    
                    results = await self.index_record(record)
                    
                    if any(r.success for r in results.values()):
                        stats["indexed"] += 1
                        
                        # Update record index status
                        doc.fts_indexed = results.get("fts", IndexResult(
                            success=False, record_id=record.name,
                            backend="fts", indexed_at=datetime.now()
                        )).success
                        doc.vector_indexed = results.get("vector", IndexResult(
                            success=False, record_id=record.name,
                            backend="vector", indexed_at=datetime.now()
                        )).success
                        doc.last_indexed_at = datetime.now()
                        doc.save(ignore_permissions=True)
                        
                        # Update stats
                        if "fts" in results and results["fts"].success:
                            stats["by_backend"]["fts"] += 1
                        if "vector" in results and results["vector"].success:
                            stats["by_backend"]["vector"] += 1
                    else:
                        stats["failed"] += 1
                        
                except Exception as e:
                    frappe.log_error(f"Reindex failed for {record_ref.name}: {str(e)}")
                    stats["failed"] += 1
            
            # Commit batch
            frappe.db.commit()
        
        return stats
    
    def get_stats(self) -> dict[str, Any]:
        """Get statistics about configured backends."""
        stats = {
            "fts_enabled": self.fts_backend is not None,
            "vector_enabled": self.vector_backend is not None,
        }
        
        if self.fts_backend:
            stats["fts"] = {
                "available": self.fts_backend.is_available(),
                "count": asyncio.run(self.fts_backend.count())
            }
        
        if self.vector_backend:
            stats["vector"] = {
                "available": self.vector_backend.is_available(),
                "count": asyncio.run(self.vector_backend.count())
            }
        
        return stats


def get_indexing_service(
    enable_fts: bool = True,
    enable_vector: bool = False,
    vector_backend_type: str = "sqlite_vec"
) -> MemoryIndexingService:
    """
    Factory function to create a MemoryIndexingService.
    
    Args:
        enable_fts: Whether to enable FTS indexing
        enable_vector: Whether to enable vector indexing
        vector_backend_type: Type of vector backend (sqlite_vec, pgvector)
        
    Returns:
        Configured MemoryIndexingService
    """
    # Import here to avoid circular dependency
    from .backends import SQLiteFTSBackend, SqliteVecBackend, NoOpBackend
    
    fts_backend = None
    vector_backend = None
    
    if enable_fts:
        fts_backend = SQLiteFTSBackend()
    
    if enable_vector:
        if vector_backend_type == "sqlite_vec":
            vector_backend = SqliteVecBackend()
        # Add pgvector support here when implemented
    
    return MemoryIndexingService(fts_backend, vector_backend)
