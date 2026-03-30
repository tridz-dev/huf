"""
Knowledge Backend Abstraction

This module provides a unified interface for knowledge storage backends.
Supported: SQLite FTS (keyword search), SQLite Vec (vector search)
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass


@dataclass
class ChunkResult:
	"""Result from a knowledge search."""
	chunk_id: str
	text: str
	title: Optional[str] = None
	score: float = 0.0
	source: Optional[str] = None
	metadata: Optional[Dict[str, Any]] = None


class KnowledgeBackend(ABC):
	"""Abstract base class for knowledge backends."""
	
	@abstractmethod
	def initialize(self, knowledge_source: str, config: Dict[str, Any]) -> None:
		"""Initialize the backend for a knowledge source."""
		pass
	
	@abstractmethod
	def add_chunks(self, chunks: List[Dict[str, Any]]) -> int:
		"""Add chunks to the backend. Returns number added."""
		pass
	
	@abstractmethod
	def delete_chunks(self, input_id: str) -> int:
		"""Delete all chunks for an input. Returns number deleted."""
		pass
	
	@abstractmethod
	def search(
		self,
		query: str,
		top_k: int = 5,
		filters: Optional[Dict[str, Any]] = None
	) -> List[ChunkResult]:
		"""Search for relevant chunks."""
		pass
	
	@abstractmethod
	def clear(self) -> None:
		"""Clear all chunks from the backend."""
		pass
	
	@abstractmethod
	def get_stats(self) -> Dict[str, Any]:
		"""Get backend statistics (chunk count, size, etc.)."""
		pass
	
	@abstractmethod
	def health_check(self) -> Tuple[bool, str]:
		"""Check backend health. Returns (is_healthy, message)."""
		...
	
	@abstractmethod
	def supports_filters(self) -> bool:
		"""Whether this backend supports metadata filtering."""
		...
	
	@abstractmethod
	def supports_hybrid_search(self) -> bool:
		"""Whether this backend supports hybrid search."""
		...
	
	def get_capabilities(self) -> Dict[str, bool]:
		"""Return backend capabilities."""
		return {
			"filters": self.supports_filters(),
			"hybrid_search": self.supports_hybrid_search(),
		}


def get_backend(backend_type: str) -> type:
	"""Get backend class by type."""
	backends = {
		"sqlite_fts": "huf.ai.knowledge.backends.sqlite_fts.SQLiteFTSBackend",
		"sqlite_vec": "huf.ai.knowledge.backends.sqlite_vec_backend.SQLiteVecBackend",
	}
	
	if backend_type not in backends:
		raise ValueError(f"Unknown backend type: {backend_type}")
	
	import frappe
	return frappe.get_attr(backends[backend_type])


# Auto-register existing backends at module load time
try:
	from .factory import BackendFactory
	from .sqlite_vec_backend import SQLiteVecBackend
	from .sqlite_fts import SQLiteFTSBackend

	BackendFactory.register("sqlite_vec", SQLiteVecBackend)
	BackendFactory.register("sqlite_fts", SQLiteFTSBackend)
except ImportError:
	# Allow importing without factory for backward compatibility
	pass
