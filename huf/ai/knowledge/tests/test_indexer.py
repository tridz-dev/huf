# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

"""Tests for the knowledge ingestion pipeline (huf/ai/knowledge/indexer.py).

Covers:

- ``_build_backend_config``: per-backend configuration shaping.
- ``_extract_text``: input-type routing (Text inline, URL via extractor with
  network mocked out).
- Chunking boundary behavior in ``chunkers/sentence.py`` (the deterministic
  ``_simple_chunk`` fallback plus the import-fallback wiring of ``chunk_text``).
- ``process_knowledge_input`` / ``rebuild_knowledge_index`` end-to-end against
  the real SQLite FTS5 backend writing into a temp directory, with all LLM /
  network surface mocked. ``update_source_stats`` is tested in isolation with
  a fake backend to avoid creating File documents.
"""

import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import frappe

from huf.ai.knowledge.backends.sqlite_fts import SQLiteFTSBackend
from huf.ai.knowledge.chunkers.sentence import Chunk, _simple_chunk, chunk_text
from huf.ai.knowledge.extractors import ExtractedText
from huf.ai.knowledge.indexer import (
	_build_backend_config,
	_extract_text,
	process_knowledge_input,
	rebuild_knowledge_index,
	update_source_stats,
)
from huf.tests.utils import HufTestSuite


class TestBuildBackendConfig(HufTestSuite):
	"""_build_backend_config shapes config dicts per knowledge_type."""

	def _source_doc(self, **overrides):
		# In-memory doc: no insert, so vector-backend availability checks in
		# the KnowledgeSource controller don't fire. _build_backend_config's
		# chroma path scrubs source.name (the autonamed docname), not
		# source_name directly — set .name explicitly to mirror what insert()
		# would have assigned via this doctype's `field:source_name` autoname.
		doc = {
			"doctype": "Knowledge Source",
			"source_name": "_Test Config Source",
			"knowledge_type": "sqlite_fts",
			"chunk_size": 1000,
			"chunk_overlap": 100,
		}
		doc.update(overrides)
		source = frappe.get_doc(doc)
		source.name = doc["source_name"]
		return source

	def test_sqlite_fts_config_contains_only_chunk_settings(self):
		config = _build_backend_config(self._source_doc())

		self.assertEqual(config, {"chunk_size": 1000, "chunk_overlap": 100})

	def test_sqlite_vec_config_adds_embedding_settings(self):
		source = self._source_doc(
			knowledge_type="sqlite_vec",
			embedding_model="openai/text-embedding-3-small",
			vector_dimension=1536,
			embedding_provider="_Test Provider",
		)

		config = _build_backend_config(source)

		self.assertEqual(config["chunk_size"], 1000)
		self.assertEqual(config["embedding_model"], "openai/text-embedding-3-small")
		self.assertEqual(config["vector_dimension"], 1536)
		self.assertEqual(config["embedding_provider"], "_Test Provider")

	def test_chroma_file_mode_sets_persist_directory(self):
		source = self._source_doc(knowledge_type="chroma", chroma_mode="File")

		with patch("frappe.utils.get_files_path", return_value="/site/private/files"):
			config = _build_backend_config(source)

		self.assertEqual(
			config["persist_directory"],
			os.path.join("/site/private/files", "knowledge", "_test_config_source_chroma"),
		)
		self.assertNotIn("host", config)

	def test_chroma_server_mode_sets_connection_settings(self):
		source = self._source_doc(
			knowledge_type="chroma",
			chroma_mode="Server",
			chroma_host="chroma.example.com",
			chroma_port=9000,
			chroma_ssl=1,
		)

		config = _build_backend_config(source)

		self.assertEqual(config["host"], "chroma.example.com")
		self.assertEqual(config["port"], 9000)
		self.assertTrue(config["ssl"])
		self.assertNotIn("persist_directory", config)


