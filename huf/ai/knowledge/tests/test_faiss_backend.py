# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""Tests for the FAISS knowledge backend and its built-in registration.

The backend uses the LlamaIndex FAISS adapter (in-memory index, explicit
persistence) plus a pickled chunk sidecar for text/metadata. Unit tests mock
the ``faiss`` module, ``FaissVectorStore``, and the filesystem; the sidecar
mapping, score normalisation, and delete-by-rebuild logic run for real.
"""

import os
import pickle
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, mock_open, patch

import frappe

from huf.ai.knowledge.backends import faiss_backend as fb
from huf.ai.knowledge.backends.faiss_backend import FaissBackend


class TestFaissBackend(unittest.TestCase):
	"""Mocked unit tests for FaissBackend (no live FAISS index required)."""

	def setUp(self):
		self.backend = FaissBackend()

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

	def _initialize(self, config=None, index_exists=False, sidecar=None):
		"""Initialize the backend with faiss, FaissVectorStore, and the FS mocked."""
		config = config or {"vector_dimension": 1536}
		dimension = int(config.get("vector_dimension") or 1536)

		self.mock_faiss = MagicMock()
		self.mock_index = MagicMock()
		self.mock_index.d = dimension
		self.mock_index.ntotal = 0
		self.mock_index.is_trained = True
		self.mock_faiss.IndexFlatL2.return_value = self.mock_index
		self.mock_faiss.IndexIVFFlat.return_value = self.mock_index

		self.mock_vector_store = MagicMock()
		self.mock_vector_store.client = self.mock_index
		# The adapter assigns sequential positional ids starting at ntotal.
		self.mock_vector_store.add.side_effect = lambda docs, **_: [str(i) for i in range(len(docs))]
		self.mock_store_class = MagicMock(return_value=self.mock_vector_store)
		self.mock_store_class.from_persist_path.return_value = self.mock_vector_store

		self.mock_file_open = mock_open(read_data=pickle.dumps(sidecar or {}))

		patchers = [
			patch.object(fb, "FAISS_DEPS_AVAILABLE", True),
			patch.object(fb, "faiss", self.mock_faiss, create=True),
			patch.object(fb, "FaissVectorStore", self.mock_store_class, create=True),
			patch.object(fb, "StorageContext", MagicMock(), create=True),
			patch.object(fb, "get_files_path", return_value="/tmp/files"),
			patch("os.makedirs"),
			patch("os.path.exists", return_value=index_exists),
			patch("builtins.open", self.mock_file_open),
		]
		for patcher in patchers:
			patcher.start()
			self.addCleanup(patcher.stop)

		self.backend.initialize("test_source", config)

	def _chunks(self, count=2, input_id="input_1"):
		return [
			{
				"chunk_id": f"chunk_{index}",
				"input_id": input_id,
				"input_type": "document",
				"source_title": "Test Document",
				"chunk_index": index,
				"text": f"This is test content for chunk {index}.",
				"metadata": {"key": "value"},
			}
			for index in range(count)
		]

	def test_initialize_creates_index(self):
		"""A missing index file builds a fresh IndexFlatL2 via the adapter."""
		self._initialize({"vector_dimension": 3072})

		self.assertTrue(self.backend._initialized)
		self.assertEqual(self.backend.knowledge_source, "test_source")
		self.assertEqual(self.backend.dimension, 3072)
		self.assertTrue(self.backend.persist_dir.endswith(os.path.join("knowledge", "test_source_faiss")))
		self.assertTrue(self.backend._index_file.endswith("default__vector_store.json"))

		self.mock_faiss.IndexFlatL2.assert_called_once_with(3072)
		self.mock_store_class.assert_called_once_with(faiss_index=self.mock_index)
		self.mock_store_class.from_persist_path.assert_not_called()
		self.assertEqual(self.backend._chunk_store, {})

	def test_initialize_loads_existing_index(self):
		"""An existing index file is loaded with its chunk sidecar."""
		sidecar = {
			"0": {
				"chunk_id": "chunk_1",
				"text": "persisted text",
				"metadata": {"input_id": "input_1"},
				"embedding": [0.1] * 1536,
			}
		}
		self._initialize(index_exists=True, sidecar=sidecar)

		self.mock_store_class.from_persist_path.assert_called_once_with(self.backend._index_file)
		self.mock_faiss.IndexFlatL2.assert_not_called()
		self.assertEqual(self.backend._chunk_store, sidecar)

	def test_initialize_rejects_dimension_mismatch(self):
		"""A persisted index with a different dimension fails loudly."""
		with (
			patch.object(fb, "FAISS_DEPS_AVAILABLE", True),
			patch.object(fb, "faiss", MagicMock(), create=True),
			patch.object(fb, "FaissVectorStore", MagicMock(), create=True),
			patch.object(fb, "StorageContext", MagicMock(), create=True),
			patch.object(fb, "get_files_path", return_value="/tmp/files"),
			patch("os.makedirs"),
			patch("os.path.exists", return_value=True),
		):
			store = MagicMock()
			store.client.d = 768
			fb.FaissVectorStore.from_persist_path.return_value = store
			with self.assertRaises(frappe.ValidationError) as ctx:
				self.backend.initialize("test_source", {"vector_dimension": 1536})
		self.assertIn("dimension 768", str(ctx.exception))

	def test_initialize_without_dependencies(self):
		"""Initialization fails with a clear error when faiss deps are missing."""
		with patch.object(fb, "FAISS_DEPS_AVAILABLE", False):
			with self.assertRaises(frappe.ValidationError) as ctx:
				self.backend.initialize("test_source", {})
		self.assertIn("llama-index-vector-stores-faiss", str(ctx.exception))

	def test_validate_config_rejects_bad_dimension(self):
		self.backend.knowledge_source = "test_source"
		self.backend.config = {"vector_dimension": -5}
		with (
			patch.object(fb, "get_files_path", return_value="/tmp/files"),
			self.assertRaises(frappe.ValidationError),
		):
			self.backend._validate_config()

	def test_validate_config_rejects_bad_index_type(self):
		self.backend.knowledge_source = "test_source"
		self.backend.config = {"vector_dimension": 1536, "faiss_index_type": "hnsw"}
		with (
			patch.object(fb, "get_files_path", return_value="/tmp/files"),
			self.assertRaises(frappe.ValidationError),
		):
			self.backend._validate_config()

	def test_validate_config_rejects_bad_nlist(self):
		self.backend.knowledge_source = "test_source"
		self.backend.config = {"vector_dimension": 1536, "faiss_index_type": "ivf", "faiss_nlist": -3}
		with (
			patch.object(fb, "get_files_path", return_value="/tmp/files"),
			self.assertRaises(frappe.ValidationError),
		):
			self.backend._validate_config()

	def test_add_chunks(self):
		"""Chunks are embedded by HUF, added to the index, sidecarred, persisted."""
		self._initialize()

		count = self.backend.add_chunks(self._chunks(2))

		self.assertEqual(count, 2)
		self.mock_get_embeds.assert_called_once()
		self.mock_vector_store.add.assert_called_once()
		documents = self.mock_vector_store.add.call_args[0][0]
		self.assertEqual(len(documents), 2)

		# Positional ids returned by the adapter map to sidecar records.
		self.assertEqual(set(self.backend._chunk_store), {"0", "1"})
		record = self.backend._chunk_store["0"]
		self.assertEqual(record["chunk_id"], "chunk_0")
		self.assertEqual(record["text"], "This is test content for chunk 0.")
		self.assertEqual(record["embedding"], [0.1] * 1536)

		# Metadata carries the HUF scoping keys.
		metadata = record["metadata"]
		self.assertEqual(metadata["site_name"], "test_site")
		self.assertEqual(metadata["knowledge_source"], "test_source")
		self.assertEqual(metadata["input_id"], "input_1")
		self.assertEqual(metadata["key"], "value")

		# Index and sidecar are persisted after the write.
		self.mock_vector_store.persist.assert_called_once_with(persist_path=self.backend._index_file)
		self.mock_file_open.assert_called_with(self.backend._sidecar_file, "wb")

	def test_add_empty_chunks(self):
		"""Adding an empty chunk list is a no-op."""
		self._initialize()

		count = self.backend.add_chunks([])

		self.assertEqual(count, 0)
		self.mock_vector_store.add.assert_not_called()
		self.mock_vector_store.persist.assert_not_called()

	def test_add_chunks_trains_ivf_index(self):
		"""An untrained IVF index is trained on the first batch before adding."""
		self._initialize({"vector_dimension": 1536, "faiss_index_type": "ivf", "faiss_nlist": 5})
		self.mock_index.is_trained = False

		self.backend.add_chunks(self._chunks(2))

		self.mock_faiss.IndexIVFFlat.assert_called_once_with(self.mock_index, 1536, 5)
		self.mock_index.train.assert_called_once()
		self.mock_vector_store.add.assert_called_once()

	def test_search(self):
		"""Search embeds the query via HUF and maps positional ids to chunks."""
		self._initialize()
		self.backend.add_chunks(self._chunks(2))
		self.mock_vector_store.query.return_value = SimpleNamespace(ids=["0", "1"], similarities=[0.0, 1.0])

		results = self.backend.search("test query", top_k=5)

		self.assertEqual(len(results), 2)
		self.assertEqual(results[0].chunk_id, "chunk_0")
		self.assertEqual(results[0].text, "This is test content for chunk 0.")
		self.assertEqual(results[0].title, "Test Document")
		self.assertEqual(results[0].source, "input_1")
		# L2 distance 0.0 -> score 1.0; distance 1.0 -> score 0.5.
		self.assertAlmostEqual(results[0].score, 1.0)
		self.assertAlmostEqual(results[1].score, 0.5)
		# Scoping keys are stripped from the returned metadata.
		self.assertNotIn("site_name", results[0].metadata)
		self.assertNotIn("knowledge_source", results[0].metadata)
		self.assertEqual(results[0].metadata["key"], "value")

		# No filters are ever passed to the FAISS adapter (it would raise).
		query_obj = self.mock_vector_store.query.call_args[0][0]
		self.assertIsNone(query_obj.filters)
		self.assertEqual(query_obj.similarity_top_k, 5)

	def test_search_ignores_filters(self):
		"""Caller filters are ignored: FAISS cannot evaluate metadata filters."""
		self._initialize()
		self.backend.add_chunks(self._chunks(1))
		self.mock_vector_store.query.return_value = SimpleNamespace(ids=["0"], similarities=[0.25])

		results = self.backend.search("test query", filters={"input_id": "other"})

		self.assertEqual(len(results), 1)
		query_obj = self.mock_vector_store.query.call_args[0][0]
		self.assertIsNone(query_obj.filters)

	def test_search_empty_query(self):
		"""An empty query short-circuits without touching the index."""
		self._initialize()

		self.assertEqual(self.backend.search(""), [])
		self.assertEqual(self.backend.search("   "), [])
		self.mock_vector_store.query.assert_not_called()

	def test_search_skips_unknown_ids(self):
		"""Index hits without a sidecar record are dropped from the results."""
		self._initialize()
		self.backend.add_chunks(self._chunks(1))
		self.mock_vector_store.query.return_value = SimpleNamespace(ids=["0", "99"], similarities=[0.0, 0.0])

		results = self.backend.search("test query")

		self.assertEqual(len(results), 1)
		self.assertEqual(results[0].chunk_id, "chunk_0")

	def test_build_search_filters_returns_none(self):
		"""Filters are never built: FAISS relies on source-per-index isolation."""
		self.assertIsNone(FaissBackend()._build_search_filters({"input_id": "x"}))
		self.assertIsNone(FaissBackend()._build_search_filters(None))

	def test_delete_chunks_rebuilds_index(self):
		"""Scoped delete drops matching sidecar records and rebuilds the index."""
		self._initialize()
		self.backend.add_chunks(self._chunks(2))
		# A third chunk from another input survives the delete.
		survivor = {
			"chunk_id": "chunk_9",
			"text": "other input",
			"metadata": {"input_id": "input_2"},
			"embedding": [0.2] * 1536,
		}
		self.backend._chunk_store["2"] = survivor
		self.mock_vector_store.persist.reset_mock()
		flat_calls_before = self.mock_faiss.IndexFlatL2.call_count

		deleted = self.backend.delete_chunks("input_1")

		self.assertEqual(deleted, 2)
		# Index rebuilt from the survivor only, sidecar re-keyed from 0.
		self.assertEqual(self.mock_faiss.IndexFlatL2.call_count, flat_calls_before + 1)
		rebuilt_vectors = self.mock_index.add.call_args[0][0]
		self.assertEqual(rebuilt_vectors.shape, (1, 1536))
		self.assertEqual(self.backend._chunk_store, {"0": survivor})
		# The rebuilt index and sidecar are persisted.
		self.mock_vector_store.persist.assert_called_with(persist_path=self.backend._index_file)

	def test_delete_chunks_no_match(self):
		"""Deleting an unknown input is a no-op and does not rebuild."""
		self._initialize()
		self.backend.add_chunks(self._chunks(2))
		flat_calls_before = self.mock_faiss.IndexFlatL2.call_count

		deleted = self.backend.delete_chunks("missing_input")

		self.assertEqual(deleted, 0)
		self.assertEqual(self.mock_faiss.IndexFlatL2.call_count, flat_calls_before)
		self.assertEqual(len(self.backend._chunk_store), 2)

	def test_delete_chunks_error_returns_zero(self):
		"""A failure during the rebuild is logged and reported as 0."""
		self._initialize()
		self.backend.add_chunks(self._chunks(2))

		with patch.object(self.backend, "_rebuild_index", side_effect=RuntimeError("boom")):
			deleted = self.backend.delete_chunks("input_1")

		self.assertEqual(deleted, 0)

	def test_clear(self):
		"""Clear resets the index and sidecar to empty and persists them."""
		self._initialize()
		self.backend.add_chunks(self._chunks(2))
		flat_calls_before = self.mock_faiss.IndexFlatL2.call_count

		self.backend.clear()

		self.assertEqual(self.backend._chunk_store, {})
		self.assertEqual(self.mock_faiss.IndexFlatL2.call_count, flat_calls_before + 1)
		self.mock_vector_store.persist.assert_called_with(persist_path=self.backend._index_file)

	def test_get_stats(self):
		"""Stats report backend_type, index type, and the sidecar chunk count."""
		self._initialize()
		self.backend.add_chunks(self._chunks(2))
		self.mock_index.ntotal = 2

		stats = self.backend.get_stats()

		self.assertEqual(stats["backend_type"], "faiss")
		self.assertEqual(stats["knowledge_source"], "test_source")
		self.assertTrue(stats["initialized"])
		self.assertEqual(stats["vector_dimension"], 1536)
		self.assertEqual(stats["index_type"], "flat")
		self.assertEqual(stats["chunk_count"], 2)
		self.assertEqual(stats["faiss_ntotal"], 2)

	def test_health_check(self):
		"""Health check verifies initialization and the persist directory."""
		self._initialize()

		with patch("os.path.isdir", return_value=True):
			is_healthy, message = self.backend.health_check()

		self.assertTrue(is_healthy)
		self.assertEqual(message, "Healthy")

	def test_health_check_not_initialized(self):
		"""Health check reports unhealthy before initialization."""
		is_healthy, message = FaissBackend().health_check()

		self.assertFalse(is_healthy)
		self.assertEqual(message, "Backend not initialized")

	def test_supports_flags(self):
		"""FAISS supports neither metadata filters nor hybrid search."""
		backend = FaissBackend()
		self.assertFalse(backend.supports_filters())
		self.assertFalse(backend.supports_hybrid_search())

	def test_advanced_config_schema(self):
		"""The advanced-config schema exposes the FAISS tuning knobs."""
		schema = FaissBackend.get_advanced_config_schema()
		keys = {entry["key"] for entry in schema}

		self.assertEqual(keys, {"faiss_index_type", "faiss_nlist"})
		for entry in schema:
			self.assertIn("label", entry)
			self.assertIn("type", entry)
			self.assertIn("default", entry)
			self.assertIn("help_text", entry)

		type_entry = next(e for e in schema if e["key"] == "faiss_index_type")
		self.assertEqual(type_entry["type"], "select")
		self.assertEqual(type_entry["options"], ["flat", "ivf"])
		# The no-metadata-filtering limitation is documented for Desk users.
		self.assertIn("metadata filtering", type_entry["help_text"])

		nlist_entry = next(e for e in schema if e["key"] == "faiss_nlist")
		self.assertEqual(nlist_entry["type"], "number")
		self.assertEqual(nlist_entry["visible_when"], {"faiss_index_type": "ivf"})


class TestFaissBackendRegistry(unittest.TestCase):
	"""FAISS resolves through the backend registry as a built-in."""

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

	def test_faiss_is_builtin(self):
		"""FAISS is a built-in backend, not hook-registered."""
		from huf.ai.knowledge.backends import _BUILTIN_BACKENDS

		self.assertEqual(
			_BUILTIN_BACKENDS["faiss"],
			"huf.ai.knowledge.backends.faiss_backend.FaissBackend",
		)

	@patch("huf.ai.knowledge.backends.frappe.get_installed_apps")
	@patch("huf.ai.knowledge.backends.frappe.get_hooks")
	def test_faiss_resolves_via_get_backend(self, mock_get_hooks, mock_get_installed_apps):
		from huf.ai.knowledge.backends import KnowledgeBackend, _discover_backends, get_backend

		mock_get_installed_apps.return_value = ["huf"]
		mock_get_hooks.return_value = []

		registry = _discover_backends()
		self.assertEqual(registry["faiss"], "huf.ai.knowledge.backends.faiss_backend.FaissBackend")

		backend_class = get_backend("faiss")
		self.assertIs(backend_class, FaissBackend)
		self.assertTrue(issubclass(backend_class, KnowledgeBackend))
		self.assertEqual(backend_class._backend_type, "faiss")

	@patch("huf.ai.knowledge.backends.frappe.get_installed_apps")
	@patch("huf.ai.knowledge.backends.frappe.get_hooks")
	def test_hook_cannot_override_faiss(self, mock_get_hooks, mock_get_installed_apps):
		"""A hook trying to register 'faiss' is skipped; the built-in wins."""
		from huf.ai.knowledge.backends import _discover_backends

		mock_get_installed_apps.return_value = ["evil_app"]

		def fake_hooks(hook_name, app_name=None):
			if hook_name == "huf_knowledge_backends" and app_name == "evil_app":
				return {"faiss": ["evil_app.faiss.OverrideBackend"]}
			return []

		mock_get_hooks.side_effect = fake_hooks

		registry = _discover_backends()
		self.assertEqual(registry["faiss"], "huf.ai.knowledge.backends.faiss_backend.FaissBackend")


if __name__ == "__main__":
	unittest.main()
