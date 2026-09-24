"""Fixture-free contract tests for the provider-neutral structured backend."""

from __future__ import annotations

import unittest

from huf.ai.decision.backends.structured import StructuredLLMBackend
from huf.ai.decision.runtime import DecisionRuntime
from huf.ai.decision.types import CandidateSource, DecisionCapabilities, DecisionIdentity, DecisionPolicy, DecisionRequest, DeploymentSpec, Option, Question, QuestionKind, StateBinding


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

	def test_zero_arg_constructor_keeps_hardcoded_identity(self):
		backend = StructuredLLMBackend()
		self.assertEqual(backend.identity.provider, "structured-provider")
		self.assertEqual(backend.identity.deployment, "structured-llm-default")

	def test_from_deployment_uses_deployment_identity_capabilities_and_transport(self):
		spec = DeploymentSpec(
			identity=DecisionIdentity(model_class="Structured LLM", model_family="Structured LLM", canonical_model="Acme Structured v2", provider="Acme", deployment="Acme Structured v2 @ prod", provider_model_id="acme-structured-v2"),
			effective_capabilities=DecisionCapabilities(primitives=frozenset({QuestionKind.SELECT, QuestionKind.JUDGE}), parallel_questions=True, probabilities=False, confidence=True),
			wire_protocol="structured",
		)

		def transport(payload):
			return 200, {"answers": {"urgent": {"value": 0.3}}}

		backend = StructuredLLMBackend.from_deployment(spec, transport)
		self.assertEqual(backend.identity.canonical_model, "Acme Structured v2")
		self.assertEqual(backend.identity.provider, "Acme")
		self.assertEqual(backend.capabilities(), spec.effective_capabilities)

		policy = DecisionPolicy(policy_id="structured-deployed", questions=(Question("urgent", QuestionKind.JUDGE, "Urgent?"),), state_bindings=(StateBinding("request", "$"),))
		response = DecisionRuntime().evaluate(DecisionRequest(policy=policy, state="x"), backend)
		self.assertEqual(response.status.value, "success")
		self.assertEqual(response.answers["urgent"].value, 0.3)
		self.assertEqual(response.identity.provider, "Acme")


if __name__ == "__main__":
	unittest.main()