class TestExtractText(HufTestSuite):
	"""_extract_text routes by input_type; no network or disk parsing here."""

	def test_text_input_returns_pasted_text(self):
		doc = frappe.get_doc({
			"doctype": "Knowledge Input",
			"input_type": "Text",
			"text": "Hello knowledge world",
		})

		extracted = _extract_text(doc)

		self.assertEqual(extracted.text, "Hello knowledge world")
		self.assertEqual(extracted.title, "Pasted Text")
		self.assertEqual(extracted.character_count, len("Hello knowledge world"))

	def test_unknown_input_type_raises(self):
		doc = frappe.get_doc({"doctype": "Knowledge Input", "input_type": "Bogus"})

		with self.assertRaises(ValueError):
			_extract_text(doc)

	def test_url_input_uses_url_extractor_without_network(self):
		doc = frappe.get_doc({
			"doctype": "Knowledge Input",
			"input_type": "URL",
			"url": "https://example.com/docs/page",
		})
		mock_instance = MagicMock()
		mock_instance.extract.return_value = ExtractedText(
			text="Fetched page content", title="Example Page"
		)

		with patch(
			"huf.ai.knowledge.extractors.url.URLExtractor", return_value=mock_instance
		):
			extracted = _extract_text(doc)

		mock_instance.extract.assert_called_once_with("https://example.com/docs/page")
		self.assertEqual(extracted.text, "Fetched page content")
		self.assertEqual(extracted.title, "Example Page")


class TestChunkingBoundaries(HufTestSuite):
	"""Boundary behavior of the deterministic _simple_chunk fallback and the
	chunk_text contract (which holds for the LlamaIndex path too)."""

	def test_short_text_produces_single_chunk(self):
		text = "Short sentence that fits in one chunk."
		chunks = _simple_chunk(text, chunk_size=512, chunk_overlap=50)

		self.assertEqual(len(chunks), 1)
		self.assertEqual(chunks[0].text, text)
		self.assertEqual(chunks[0].chunk_index, 0)
		self.assertEqual(chunks[0].char_start, 0)
		self.assertEqual(chunks[0].char_end, len(text))

	def test_empty_text_produces_no_chunks(self):
		self.assertEqual(_simple_chunk("", chunk_size=512, chunk_overlap=50), [])

	def test_long_text_prefers_sentence_boundary(self):
		# "Hello world. " is 13 chars; with chunk_size=100 the naive cut at
		# 100 lands mid-sentence, but a ". " boundary at offset 89 (> midpoint
		# 50) must be chosen instead.
		text = "Hello world. " * 40
		chunks = _simple_chunk(text, chunk_size=100, chunk_overlap=20)

		self.assertGreater(len(chunks), 1)
		self.assertEqual(chunks[0].char_start, 0)
		self.assertEqual(chunks[0].char_end, 91)  # 89 + len(". ")
		self.assertTrue(chunks[0].text.endswith("world."))

	def test_overlap_between_consecutive_chunks(self):
		text = "Hello world. " * 40
		chunks = _simple_chunk(text, chunk_size=100, chunk_overlap=20)

		self.assertEqual(chunks[1].char_start, chunks[0].char_end - 20)

	def test_text_without_sentence_boundaries_hard_splits(self):
		text = "a" * 250
		chunks = _simple_chunk(text, chunk_size=100, chunk_overlap=20)

		self.assertEqual(len(chunks), 3)
		self.assertEqual(len(chunks[0].text), 100)
		self.assertEqual(len(chunks[1].text), 100)
		self.assertEqual(len(chunks[2].text), 90)
		self.assertEqual(chunks[-1].char_end, len(text))

	def test_chunk_indices_are_sequential(self):
		text = "Hello world. " * 40
		chunks = _simple_chunk(text, chunk_size=100, chunk_overlap=20)

		self.assertEqual([c.chunk_index for c in chunks], list(range(len(chunks))))

	def test_last_chunk_covers_end_of_text(self):
		text = "Hello world. " * 40
		chunks = _simple_chunk(text, chunk_size=100, chunk_overlap=20)

		self.assertEqual(chunks[-1].char_end, len(text))

	def test_chunk_text_falls_back_when_llamaindex_missing(self):
		# A None entry in sys.modules makes the import raise ImportError,
		# exercising the except branch regardless of whether llama_index is
		# installed in the environment.
		with patch.dict(sys.modules, {"llama_index.core.node_parser": None}), patch(
			"huf.ai.knowledge.chunkers.sentence._simple_chunk",
			return_value=[Chunk(text="x", chunk_index=0, char_start=0, char_end=1)],
		) as mock_simple:
			chunks = chunk_text("whatever", chunk_size=512, chunk_overlap=50)

		mock_simple.assert_called_once_with("whatever", 512, 50)
		self.assertEqual(len(chunks), 1)

	def test_chunk_text_returns_positioned_chunks(self):
		# Implementation-agnostic contract: sequential indices, Chunk objects,
		# coverage starting at 0. Holds for LlamaIndex and fallback paths.
		text = "The quick brown fox jumps over the lazy dog. " * 40
		chunks = chunk_text(text, chunk_size=200, chunk_overlap=40)

		self.assertTrue(chunks)
		for i, chunk in enumerate(chunks):
			self.assertIsInstance(chunk, Chunk)
			self.assertEqual(chunk.chunk_index, i)
			self.assertTrue(chunk.text.strip())
		self.assertEqual(chunks[0].char_start, 0)


