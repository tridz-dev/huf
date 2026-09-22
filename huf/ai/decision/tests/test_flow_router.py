import unittest

from huf.ai.decision.flow_router import resolve_decision_route
from huf.ai.decision.types import DecisionAnswer, DecisionIdentity, DecisionResponse, DecisionStatus, QuestionKind


class TestFlowDecisionRouter(unittest.TestCase):
	def response(self, value, confidence=0.9):
		return DecisionResponse(status=DecisionStatus.SUCCESS, identity=DecisionIdentity(canonical_model="Jev 1.13"), answers={"route": DecisionAnswer("route", QuestionKind.SELECT, value, confidence=confidence)})

	def test_selects_only_declared_branch(self):
		result = resolve_decision_route(self.response("billing"), candidate_node_ids={"billing", "shipping"})
		self.assertEqual(result["next_node_id"], "billing")

	def test_low_confidence_routes_to_uncertain_next(self):
		result = resolve_decision_route(self.response("billing", 0.2), candidate_node_ids={"billing"}, minimum_confidence=0.8, uncertain_next="review")
		self.assertEqual(result, {"status": "uncertain", "next_node_id": "review", "reason": "decision_low_confidence"})
