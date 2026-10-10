import unittest
from types import SimpleNamespace

from huf.ai.decision.context_relevance import retain_relevant_context


class TestContextRelevance(unittest.TestCase):
	def test_uncertain_decision_retains_all_context(self):
		items = (SimpleNamespace(id="required"), SimpleNamespace(id="optional"))
		self.assertEqual(retain_relevant_context(items, ["optional"], required_ids=["required"]), items)

	def test_successful_compaction_never_drops_required_context(self):
		items = (SimpleNamespace(id="required"), SimpleNamespace(id="optional"), SimpleNamespace(id="drop"))
		result = retain_relevant_context(items, ["optional"], required_ids=["required"], decision_succeeded=True)
		self.assertEqual([item.id for item in result], ["required", "optional"])
