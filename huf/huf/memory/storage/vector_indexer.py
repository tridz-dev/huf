"""
HUF Memory System - Vector Indexing Pipeline

Vector/semantic indexing pipeline for Memory Records using sqlite-vec
or other vector backends. This module provides the indexing service
and pipeline for vector operations.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

import frappe

from .index_backend import EmbeddingGenerator, IndexResult, ScopeFilter, SearchResult

if TYPE_CHECKING:
    from .storage_service import MemoryRecord
    from .backends.sqlite_vec import SqliteVecBackend


class VectorIndexer:
    """
    Vector indexing service for Memory Records.
    
    This class coordinates vector indexing operations between canonical
    storage and the vector backend (sqlite-vec, pgvector, etc.).
    """
    
    def __init__(
        self,
        backend: Optional["SqliteVecBackend"] = None,
        embedding_generator: Optional[EmbeddingGenerator] = None
    ):
        self._backend = backend
        self._embedding_generator = embedding_generator
        self._initialized = False
    
    async def initialize(self) -> bool:
        """Initialize the vector backend."""
        if self._backend is None:
            from .backends.sqlite_vec import SqliteVecBackend
            self._backend = SqliteVecBackend(
                embedding_generator=self._embedding_generator
            )
        
        self._initialized = await self._backend.initialize()
        return self._initialized
    
    def is_initialized(self) -> bool:
        """Check if the indexer is initialized."""
        return self._initialized and self._backend is not None
    
    async def index(self, record: MemoryRecord) -> IndexResult:
        """
        Index a memory record to vector store.
        
        Args:
            record: The MemoryRecord to index
            
        Returns:
            IndexResult with success status
        """
        if not self._initialized:
            await self.initialize()
        
        if self._backend is None:
            return IndexResult(
                success=False,
                record_id=record.name,
                backend="vector",
                indexed_at=datetime.now(),
                error_message="Vector backend not available"
            )
        
        return await self._backend.index(record)
    
    async def search(
        self,
        query: str,
        scope: Optional[ScopeFilter] = None,
        limit: int = 10
    ) -> list[SearchResult]:
        """
        Search the vector index.
        
        Args:
            query: The search query string
            scope: Optional scope filter
            limit: Maximum results to return
            
        Returns:
            List of SearchResult objects
        """
        if not self._initialized:
            await self.initialize()
        
        if self._backend is None:
            return []
        
        scope = scope or ScopeFilter()
        return await self._backend.search(query, scope, limit)
    
    async def delete(self, record_id: str) -> bool:
        """
        Remove a record from the vector index.
        
        Args:
            record_id: The record ID to remove
            
        Returns:
            True if deleted or not found
        """
        if not self._initialized or self._backend is None:
            return True
        
        return await self._backend.delete(record_id)
    
    async def reindex(self, record: MemoryRecord) -> IndexResult:
        """
        Reindex a record (update existing).
        
        Args:
            record: The MemoryRecord to reindex
            
        Returns:
            IndexResult with success status
        """
        if not self._initialized:
            await self.initialize()
        
        if self._backend is None:
            return IndexResult(
                success=False,
                record_id=record.name,
                backend="vector",
                indexed_at=datetime.now(),
                error_message="Vector backend not available"
            )
        
        return await self._backend.reindex(record)
    
    async def clear(self) -> bool:
        """Clear all records from the vector index."""
        if not self._initialized or self._backend is None:
            return True
        
        return await self._backend.clear()
    
    async def count(self) -> int:
        """Get the number of indexed records."""
        if not self._initialized or self._backend is None:
            return 0
        
        return await self._backend.count()
    
    async def rebuild(
        self,
        batch_size: int = 100,
        filters: Optional[dict] = None
    ) -> dict[str, Any]:
        """
        Rebuild the vector index from canonical storage.
        
        Args:
            batch_size: Number of records to process per batch
            filters: Optional filters for which records to index
            
        Returns:
            Statistics about the rebuild operation
        """
        # Clear existing index
        await self.clear()
        
        # Query active records with vector indexing enabled
        base_filters = {
            "status": "active",
            "enable_vector_index": True
        }
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
            "no_embedding": 0
        }
        
        # Process in batches
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            
            for record_ref in batch:
                try:
                    doc = frappe.get_doc("Memory Record", record_ref.name)
                    from .storage_service import MemoryRecord
                    record = MemoryRecord.from_doc(doc)
                    
                    result = await self.index(record)
                    
                    if result.success:
                        stats["indexed"] += 1
                        # Update record index status
                        doc.vector_indexed = True
                        doc.last_indexed_at = datetime.now()
                        doc.save(ignore_permissions=True)
                    elif "No embedding available" in (result.error_message or ""):
                        stats["no_embedding"] += 1
                    else:
                        stats["failed"] += 1
                    
                except Exception as e:
                    frappe.log_error(f"Vector rebuild failed for {record_ref.name}: {str(e)}")
                    stats["failed"] += 1
            
            frappe.db.commit()
        
        return stats
    
    def get_stats(self) -> dict[str, Any]:
        """Get vector indexer statistics."""
        import asyncio
        
        stats = {
            "initialized": self._initialized,
            "available": self._backend.is_available() if self._backend else False,
        }
        
        if self._backend:
            try:
                stats["count"] = asyncio.run(self.count())
            except Exception:
                stats["count"] = 0
        
        return stats


class VectorIndexPipeline:
    """
    Pipeline for vector indexing operations.
    
    This class provides a higher-level interface for batch operations
    and integration with the capture pipeline.
    """
    
    def __init__(
        self,
        indexer: Optional[VectorIndexer] = None,
        embedding_generator: Optional[EmbeddingGenerator] = None
    ):
        self.indexer = indexer or VectorIndexer(embedding_generator=embedding_generator)
    
    async def process_record(
        self,
        record: MemoryRecord,
        operation: str = "index"
    ) -> IndexResult:
        """
        Process a single record through the vector pipeline.
        
        Args:
            record: The MemoryRecord to process
            operation: One of 'index', 'reindex', 'delete'
            
        Returns:
            IndexResult with success status
        """
        if operation == "index":
            return await self.indexer.index(record)
        elif operation == "reindex":
            return await self.indexer.reindex(record)
        elif operation == "delete":
            success = await self.indexer.delete(record.name)
            return IndexResult(
                success=success,
                record_id=record.name,
                backend="vector",
                indexed_at=datetime.now()
            )
        else:
            raise ValueError(f"Unknown operation: {operation}")
    
    async def process_batch(
        self,
        records: list[MemoryRecord],
        operation: str = "index"
    ) -> list[IndexResult]:
        """
        Process a batch of records through the vector pipeline.
        
        Args:
            records: List of MemoryRecords to process
            operation: One of 'index', 'reindex', 'delete'
            
        Returns:
            List of IndexResult objects
        """
        results = []
        
        for record in records:
            try:
                result = await self.process_record(record, operation)
                results.append(result)
            except Exception as e:
                results.append(IndexResult(
                    success=False,
                    record_id=record.name,
                    backend="vector",
                    indexed_at=datetime.now(),
                    error_message=str(e)
                ))
        
        return results
    
    async def index_for_conversation(
        self,
        conversation_id: str
    ) -> dict[str, Any]:
        """
        Index all unindexed records for a conversation.
        
        Args:
            conversation_id: The conversation ID
            
        Returns:
            Statistics about the indexing operation
        """
        records = frappe.get_all(
            "Memory Record",
            filters={
                "conversation": conversation_id,
                "status": "active",
                "vector_indexed": False,
                "enable_vector_index": True
            },
            fields=["name"]
        )
        
        stats = {
            "total": len(records),
            "indexed": 0,
            "failed": 0,
            "no_embedding": 0
        }
        
        for record_ref in records:
            try:
                doc = frappe.get_doc("Memory Record", record_ref.name)
                from .storage_service import MemoryRecord
                record = MemoryRecord.from_doc(doc)
                
                result = await self.indexer.index(record)
                
                if result.success:
                    stats["indexed"] += 1
                    doc.vector_indexed = True
                    doc.last_indexed_at = datetime.now()
                    doc.save(ignore_permissions=True)
                elif "No embedding available" in (result.error_message or ""):
                    stats["no_embedding"] += 1
                else:
                    stats["failed"] += 1
                    
            except Exception as e:
                frappe.log_error(f"Vector index failed for {record_ref.name}: {str(e)}")
                stats["failed"] += 1
        
        frappe.db.commit()
        return stats


def get_vector_indexer(
    embedding_generator: Optional[EmbeddingGenerator] = None
) -> VectorIndexer:
    """Factory function to get a VectorIndexer instance."""
    return VectorIndexer(embedding_generator=embedding_generator)
