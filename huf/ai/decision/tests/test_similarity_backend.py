import unittest

from huf.ai.decision.backends.similarity import SimilarityBackend
from huf.ai.decision.runtime import DecisionRuntime
from huf.ai.decision.types import CandidateSource, DecisionCapabilities, DecisionIdentity, DecisionPolicy, DecisionRequest, DecisionStatus, DeploymentSpec, Option, Question, QuestionKind, StateBinding


class TestSimilarityBackend(unittest.TestCase):
	def test_similarity_selects_highest_scoring_option(self):
		policy = DecisionPolicy(policy_id="similarity", questions=(Question("team", QuestionKind.SELECT, "Team", (Option("billing"), Option("support"))),), state_bindings=(StateBinding("request", "$"),))
		backend = SimilarityBackend(lambda state, question, option: 0.9 if option.id == "billing" else 0.1)
		response = DecisionRuntime().evaluate(DecisionRequest(policy=policy, state="invoice", candidate_source=CandidateSource.POLICY_OPTIONS), backend)
		self.assertEqual(response.status, DecisionStatus.SUCCESS)
		self.assertEqual(response.identity.model_class, "Similarity")
		self.assertEqual(response.answers["team"].value, "billing")

	def test_zero_arg_constructor_keeps_hardcoded_identity(self):
		backend = SimilarityBackend()
		self.assertEqual(backend.identity.canonical_model, "Local Similarity v1")
		self.assertIsNone(backend.scorer)

	def test_from_deployment_uses_deployment_identity_and_capabilities_but_no_scorer(self):
		spec = DeploymentSpec(
			identity=DecisionIdentity(model_class="Similarity", model_family="Local", canonical_model="Acme Similarity v2", provider="Acme"),
			effective_capabilities=DecisionCapabilities(primitives=frozenset({QuestionKind.SELECT}), parallel_questions=False, probabilities=True, confidence=True),
			wire_protocol="local",
		)
		backend = SimilarityBackend.from_deployment(spec, transport=None)
		self.assertEqual(backend.identity.canonical_model, "Acme Similarity v2")
		self.assertEqual(backend.capabilities(), spec.effective_capabilities)
		self.assertIsNone(backend.scorer)

	def test_from_deployment_without_scorer_raises_on_evaluate(self):
		spec = DeploymentSpec(
			identity=DecisionIdentity(canonical_model="Acme Similarity v2"),
			effective_capabilities=DecisionCapabilities(primitives=frozenset({QuestionKind.SELECT})),
			wire_protocol="local",
		)
		backend = SimilarityBackend.from_deployment(spec, transport=None)
		policy = DecisionPolicy(policy_id="similarity", questions=(Question("team", QuestionKind.SELECT, "Team", (Option("billing"),)),), state_bindings=(StateBinding("request", "$"),))
		response = DecisionRuntime().evaluate(DecisionRequest(policy=policy, state="x", candidate_source=CandidateSource.POLICY_OPTIONS), backend)
		self.assertEqual(response.status, DecisionStatus.FAILED)
