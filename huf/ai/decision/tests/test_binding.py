import unittest
from types import SimpleNamespace

from huf.ai.decision.binding import resolve_agent_decision_binding


class TestDecisionBinding(unittest.TestCase):
	def test_off_binding_is_inert_by_default(self):
		agent = SimpleNamespace(decision_bindings=[SimpleNamespace(surface="Tool Selection", policy="pick", mode="Off", enabled=True)])
		self.assertIsNone(resolve_agent_decision_binding(agent, "Tool Selection"))

	def test_enforce_binding_is_explicit_and_priority_ordered(self):
		agent = SimpleNamespace(decision_bindings=[SimpleNamespace(surface="Tool Selection", policy="slow", mode="Enforce", priority=20, enabled=True), SimpleNamespace(surface="Tool Selection", policy="fast", mode="Enforce", priority=10, enabled=True)])
		resolved = resolve_agent_decision_binding(agent, "Tool Selection")
		self.assertEqual((resolved.policy, resolved.mode), ("fast", "Enforce"))
