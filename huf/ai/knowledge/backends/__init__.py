"""
Knowledge Backend Abstraction

This module provides a unified interface for knowledge storage backends.
Supported: SQLite FTS (keyword search), SQLite Vec (vector search), ChromaDB (vector search), PGVector (vector search)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import frappe
from frappe import _


@dataclass
class ChunkResult:
	"""Result from a knowledge search."""

	chunk_id: str
	text: str
	title: str | None = None
	score: float = 0.0
	source: str | None = None
	metadata: dict[str, Any] | None = None


class KnowledgeBackend(ABC):
	"""Abstract base class for knowledge backends."""

	@abstractmethod
	def initialize(self, knowledge_source: str, config: dict[str, Any]) -> None:
		"""Initialize the backend for a knowledge source."""
		pass

	@abstractmethod
	def add_chunks(self, chunks: list[dict[str, Any]]) -> int:
		"""Add chunks to the backend. Returns number added."""
		pass

	@abstractmethod
	def delete_chunks(self, input_id: str) -> int:
		"""Delete all chunks for an input. Returns number deleted."""
		pass

	@abstractmethod
	def search(self, query: str, top_k: int = 5, filters: dict[str, Any] | None = None) -> list[ChunkResult]:
		"""Search for relevant chunks."""
		pass

	@abstractmethod
	def clear(self) -> None:
		"""Clear all chunks from the backend."""
		pass

	@abstractmethod
	def get_stats(self) -> dict[str, Any]:
		"""Get backend statistics (chunk count, size, etc.)."""
		pass

	@classmethod
	def get_advanced_config_schema(cls) -> list[dict[str, Any]]:
		"""Return schema for backend-specific advanced configuration.

		Each entry is a dict with:
			key, label, type (number|text|boolean|select), default, help_text,
			options? (select only), min/max? (number only), visible_when? ({field: value}).
		"""
		return []


def get_backend(backend_type: str) -> type:
	"""Get backend class by type."""
	backends = {
		"sqlite_fts": "huf.ai.knowledge.backends.sqlite_fts.SQLiteFTSBackend",
		"sqlite_vec": "huf.ai.knowledge.backends.sqlite_vec_backend.SQLiteVecBackend",
		"chroma": "huf.ai.knowledge.backends.chroma_backend.ChromaBackend",
		"pgvector": "huf.ai.knowledge.backends.pgvector_backend.PGVectorBackend",
	}

	if backend_type not in backends:
		frappe.throw(_("Unknown backend type: {0}").format(backend_type))

	return frappe.get_attr(backends[backend_type])


@frappe.whitelist()
def get_advanced_config_schema(knowledge_type: str) -> list[dict[str, Any]]:
	"""Return the advanced-config schema for a given knowledge backend type."""
	backend_class = get_backend(knowledge_type)
	return backend_class.get_advanced_config_schema()
