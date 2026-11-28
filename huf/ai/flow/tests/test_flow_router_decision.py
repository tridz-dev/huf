import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from huf.ai.decision.backends.fake import FakeDecisionBackend
from huf.ai.decision.types import DecisionAnswer, DecisionStatus, QuestionKind
from huf.ai.flow.nodes.routing import router_decision as rd
from huf.ai.run_budget import AIDisabled, RunBudget, RunBudgetExceeded

DECISION = {
	"candidates": [{"node_id": "billing", "label": "Billing"}, {"node_id": "shipping", "label": "Shipping"}],
	"instructions": "Pick the team",
	"uncertain_next": "review",
	"minimum_confidence": 0.7,
}


def _answer(value, confidence=0.9):
	return FakeDecisionBackend(answers={"route": DecisionAnswer("route", QuestionKind.SELECT, value, confidence=confidence)})


class TestFlowRouterDecision(unittest.TestCase):
	def setUp(self):
		p1 = patch("huf.ai.run_budget.assert_ai_enabled", return_value={"enabled": True})
		p2 = patch("huf.ai.run_budget.peek_current_budget", return_value=None)
		self.ai = p1.start()
		self.budget = p2.start()
		self.addCleanup(patch.stopall)

	def run_node(self, backend, decision=DECISION):
		return rd.exec_router_decision(None, {"id": "r"}, {"decision": decision}, {}, None, backend=backend)

	def test_success_routes_to_selected_node(self):
		backend = _answer("shipping")
		out = self.run_node(backend)
		self.assertEqual(out["next_node_id"], "shipping")
		self.assertEqual(out["output"]["decision"], "success")
		self.assertEqual(backend.call_count, 1)

	def test_low_confidence_routes_uncertain(self):
		out = self.run_node(_answer("billing", 0.2))
		self.assertEqual((out["next_node_id"], out["output"]["reason"]), ("review", "decision_low_confidence"))

	def test_invalid_route_routes_uncertain(self):
		out = self.run_node(_answer("refunds"))
		self.assertEqual(out["next_node_id"], "review")

	def test_backend_error_routes_uncertain(self):
		out = self.run_node(FakeDecisionBackend(status=DecisionStatus.FAILED))
		self.assertEqual(out["next_node_id"], "review")
		self.assertEqual(out["output"]["decision"], "uncertain")

	def test_kill_switch_skips_backend(self):
		self.ai.side_effect = AIDisabled("ai_disabled")
		backend = _answer("billing")
		out = self.run_node(backend)
		self.assertEqual((out["next_node_id"], out["output"]["reason"]), ("review", "ai_disabled"))
		self.assertEqual(backend.call_count, 0)

	def test_expired_budget_skips_backend(self):
		budget = RunBudget(datetime.now() - timedelta(seconds=5), 10, 0, [], 0.0)
		self.assertTrue(budget.is_deadline_exceeded())
		self.budget.return_value = budget
		backend = _answer("billing")
		with patch.object(budget, "check_deadline", side_effect=RunBudgetExceeded("deadline")):
			out = self.run_node(backend)
		self.assertEqual((out["next_node_id"], out["output"]["reason"]), ("review", "budget_exceeded"))
		self.assertEqual(backend.call_count, 0)

	def test_missing_uncertain_next_fails(self):
		out = self.run_node(_answer("billing"), {**DECISION, "uncertain_next": None})
		self.assertEqual(out["status"], "failed")

	def test_rule_mode_without_decision(self):
		with patch("huf.ai.flow.nodes.routing.switch.exec_switch", return_value={"status": "success", "next_node_id": "d"}) as sw:
			out = rd.exec_router_decision(None, {}, {"default": "d"}, {}, None)
		self.assertEqual(out["next_node_id"], "d")
		sw.assert_called_once()
