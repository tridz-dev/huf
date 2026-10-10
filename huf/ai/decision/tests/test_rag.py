import unittest
from types import SimpleNamespace

from huf.ai.decision.rag import get_retrieval_candidates, retain_selected_context


class TestRagCandidates(unittest.TestCase):
	def test_hard_visibility_filter_precedes_context_selection(self):
		docs = [SimpleNamespace(id="a", visible=True), SimpleNamespace(id="b", visible=False), SimpleNamespace(id="a", visible=True)]
		eligible = get_retrieval_candidates(docs, eligible=lambda item: item.visible)
		self.assertEqual([item.id for item in eligible], ["a"])
		self.assertEqual([item.id for item in retain_selected_context(eligible, ["a", "b"])], ["a"])
