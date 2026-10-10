"""Fixture-free contract tests for the provider-neutral structured backend."""

from __future__ import annotations

import unittest

from huf.ai.decision.backends.structured import StructuredLLMBackend
from huf.ai.decision.runtime import DecisionRuntime
from huf.ai.decision.types import CandidateSource, DecisionPolicy, DecisionRequest, Option, Question, QuestionKind, StateBinding


class TestStructuredLLMBackend(unittest.TestCase):
	def test_same_policy_contract_normalizes_structured_answers(self):
		questions = (
			Question("route", QuestionKind.SELECT, "Choose a route", (Option("billing"), Option("shipping"))),
			Question("urgent", QuestionKind.JUDGE, "Is this urgent?"),
		)
		policy = DecisionPolicy(
			policy_id="structured-contract",
			questions=questions,
			state_bindings=(StateBinding("request", "$"),),
		)
		request = DecisionRequest(policy=policy, state="synthetic", candidate_source=CandidateSource.POLICY_OPTIONS)

		def transport(payload):
			return 200, {
				"answers": {
					"route": {"value": "billing", "confidence": 0.9, "probabilities": {"billing": 0.9, "shipping": 0.1}},
					"urgent": {"value": 0.2, "confidence": 0.8},
				},
				"usage": {"input_tokens": 10, "output_tokens": 8},
			}

		response = DecisionRuntime().evaluate(request, StructuredLLMBackend(transport=transport))
		self.assertEqual(response.status.value, "success")
		self.assertEqual(response.answers["route"].value, "billing")
		self.assertEqual(response.answers["urgent"].value, 0.2)
		self.assertEqual(response.identity.model_class, "Structured LLM")

	def test_malformed_structured_answer_is_invalid(self):
		question = Question("urgent", QuestionKind.JUDGE, "Is this urgent?")
		policy = DecisionPolicy(policy_id="bad-structured", questions=(question,), state_bindings=(StateBinding("request", "$"),))
		request = DecisionRequest(policy=policy, state="synthetic", candidate_source=CandidateSource.POLICY_OPTIONS)
		backend = StructuredLLMBackend(transport=lambda payload: (200, {"answers": {"urgent": {"wrong": 1}}}))
		response = DecisionRuntime().evaluate(request, backend)
		self.assertEqual(response.status.value, "invalid_response")


if __name__ == "__main__":
	unittest.main()
