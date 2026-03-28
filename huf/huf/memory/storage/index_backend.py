"""
HUF Memory System - Index Backend Abstraction

Abstract interface and utilities for memory indexing backends.
This module provides the base classes and shared utilities for
implementing different indexing backends (FTS, vector, hybrid).
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

import frappe

if TYPE_CHECKING:
    from .storage_service import MemoryRecord


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
    # Import here to avoid circular dependency
    from .backends.sqlite_fts import SQLiteFTSBackend
    from .backends.sqlite_vec import SqliteVecBackend
    
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
        return NoOpBackend()
    
    if len(backends) == 1:
        return backends[0]
    
    # Import HybridBackend here to avoid circular dependency
    from .backends.hybrid import HybridBackend
    return HybridBackend(backends)
