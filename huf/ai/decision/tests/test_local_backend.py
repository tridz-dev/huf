import unittest

from huf.ai.decision.backends.local import LocalRulesBackend
from huf.ai.decision.runtime import DecisionRuntime
from huf.ai.decision.types import DecisionCapabilities, DecisionIdentity, DecisionPolicy, DecisionRequest, DeploymentSpec, Question, QuestionKind, StateBinding


class TestLocalBackend(unittest.TestCase):
	def test_local_rules_uses_the_same_normalized_runtime_contract(self):
		policy = DecisionPolicy(policy_id="local", questions=(Question("urgent", QuestionKind.JUDGE, "Urgent?"),), state_bindings=(StateBinding("request", "$"),))
		response = DecisionRuntime().evaluate(DecisionRequest(policy=policy, state="x", identity=DecisionIdentity(canonical_model="Local Rules v1")), LocalRulesBackend({"urgent": 0.9}))
		self.assertEqual(response.status.value, "success")
		self.assertEqual(response.identity.model_family, "Local")
		self.assertEqual(response.answers["urgent"].value, 0.9)

	def test_zero_arg_constructor_keeps_hardcoded_identity(self):
		backend = LocalRulesBackend()
		self.assertEqual(backend.identity.canonical_model, "Local Rules v1")
		self.assertEqual(backend.identity.model_class, "Rules")

	def test_from_deployment_uses_deployment_identity_and_capabilities(self):
		spec = DeploymentSpec(
			identity=DecisionIdentity(model_class="Rules", model_family="Local", canonical_model="Acme Rules v2", canonical_version="2", provider="Acme", deployment="Acme Rules v2 @ prod"),
			effective_capabilities=DecisionCapabilities(primitives=frozenset({QuestionKind.JUDGE}), parallel_questions=False, probabilities=False, confidence=True),
			wire_protocol="local",
		)
		backend = LocalRulesBackend.from_deployment(spec, transport=None)
		self.assertEqual(backend.identity.canonical_model, "Acme Rules v2")
		self.assertEqual(backend.identity.provider, "Acme")
		self.assertEqual(backend.capabilities(), spec.effective_capabilities)

	def test_from_deployment_ignores_transport(self):
		spec = DeploymentSpec(
			identity=DecisionIdentity(canonical_model="Acme Rules v2"),
			effective_capabilities=DecisionCapabilities(primitives=frozenset(QuestionKind), confidence=True),
			wire_protocol="local",
		)
		backend = LocalRulesBackend.from_deployment(spec, transport=object())
		policy = DecisionPolicy(policy_id="local", questions=(Question("urgent", QuestionKind.JUDGE, "Urgent?"),), state_bindings=(StateBinding("request", "$"),))
		response = DecisionRuntime().evaluate(DecisionRequest(policy=policy, state="x"), backend)
		self.assertEqual(response.status.value, "success")
		self.assertEqual(response.identity.canonical_model, "Acme Rules v2")
