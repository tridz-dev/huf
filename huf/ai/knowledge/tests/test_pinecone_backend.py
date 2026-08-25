# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""Tests for the Pinecone knowledge backend and its built-in registration.

The backend talks to Pinecone through the ``llama-index-vector-stores-pinecone``
adapter and the ``pinecone`` client. Unit tests mock both (no live Pinecone
index required); config validation, namespace isolation, filter building, and
stats normalisation are exercised for real.
"""

import os
import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe

from huf.ai.knowledge.backends import pinecone_backend as pb
from huf.ai.knowledge.backends.pinecone_backend import PineconeBackend


class _FakeExactMatchFilter:
	"""Stand-in for llama_index ExactMatchFilter (records key/value)."""

	def __init__(self, key, value, operator="=="):
		self.key = key
		self.value = value
		self.operator = operator


class _FakeMetadataFilters:
	"""Stand-in for llama_index MetadataFilters (records the filter list)."""

	def __init__(self, filters, condition="and"):
		self.filters = list(filters)
		self.condition = condition


class TestPineconeBackend(unittest.TestCase):
	"""Mocked unit tests for PineconeBackend (no live Pinecone index required)."""

	def setUp(self):
		self.backend = PineconeBackend()

		self._previous_site = getattr(frappe.local, "site", None)
		frappe.local.site = "test_site"
		# frappe.throw/msgprint and logging need these bound outside a site context;
		# restored in tearDown because bench run-tests runs inside a real process with
		# a real frappe.local.flags that the rest of the suite depends on.
		self._previous_flags = getattr(frappe.local, "flags", None)
		frappe.local.flags = frappe._dict()
		self._previous_message_log = getattr(frappe.local, "message_log", None)
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

		if self._previous_flags is None:
			if hasattr(frappe.local, "flags"):
				del frappe.local.flags
		else:
			frappe.local.flags = self._previous_flags

		if self._previous_message_log is None:
			if hasattr(frappe.local, "message_log"):
				del frappe.local.message_log
		else:
			frappe.local.message_log = self._previous_message_log

	def _config(self, **overrides):
		config = {
			"pinecone_api_key": "test-key",
			"pinecone_index_name": "huf-test",
			"vector_dimension": 1536,
		}
		config.update(overrides)
		return config

	def _initialize(self, config=None, index_exists=False):
		"""Initialize the backend with the pinecone client and adapter mocked."""
		config = config or self._config()

		self.mock_pinecone_cls = MagicMock()
		self.mock_client = self.mock_pinecone_cls.return_value
		self.mock_client.has_index.return_value = index_exists
		self.mock_client.describe_index.return_value = SimpleNamespace(
			dimension=int(config.get("vector_dimension") or 1536)
		)
		self.mock_index = self.mock_client.Index.return_value

		self.mock_pvs_cls = MagicMock()
		self.mock_store = self.mock_pvs_cls.return_value
		self.mock_spec_cls = MagicMock()

		# Fake the llama_index filter types so filter assertions stay hermetic.
		fake_types = ModuleType("llama_index.core.vector_stores.types")
		fake_types.ExactMatchFilter = _FakeExactMatchFilter
		fake_types.MetadataFilters = _FakeMetadataFilters

		patchers = [
			patch.object(pb, "PINECONE_DEPS_AVAILABLE", True),
			patch.object(pb, "LLAMAINDEX_AVAILABLE", True),
			patch.object(pb, "Pinecone", self.mock_pinecone_cls, create=True),
			patch.object(pb, "PineconeVectorStore", self.mock_pvs_cls, create=True),
			patch.object(pb, "ServerlessSpec", self.mock_spec_cls, create=True),
			patch("huf.ai.knowledge.backends.llamaindex_base.StorageContext", create=True),
			patch("huf.ai.knowledge.backends.llamaindex_base.Document", create=True),
			patch("huf.ai.knowledge.backends.llamaindex_base.VectorStoreQuery", create=True),
			patch.dict(sys.modules, {"llama_index.core.vector_stores.types": fake_types}),
		]
		for patcher in patchers:
			patcher.start()
			self.addCleanup(patcher.stop)

		self.backend.initialize("test_source", config)

	def test_initialize_creates_index(self):
		"""A missing index goes through create_index with dimension and cosine metric."""
		self._initialize(self._config(vector_dimension=3072))

		self.assertTrue(self.backend._initialized)
		self.assertEqual(self.backend.knowledge_source, "test_source")
		self.assertEqual(self.backend.dimension, 3072)

		self.mock_client.has_index.assert_called_once_with("huf-test")
		self.mock_client.create_index.assert_called_once()
		create_kwargs = self.mock_client.create_index.call_args.kwargs
		self.assertEqual(create_kwargs["name"], "huf-test")
		self.assertEqual(create_kwargs["dimension"], 3072)
		self.assertEqual(create_kwargs["metric"], "cosine")

		# Serverless spec defaults to aws/us-east-1.
		self.mock_spec_cls.assert_called_once_with(cloud="aws", region="us-east-1")

		# Vector store is bound to the index handle and the per-source namespace.
		store_kwargs = self.mock_pvs_cls.call_args.kwargs
		self.assertIs(store_kwargs["pinecone_index"], self.mock_index)
		self.assertEqual(store_kwargs["namespace"], "test_site_test_source")

	def test_initialize_opens_existing_index(self):
		"""An existing index is validated, not recreated."""
		self._initialize(index_exists=True)

		self.mock_client.create_index.assert_not_called()
		self.mock_client.describe_index.assert_called_once_with("huf-test")

	def test_initialize_existing_index_dimension_mismatch(self):
		"""describe_index dimension must match the configured vector dimension."""
		config = self._config(vector_dimension=1536)

		mock_pinecone_cls = MagicMock()
		mock_client = mock_pinecone_cls.return_value
		mock_client.has_index.return_value = True
		mock_client.describe_index.return_value = SimpleNamespace(dimension=768)

		patchers = [
			patch.object(pb, "PINECONE_DEPS_AVAILABLE", True),
			patch.object(pb, "LLAMAINDEX_AVAILABLE", True),
			patch.object(pb, "Pinecone", mock_pinecone_cls, create=True),
			patch.object(pb, "PineconeVectorStore", MagicMock(), create=True),
			patch.object(pb, "ServerlessSpec", MagicMock(), create=True),
		]
		for patcher in patchers:
			patcher.start()
			self.addCleanup(patcher.stop)

		with self.assertRaises(frappe.ValidationError) as ctx:
			self.backend.initialize("test_source", config)
		self.assertIn("768", str(ctx.exception))

	def test_initialize_without_dependencies(self):
		"""Initialization fails with a clear error when the adapter is missing."""
		with patch.object(pb, "PINECONE_DEPS_AVAILABLE", False):
			with self.assertRaises(frappe.ValidationError) as ctx:
				self.backend.initialize("test_source", self._config())
		self.assertIn("llama-index-vector-stores-pinecone", str(ctx.exception))

	def test_validate_config_requires_api_key(self):
		"""Missing API key (config and env) is rejected."""
		with patch.dict(os.environ, {}, clear=False):
			os.environ.pop("PINECONE_API_KEY", None)
			self.backend.config = self._config(pinecone_api_key=None)
			with self.assertRaises(frappe.ValidationError) as ctx:
				self.backend._validate_config()
		self.assertIn("API key", str(ctx.exception))

	def test_validate_config_api_key_from_env(self):
		"""The PINECONE_API_KEY env var is accepted as a fallback."""
		with patch.dict(os.environ, {"PINECONE_API_KEY": "env-key"}):
			self.backend.knowledge_source = "test_source"
			self.backend.config = self._config(pinecone_api_key=None)
			self.backend._validate_config()
		self.assertEqual(self.backend.api_key, "env-key")

	def test_validate_config_rejects_bad_index_name(self):
		for bad_name in ("Bad_Name", "-leading", "trailing-", "", "UPPERCASE"):
			self.backend.knowledge_source = "test_source"
			self.backend.config = self._config(pinecone_index_name=bad_name)
			with self.assertRaises(frappe.ValidationError, msg=bad_name):
				self.backend._validate_config()

	def test_validate_config_rejects_bad_dimension(self):
		self.backend.knowledge_source = "test_source"
		self.backend.config = self._config(vector_dimension=-5)
		with self.assertRaises(frappe.ValidationError):
			self.backend._validate_config()

	def test_validate_config_rejects_bad_cloud(self):
		self.backend.knowledge_source = "test_source"
		self.backend.config = self._config(pinecone_cloud="digitalocean")
		with self.assertRaises(frappe.ValidationError):
			self.backend._validate_config()

	def test_default_namespace_scrubs_site_and_source(self):
		"""The default namespace is per-site, per-source for isolation."""
		self._initialize()

		self.assertEqual(self.backend.namespace, "test_site_test_source")

	def test_config_namespace_override(self):
		"""A configured namespace wins over the default."""
		self._initialize(self._config(pinecone_namespace="shared-ns"))

		self.assertEqual(self.backend.namespace, "shared-ns")
		store_kwargs = self.mock_pvs_cls.call_args.kwargs
		self.assertEqual(store_kwargs["namespace"], "shared-ns")

	def test_add_chunks(self):
		"""Chunks are embedded by HUF and added with scoped metadata."""
		self._initialize()

		chunks = [
			{
				"chunk_id": "chunk_1",
				"input_id": "input_1",
				"input_type": "document",
				"source_title": "Test Document",
				"chunk_index": 0,
				"text": "This is test content for chunk 1.",
				"metadata": {"key": "value"},
			},
			{
				"chunk_id": "chunk_2",
				"input_id": "input_1",
				"input_type": "document",
				"source_title": "Test Document",
				"chunk_index": 1,
				"text": "This is test content for chunk 2.",
				"metadata": {},
			},
		]

		count = self.backend.add_chunks(chunks)

		self.assertEqual(count, 2)
		self.mock_get_embeds.assert_called_once()
		self.mock_store.add.assert_called_once()
		# Both documents were built and passed to the store.
		self.assertEqual(len(self.mock_store.add.call_args[0][0]), 2)

		from huf.ai.knowledge.backends import llamaindex_base

		doc_kwargs = llamaindex_base.Document.call_args_list[0].kwargs
		self.assertEqual(doc_kwargs["id_"], "chunk_1")
		self.assertEqual(doc_kwargs["text"], "This is test content for chunk 1.")
		metadata = doc_kwargs["metadata"]
		self.assertEqual(metadata["site_name"], "test_site")
		self.assertEqual(metadata["knowledge_source"], "test_source")
		self.assertEqual(metadata["input_id"], "input_1")
		self.assertEqual(metadata["key"], "value")

	def test_add_empty_chunks(self):
		"""Adding an empty chunk list is a no-op."""
		self._initialize()

		count = self.backend.add_chunks([])

		self.assertEqual(count, 0)
		self.mock_store.add.assert_not_called()

	def _make_node(self, chunk_id, score=None, **metadata):
		node = MagicMock()
		node.id_ = chunk_id
		node.text = metadata.pop("text", "Test result")
		node.metadata = {
			"chunk_id": chunk_id,
			"source_title": "Test Doc",
			"input_id": "input_1",
			"knowledge_source": "test_source",
			"site_name": "test_site",
			**metadata,
		}
		return node

	def test_search(self):
		"""Search embeds the query via HUF and normalises nodes to ChunkResults."""
		self._initialize()
		self.mock_store.query.return_value = SimpleNamespace(
			nodes=[self._make_node("chunk_1", chunk_index=0, key="value")],
			similarities=[0.9],
			ids=["chunk_1"],
		)

		results = self.backend.search("test query", top_k=5)

		self.assertEqual(len(results), 1)
		self.assertEqual(results[0].text, "Test result")
		self.assertAlmostEqual(results[0].score, 0.9)
		self.assertEqual(results[0].chunk_id, "chunk_1")
		self.assertEqual(results[0].title, "Test Doc")
		self.assertEqual(results[0].source, "input_1")
		self.assertEqual(results[0].metadata["chunk_index"], 0)
		self.assertEqual(results[0].metadata["key"], "value")
		# Scoping keys are stripped from the returned metadata.
		self.assertNotIn("knowledge_source", results[0].metadata)
		self.assertNotIn("site_name", results[0].metadata)

		from huf.ai.knowledge.backends import llamaindex_base

		query_kwargs = llamaindex_base.VectorStoreQuery.call_args.kwargs
		self.assertEqual(query_kwargs["similarity_top_k"], 5)
		# Mandatory site/source scoping filters are always applied.
		filter_keys = [f.key for f in query_kwargs["filters"].filters]
		self.assertIn("site_name", filter_keys)
		self.assertIn("knowledge_source", filter_keys)

	def test_search_with_caller_filters(self):
		"""Caller filters are added on top of the site/source scoping."""
		self._initialize()
		self.mock_store.query.return_value = SimpleNamespace(nodes=[], similarities=[], ids=[])

		self.backend.search("test query", filters={"input_type": "document"})

		from huf.ai.knowledge.backends import llamaindex_base

		query_filters = llamaindex_base.VectorStoreQuery.call_args.kwargs["filters"]
		pairs = {f.key: f.value for f in query_filters.filters}
		self.assertEqual(pairs["site_name"], "test_site")
		self.assertEqual(pairs["knowledge_source"], "test_source")
		self.assertEqual(pairs["input_type"], "document")

	def test_search_empty_query(self):
		"""An empty query short-circuits without touching the store."""
		self._initialize()

		self.assertEqual(self.backend.search(""), [])
		self.assertEqual(self.backend.search("   "), [])
		self.mock_store.query.assert_not_called()

	def test_search_not_initialized(self):
		with self.assertRaises(RuntimeError):
			PineconeBackend().search("test query")

	def test_delete_chunks(self):
		"""Deletion counts matching vectors first, then deletes by metadata filter."""
		self._initialize()
		self.mock_store.get_nodes.return_value = [MagicMock(), MagicMock()]

		deleted = self.backend.delete_chunks("input_1")

		self.assertEqual(deleted, 2)
		count_kwargs = self.mock_store.get_nodes.call_args.kwargs
		self.assertEqual(count_kwargs["limit"], pb.COUNT_QUERY_LIMIT)
		filter_keys = [f.key for f in count_kwargs["filters"].filters]
		self.assertIn("input_id", filter_keys)
		self.mock_store.delete_nodes.assert_called_once()

	def test_delete_chunks_none_matching(self):
		"""No matching vectors means no delete call and a zero count."""
		self._initialize()
		self.mock_store.get_nodes.return_value = []

		deleted = self.backend.delete_chunks("input_1")

		self.assertEqual(deleted, 0)
		self.mock_store.delete_nodes.assert_not_called()

	def test_delete_chunks_error_returns_zero(self):
		"""A Pinecone failure during delete is logged and reported as 0."""
		self._initialize()
		self.mock_store.get_nodes.side_effect = RuntimeError("boom")

		self.assertEqual(self.backend.delete_chunks("input_1"), 0)

	def test_clear(self):
		"""Clear deletes every vector in this source's namespace."""
		self._initialize()

		self.backend.clear()

		self.mock_store.clear.assert_called_once()

	def test_clear_not_initialized(self):
		with self.assertRaises(RuntimeError):
			PineconeBackend().clear()

	def test_get_stats(self):
		"""Stats read describe_index_stats; chunk_count is namespace-scoped."""
		self._initialize()
		self.mock_store.client.describe_index_stats.return_value = SimpleNamespace(
			total_vector_count=10,
			namespaces={"test_site_test_source": SimpleNamespace(vector_count=7)},
		)

		stats = self.backend.get_stats()

		self.assertEqual(stats["backend_type"], "pinecone")
		self.assertEqual(stats["knowledge_source"], "test_source")
		self.assertEqual(stats["index_name"], "huf-test")
		self.assertEqual(stats["namespace"], "test_site_test_source")
		self.assertTrue(stats["initialized"])
		self.assertEqual(stats["vector_dimension"], 1536)
		self.assertEqual(stats["index_vector_count"], 10)
		self.assertEqual(stats["chunk_count"], 7)

	def test_get_stats_dict_style_response(self):
		"""Dict-style describe_index_stats responses are also accepted."""
		self._initialize()
		self.mock_store.client.describe_index_stats.return_value = {
			"total_vector_count": 4,
			"namespaces": {"test_site_test_source": {"vector_count": 3}},
		}

		stats = self.backend.get_stats()

		self.assertEqual(stats["index_vector_count"], 4)
		self.assertEqual(stats["chunk_count"], 3)

	def test_get_stats_not_initialized(self):
		"""Uninitialized stats report zeros without touching the client."""
		stats = PineconeBackend().get_stats()

		self.assertEqual(stats["backend_type"], "pinecone")
		self.assertFalse(stats["initialized"])
		self.assertEqual(stats["chunk_count"], 0)

	def test_health_check(self):
		"""Health check verifies initialization and index readability."""
		self._initialize()
		self.mock_store.client.describe_index_stats.return_value = SimpleNamespace(
			total_vector_count=0, namespaces={}
		)

		is_healthy, message = self.backend.health_check()

		self.assertTrue(is_healthy)
		self.assertEqual(message, "Healthy")

	def test_health_check_not_initialized(self):
		"""Health check reports unhealthy before initialization."""
		is_healthy, message = PineconeBackend().health_check()

		self.assertFalse(is_healthy)
		self.assertEqual(message, "Backend not initialized")

	def test_supports_flags(self):
		"""Pinecone supports metadata filters but not hybrid search."""
		backend = PineconeBackend()
		self.assertTrue(backend.supports_filters())
		self.assertFalse(backend.supports_hybrid_search())

	def test_advanced_config_schema(self):
		"""The advanced-config schema exposes the Pinecone connection knobs."""
		schema = PineconeBackend.get_advanced_config_schema()
		keys = {entry["key"] for entry in schema}

		self.assertEqual(
			keys,
			{
				"pinecone_api_key",
				"pinecone_index_name",
				"pinecone_namespace",
				"pinecone_cloud",
				"pinecone_region",
			},
		)
		for entry in schema:
			self.assertIn("label", entry)
			self.assertIn("type", entry)
			self.assertIn("default", entry)
			self.assertIn("help_text", entry)

		api_key_entry = next(e for e in schema if e["key"] == "pinecone_api_key")
		self.assertIn("plaintext", api_key_entry["help_text"])

		cloud_entry = next(e for e in schema if e["key"] == "pinecone_cloud")
		self.assertEqual(cloud_entry["type"], "select")
		self.assertEqual(cloud_entry["options"], ["aws", "gcp", "azure"])


