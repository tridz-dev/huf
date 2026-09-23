"""Fixture-backed semantic Jev adapter tests; no live provider required."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from huf.ai.decision.backends.jev import SystemOneBackend
from huf.ai.decision.runtime import DecisionRuntime
from huf.ai.decision.types import CandidateSource, DecisionIdentity, DecisionPolicy, DecisionRequest, Option, Question, QuestionKind, StateBinding


FIXTURES = Path(__file__).parents[4] / "docs" / "fixtures" / "decision-runtime" / "jev-systemone"

# Backend no longer hardcodes provider/deployment identity in its constructor (that came from
# a deployment spec via from_deployment in real use); tests supply an explicit fixture identity
# so assertions on response.identity still exercise pass-through end to end.
FIXTURE_IDENTITY = DecisionIdentity(
	model_class="System One",
	model_family="Jev",
	canonical_model="Jev 1.13",
	canonical_version="1.13",
	provider="OpenCode Zen",
	deployment="Jev 1.13 @ OpenCode Zen",
	provider_model_id="jev-1.13-free",
)


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
			SystemOneBackend(transport=fixture_transport("mixed_success.json"), identity=FIXTURE_IDENTITY),
		)
		self.assertEqual(response.status.value, "success")
		self.assertEqual(response.answers["department"].value, "shipping")
		self.assertEqual(response.answers["frustration"].value, "very_angry")
		self.assertEqual(response.identity.model_family, "Jev")
		self.assertEqual(response.identity.provider_model_id, "jev-1.13-free")

	def test_score_fixture_maps_numeric_legend_to_ordered_huf_levels(self):
		question = Question("frustration", QuestionKind.SCORE, "How frustrated?", (Option("calm", "Calm"), Option("frustrated", "Frustrated"), Option("very_angry", "Very angry")))
		response = DecisionRuntime().evaluate(self.request((question,)), SystemOneBackend(transport=fixture_transport("score_success.json"), identity=FIXTURE_IDENTITY))
		self.assertEqual(response.answers["frustration"].value, "calm")

	def test_provider_failures_are_normalized(self):
		question = Question("urgent", QuestionKind.JUDGE, "Urgent?")
		for status, expected in ((401, "authentication_failed"), (429, "rate_limited"), (503, "unavailable")):
			with self.subTest(status=status):
				backend = SystemOneBackend(transport=lambda payload, status=status: (status, {}), identity=FIXTURE_IDENTITY)
				response = DecisionRuntime().evaluate(self.request((question,)), backend)
				self.assertEqual(response.status.value, expected)

	def test_zero_arg_construction_has_no_hardcoded_provider_identity(self):
		backend = SystemOneBackend()
		self.assertIsNone(backend.identity.provider)
		self.assertIsNone(backend.identity.deployment)
		self.assertIsNone(backend.identity.provider_model_id)
		self.assertEqual(backend.identity.model_family, "Jev")
		with self.assertRaises(ConnectionError):
			backend.transport({})

	def test_from_deployment_builds_identity_and_capabilities_from_spec(self):
		from huf.ai.decision.types import DecisionCapabilities, DeploymentSpec

		spec = DeploymentSpec(
			identity=FIXTURE_IDENTITY,
			effective_capabilities=DecisionCapabilities(
				primitives=frozenset({QuestionKind.JUDGE}),
				parallel_questions=True,
				probabilities=False,
				confidence=False,
				input_modalities=frozenset({"text"}),
			),
			wire_protocol="jev-systemone",
		)
		transport = fixture_transport("mixed_success.json")
		backend = SystemOneBackend.from_deployment(spec, transport)
		self.assertIs(backend.transport, transport)
		self.assertEqual(backend.identity, FIXTURE_IDENTITY)
		self.assertEqual(backend.capabilities(), spec.effective_capabilities)


if __name__ == "__main__":
	unittest.main()
