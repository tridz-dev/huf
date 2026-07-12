# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

"""Tests for knowledge retrieval.

Two layers are covered:

- ``knowledge_search`` orchestration in ``huf/ai/knowledge/retriever.py``
  (source gating by status/disabled/permissions, cross-source aggregation,
  score sorting, top_k truncation, error isolation) using a fake backend.
- Real BM25 ranking through the SQLite FTS5 backend, exercised end-to-end
  against a throwaway index in a temp directory so search/relevance behavior
  is verified against actual FTS5 semantics rather than mocks.
"""

import sqlite3
import tempfile
from unittest.mock import patch

import frappe

from huf.ai.knowledge.backends import ChunkResult
from huf.ai.knowledge.backends.sqlite_fts import SQLiteFTSBackend
from huf.ai.knowledge.retriever import (
	get_mandatory_knowledge,
	get_optional_knowledge,
	get_search_diagnostics,
	knowledge_search,
)
from huf.tests.utils import HufTestSuite


def _fake_backend_class(results_by_source=None, error=None):
	"""Build a backend class returning canned ChunkResults per source name.

	``retriever.knowledge_search`` calls ``get_backend(type)()`` then
	``initialize(source_name, config)`` then ``search(...)``, so the fake keys
	canned results off the source name passed to ``initialize``.
	"""

	class _FakeBackend:
		def initialize(self, knowledge_source, config):
			self.knowledge_source = knowledge_source

		def search(self, query, top_k=5, filters=None):
			if error:
				raise error
			return list((results_by_source or {}).get(self.knowledge_source, []))

	return _FakeBackend


