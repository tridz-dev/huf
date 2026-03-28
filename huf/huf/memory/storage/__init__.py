"""
HUF Memory System - Storage Layer

Canonical storage and indexing infrastructure for the HUF Agent Memory system.

This package provides:
- Canonical storage service for Memory Records (MariaDB/DocType)
- FTS indexing pipeline (SQLite FTS5)
- Vector indexing pipeline (sqlite-vec, pgvector)
- Index backend abstraction layer

Modules:
    storage_service: Canonical storage interface (CRUD operations)
    fts_indexer: Full-text search indexing pipeline
    vector_indexer: Vector/semantic indexing pipeline
    index_backend: Abstract backend interface and utilities
    backends: Concrete backend implementations

Based on:
    - STORAGE_ARCHITECTURE.md: Technical specifications
    - IMPLEMENTATION_PLAN.md Section 14: Storage & Indexing
"""

from .storage_service import (
    MemoryRecord,
    MemoryStorage,
    SourceType,
    ProducerMode,
    MemoryType,
    ScopeType,
    Visibility,
    MemoryStatus,
    IndexBackend,
    get_storage,
)

from .index_backend import (
    MemoryIndexBackend,
    NoOpBackend,
    SearchResult,
    IndexResult,
    ScopeFilter,
    EmbeddingGenerator,
    get_backend_for_policy,
)

from .fts_indexer import (
    FTSIndexer,
    FTSIndexPipeline,
    get_fts_indexer,
)

from .vector_indexer import (
    VectorIndexer,
    VectorIndexPipeline,
    get_vector_indexer,
)

__all__ = [
    # Storage Service
    "MemoryRecord",
    "MemoryStorage",
    "SourceType",
    "ProducerMode",
    "MemoryType",
    "ScopeType",
    "Visibility",
    "MemoryStatus",
    "IndexBackend",
    "get_storage",
    # Index Backend
    "MemoryIndexBackend",
    "NoOpBackend",
    "SearchResult",
    "IndexResult",
    "ScopeFilter",
    "EmbeddingGenerator",
    "get_backend_for_policy",
    # FTS Indexer
    "FTSIndexer",
    "FTSIndexPipeline",
    "get_fts_indexer",
    # Vector Indexer
    "VectorIndexer",
    "VectorIndexPipeline",
    "get_vector_indexer",
]
