import unittest

from huf.ai.decision.backends.similarity import SimilarityBackend
from huf.ai.decision.runtime import DecisionRuntime
from huf.ai.decision.types import CandidateSource, DecisionPolicy, DecisionRequest, DecisionStatus, Option, Question, QuestionKind, StateBinding


class TestSimilarityBackend(unittest.TestCase):
	def test_similarity_selects_highest_scoring_option(self):
		policy = DecisionPolicy(policy_id="similarity", questions=(Question("team", QuestionKind.SELECT, "Team", (Option("billing"), Option("support"))),), state_bindings=(StateBinding("request", "$"),))
		backend = SimilarityBackend(lambda state, question, option: 0.9 if option.id == "billing" else 0.1)
		response = DecisionRuntime().evaluate(DecisionRequest(policy=policy, state="invoice", candidate_source=CandidateSource.POLICY_OPTIONS), backend)
		self.assertEqual(response.status, DecisionStatus.SUCCESS)
		self.assertEqual(response.identity.model_class, "Similarity")
		self.assertEqual(response.answers["team"].value, "billing")
