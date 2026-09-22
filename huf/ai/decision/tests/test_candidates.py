import unittest
from types import SimpleNamespace

from huf.ai.decision.candidates import constrain_selected_tool, get_tool_candidates


class TestDecisionCandidates(unittest.TestCase):
	def test_candidates_are_deduplicated_from_authoritative_tools(self):
		tools = [SimpleNamespace(tool_name="refund", description="Refund a payment"), SimpleNamespace(tool_name="refund"), SimpleNamespace(tool_name="lookup")]
		self.assertEqual([option.id for option in get_tool_candidates(tools)], ["refund", "lookup"])

	def test_selection_cannot_widen_authority(self):
		tools = [SimpleNamespace(tool_name="refund")]
		self.assertEqual(constrain_selected_tool("refund", tools), "refund")
		self.assertIsNone(constrain_selected_tool("delete", tools))
