import unittest

from huf.ai.decision.guardrails import evaluate_guardrail
from huf.ai.decision.types import DecisionAnswer, DecisionIdentity, DecisionResponse, DecisionStatus, QuestionKind


class TestGuardrails(unittest.TestCase):
	def response(self, value, confidence):
		return DecisionResponse(status=DecisionStatus.SUCCESS, identity=DecisionIdentity(canonical_model="Jev 1.13"), answers={"safe": DecisionAnswer("safe", QuestionKind.JUDGE, value, confidence=confidence)})

	def test_rejects_only_after_confident_judge(self):
		self.assertEqual(evaluate_guardrail(self.response(0.9, 0.95)).action, "reject")
		self.assertEqual(evaluate_guardrail(self.response(0.9, 0.2)).status, "uncertain")
		self.assertEqual(evaluate_guardrail(self.response(0.1, 0.95)).action, "allow")
