import unittest

from huf.ai.decision.backends.classifier import ClassifierBackend
from huf.ai.decision.runtime import DecisionRuntime
from huf.ai.decision.types import CandidateSource, DecisionCapabilities, DecisionIdentity, DecisionPolicy, DecisionRequest, DecisionStatus, DeploymentSpec, Option, Question, QuestionKind, StateBinding


class TestClassifierBackend(unittest.TestCase):
	def test_classifier_uses_normalized_contract(self):
		policy = DecisionPolicy(policy_id="classify", questions=(Question("label", QuestionKind.SELECT, "Label", (Option("billing"), Option("support"))),), state_bindings=(StateBinding("request", "$"),))
		backend = ClassifierBackend(lambda state, question: ("billing", 0.91))
		response = DecisionRuntime().evaluate(DecisionRequest(policy=policy, state="invoice issue", candidate_source=CandidateSource.POLICY_OPTIONS), backend)
		self.assertEqual(response.status, DecisionStatus.SUCCESS)
		self.assertEqual(response.identity.model_class, "Classifier")
		self.assertEqual(response.answers["label"].value, "billing")

	def test_zero_arg_constructor_keeps_hardcoded_identity(self):
		backend = ClassifierBackend()
		self.assertEqual(backend.identity.canonical_model, "Local Classifier v1")
		self.assertIsNone(backend.classifier)

	def test_from_deployment_uses_deployment_identity_and_capabilities_but_no_classifier(self):
		spec = DeploymentSpec(
			identity=DecisionIdentity(model_class="Classifier", model_family="Local", canonical_model="Acme Classifier v2", provider="Acme"),
			effective_capabilities=DecisionCapabilities(primitives=frozenset({QuestionKind.SELECT}), parallel_questions=False, probabilities=False, confidence=True),
			wire_protocol="local",
		)
		backend = ClassifierBackend.from_deployment(spec, transport=None)
		self.assertEqual(backend.identity.canonical_model, "Acme Classifier v2")
		self.assertEqual(backend.capabilities(), spec.effective_capabilities)
		self.assertIsNone(backend.classifier)

	def test_from_deployment_without_classifier_raises_on_evaluate(self):
		spec = DeploymentSpec(
			identity=DecisionIdentity(canonical_model="Acme Classifier v2"),
			effective_capabilities=DecisionCapabilities(primitives=frozenset({QuestionKind.SELECT})),
			wire_protocol="local",
		)
		backend = ClassifierBackend.from_deployment(spec, transport=None)
		policy = DecisionPolicy(policy_id="classify", questions=(Question("label", QuestionKind.SELECT, "Label", (Option("billing"),)),), state_bindings=(StateBinding("request", "$"),))
		# DecisionRuntime.evaluate catches this and returns a FAILED response rather than
		# propagating -- confirms the missing-classifier case is a normal evaluate-time failure,
		# not a crash.
		response = DecisionRuntime().evaluate(DecisionRequest(policy=policy, state="x", candidate_source=CandidateSource.POLICY_OPTIONS), backend)
		self.assertEqual(response.status, DecisionStatus.FAILED)