class TestKnowledgeSearchOrchestration(HufTestSuite):
	"""Gating, aggregation, and sorting logic in knowledge_search()."""

	def _make_source(self, name="_Test Retriever Source", **overrides):
		doc = {
			"doctype": "Knowledge Source",
			"source_name": name,
			"knowledge_type": "sqlite_fts",
			"status": "Ready",
		}
		doc.update(overrides)
		return frappe.get_doc(doc).insert(ignore_permissions=True)

	def test_empty_query_returns_no_results(self):
		self.assertEqual(knowledge_search(query="", knowledge_source="anything"), [])
		self.assertEqual(knowledge_search(query="   ", knowledge_source="anything"), [])

	def test_source_argument_required(self):
		# frappe.throw() raises ValidationError by default
		with self.assertRaises(frappe.ValidationError):
			knowledge_search(query="something")

	def test_skips_sources_not_ready(self):
		source = self._make_source(status="Pending")
		fake = _fake_backend_class({source.name: [ChunkResult(chunk_id="c1", text="hit", score=1.0)]})

		with patch("huf.ai.knowledge.retriever.get_backend", return_value=fake):
			results = knowledge_search(
				query="hit", knowledge_source=source.name, ignore_permissions=True
			)

		self.assertEqual(results, [])

	def test_skips_disabled_sources(self):
		source = self._make_source(disabled=1)
		fake = _fake_backend_class({source.name: [ChunkResult(chunk_id="c1", text="hit", score=1.0)]})

		with patch("huf.ai.knowledge.retriever.get_backend", return_value=fake):
			results = knowledge_search(
				query="hit", knowledge_source=source.name, ignore_permissions=True
			)

		self.assertEqual(results, [])

	def test_skips_sources_without_read_permission(self):
		source = self._make_source()
		fake = _fake_backend_class({source.name: [ChunkResult(chunk_id="c1", text="hit", score=1.0)]})

		with patch("huf.ai.knowledge.retriever.get_backend", return_value=fake), patch.object(
			frappe, "has_permission", return_value=False
		):
			results = knowledge_search(query="hit", knowledge_source=source.name)

		self.assertEqual(results, [])

	def test_nonexistent_source_is_skipped(self):
		results = knowledge_search(
			query="hit", knowledge_sources=["_Test Missing Source"], ignore_permissions=True
		)
		self.assertEqual(results, [])

	def test_results_sorted_by_score_with_source_attribution(self):
		s1 = self._make_source("_Test Retriever Source A")
		s2 = self._make_source("_Test Retriever Source B")
		fake = _fake_backend_class({
			s1.name: [ChunkResult(chunk_id="a1", text="mid hit", title="Doc A", score=0.5, metadata={"k": "v"})],
			s2.name: [
				ChunkResult(chunk_id="b1", text="best hit", title="Doc B", score=0.9),
				ChunkResult(chunk_id="b2", text="weak hit", title="Doc B", score=0.1),
			],
		})

		with patch("huf.ai.knowledge.retriever.get_backend", return_value=fake):
			results = knowledge_search(
				query="hit", knowledge_sources=[s1.name, s2.name], top_k=10, ignore_permissions=True
			)

		self.assertEqual([r["score"] for r in results], [0.9, 0.5, 0.1])
		self.assertEqual([r["chunk_id"] for r in results], ["b1", "a1", "b2"])
		# every result carries the source it came from plus the full contract keys
		self.assertEqual(results[0]["source"], s2.name)
		self.assertEqual(results[1]["source"], s1.name)
		for result in results:
			for key in ("text", "title", "score", "chunk_id", "source", "metadata"):
				self.assertIn(key, result)
		self.assertEqual(results[1]["metadata"], {"k": "v"})

	def test_top_k_limits_total_results_across_sources(self):
		s1 = self._make_source("_Test Retriever Source A")
		s2 = self._make_source("_Test Retriever Source B")
		fake = _fake_backend_class({
			s1.name: [
				ChunkResult(chunk_id="a1", text="r1", score=0.9),
				ChunkResult(chunk_id="a2", text="r2", score=0.8),
			],
			s2.name: [
				ChunkResult(chunk_id="b1", text="r3", score=0.7),
				ChunkResult(chunk_id="b2", text="r4", score=0.6),
			],
		})

		with patch("huf.ai.knowledge.retriever.get_backend", return_value=fake):
			results = knowledge_search(
				query="r", knowledge_sources=[s1.name, s2.name], top_k=2, ignore_permissions=True
			)

		# global top_k applies after cross-source score sorting
		self.assertEqual(len(results), 2)
		self.assertEqual([r["score"] for r in results], [0.9, 0.8])

	def test_backend_error_is_logged_and_other_sources_still_return(self):
		s1 = self._make_source("_Test Retriever Source A")
		s2 = self._make_source("_Test Retriever Source B")
		good = _fake_backend_class({s2.name: [ChunkResult(chunk_id="b1", text="hit", score=0.9)]})

		erroring = _fake_backend_class(error=RuntimeError("boom"))

		# get_backend() is called with the source's knowledge_type; the returned
		# class is initialized per source, so dispatch fake vs erroring there.
		def dispatch_get_backend(backend_type):
			class _DispatchBackend:
				def initialize(self, knowledge_source, config):
					self.impl = (erroring if knowledge_source == s1.name else good)()

				def search(self, query, top_k=5, filters=None):
					return self.impl.search(query, top_k=top_k, filters=filters)

			return _DispatchBackend

		with patch("huf.ai.knowledge.retriever.get_backend", new=dispatch_get_backend), patch.object(
			frappe, "log_error"
		) as mock_log:
			results = knowledge_search(
				query="hit", knowledge_sources=[s1.name, s2.name], top_k=5, ignore_permissions=True
			)

		self.assertEqual(len(results), 1)
		self.assertEqual(results[0]["source"], s2.name)
		self.assertTrue(mock_log.called)


class TestSearchDiagnostics(HufTestSuite):
	"""get_search_diagnostics explains why sources were skipped."""

	def test_reports_status_disabled_and_missing(self):
		pending = frappe.get_doc({
			"doctype": "Knowledge Source",
			"source_name": "_Test Diagnostics Pending",
			"knowledge_type": "sqlite_fts",
			"status": "Pending",
		}).insert(ignore_permissions=True)
		disabled = frappe.get_doc({
			"doctype": "Knowledge Source",
			"source_name": "_Test Diagnostics Disabled",
			"knowledge_type": "sqlite_fts",
			"status": "Ready",
			"disabled": 1,
		}).insert(ignore_permissions=True)

		diagnostics = get_search_diagnostics(
			[pending.name, disabled.name, "_Test Diagnostics Missing"]
		)
		by_source = {d["source"]: d for d in diagnostics}

		self.assertIn("Pending", by_source[pending.name]["reason"])
		self.assertIn("disabled", by_source[disabled.name]["reason"])
		self.assertIn("does not exist", by_source["_Test Diagnostics Missing"]["reason"])

	def test_ready_enabled_source_reports_possibly_empty_index(self):
		ready = frappe.get_doc({
			"doctype": "Knowledge Source",
			"source_name": "_Test Diagnostics Ready",
			"knowledge_type": "sqlite_fts",
			"status": "Ready",
		}).insert(ignore_permissions=True)

		diagnostics = get_search_diagnostics([ready.name])

		self.assertEqual(diagnostics[0]["status"], "Ready")
		self.assertIn("empty", diagnostics[0]["reason"])