class TestProcessKnowledgeInput(HufTestSuite):
	"""End-to-end ingestion into a real SQLite FTS5 index in a temp dir.

	Knowledge Input's after_insert enqueues process_knowledge_input, which
	runs synchronously under frappe.flags.in_test — so all inserts happen
	inside the same patch context as the explicit call, keeping every write
	(SQLite file, stats) pointed at the temp dir. update_source_stats is
	mocked here and tested separately to avoid creating File documents.
	"""

	def setUp(self):
		self.tmpdir = tempfile.TemporaryDirectory()
		self.addCleanup(self.tmpdir.cleanup)

		files_patch = patch(
			"huf.ai.knowledge.backends.sqlite_fts.get_files_path",
			return_value=self.tmpdir.name,
		)
		files_patch.start()
		self.addCleanup(files_patch.stop)

		stats_patch = patch("huf.ai.knowledge.indexer.update_source_stats")
		self.mock_update_stats = stats_patch.start()
		self.addCleanup(stats_patch.stop)

	def _make_source(self, name="_Test Index Source"):
		return frappe.get_doc({
			"doctype": "Knowledge Source",
			"source_name": name,
			"knowledge_type": "sqlite_fts",
		}).insert(ignore_permissions=True)

	def _make_input(self, source, text):
		return frappe.get_doc({
			"doctype": "Knowledge Input",
			"knowledge_source": source.name,
			"input_type": "Text",
			"text": text,
		}).insert(ignore_permissions=True)

	def _delete_docs(self, source_name, input_names=()):
		for input_name in input_names:
			if frappe.db.exists("Knowledge Input", input_name):
				frappe.delete_doc("Knowledge Input", input_name, force=True)
		if frappe.db.exists("Knowledge Source", source_name):
			frappe.delete_doc("Knowledge Source", source_name, force=True)
		frappe.db.commit()

	def test_process_text_input_success_then_searchable(self):
		text = "The quick brown fox jumps over the lazy dog. " * 140  # ~6.3k chars

		# Keep all writes in-transaction so HufTestSuite's rollback isolates
		# the test. Knowledge Input's after_insert enqueues processing, which
		# runs synchronously under frappe.flags.in_test and would otherwise
		# commit via process_knowledge_input's internal commits.
		with patch.object(frappe.db, "commit"):
			source = self._make_source()
			ki = self._make_input(source, text)
			result = process_knowledge_input(ki.name, skip_lock=True)

		self.assertEqual(result["status"], "success")
		# ~6.3k chars at chunk_size 512 must split under either chunker
		self.assertGreaterEqual(result["chunks_created"], 2)
		self.assertEqual(result["character_count"], len(text))

		ki.reload()
		self.assertEqual(ki.status, "Indexed")
		self.assertEqual(ki.chunks_created, result["chunks_created"])
		self.assertEqual(ki.character_count, len(text))
		self.assertIsNotNone(ki.processed_at)
		self.assertIsNone(ki.error_message)

		source.reload()
		self.assertEqual(source.status, "Ready")
		self.assertIsNotNone(source.last_indexed_at)
		self.assertTrue(self.mock_update_stats.called)

		# The chunks landed in the FTS index and are retrievable.
		backend = SQLiteFTSBackend()
		backend.initialize(source.name, {"chunk_size": 512, "chunk_overlap": 50})
		hits = backend.search("quick brown fox", top_k=5)
		self.assertTrue(hits)
		self.assertGreater(hits[0].score, 0)
		self.assertIn("quick", hits[0].text)

	def test_reprocess_replaces_chunks_without_duplicates(self):
		text = "Unique pangram content for reprocessing. " * 30

		with patch.object(frappe.db, "commit"):
			source = self._make_source("_Test Reprocess Source")
			ki = self._make_input(source, text)
			first = process_knowledge_input(ki.name, skip_lock=True)
			second = process_knowledge_input(ki.name, skip_lock=True)

		self.assertEqual(first["status"], "success")
		self.assertEqual(second["status"], "success")

		# delete-before-add: reprocessing must not duplicate chunks.
		backend = SQLiteFTSBackend()
		backend.initialize(source.name, {"chunk_size": 512, "chunk_overlap": 50})
		self.assertEqual(
			backend.get_stats()["chunk_count"], second["chunks_created"]
		)

	def test_lock_contention_marks_input_error(self):
		source = self._make_source("_Test Lock Source")
		ki = self._make_input(source, "Content for lock contention test.")
		# The error path rolls back then reloads — docs must be committed to
		# survive that, so clean them up explicitly afterwards.
		frappe.db.commit()
		self.addCleanup(self._delete_docs, source.name, (ki.name,))

		# frappe.cache() is used all over the framework internals (e.g.
		# workflow lookups) — a blanket MagicMock replacement breaks those.
		# Only fake the .set() call for our specific lock key; everything
		# else goes through the real cache.
		real_cache = frappe.cache()
		lock_key = f"knowledge_index_{source.name}"

		def fake_set(key, *args, **kwargs):
			if key == lock_key:
				return False  # lock already held
			return real_cache.set(key, *args, **kwargs)

		with patch.object(real_cache, "set", side_effect=fake_set):
			result = process_knowledge_input(ki.name)

		self.assertEqual(result["status"], "error")
		self.assertIn("in progress", result["error"])

		ki.reload()
		self.assertEqual(ki.status, "Error")
		self.assertIn("in progress", ki.error_message)

	def test_extraction_failure_marks_input_and_source_error(self):
		source = self._make_source("_Test Failure Source")
		ki = self._make_input(source, "Content that will fail extraction.")
		frappe.db.commit()
		self.addCleanup(self._delete_docs, source.name, (ki.name,))

		with patch(
			"huf.ai.knowledge.indexer._extract_text",
			side_effect=RuntimeError("boom"),
		):
			result = process_knowledge_input(ki.name, skip_lock=True)

		self.assertEqual(result["status"], "error")
		self.assertIn("boom", result["error"])

		ki.reload()
		self.assertEqual(ki.status, "Error")
		self.assertIn("boom", ki.error_message)
		source.reload()
		self.assertEqual(source.status, "Error")
		self.assertIn("boom", source.error_message)

	def test_rebuild_reindexes_all_inputs(self):
		with patch.object(frappe.db, "commit"):
			source = self._make_source("_Test Rebuild Source")
			ki1 = self._make_input(source, "First rebuild document about alpha. " * 20)
			ki2 = self._make_input(source, "Second rebuild document about beta. " * 20)
			result = rebuild_knowledge_index(source.name)

		self.assertEqual(result["status"], "success")
		self.assertEqual(result["inputs_processed"], 2)
		self.assertGreater(result["total_chunks"], 0)

		source.reload()
		self.assertEqual(source.status, "Ready")

		# Both inputs' content is searchable after the rebuild.
		backend = SQLiteFTSBackend()
		backend.initialize(source.name, {"chunk_size": 512, "chunk_overlap": 50})
		self.assertTrue(backend.search("alpha", top_k=5))
		self.assertTrue(backend.search("beta", top_k=5))

		ki1.reload()
		ki2.reload()
		self.assertEqual(ki1.status, "Indexed")
		self.assertEqual(ki2.status, "Indexed")


class TestUpdateSourceStats(HufTestSuite):
	"""update_source_stats copies backend stats onto the source doc."""

	def test_stats_copied_without_db_file(self):
		source = frappe.get_doc({
			"doctype": "Knowledge Source",
			"source_name": "_Test Stats Source",
			"knowledge_type": "sqlite_fts",
		}).insert(ignore_permissions=True)

		fake_backend = MagicMock()
		fake_backend.get_stats.return_value = {
			"chunk_count": 7,
			"input_count": 2,
			"size_bytes": 4096,
		}
		fake_backend.db_path = None  # skips the File-doc creation branch

		update_source_stats(source, fake_backend)

		source.reload()
		self.assertEqual(source.total_chunks, 7)
		self.assertEqual(source.total_inputs, 2)
		self.assertEqual(source.index_size_bytes, 4096)
		self.assertFalse(source.sqlite_file)
