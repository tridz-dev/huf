"""
Knowledge Backend Abstraction

This module provides a unified interface for knowledge storage backends.
Supported: SQLite FTS (keyword search), SQLite Vec (vector search), ChromaDB (vector search), PGVector (vector search), Zvec (vector search)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import frappe
from frappe import _

# Built-in backend registry. Hooked backends are merged on top per request.
_BUILTIN_BACKENDS = {
	"sqlite_fts": "huf.ai.knowledge.backends.sqlite_fts.SQLiteFTSBackend",
	"sqlite_vec": "huf.ai.knowledge.backends.sqlite_vec_backend.SQLiteVecBackend",
	"chroma": "huf.ai.knowledge.backends.chroma_backend.ChromaBackend",
	"pgvector": "huf.ai.knowledge.backends.pgvector_backend.PGVectorBackend",
	"zvec": "huf.ai.knowledge.backends.zvec_backend.ZvecBackend",
}


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


def _discover_backends() -> dict[str, str]:
	"""Return the merged registry of built-in + hooked knowledge backends.

	Built-in backends are loaded first. Each installed app may contribute
	additional backends via the ``huf_knowledge_backends`` hook. The hook value
	must be a dict mapping ``backend_type`` to ``dotted.path.to.Class``; Frappe
	merges dict-valued hooks into a single dict of lists, which
	:func:`_iter_hook_backends` normalises.

	Hook-provided type keys that collide with a built-in key are skipped and
	logged as a warning so external apps cannot shadow HUF's built-ins.
	"""
	backends = dict(_BUILTIN_BACKENDS)

	for app in frappe.get_installed_apps():
		for backend_type, dotted_path in _iter_hook_backends(app):
			if backend_type in _BUILTIN_BACKENDS:
				frappe.logger().warning(
					_(
						"huf_knowledge_backends in app '{0}' tried to override built-in "
						"backend '{1}'; skipping."
					).format(app, backend_type)
				)
				continue
			if backend_type in backends:
				frappe.logger().warning(
					_(
						"huf_knowledge_backends in app '{0}' declares duplicate backend "
						"type '{1}'; keeping first registration."
					).format(app, backend_type)
				)
				continue
			backends[backend_type] = dotted_path

	return backends


def _iter_hook_backends(app: str):
	"""Yield ``(backend_type, dotted_path)`` declared by one app's hook.

	Frappe merges dict-valued hooks into a single dict whose values are lists
	of declared values (one per declaration). The first declaration for a type
	wins. A plain list of dicts is also accepted defensively.
	"""
	app_hooks = frappe.get_hooks("huf_knowledge_backends", app_name=app) or {}

	if isinstance(app_hooks, dict):
		entries = app_hooks.items()
	elif isinstance(app_hooks, list):
		entries = []
		for hook_entry in app_hooks:
			if not isinstance(hook_entry, dict):
				frappe.logger().warning(
					_("huf_knowledge_backends entry in app '{0}' must be a dict; got {1}").format(
						app, type(hook_entry).__name__
					)
				)
				continue
			entries.extend(hook_entry.items())
	else:
		frappe.logger().warning(
			_("huf_knowledge_backends entry in app '{0}' must be a dict; got {1}").format(
				app, type(app_hooks).__name__
			)
		)
		return

	for backend_type, dotted_paths in entries:
		if isinstance(dotted_paths, str):
			dotted_paths = [dotted_paths]
		if not dotted_paths:
			continue
		yield backend_type, dotted_paths[0]


def _get_backend_registry() -> dict[str, str]:
	"""Return the discovered backend registry, cached for the current request."""
	if not getattr(frappe.local, "huf_backend_registry", None):
		frappe.local.huf_backend_registry = _discover_backends()
	return frappe.local.huf_backend_registry


def get_backend(backend_type: str) -> type:
	"""Get backend class by type."""
	backends = _get_backend_registry()

	if backend_type not in backends:
		frappe.throw(_("Unknown backend type: {0}").format(backend_type))

	dotted_path = backends[backend_type]
	backend_class = frappe.get_attr(dotted_path)

	if not isinstance(backend_class, type) or not issubclass(backend_class, KnowledgeBackend):
		frappe.throw(
			_("Knowledge backend '{0}' ({1}) must be a subclass of KnowledgeBackend.").format(
				backend_type, dotted_path
			)
		)

	return backend_class


@frappe.whitelist()
def get_advanced_config_schema(knowledge_type: str) -> list[dict[str, Any]]:
	"""Return the advanced-config schema for a given knowledge backend type."""
	backend_class = get_backend(knowledge_type)
	return backend_class.get_advanced_config_schema()