class TestPineconeBackendRegistry(unittest.TestCase):
	"""Pinecone resolves through the backend registry as a built-in."""

	def _clear_registry_cache(self):
		if hasattr(frappe.local, "huf_backend_registry"):
			del frappe.local.huf_backend_registry

	def setUp(self):
		self._clear_registry_cache()
		# frappe.get_attr consults local.flags outside install/uninstall; restored in
		# tearDown because bench run-tests runs inside a real process with a real
		# frappe.local.flags that the rest of the suite depends on.
		self._previous_flags = getattr(frappe.local, "flags", None)
		frappe.local.flags = frappe._dict()

	def tearDown(self):
		if self._previous_flags is None:
			if hasattr(frappe.local, "flags"):
				del frappe.local.flags
		else:
			frappe.local.flags = self._previous_flags

		self._clear_registry_cache()

	def test_pinecone_is_builtin(self):
		"""Pinecone is a built-in backend, not hook-registered."""
		from huf.ai.knowledge.backends import _BUILTIN_BACKENDS

		self.assertEqual(
			_BUILTIN_BACKENDS["pinecone"],
			"huf.ai.knowledge.backends.pinecone_backend.PineconeBackend",
		)

	@patch("huf.ai.knowledge.backends.frappe.get_installed_apps")
	@patch("huf.ai.knowledge.backends.frappe.get_hooks")
	def test_pinecone_resolves_via_get_backend(self, mock_get_hooks, mock_get_installed_apps):
		from huf.ai.knowledge.backends import KnowledgeBackend, _discover_backends, get_backend

		mock_get_installed_apps.return_value = ["huf"]
		mock_get_hooks.return_value = []

		registry = _discover_backends()
		self.assertEqual(registry["pinecone"], "huf.ai.knowledge.backends.pinecone_backend.PineconeBackend")

		backend_class = get_backend("pinecone")
		self.assertIs(backend_class, PineconeBackend)
		self.assertTrue(issubclass(backend_class, KnowledgeBackend))
		self.assertEqual(backend_class._backend_type, "pinecone")

	@patch("huf.ai.knowledge.backends.frappe.get_installed_apps")
	@patch("huf.ai.knowledge.backends.frappe.get_hooks")
	def test_hook_cannot_override_pinecone(self, mock_get_hooks, mock_get_installed_apps):
		"""A hook trying to register 'pinecone' is skipped; the built-in wins."""
		from huf.ai.knowledge.backends import _discover_backends

		mock_get_installed_apps.return_value = ["evil_app"]

		def fake_hooks(hook_name, app_name=None):
			if hook_name == "huf_knowledge_backends" and app_name == "evil_app":
				return {"pinecone": ["evil_app.pinecone.OverrideBackend"]}
			return []

		mock_get_hooks.side_effect = fake_hooks

		registry = _discover_backends()
		self.assertEqual(registry["pinecone"], "huf.ai.knowledge.backends.pinecone_backend.PineconeBackend")


if __name__ == "__main__":
	unittest.main()
