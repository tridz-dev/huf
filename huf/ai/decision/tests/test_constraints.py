import unittest
from types import SimpleNamespace

from huf.ai.decision.constraints import apply_hard_constraints


class TestHardConstraints(unittest.TestCase):
	def test_filter_runs_before_decision_and_deduplicates(self):
		candidates = [SimpleNamespace(id="allowed", enabled=True), SimpleNamespace(id="blocked", enabled=False), SimpleNamespace(id="allowed", enabled=True)]
		result = apply_hard_constraints(candidates, lambda item: item.enabled)
		self.assertEqual([item.id for item in result], ["allowed"])
