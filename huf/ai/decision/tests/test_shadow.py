import unittest

from huf.ai.decision.shadow import DecisionShadowConfig, run_shadow, should_shadow
from huf.ai.decision.types import DecisionAnswer, DecisionIdentity, DecisionResponse, DecisionStatus, QuestionKind


class TestDecisionShadow(unittest.TestCase):
	def response(self, value):
		return DecisionResponse(status=DecisionStatus.SUCCESS, identity=DecisionIdentity(canonical_model="Jev 1.13"), answers={"urgent": DecisionAnswer("urgent", QuestionKind.JUDGE, value)})

	def test_default_off_and_write_paths_never_shadow(self):
		config = DecisionShadowConfig()
		self.assertFalse(should_shadow(config, read_only=True, contains_writes=False, runs_used=0, random_value=0))
		self.assertFalse(should_shadow(DecisionShadowConfig(enabled=True, sample_rate=1, max_runs=2), read_only=True, contains_writes=True, runs_used=0, random_value=0))

	def test_shadow_compares_normalized_answers_without_changing_primary(self):
		result = run_shadow(self.response(0.9), lambda: self.response(0.1), config=DecisionShadowConfig(enabled=True, sample_rate=1, max_runs=1), read_only=True, contains_writes=False, runs_used=0, random_value=0)
		self.assertTrue(result.sampled)
		self.assertFalse(result.matched)
		self.assertEqual(result.answer_mismatches, ("urgent",))
