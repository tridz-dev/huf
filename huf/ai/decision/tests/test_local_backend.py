import unittest

from huf.ai.decision.backends.local import LocalRulesBackend
from huf.ai.decision.runtime import DecisionRuntime
from huf.ai.decision.types import DecisionIdentity, DecisionPolicy, DecisionRequest, Question, QuestionKind, StateBinding


class TestLocalBackend(unittest.TestCase):
	def test_local_rules_uses_the_same_normalized_runtime_contract(self):
		policy = DecisionPolicy(policy_id="local", questions=(Question("urgent", QuestionKind.JUDGE, "Urgent?"),), state_bindings=(StateBinding("request", "$"),))
		response = DecisionRuntime().evaluate(DecisionRequest(policy=policy, state="x", identity=DecisionIdentity(canonical_model="Local Rules v1")), LocalRulesBackend({"urgent": 0.9}))
		self.assertEqual(response.status.value, "success")
		self.assertEqual(response.identity.model_family, "Local")
		self.assertEqual(response.answers["urgent"].value, 0.9)
