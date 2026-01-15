"""
Knowledge Backend Abstraction

This module provides a unified interface for knowledge storage backends.
Phase 1: SQLite FTS only
Future: Chroma, pgvector, managed vector DBs
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
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


def get_backend(backend_type: str) -> type:
	"""Get backend class by type."""
	backends = {
		"sqlite_fts": "huf.ai.knowledge.backends.sqlite_fts.SQLiteFTSBackend",
		# Future backends:
		# "chroma": "huf.ai.knowledge.backends.chroma.ChromaBackend",
		# "pgvector": "huf.ai.knowledge.backends.pgvector.PgVectorBackend",
	}
	
	if backend_type not in backends:
		raise ValueError(f"Unknown backend type: {backend_type}")
	
	import frappe
	return frappe.get_attr(backends[backend_type])