class TestAgentKnowledgeConfig(HufTestSuite):
	"""get_mandatory_knowledge / get_optional_knowledge read Agent config."""

	def _make_agent_with_knowledge(self, name, rows):
		return frappe.get_doc({
			"doctype": "Agent",
			"agent_name": name,
			"provider": self.bootstrap.provider.name,
			"model": self.bootstrap.model.name,
			"instructions": "You are a test agent.",
			"agent_knowledge": rows,
		}).insert(ignore_permissions=True)

	def test_mandatory_sources_sorted_by_priority_with_defaults(self):
		s1 = frappe.get_doc({
			"doctype": "Knowledge Source",
			"source_name": "_Test Mandatory Low",
			"knowledge_type": "sqlite_fts",
		}).insert(ignore_permissions=True)
		s2 = frappe.get_doc({
			"doctype": "Knowledge Source",
			"source_name": "_Test Mandatory High",
			"knowledge_type": "sqlite_fts",
		}).insert(ignore_permissions=True)
		s3 = frappe.get_doc({
			"doctype": "Knowledge Source",
			"source_name": "_Test Optional Source",
			"knowledge_type": "sqlite_fts",
		}).insert(ignore_permissions=True)

		agent = self._make_agent_with_knowledge("_Test Knowledge Agent", [
			{"knowledge_source": s1.name, "mode": "Mandatory", "priority": 1},
			{"knowledge_source": s2.name, "mode": "Mandatory", "priority": 10},
			{"knowledge_source": s3.name, "mode": "Optional", "priority": 5},
		])

		mandatory = get_mandatory_knowledge(agent.name)

		# higher priority first; optional source excluded
		self.assertEqual([m["knowledge_source"] for m in mandatory], [s2.name, s1.name])
		# unset max_chunks / token_budget fall back to defaults
		self.assertEqual(mandatory[0]["max_chunks"], 5)
		self.assertEqual(mandatory[0]["token_budget"], 2000)

	def test_optional_sources_exclude_mandatory(self):
		s1 = frappe.get_doc({
			"doctype": "Knowledge Source",
			"source_name": "_Test Opt Mandatory",
			"knowledge_type": "sqlite_fts",
		}).insert(ignore_permissions=True)
		s2 = frappe.get_doc({
			"doctype": "Knowledge Source",
			"source_name": "_Test Opt Optional",
			"knowledge_type": "sqlite_fts",
		}).insert(ignore_permissions=True)

		agent = self._make_agent_with_knowledge("_Test Optional Agent", [
			{"knowledge_source": s1.name, "mode": "Mandatory", "priority": 1},
			{"knowledge_source": s2.name, "mode": "Optional", "priority": 5},
		])

		optional = get_optional_knowledge(agent.name)

		self.assertEqual([o["knowledge_source"] for o in optional], [s2.name])


