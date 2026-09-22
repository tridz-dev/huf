import unittest

from huf.ai.decision.backends.classifier import ClassifierBackend
from huf.ai.decision.runtime import DecisionRuntime
from huf.ai.decision.types import CandidateSource, DecisionPolicy, DecisionRequest, DecisionStatus, Option, Question, QuestionKind, StateBinding


class TestClassifierBackend(unittest.TestCase):
	def test_classifier_uses_normalized_contract(self):
		policy = DecisionPolicy(policy_id="classify", questions=(Question("label", QuestionKind.SELECT, "Label", (Option("billing"), Option("support"))),), state_bindings=(StateBinding("request", "$"),))
		backend = ClassifierBackend(lambda state, question: ("billing", 0.91))
		response = DecisionRuntime().evaluate(DecisionRequest(policy=policy, state="invoice issue", candidates=(Option("billing"), Option("support")), candidate_source=CandidateSource.POLICY_OPTIONS), backend)
		self.assertEqual(response.status, DecisionStatus.SUCCESS)
		self.assertEqual(response.identity.model_class, "Classifier")
		self.assertEqual(response.answers["label"].value, "billing")
