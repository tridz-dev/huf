"""
HUF Memory System - Hybrid Backend

Hybrid backend that combines results from multiple backends using RRF
(Reciprocal Rank Fusion).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

import frappe

from ..index_backend import IndexResult, MemoryIndexBackend, ScopeFilter, SearchResult

if TYPE_CHECKING:
    from ..storage_service import MemoryRecord


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
