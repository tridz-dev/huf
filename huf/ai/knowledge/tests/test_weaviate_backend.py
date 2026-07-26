# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""Tests for the Weaviate knowledge backend and its built-in registration.

The backend builds on the LlamaIndex Weaviate adapter plus a weaviate-client
connection. Unit tests mock both (no live Weaviate server required); the
config validation, metadata/filter scoping, and stats logic is exercised for
real. When frappe/llama_index are not importable (e.g. running standalone
outside a bench), minimal fakes are installed into ``sys.modules`` first.
"""

import importlib
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

try:
	import frappe
except ImportError:  # standalone run outside a bench: install a minimal fake
	frappe = types.ModuleType("frappe")

	class ValidationError(Exception):
		pass

	class _dict(dict):
		def __getattr__(self, key):
			return self.get(key)

		def __setattr__(self, key, value):
			self[key] = value

	def _throw(msg, exc=None):
		raise (exc or ValidationError)(msg)

	def _get_attr(dotted_path):
		module_path, _, attr = dotted_path.rpartition(".")
		return getattr(importlib.import_module(module_path), attr)

	def _whitelist(*args, **kwargs):
		def decorator(fn):
			return fn

		return decorator

	frappe.ValidationError = ValidationError
	frappe._dict = _dict
	frappe._ = lambda message: message
	frappe.throw = _throw
	frappe.local = SimpleNamespace()
	frappe.logger = MagicMock()
	frappe.whitelist = _whitelist
	frappe.get_attr = _get_attr
	frappe.get_installed_apps = lambda: ["huf"]
	frappe.get_hooks = lambda *args, **kwargs: []
	frappe.conf = SimpleNamespace()
	sys.modules["frappe"] = frappe

try:
	from llama_index.core.vector_stores.types import MetadataFilters
except ImportError:  # standalone run: install a minimal fake llama_index tree

	class _ExactMatchFilter:
		def __init__(self, key, value):
			self.key = key
			self.value = value

	class _MetadataFilters:
		def __init__(self, filters):
			self.filters = filters

	class _VectorStoreQuery:
		def __init__(self, **kwargs):
			self.__dict__.update(kwargs)

	class _Document:
		def __init__(self, **kwargs):
			self.__dict__.update(kwargs)

	class _StorageContext:
		@classmethod
		def from_defaults(cls, **kwargs):
			return cls()

	li = types.ModuleType("llama_index")
	li_core = types.ModuleType("llama_index.core")
	li_core.Document = _Document
	li_core.StorageContext = _StorageContext
	li_vs = types.ModuleType("llama_index.core.vector_stores")
	li_vs.VectorStoreQuery = _VectorStoreQuery
	li_vs_types = types.ModuleType("llama_index.core.vector_stores.types")
	li_vs_types.ExactMatchFilter = _ExactMatchFilter
	li_vs_types.MetadataFilters = _MetadataFilters
	li_core.vector_stores = li_vs
	li_vs.types = li_vs_types
	li.core = li_core
	sys.modules["llama_index"] = li
	sys.modules["llama_index.core"] = li_core
	sys.modules["llama_index.core.vector_stores"] = li_vs
	sys.modules["llama_index.core.vector_stores.types"] = li_vs_types

from huf.ai.knowledge.backends import llamaindex_base as lb
from huf.ai.knowledge.backends import weaviate_backend as wb
from huf.ai.knowledge.backends.weaviate_backend import WeaviateBackend


class TestWeaviateBackend(unittest.TestCase):
	"""Mocked unit tests for WeaviateBackend (no live Weaviate server required)."""

	def setUp(self):
		self.backend = WeaviateBackend()

		self._previous_site = getattr(frappe.local, "site", None)
		frappe.local.site = "test_site"
		# frappe.throw/msgprint and logging need these bound outside a site context.
		frappe.local.flags = frappe._dict()
		frappe.local.message_log = []

		self.patcher_config = patch("huf.ai.knowledge.embedding.resolve_embedding_config")
		self.mock_resolve = self.patcher_config.start()
		self.mock_resolve.return_value = {"model": "test-model", "api_key": "test", "api_base": "test"}

		self.patcher_embeds = patch("huf.ai.knowledge.embedding.get_embeddings")
		self.mock_get_embeds = self.patcher_embeds.start()
		self.mock_get_embeds.side_effect = lambda texts, **_: [[0.1] * 1536 for _ in texts]

		self.patcher_embed = patch("huf.ai.knowledge.embedding.get_embedding")
		self.mock_get_embed = self.patcher_embed.start()
		self.mock_get_embed.return_value = [0.1] * 1536

		# Outside a site context frappe.logger() tries to open site log files.
		self.patcher_logger = patch.object(frappe, "logger", MagicMock())
		self.patcher_logger.start()

	def tearDown(self):
		self.patcher_config.stop()
		self.patcher_embeds.stop()
		self.patcher_embed.stop()
		self.patcher_logger.stop()

		if self._previous_site is None:
			if hasattr(frappe.local, "site"):
				del frappe.local.site
		else:
			frappe.local.site = self._previous_site

	def _initialize(self, config=None, knowledge_source="test_source"):
		"""Initialize the backend with weaviate-client and the adapter mocked."""
		config = config or {}

		self.mock_weaviate = MagicMock()
		self.mock_client = MagicMock()
		self.mock_weaviate.connect_to_custom.return_value = self.mock_client
		self.mock_collection = MagicMock()
		self.mock_client.collections.get.return_value = self.mock_collection

		self.mock_vector_store = MagicMock()
		self.mock_store_cls = MagicMock(return_value=self.mock_vector_store)

		patchers = [
			patch.object(wb, "LLAMAINDEX_AVAILABLE", True),
			patch.object(wb, "WEAVIATE_DEPS_AVAILABLE", True),
			patch.object(wb, "weaviate", self.mock_weaviate, create=True),
			patch.object(wb, "WeaviateVectorStore", self.mock_store_cls, create=True),
			patch.object(wb, "WeaviateFilter", MagicMock(), create=True),
			patch.object(lb, "StorageContext", MagicMock(), create=True),
		]
		for patcher in patchers:
			patcher.start()
			self.addCleanup(patcher.stop)

		self.backend.initialize(knowledge_source, config)

	# ------------------------------------------------------------------
	# Initialization / config validation
	# ------------------------------------------------------------------
	def test_initialize_creates_client_and_store(self):
		"""Initialization connects via weaviate-client and builds the adapter."""
		self._initialize(
			{
				"weaviate_host": "weaviate-vec",
				"weaviate_port": 8080,
				"weaviate_grpc_port": 50051,
				"weaviate_api_key": "secret-key",
			}
		)

		self.assertTrue(self.backend._initialized)
		self.assertEqual(self.backend.knowledge_source, "test_source")
		self.assertEqual(self.backend.index_name, "Huf_test_source")

		connect_kwargs = self.mock_weaviate.connect_to_custom.call_args.kwargs
		self.assertEqual(connect_kwargs["http_host"], "weaviate-vec")
		self.assertEqual(connect_kwargs["http_port"], 8080)
		self.assertEqual(connect_kwargs["grpc_host"], "weaviate-vec")
		self.assertEqual(connect_kwargs["grpc_port"], 50051)
		self.assertFalse(connect_kwargs["http_secure"])
		self.assertFalse(connect_kwargs["grpc_secure"])
		self.assertEqual(
			connect_kwargs["auth_credentials"],
			self.mock_weaviate.auth.AuthApiKey.return_value,
		)
		self.mock_weaviate.auth.AuthApiKey.assert_called_once_with("secret-key")

		self.mock_store_cls.assert_called_once_with(
			weaviate_client=self.mock_client,
			index_name="Huf_test_source",
		)

	def test_initialize_defaults_and_anonymous_access(self):
		"""Empty config defaults to localhost:8080/50051 without auth."""
		self._initialize()

		connect_kwargs = self.mock_weaviate.connect_to_custom.call_args.kwargs
		self.assertEqual(connect_kwargs["http_host"], "localhost")
		self.assertEqual(connect_kwargs["http_port"], 8080)
		self.assertEqual(connect_kwargs["grpc_port"], 50051)
		self.assertNotIn("auth_credentials", connect_kwargs)
		self.mock_weaviate.auth.AuthApiKey.assert_not_called()

	def test_initialize_without_dependencies(self):
		"""Initialization fails with a clear error when the adapter is missing."""
		with patch.object(wb, "WEAVIATE_DEPS_AVAILABLE", False):
			with self.assertRaises(frappe.ValidationError) as ctx:
				self.backend.initialize("test_source", {})
		self.assertIn("llama-index-vector-stores-weaviate", str(ctx.exception))

	def test_index_name_sanitizes_source_name(self):
		"""The default collection name is Huf_<scrubbed knowledge source>."""
		self._initialize(knowledge_source="My Source-1")

		self.assertEqual(self.backend.index_name, "Huf_My_Source_1")

	def test_index_name_override(self):
		"""weaviate_index_name overrides the default collection name."""
		self._initialize({"weaviate_index_name": "Custom_Index"})

		self.assertEqual(self.backend.index_name, "Custom_Index")
		self.mock_store_cls.assert_called_once_with(
			weaviate_client=self.mock_client,
			index_name="Custom_Index",
		)

	def test_index_name_override_invalid(self):
		"""Collection names must start with a capital letter."""
		self.backend.knowledge_source = "test_source"
		self.backend.config = {"weaviate_index_name": "lowercase_name"}

		with self.assertRaises(frappe.ValidationError):
			self.backend._validate_config()

	def test_validate_config_rejects_bad_ports(self):
		self.backend.knowledge_source = "test_source"

		self.backend.config = {"weaviate_port": 0}
		with self.assertRaises(frappe.ValidationError):
			self.backend._validate_config()

		self.backend.config = {"weaviate_grpc_port": 70000}
		with self.assertRaises(frappe.ValidationError):
			self.backend._validate_config()

	# ------------------------------------------------------------------
	# Metadata / filter scoping
	# ------------------------------------------------------------------
	def test_build_chunk_metadata_scopes_site_and_source(self):
		"""Chunk metadata carries site_name + knowledge_source scoping keys."""
		self.backend.knowledge_source = "test_source"

		metadata = self.backend._build_chunk_metadata(
			{
				"input_id": "input_1",
				"input_type": "document",
				"source_title": "Doc",
				"chunk_index": 3,
				"metadata": {"key": "value"},
			},
			"chunk_1",
		)

		self.assertEqual(metadata["site_name"], "test_site")
		self.assertEqual(metadata["knowledge_source"], "test_source")
		self.assertEqual(metadata["input_id"], "input_1")
		self.assertEqual(metadata["chunk_id"], "chunk_1")
		self.assertEqual(metadata["key"], "value")

	def test_build_search_filters_scopes_site_and_source(self):
		"""Search filters always include site + source, plus caller filters."""
		self.backend.knowledge_source = "test_source"

		llama_filters = self.backend._build_search_filters({"input_type": "document"})

		pairs = [(f.key, f.value) for f in llama_filters.filters]
		self.assertIn(("site_name", "test_site"), pairs)
		self.assertIn(("knowledge_source", "test_source"), pairs)
		self.assertIn(("input_type", "document"), pairs)
		self.assertEqual(len(pairs), 3)

	# ------------------------------------------------------------------
	# Search
	# ------------------------------------------------------------------
	def _query_result(self):
		node = MagicMock()
		node.id_ = "node_1"
		node.text = "Test result"
		node.metadata = {
			"chunk_id": "chunk_1",
			"source_title": "Test Doc",
			"input_id": "input_1",
			"site_name": "test_site",
			"knowledge_source": "test_source",
			"key": "value",
		}
		return SimpleNamespace(nodes=[node], similarities=[0.87])

	def test_search_vector_default(self):
		"""Default search issues a pure vector query and normalizes results."""
		self._initialize()
		self.mock_vector_store.query.return_value = self._query_result()

		results = self.backend.search("test query", top_k=5)

		self.assertEqual(len(results), 1)
		self.assertEqual(results[0].text, "Test result")
		self.assertAlmostEqual(results[0].score, 0.87)
		self.assertEqual(results[0].chunk_id, "chunk_1")
		self.assertEqual(results[0].title, "Test Doc")
		self.assertEqual(results[0].source, "input_1")
		# Scoping keys are stripped from ChunkResult.metadata.
		self.assertNotIn("site_name", results[0].metadata)
		self.assertEqual(results[0].metadata["key"], "value")

		query_obj = self.mock_vector_store.query.call_args[0][0]
		self.assertEqual(query_obj.mode, "default")
		self.assertEqual(query_obj.similarity_top_k, 5)
		# Site + source scoping filters are attached.
		pairs = [(f.key, f.value) for f in query_obj.filters.filters]
		self.assertIn(("site_name", "test_site"), pairs)
		self.assertIn(("knowledge_source", "test_source"), pairs)

	def test_search_hybrid_mode(self):
		"""With hybrid_search enabled, the query string and alpha are sent."""
		self._initialize({"hybrid_search": True, "weaviate_hybrid_alpha": 0.7})
		self.mock_vector_store.query.return_value = self._query_result()

		results = self.backend.search("test query", top_k=3)

		self.assertEqual(len(results), 1)
		query_obj = self.mock_vector_store.query.call_args[0][0]
		self.assertEqual(query_obj.mode, "hybrid")
		self.assertEqual(query_obj.query_str, "test query")
		self.assertAlmostEqual(query_obj.alpha, 0.7)
		self.assertEqual(query_obj.similarity_top_k, 3)

	def test_search_empty_query(self):
		"""An empty query short-circuits without touching the store."""
		self._initialize({"hybrid_search": True})

		self.assertEqual(self.backend.search(""), [])
		self.assertEqual(self.backend.search("   "), [])
		self.mock_vector_store.query.assert_not_called()

	def test_search_not_initialized(self):
		"""Search before initialization raises."""
		with self.assertRaises(RuntimeError):
			self.backend.search("test query")

	def test_supports_hybrid_search(self):
		backend = WeaviateBackend()
		self.assertFalse(backend.supports_hybrid_search())
		backend.config = {"hybrid_search": True}
		self.assertTrue(backend.supports_hybrid_search())

	# ------------------------------------------------------------------
	# Delete / clear
	# ------------------------------------------------------------------
	def test_delete_chunks(self):
		"""Deletion counts scoped chunks, then deletes via adapter filters."""
		self._initialize()
		self.mock_collection.aggregate.over_all.return_value = SimpleNamespace(total_count=2)

		deleted = self.backend.delete_chunks("input_1")

		self.assertEqual(deleted, 2)
		# Count ran against the scoped collection with total_count aggregation.
		count_kwargs = self.mock_collection.aggregate.over_all.call_args.kwargs
		self.assertTrue(count_kwargs["total_count"])
		self.assertIn("filters", count_kwargs)

		# The real delete path: adapter delete_nodes with site+source+input filters.
		self.mock_vector_store.delete_nodes.assert_called_once()
		delete_filters = self.mock_vector_store.delete_nodes.call_args.kwargs["filters"]
		pairs = [(f.key, f.value) for f in delete_filters.filters]
		self.assertEqual(
			pairs,
			[
				("site_name", "test_site"),
				("knowledge_source", "test_source"),
				("input_id", "input_1"),
			],
		)

	def test_delete_chunks_none_matching(self):
		"""Nothing to delete: no adapter call, returns 0."""
		self._initialize()
		self.mock_collection.aggregate.over_all.return_value = SimpleNamespace(total_count=0)

		self.assertEqual(self.backend.delete_chunks("input_1"), 0)
		self.mock_vector_store.delete_nodes.assert_not_called()

	def test_delete_chunks_error_returns_zero(self):
		"""A Weaviate failure during delete is logged and reported as 0."""
		self._initialize()
		self.mock_collection.aggregate.over_all.return_value = SimpleNamespace(total_count=3)
		self.mock_vector_store.delete_nodes.side_effect = RuntimeError("boom")

		self.assertEqual(self.backend.delete_chunks("input_1"), 0)

	def test_clear(self):
		"""Clear deletes all site+source chunks via the adapter, scoped."""
		self._initialize()

		self.backend.clear()

		self.mock_vector_store.delete_nodes.assert_called_once()
		clear_filters = self.mock_vector_store.delete_nodes.call_args.kwargs["filters"]
		pairs = [(f.key, f.value) for f in clear_filters.filters]
		self.assertEqual(pairs, [("site_name", "test_site"), ("knowledge_source", "test_source")])

	def test_clear_not_initialized(self):
		with self.assertRaises(RuntimeError):
			self.backend.clear()

	# ------------------------------------------------------------------
	# Stats / health
	# ------------------------------------------------------------------
	def test_get_stats(self):
		"""Stats report backend_type and a scoped chunk count."""
		self._initialize()
		self.mock_collection.aggregate.over_all.return_value = SimpleNamespace(total_count=7)

		stats = self.backend.get_stats()

		self.assertEqual(stats["backend_type"], "weaviate")
		self.assertEqual(stats["knowledge_source"], "test_source")
		self.assertEqual(stats["index_name"], "Huf_test_source")
		self.assertTrue(stats["initialized"])
		self.assertEqual(stats["chunk_count"], 7)

	def test_get_stats_count_error_returns_zero(self):
		"""A Weaviate count failure degrades to chunk_count 0."""
		self._initialize()
		self.mock_collection.aggregate.over_all.side_effect = RuntimeError("down")

		stats = self.backend.get_stats()

		self.assertEqual(stats["chunk_count"], 0)

	def test_health_check(self):
		"""Health check verifies initialization and server readiness."""
		self._initialize()
		self.mock_client.is_ready.return_value = True

		self.assertEqual(self.backend.health_check(), (True, "Healthy"))

		self.mock_client.is_ready.return_value = False
		self.assertEqual(self.backend.health_check(), (False, "Weaviate server not ready"))

	def test_health_check_not_initialized(self):
		is_healthy, message = WeaviateBackend().health_check()

		self.assertFalse(is_healthy)
		self.assertEqual(message, "Backend not initialized")

	# ------------------------------------------------------------------
	# Advanced config schema
	# ------------------------------------------------------------------
	def test_advanced_config_schema(self):
		"""The advanced-config schema exposes the Weaviate connection knobs."""
		schema = WeaviateBackend.get_advanced_config_schema()
		keys = {entry["key"] for entry in schema}

		self.assertEqual(
			keys,
			{
				"weaviate_host",
				"weaviate_port",
				"weaviate_grpc_port",
				"weaviate_api_key",
				"weaviate_index_name",
				"hybrid_search",
				"weaviate_hybrid_alpha",
			},
		)
		for entry in schema:
			self.assertIn("label", entry)
			self.assertIn("type", entry)
			self.assertIn("default", entry)
			self.assertIn("help_text", entry)

		port_entry = next(e for e in schema if e["key"] == "weaviate_port")
		self.assertEqual(port_entry["type"], "number")
		self.assertEqual(port_entry["default"], 8080)

		api_key_entry = next(e for e in schema if e["key"] == "weaviate_api_key")
		self.assertEqual(api_key_entry["type"], "text")
		self.assertIn("plaintext", api_key_entry["help_text"])

		alpha_entry = next(e for e in schema if e["key"] == "weaviate_hybrid_alpha")
		self.assertEqual(alpha_entry["visible_when"], {"hybrid_search": True})


class TestWeaviateBackendRegistry(unittest.TestCase):
	"""Weaviate resolves through the backend registry as a built-in."""

	def _clear_registry_cache(self):
		if hasattr(frappe.local, "huf_backend_registry"):
			del frappe.local.huf_backend_registry

	def setUp(self):
		self._clear_registry_cache()
		# frappe.get_attr consults local.flags outside install/uninstall.
		frappe.local.flags = frappe._dict()

	def tearDown(self):
		self._clear_registry_cache()

	def test_weaviate_is_builtin(self):
		"""Weaviate is a built-in backend, not hook-registered."""
		from huf.ai.knowledge.backends import _BUILTIN_BACKENDS

		self.assertEqual(
			_BUILTIN_BACKENDS["weaviate"],
			"huf.ai.knowledge.backends.weaviate_backend.WeaviateBackend",
		)

	@patch("huf.ai.knowledge.backends.frappe.get_installed_apps")
	@patch("huf.ai.knowledge.backends.frappe.get_hooks")
	def test_weaviate_resolves_via_get_backend(self, mock_get_hooks, mock_get_installed_apps):
		from huf.ai.knowledge.backends import KnowledgeBackend, _discover_backends, get_backend

		mock_get_installed_apps.return_value = ["huf"]
		mock_get_hooks.return_value = []

		registry = _discover_backends()
		self.assertEqual(registry["weaviate"], "huf.ai.knowledge.backends.weaviate_backend.WeaviateBackend")

		backend_class = get_backend("weaviate")
		self.assertIs(backend_class, WeaviateBackend)
		self.assertTrue(issubclass(backend_class, KnowledgeBackend))
		self.assertEqual(backend_class._backend_type, "weaviate")

	@patch("huf.ai.knowledge.backends.frappe.get_installed_apps")
	@patch("huf.ai.knowledge.backends.frappe.get_hooks")
	def test_hook_cannot_override_weaviate(self, mock_get_hooks, mock_get_installed_apps):
		"""A hook trying to register 'weaviate' is skipped; the built-in wins."""
		from huf.ai.knowledge.backends import _discover_backends

		mock_get_installed_apps.return_value = ["evil_app"]

		def fake_hooks(hook_name, app_name=None):
			if hook_name == "huf_knowledge_backends" and app_name == "evil_app":
				return {"weaviate": ["evil_app.weaviate.OverrideBackend"]}
			return []

		mock_get_hooks.side_effect = fake_hooks

		registry = _discover_backends()
		self.assertEqual(registry["weaviate"], "huf.ai.knowledge.backends.weaviate_backend.WeaviateBackend")


if __name__ == "__main__":
	unittest.main()
