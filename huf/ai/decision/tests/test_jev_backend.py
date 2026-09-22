"""Fixture-backed semantic Jev adapter tests; no live provider required."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from huf.ai.decision.backends.jev import JevSystemOneBackend
from huf.ai.decision.runtime import DecisionRuntime
from huf.ai.decision.types import CandidateSource, DecisionPolicy, DecisionRequest, Option, Question, QuestionKind, StateBinding


FIXTURES = Path(__file__).parents[4] / "docs" / "fixtures" / "decision-runtime" / "jev-systemone"


def fixture_transport(name):
	data = json.loads((FIXTURES / name).read_text())
	return lambda payload: (data["http_status"], data["response"])


class TestJevSystemOneBackend(unittest.TestCase):
	def request(self, questions, state="synthetic support request"):
		policy = DecisionPolicy(
			policy_id="jev-fixture",
			questions=tuple(questions),
			state_bindings=(StateBinding("request", "$"),),
		)
		return DecisionRequest(policy=policy, state=state, candidate_source=CandidateSource.POLICY_OPTIONS)

	def test_mixed_fixture_normalizes_to_huf_answers(self):
		questions = (
			Question("is_urgent", QuestionKind.JUDGE, "Does this require urgent attention?"),
			Question("department", QuestionKind.SELECT, "Which team?", (Option("returns"), Option("shipping"), Option("billing"))),
			Question("frustration", QuestionKind.SCORE, "How frustrated?", (Option("calm", "Calm"), Option("frustrated", "Frustrated"), Option("very_angry", "Very angry"))),
		)
		response = DecisionRuntime().evaluate(
			self.request(questions),
			JevSystemOneBackend(transport=fixture_transport("mixed_success.json")),
		)
		self.assertEqual(response.status.value, "success")
		self.assertEqual(response.answers["department"].value, "shipping")
		self.assertEqual(response.answers["frustration"].value, "very_angry")
		self.assertEqual(response.identity.model_family, "Jev")
		self.assertEqual(response.identity.provider_model_id, "jev-1.13-free")

	def test_score_fixture_maps_numeric_legend_to_ordered_huf_levels(self):
		question = Question("frustration", QuestionKind.SCORE, "How frustrated?", (Option("calm", "Calm"), Option("frustrated", "Frustrated"), Option("very_angry", "Very angry")))
		response = DecisionRuntime().evaluate(self.request((question,)), JevSystemOneBackend(transport=fixture_transport("score_success.json")))
		self.assertEqual(response.answers["frustration"].value, "calm")

	def test_provider_failures_are_normalized(self):
		question = Question("urgent", QuestionKind.JUDGE, "Urgent?")
		for status, expected in ((401, "authentication_failed"), (429, "rate_limited"), (503, "unavailable")):
			with self.subTest(status=status):
				backend = JevSystemOneBackend(transport=lambda payload, status=status: (status, {}))
				response = DecisionRuntime().evaluate(self.request((question,)), backend)
				self.assertEqual(response.status.value, expected)


if __name__ == "__main__":
	unittest.main()
