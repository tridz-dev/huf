# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

"""Tests for knowledge context assembly (huf/ai/knowledge/context_builder.py).

Covers:

- ``build_knowledge_context``: mandatory-source lookup, markdown formatting
  with source attribution, the 4-chars-per-token budget truncation, and
  per-source error isolation. ``knowledge_search`` is mocked so formatting /
  truncation logic is tested independently of retrieval.
- ``inject_knowledge_context``: prompt injection placement.
"""

from unittest.mock import patch

import frappe

from huf.ai.knowledge.context_builder import (
	build_knowledge_context,
	inject_knowledge_context,
)
from huf.tests.utils import HufTestSuite


def _chunk(text, chunk_id, source, title="Doc", score=0.9):
	return {
		"text": text,
		"title": title,
		"score": score,
		"chunk_id": chunk_id,
		"source": source,
		"metadata": {},
	}


class TestBuildKnowledgeContext(HufTestSuite):
	def test_no_mandatory_sources_returns_empty_context(self):
		# The bootstrap agent has no agent_knowledge rows — real lookup path.
		result = build_knowledge_context(self.bootstrap.agent.name, "any query")

		self.assertEqual(result, {"context_text": "", "sources_used": [], "chunks_used": []})

	def test_search_not_called_when_no_mandatory_sources(self):
		with patch(
			"huf.ai.knowledge.context_builder.get_mandatory_knowledge", return_value=[]
		), patch("huf.ai.knowledge.context_builder.knowledge_search") as mock_search:
			result = build_knowledge_context("Some Agent", "query")

		mock_search.assert_not_called()
		self.assertEqual(result["context_text"], "")

	def test_context_text_formatting_with_source_attribution(self):
		mandatory = [{"knowledge_source": "S1", "max_chunks": 3, "priority": 0, "token_budget": 2000}]
		chunks = [
			_chunk("Alpha content here", "c1", "S1", title="Doc A"),
			_chunk("Beta content here", "c2", "S1", title="Doc B"),
		]

		with patch(
			"huf.ai.knowledge.context_builder.get_mandatory_knowledge",
			return_value=mandatory,
		), patch(
			"huf.ai.knowledge.context_builder.knowledge_search", return_value=chunks
		) as mock_search:
			result = build_knowledge_context("Some Agent", "user query")

		# max_chunks from the agent config is passed through as top_k, and
		# agent-linked knowledge bypasses permission checks.
		mock_search.assert_called_once_with(
			query="user query",
			knowledge_source="S1",
			top_k=3,
			ignore_permissions=True,
		)

		text = result["context_text"]
		self.assertTrue(text.startswith("## Relevant Knowledge\n"))
		self.assertIn("### Doc A\n", text)
		self.assertIn("Alpha content here", text)
		self.assertIn("### Doc B\n", text)
		self.assertIn("Beta content here", text)

		self.assertEqual(result["sources_used"], ["S1"])
		self.assertEqual(result["chunks_used"], [
			{"chunk_id": "c1", "source": "S1", "title": "Doc A"},
			{"chunk_id": "c2", "source": "S1", "title": "Doc B"},
		])

	def test_sources_used_only_includes_sources_with_hits(self):
		mandatory = [
			{"knowledge_source": "S1", "max_chunks": 5},
			{"knowledge_source": "S2", "max_chunks": 5},
		]

		def search(query, knowledge_source, top_k, ignore_permissions):
			if knowledge_source == "S1":
				return []
			return [_chunk("Only S2 has content", "c9", "S2", title="Doc S2")]

		with patch(
			"huf.ai.knowledge.context_builder.get_mandatory_knowledge",
			return_value=mandatory,
		), patch(
			"huf.ai.knowledge.context_builder.knowledge_search", side_effect=search
		):
			result = build_knowledge_context("Some Agent", "query")

		self.assertEqual(result["sources_used"], ["S2"])
		self.assertIn("Only S2 has content", result["context_text"])
		self.assertEqual(len(result["chunks_used"]), 1)

	def test_search_exception_logged_and_other_sources_continue(self):
		mandatory = [
			{"knowledge_source": "S1", "max_chunks": 5},
			{"knowledge_source": "S2", "max_chunks": 5},
		]

		def search(query, knowledge_source, top_k, ignore_permissions):
			if knowledge_source == "S1":
				raise RuntimeError("index corrupted")
			return [_chunk("S2 survived", "c2", "S2")]

		with patch(
			"huf.ai.knowledge.context_builder.get_mandatory_knowledge",
			return_value=mandatory,
		), patch(
			"huf.ai.knowledge.context_builder.knowledge_search", side_effect=search
		), patch.object(frappe, "log_error") as mock_log:
			result = build_knowledge_context("Some Agent", "query")

		self.assertTrue(mock_log.called)
		self.assertEqual(result["sources_used"], ["S2"])
		self.assertIn("S2 survived", result["context_text"])

	def test_all_sources_empty_returns_empty_context(self):
		mandatory = [{"knowledge_source": "S1", "max_chunks": 5}]

		with patch(
			"huf.ai.knowledge.context_builder.get_mandatory_knowledge",
			return_value=mandatory,
		), patch("huf.ai.knowledge.context_builder.knowledge_search", return_value=[]):
			result = build_knowledge_context("Some Agent", "query")

		self.assertEqual(result, {"context_text": "", "sources_used": [], "chunks_used": []})

	def test_token_budget_truncates_at_four_chars_per_token(self):
		# chunk_tokens = len(text) // 4. With max_tokens=10, a 40-char chunk
		# (10 tokens) fits exactly; a second 40-char chunk would reach 20 > 10
		# and is excluded.
		mandatory = [{"knowledge_source": "S1", "max_chunks": 5}]
		chunks = [
			_chunk("A" * 40, "c1", "S1", title="First"),
			_chunk("B" * 40, "c2", "S1", title="Second"),
		]

		with patch(
			"huf.ai.knowledge.context_builder.get_mandatory_knowledge",
			return_value=mandatory,
		), patch(
			"huf.ai.knowledge.context_builder.knowledge_search", return_value=chunks
		):
			result = build_knowledge_context("Some Agent", "query", max_tokens=10)

		self.assertEqual([c["chunk_id"] for c in result["chunks_used"]], ["c1"])
		self.assertIn("A" * 40, result["context_text"])
		self.assertNotIn("B" * 40, result["context_text"])

	def test_oversized_first_chunk_yields_header_only(self):
		# The loop breaks (not skips) on the first chunk that exceeds the
		# remaining budget, so an oversized first chunk means no chunk content
		# at all — only the header is emitted.
		mandatory = [{"knowledge_source": "S1", "max_chunks": 5}]
		chunks = [_chunk("X" * 100, "c1", "S1")]  # 25 estimated tokens

		with patch(
			"huf.ai.knowledge.context_builder.get_mandatory_knowledge",
			return_value=mandatory,
		), patch(
			"huf.ai.knowledge.context_builder.knowledge_search", return_value=chunks
		):
			result = build_knowledge_context("Some Agent", "query", max_tokens=5)

		self.assertEqual(result["context_text"], "## Relevant Knowledge\n")
		self.assertEqual(result["chunks_used"], [])
		# the source still counts as "used" — it returned results
		self.assertEqual(result["sources_used"], ["S1"])


class TestInjectKnowledgeContext(HufTestSuite):
	def test_context_prepended_before_prompt(self):
		prompt = "What is the refund policy?"
		result = inject_knowledge_context(prompt, {"context_text": "## Relevant Knowledge\n..."})

		self.assertEqual(result, "## Relevant Knowledge\n...\n---\n\nWhat is the refund policy?")

	def test_empty_context_returns_prompt_unchanged(self):
		prompt = "What is the refund policy?"

		self.assertEqual(inject_knowledge_context(prompt, {"context_text": ""}), prompt)
		self.assertEqual(inject_knowledge_context(prompt, {}), prompt)
