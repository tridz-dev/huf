# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""Tests for the Zvec knowledge backend and its built-in registration.

The backend talks to the embedded ``zvec`` package directly. Unit tests mock
the zvec module and its Collection (no on-disk collection required); the
filter-expression and score-normalisation logic is exercised for real.
"""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe

from huf.ai.knowledge.backends import zvec_backend as zb
from huf.ai.knowledge.backends.zvec_backend import ZvecBackend


class TestZvecBackend(unittest.TestCase):
	"""Mocked unit tests for ZvecBackend (no live zvec collection required)."""

	def setUp(self):
		self.backend = ZvecBackend()

		self._previous_site = getattr(frappe.local, "site", None)
		frappe.local.site = "test_site"
		# frappe.throw/msgprint and logging need these bound outside a site context,
		# and restored because bench run-tests runs inside a real frappe process
		# whose frappe.local.flags carries state the rest of the suite depends on.
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

	def _initialize(self, config=None, collection_exists=False):
		"""Initialize the backend with the zvec module and Collection mocked."""
		config = config or {"vector_dimension": 1536}

		self.mock_zvec = MagicMock()
		self.mock_collection = MagicMock()
		# Opened collections are validated against the configured dimension.
		vector_field = MagicMock()
		vector_field.name = "embedding"
		vector_field.dimension = int(config.get("vector_dimension") or 1536)
		self.mock_collection.schema.vectors = [vector_field]
		self.mock_zvec.create_and_open.return_value = self.mock_collection
		self.mock_zvec.open.return_value = self.mock_collection
		# MetricType.COSINE etc. are looked up on the mocked module.
		self.mock_zvec.MetricType.COSINE = "COSINE"
		self.mock_zvec.MetricType.L2 = "L2"
		self.mock_zvec.MetricType.IP = "IP"

		patchers = [
			patch.object(zb, "ZVEC_AVAILABLE", True),
			patch.object(zb, "zvec", self.mock_zvec, create=True),
			patch.object(zb, "get_files_path", return_value="/tmp/files"),
			patch("os.makedirs"),
			patch("os.path.exists", return_value=collection_exists),
		]
		for patcher in patchers:
			patcher.start()
			self.addCleanup(patcher.stop)

		self.backend.initialize("test_source", config)

	def test_initialize_creates_collection(self):
		"""A missing collection path goes through create_and_open with a schema."""
		self._initialize({"vector_dimension": 3072, "zvec_metric_type": "cosine"})

		self.assertTrue(self.backend._initialized)
		self.assertEqual(self.backend.knowledge_source, "test_source")
		self.assertEqual(self.backend.dimension, 3072)
		self.assertTrue(self.backend.db_path.endswith(os.path.join("knowledge", "test_source.zvec")))

		self.mock_zvec.create_and_open.assert_called_once()
		self.mock_zvec.open.assert_not_called()
		self.assertEqual(self.mock_zvec.create_and_open.call_args.kwargs["path"], self.backend.db_path)

		# Vector schema uses the configured dimension and HNSW params.
		vector_schema = self.mock_zvec.VectorSchema.call_args
		self.assertEqual(vector_schema[0][0], "embedding")
		self.assertEqual(vector_schema[0][2], 3072)

	def test_initialize_opens_existing_collection(self):
		"""An existing collection path is opened, not recreated."""
		self._initialize(collection_exists=True)

		self.mock_zvec.open.assert_called_once_with(self.backend.db_path)
		self.mock_zvec.create_and_open.assert_not_called()

	def test_initialize_without_dependencies(self):
		"""Initialization fails with a clear error when zvec is missing."""
		with patch.object(zb, "ZVEC_AVAILABLE", False):
			with self.assertRaises(frappe.ValidationError) as ctx:
				self.backend.initialize("test_source", {})
		self.assertIn("zvec>=0.2.1", str(ctx.exception))

	def test_validate_config_rejects_bad_dimension(self):
		self.backend.config = {"vector_dimension": -5}
		with self.assertRaises(frappe.ValidationError):
			self.backend._validate_config()

	def test_validate_config_rejects_bad_metric(self):
		self.backend.config = {"vector_dimension": 1536, "zvec_metric_type": "manhattan"}
		with self.assertRaises(frappe.ValidationError):
			self.backend._validate_config()

	def test_add_chunks(self):
		"""Chunks are embedded by HUF and upserted as zvec Docs."""
		self._initialize()
		self.mock_collection.upsert.return_value = [MagicMock(ok=lambda: True), MagicMock(ok=lambda: True)]

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
		self.mock_zvec.Doc.assert_called()
		self.mock_collection.upsert.assert_called_once()
		# Both docs were built and passed to upsert.
		self.assertEqual(len(self.mock_collection.upsert.call_args[0][0]), 2)

		doc_kwargs = self.mock_zvec.Doc.call_args_list[0].kwargs
		self.assertEqual(doc_kwargs["id"], "chunk_1")
		self.assertEqual(doc_kwargs["fields"]["input_id"], "input_1")
		self.assertEqual(doc_kwargs["fields"]["text"], "This is test content for chunk 1.")

	def test_add_empty_chunks(self):
		"""Adding an empty chunk list is a no-op."""
		self._initialize()

		count = self.backend.add_chunks([])

		self.assertEqual(count, 0)
		self.mock_collection.upsert.assert_not_called()

	def _make_doc(self, doc_id, score, **fields):
		doc = MagicMock()
		doc.id = doc_id
		doc.score = score
		doc.fields = fields
		return doc

	def test_search(self):
		"""Search embeds the query via HUF and normalises cosine distance to score."""
		self._initialize()
		self.mock_collection.query.return_value = [
			self._make_doc(
				"chunk_1",
				0.05,
				text="Test result",
				source_title="Test Doc",
				input_id="input_1",
				input_type="document",
				chunk_index=0,
				metadata_json='{"key": "value"}',
			)
		]

		results = self.backend.search("test query", top_k=5)

		self.assertEqual(len(results), 1)
		self.assertEqual(results[0].text, "Test result")
		# Cosine: score = 1 - distance.
		self.assertAlmostEqual(results[0].score, 0.95)
		self.assertEqual(results[0].chunk_id, "chunk_1")
		self.assertEqual(results[0].title, "Test Doc")
		self.assertEqual(results[0].source, "input_1")
		self.assertEqual(results[0].metadata["key"], "value")
		self.assertEqual(results[0].metadata["chunk_index"], 0)
		self.assertEqual(results[0].metadata["input_type"], "document")

		query_kwargs = self.mock_collection.query.call_args.kwargs
		self.assertEqual(query_kwargs["topk"], 5)
		self.assertNotIn("filter", query_kwargs)
		self.assertIn("queries", query_kwargs)

	def test_search_with_caller_filters(self):
		"""Caller filters become a quoted, single-= zvec filter expression."""
		self._initialize()
		self.mock_collection.query.return_value = []

		self.backend.search("test query", filters={"input_type": "document", "chunk_index": 2})

		filter_expr = self.mock_collection.query.call_args.kwargs["filter"]
		self.assertIn("input_type = 'document'", filter_expr)
		self.assertIn("chunk_index = 2", filter_expr)
		self.assertIn(" AND ", filter_expr)
		self.assertNotIn("==", filter_expr)

	def test_search_filter_escapes_quotes(self):
		"""Single quotes in filter values are backslash-escaped (no injection)."""
		self._initialize()
		self.mock_collection.query.return_value = []

		self.backend.search("test query", filters={"input_id": "x' OR '1'='1"})

		filter_expr = self.mock_collection.query.call_args.kwargs["filter"]
		self.assertEqual(filter_expr, "input_id = 'x\\' OR \\'1\\'=\\'1'")

	def test_search_filter_rejects_unknown_field(self):
		"""Filter keys outside the declared scalar fields are rejected."""
		self._initialize()

		with self.assertRaises(frappe.ValidationError):
			self.backend.search("test query", filters={"1=1 OR input_id": "x"})

		with self.assertRaises(frappe.ValidationError):
			self.backend.search("test query", filters={"metadata_json": "{}"})

	def test_quote_filter_value(self):
		"""Literal rendering: strings quoted, bools/numbers bare, trailing backslash rejected."""
		self.assertEqual(zb._quote_filter_value("abc"), "'abc'")
		self.assertEqual(zb._quote_filter_value("o'brien"), "'o\\'brien'")
		self.assertEqual(zb._quote_filter_value(True), "true")
		self.assertEqual(zb._quote_filter_value(False), "false")
		self.assertEqual(zb._quote_filter_value(7), "7")
		self.assertEqual(zb._quote_filter_value(1.5), "1.5")
		with self.assertRaises(frappe.ValidationError):
			zb._quote_filter_value("ends with backslash\\")

	def test_search_empty_query(self):
		"""An empty query short-circuits without touching the collection."""
		self._initialize()

		self.assertEqual(self.backend.search(""), [])
		self.assertEqual(self.backend.search("   "), [])
		self.mock_collection.query.assert_not_called()

	def test_score_normalisation_by_metric(self):
		"""Cosine distance maps to 1-d; L2 to 1/(1+d); IP is passed through."""
		backend = ZvecBackend()
		backend.metric_type = "cosine"
		self.assertAlmostEqual(backend._score_from_distance(0.0), 1.0)
		self.assertAlmostEqual(backend._score_from_distance(2.0), -1.0)
		backend.metric_type = "l2"
		self.assertAlmostEqual(backend._score_from_distance(0.0), 1.0)
		self.assertAlmostEqual(backend._score_from_distance(1.0), 0.5)
		backend.metric_type = "ip"
		self.assertAlmostEqual(backend._score_from_distance(0.7), 0.7)

	def test_delete_chunks(self):
		"""Deletion counts matching docs via a filter-only query, then deletes."""
		self._initialize()
		self.mock_collection.stats = SimpleNamespace(doc_count=10)
		self.mock_collection.query.return_value = [
			self._make_doc("chunk_1", 0.0),
			self._make_doc("chunk_2", 0.0),
		]

		deleted = self.backend.delete_chunks("input_1")

		self.assertEqual(deleted, 2)
		count_kwargs = self.mock_collection.query.call_args.kwargs
		self.assertEqual(count_kwargs["filter"], "input_id = 'input_1'")
		self.assertEqual(count_kwargs["topk"], 10)
		self.assertNotIn("queries", count_kwargs)
		self.mock_collection.delete_by_filter.assert_called_once_with("input_id = 'input_1'")

	def test_delete_chunks_escapes_input_id(self):
		"""Quotes in the input_id cannot break out of the delete filter."""
		self._initialize()
		self.mock_collection.stats = SimpleNamespace(doc_count=0)
		self.mock_collection.query.return_value = []

		deleted = self.backend.delete_chunks("x' OR '1'='1")

		self.assertEqual(deleted, 0)
		filter_expr = self.mock_collection.query.call_args.kwargs["filter"]
		self.assertEqual(filter_expr, "input_id = 'x\\' OR \\'1\\'=\\'1'")
		self.mock_collection.delete_by_filter.assert_not_called()

	def test_delete_chunks_error_returns_zero(self):
		"""A zvec failure during delete is logged and reported as 0."""
		self._initialize()
		self.mock_collection.stats = SimpleNamespace(doc_count=5)
		self.mock_collection.query.side_effect = RuntimeError("boom")

		self.assertEqual(self.backend.delete_chunks("input_1"), 0)

	def test_clear(self):
		"""Clear destroys the on-disk collection and recreates it empty."""
		self._initialize()

		self.backend.clear()

		self.mock_collection.destroy.assert_called_once()
		self.assertEqual(self.mock_zvec.create_and_open.call_count, 2)

	def test_get_stats(self):
		"""Stats report backend_type and doc_count from collection stats."""
		self._initialize()
		self.mock_collection.stats = SimpleNamespace(doc_count=7)

		stats = self.backend.get_stats()

		self.assertEqual(stats["backend_type"], "zvec")
		self.assertEqual(stats["knowledge_source"], "test_source")
		self.assertTrue(stats["initialized"])
		self.assertEqual(stats["vector_dimension"], 1536)
		self.assertEqual(stats["metric_type"], "cosine")
		self.assertEqual(stats["chunk_count"], 7)

	def test_health_check(self):
		"""Health check verifies initialization and collection readability."""
		self._initialize()
		self.mock_collection.stats = SimpleNamespace(doc_count=0)

		with patch("os.path.exists", return_value=True):
			is_healthy, message = self.backend.health_check()

		self.assertTrue(is_healthy)
		self.assertEqual(message, "Healthy")

	def test_health_check_not_initialized(self):
		"""Health check reports unhealthy before initialization."""
		is_healthy, message = ZvecBackend().health_check()

		self.assertFalse(is_healthy)
		self.assertEqual(message, "Backend not initialized")

	def test_supports_flags(self):
		"""zvec supports metadata filters but not hybrid search."""
		backend = ZvecBackend()
		self.assertTrue(backend.supports_filters())
		self.assertFalse(backend.supports_hybrid_search())

	def test_advanced_config_schema(self):
		"""The advanced-config schema exposes the zvec tuning knobs."""
		schema = ZvecBackend.get_advanced_config_schema()
		keys = {entry["key"] for entry in schema}

		self.assertEqual(
			keys,
			{"zvec_metric_type", "zvec_hnsw_m", "zvec_hnsw_ef_construction", "zvec_hnsw_ef"},
		)
		for entry in schema:
			self.assertIn("label", entry)
			self.assertIn("type", entry)
			self.assertIn("default", entry)
			self.assertIn("help_text", entry)

		metric_entry = next(e for e in schema if e["key"] == "zvec_metric_type")
		self.assertEqual(metric_entry["type"], "select")
		self.assertEqual(metric_entry["options"], ["cosine", "l2", "ip"])

		m_entry = next(e for e in schema if e["key"] == "zvec_hnsw_m")
		self.assertEqual(m_entry["type"], "number")
		self.assertEqual(m_entry["min"], 2)
		self.assertEqual(m_entry["max"], 100)


class TestZvecBackendRegistry(unittest.TestCase):
	"""Zvec resolves through the backend registry as a built-in."""

	def _clear_registry_cache(self):
		if hasattr(frappe.local, "huf_backend_registry"):
			del frappe.local.huf_backend_registry

	def setUp(self):
		self._clear_registry_cache()
		# frappe.get_attr consults local.flags outside install/uninstall,
		# and restored because bench run-tests runs inside a real frappe process.
		self._previous_flags = getattr(frappe.local, "flags", None)
		frappe.local.flags = frappe._dict()

	def tearDown(self):
		if self._previous_flags is None:
			if hasattr(frappe.local, "flags"):
				del frappe.local.flags
		else:
			frappe.local.flags = self._previous_flags

		self._clear_registry_cache()

	def test_zvec_is_builtin(self):
		"""Zvec is a built-in backend, not hook-registered."""
		from huf.ai.knowledge.backends import _BUILTIN_BACKENDS

		self.assertEqual(
			_BUILTIN_BACKENDS["zvec"],
			"huf.ai.knowledge.backends.zvec_backend.ZvecBackend",
		)

	@patch("huf.ai.knowledge.backends.frappe.get_installed_apps")
	@patch("huf.ai.knowledge.backends.frappe.get_hooks")
	def test_zvec_resolves_via_get_backend(self, mock_get_hooks, mock_get_installed_apps):
		from huf.ai.knowledge.backends import KnowledgeBackend, _discover_backends, get_backend

		mock_get_installed_apps.return_value = ["huf"]
		mock_get_hooks.return_value = []

		registry = _discover_backends()
		self.assertEqual(registry["zvec"], "huf.ai.knowledge.backends.zvec_backend.ZvecBackend")

		backend_class = get_backend("zvec")
		self.assertIs(backend_class, ZvecBackend)
		self.assertTrue(issubclass(backend_class, KnowledgeBackend))
		self.assertEqual(backend_class._backend_type, "zvec")

	@patch("huf.ai.knowledge.backends.frappe.get_installed_apps")
	@patch("huf.ai.knowledge.backends.frappe.get_hooks")
	def test_hook_cannot_override_zvec(self, mock_get_hooks, mock_get_installed_apps):
		"""A hook trying to register 'zvec' is skipped; the built-in wins."""
		from huf.ai.knowledge.backends import _discover_backends

		mock_get_installed_apps.return_value = ["evil_app"]

		def fake_hooks(hook_name, app_name=None):
			if hook_name == "huf_knowledge_backends" and app_name == "evil_app":
				return {"zvec": ["evil_app.zvec.OverrideBackend"]}
			return []

		mock_get_hooks.side_effect = fake_hooks

		registry = _discover_backends()
		self.assertEqual(registry["zvec"], "huf.ai.knowledge.backends.zvec_backend.ZvecBackend")


if __name__ == "__main__":
	unittest.main()