class TestSQLiteFTSRanking(HufTestSuite):
	"""Real BM25 ranking through SQLiteFTSBackend against a temp index.

	The corpus below was validated against the exact schema/triggers/query in
	sqlite_fts.py: multi-term matches outrank single-term matches, irrelevant
	documents are excluded, and escaped junk queries degrade gracefully.
	"""

	CORPUS = [
		{
			"chunk_id": "c1",
			"input_id": "in1",
			"input_type": "Text",
			"source_title": "Python Guide",
			"chunk_index": 0,
			"text": "Python decorators are a powerful way to wrap functions and extend "
			"their behavior without modifying them.",
		},
		{
			"chunk_id": "c2",
			"input_id": "in2",
			"input_type": "Text",
			"source_title": "Recipe Book",
			"chunk_index": 0,
			"text": "A banana smoothie recipe: blend two bananas with milk, honey, "
			"and ice for a healthy breakfast drink.",
		},
		{
			"chunk_id": "c3",
			"input_id": "in1",
			"input_type": "Text",
			"source_title": "Python Guide",
			"chunk_index": 1,
			"text": "Python generators use the yield keyword to produce values lazily, "
			"saving memory on large datasets.",
		},
		{
			"chunk_id": "c4",
			"input_id": "in3",
			"input_type": "Text",
			"source_title": "Physics Notes",
			"chunk_index": 0,
			"text": "Quantum computing uses qubits that can exist in superposition, "
			"unlike classical binary bits.",
		},
		{
			"chunk_id": "c5",
			"input_id": "in1",
			"input_type": "Text",
			"source_title": "Python Guide",
			"chunk_index": 2,
			"text": "Decorators in Python use the at-symbol syntax placed above a "
			"function definition line.",
		},
	]

	def setUp(self):
		try:
			conn = sqlite3.connect(":memory:")
			conn.execute("CREATE VIRTUAL TABLE t USING fts5(text, tokenize='porter unicode61')")
			conn.close()
		except sqlite3.OperationalError:
			self.skipTest("SQLite FTS5 with porter tokenizer not available")

		self.tmpdir = tempfile.TemporaryDirectory()
		self.addCleanup(self.tmpdir.cleanup)
		# Redirect the index file into the temp dir instead of site files.
		files_patch = patch(
			"huf.ai.knowledge.backends.sqlite_fts.get_files_path",
			return_value=self.tmpdir.name,
		)
		files_patch.start()
		self.addCleanup(files_patch.stop)

		self.source = frappe.get_doc({
			"doctype": "Knowledge Source",
			"source_name": "_Test FTS Ranking Source",
			"knowledge_type": "sqlite_fts",
			"status": "Ready",
		}).insert(ignore_permissions=True)

		self.backend = SQLiteFTSBackend()
		self.backend.initialize(self.source.name, {"chunk_size": 512, "chunk_overlap": 50})
		self.backend.add_chunks(self.CORPUS)

	def test_relevant_chunks_returned_irrelevant_excluded(self):
		results = self.backend.search("python", top_k=5)

		chunk_ids = [r.chunk_id for r in results]
		self.assertEqual(set(chunk_ids), {"c1", "c3", "c5"})
		self.assertNotIn("c2", chunk_ids)
		self.assertNotIn("c4", chunk_ids)
		# scores are positive (BM25 negatives are absolutized) and sorted desc
		scores = [r.score for r in results]
		self.assertTrue(all(s > 0 for s in scores))
		self.assertEqual(scores, sorted(scores, reverse=True))
		self.assertEqual(results[0].title, "Python Guide")

	def test_multi_term_query_ranks_best_match_first(self):
		results = self.backend.search("python decorators", top_k=5)

		# c5 contains both terms in a short document — highest BM25 score;
		# c3 matches only "python" and must rank below the two-term matches.
		self.assertEqual(results[0].chunk_id, "c5")
		rank = {r.chunk_id: i for i, r in enumerate(results)}
		self.assertLess(rank["c5"], rank["c3"])
		self.assertLess(rank["c1"], rank["c3"])

	def test_top_k_limits_results(self):
		results = self.backend.search("python", top_k=1)

		self.assertEqual(len(results), 1)
		self.assertEqual(results[0].chunk_id, "c5")

	def test_no_match_returns_empty(self):
		self.assertEqual(self.backend.search("zzzznotfound", top_k=5), [])

	def test_deleted_chunks_stop_matching(self):
		self.backend.add_chunks([{
			"chunk_id": "c9",
			"input_id": "in_delete",
			"input_type": "Text",
			"source_title": "Temp Doc",
			"chunk_index": 0,
			"text": "The zephyr breeze carried pollen across the meadow.",
		}])
		self.assertEqual(len(self.backend.search("zephyr", top_k=5)), 1)

		deleted = self.backend.delete_chunks("in_delete")

		self.assertEqual(deleted, 1)
		self.assertEqual(self.backend.search("zephyr", top_k=5), [])

	def test_escape_fts_query(self):
		escape = self.backend._escape_fts_query

		# single term passes through untouched
		self.assertEqual(escape("python"), "python")
		# multiple terms become OR-joined quoted phrases
		self.assertEqual(escape("python decorators"), '"python" OR "decorators"')
		# special FTS5 characters are stripped before quoting
		self.assertEqual(escape("a-b+c"), '"a" OR "b" OR "c"')

	def test_escaped_special_characters_do_not_error(self):
		# apostrophes/parens/etc. must not produce an FTS5 syntax error
		self.assertEqual(self.backend.search("what's (new)?", top_k=5), [])

	def test_knowledge_search_end_to_end(self):
		results = knowledge_search(
			query="python",
			knowledge_source=self.source.name,
			top_k=5,
			ignore_permissions=True,
		)

		self.assertEqual(len(results), 3)
		self.assertEqual([r["chunk_id"] for r in results], ["c5", "c3", "c1"])
		for result in results:
			self.assertEqual(result["source"], self.source.name)
			self.assertGreater(result["score"], 0)

		# global top_k truncation applies to the real backend too
		self.assertEqual(
			len(knowledge_search(
				query="python",
				knowledge_source=self.source.name,
				top_k=1,
				ignore_permissions=True,
			)),
			1,
		)
