"""Reusable unittest conformance checks for Decision Runtime backends."""

from __future__ import annotations

import unittest

from huf.ai.decision.runtime import DecisionRuntime
from huf.ai.decision.types import (
	DecisionPolicy,
	DecisionRequest,
	DecisionStatus,
	Option,
	Question,
	QuestionKind,
	StateBinding,
	CandidateSource,
)


class DecisionBackendConformance:
	"""Subclass and implement ``make_backend`` to run the common backend contract."""

	@classmethod
	def make_backend(cls):
		raise NotImplementedError

	def request(
		self,
		*,
		state="A customer needs help",
		questions=None,
		modalities=frozenset({"text"}),
		execution_context=None,
		**policy_fields,
	):
		questions = questions or (
			Question(
				id="route",
				kind=QuestionKind.SELECT,
				instructions="Choose the best route",
				options=(Option("billing", "Payment problems"), Option("shipping", "Delivery problems")),
			),
			Question(id="urgent", kind=QuestionKind.JUDGE, instructions="Does this need urgent attention?"),
			Question(
				id="sentiment",
				kind=QuestionKind.SCORE,
				instructions="Rate the sentiment",
				options=(Option("calm"), Option("upset")),
			),
		)
		policy_fields.setdefault("state_bindings", (StateBinding("request", "$"),))
		policy = DecisionPolicy(policy_id="conformance", questions=questions, **policy_fields)
		return DecisionRequest(
			policy=policy,
			state=state,
			candidate_source=CandidateSource.POLICY_OPTIONS,
			modalities=modalities,
			execution_context=execution_context or {},
		)

	def test_mixed_questions_are_batched_and_normalized(self):
		backend = self.make_backend()
		response = DecisionRuntime().evaluate(self.request(), backend)
		self.assertEqual(response.status, DecisionStatus.SUCCESS)
		self.assertEqual(set(response.answers), {"route", "urgent", "sentiment"})
		self.assertEqual(backend.call_count, 1)
		self.assertEqual(backend.last_request.policy.questions[0].kind, QuestionKind.SELECT)

	def test_select_never_invents_a_candidate(self):
		backend = self.make_backend()
		response = DecisionRuntime().evaluate(self.request(), backend)
		if response.status == DecisionStatus.SUCCESS:
			self.assertIn(response.answers["route"].value, {"billing", "shipping"})

	def test_usage_unknown_is_not_reported_as_zero(self):
		backend = self.make_backend()
		response = DecisionRuntime().evaluate(self.request(), backend)
		if response.status == DecisionStatus.SUCCESS:
			self.assertIsNone(response.usage.input_tokens)
			self.assertIsNone(response.usage.output_tokens)


class TestFakeBackendConformance(DecisionBackendConformance, unittest.TestCase):
	@classmethod
	def make_backend(cls):
		from huf.ai.decision.backends.fake import FakeDecisionBackend

		return FakeDecisionBackend()

	def test_invalid_candidate_is_rejected(self):
		from huf.ai.decision.backends.fake import FakeDecisionBackend
		from huf.ai.decision.types import DecisionAnswer

		backend = FakeDecisionBackend(
			answers={"route": DecisionAnswer("route", QuestionKind.SELECT, "admin", confidence=1.0)}
		)
		response = DecisionRuntime().evaluate(self.request(), backend)
		self.assertEqual(response.status, DecisionStatus.FAILED)
		self.assertEqual(response.error_code, "DECISION_CANDIDATE_INVALID")

	def test_response_answer_id_must_match_mapping_key(self):
		from huf.ai.decision.backends.fake import FakeDecisionBackend
		from huf.ai.decision.types import DecisionAnswer

		backend = FakeDecisionBackend(answers={
			"route": DecisionAnswer("urgent", QuestionKind.SELECT, "billing"),
		})
		response = DecisionRuntime().evaluate(self.request(), backend)
		self.assertEqual(response.status, DecisionStatus.INVALID_RESPONSE)

	def test_score_probabilities_cannot_name_unknown_levels(self):
		from huf.ai.decision.backends.fake import FakeDecisionBackend
		from huf.ai.decision.types import DecisionAnswer

		backend = FakeDecisionBackend(answers={
			"sentiment": DecisionAnswer(
				"sentiment", QuestionKind.SCORE, "calm", probabilities={"admin": 1.0}
			),
		})
		response = DecisionRuntime().evaluate(self.request(), backend)
		self.assertEqual(response.status, DecisionStatus.INVALID_RESPONSE)
		self.assertEqual(response.error_code, "DECISION_INVALID_RESPONSE")

	def test_state_limit_is_checked_before_dispatch(self):
		from huf.ai.decision.backends.fake import FakeDecisionBackend

		backend = FakeDecisionBackend()
		request = self.request(state="x" * 100, max_state_bytes=10)
		response = DecisionRuntime().evaluate(request, backend)
		self.assertEqual(response.error_code, "DECISION_STATE_TOO_LARGE")
		self.assertEqual(backend.call_count, 0)

	def test_unsupported_modality_is_not_stringified(self):
		from huf.ai.decision.backends.fake import FakeDecisionBackend

		backend = FakeDecisionBackend()
		request = self.request(modalities=frozenset({"text", "image"}))
		response = DecisionRuntime().evaluate(request, backend)
		self.assertEqual(response.error_code, "DECISION_UNSUPPORTED_MODALITY")
		self.assertEqual(backend.call_count, 0)

	def test_unavailable_capability_is_rejected_without_fanout(self):
		from huf.ai.decision.backends.fake import FakeDecisionBackend
		from huf.ai.decision.types import DecisionCapabilities

		backend = FakeDecisionBackend(
			capabilities=DecisionCapabilities(primitives=frozenset({QuestionKind.SELECT}), parallel_questions=False)
		)
		response = DecisionRuntime().evaluate(self.request(), backend)
		self.assertEqual(response.error_code, "DECISION_UNSUPPORTED_CAPABILITY")
		self.assertEqual(backend.call_count, 0)

	def test_telemetry_redacts_state_and_excludes_execution_context(self):
		from huf.ai.decision.backends.fake import FakeDecisionBackend

		events = []
		request = self.request(state={"text": "private"}, execution_context={"api_key": "secret"})
		response = DecisionRuntime(telemetry_sink=events.append).evaluate(request, FakeDecisionBackend())
		self.assertEqual(response.status, DecisionStatus.SUCCESS)
		self.assertEqual(len(events), 1)
		self.assertIsNotNone(events[0].state_hash)
		self.assertIsNone(events[0].state_snapshot)
		self.assertNotIn("secret", repr(events[0]))

	def test_model_and_provider_identity_are_separate(self):
		from huf.ai.decision.backends.fake import FakeDecisionBackend
		from huf.ai.decision.types import DecisionIdentity

		identity = DecisionIdentity(
			model_class="System One",
			model_family="Jev",
			canonical_model="Jev 1.13",
			canonical_version="1.13",
			provider="OpenCode Zen",
			deployment="Jev 1.13 @ OpenCode Zen",
			provider_model_id="jev-1.13-free",
		)
		response = DecisionRuntime().evaluate(
			DecisionRequest(policy=self.request().policy, state="test", identity=identity), FakeDecisionBackend()
		)
		self.assertEqual(response.identity.canonical_model, "Jev 1.13")
		self.assertEqual(response.identity.provider, "OpenCode Zen")
		self.assertEqual(response.identity.provider_model_id, "jev-1.13-free")


if __name__ == "__main__":
	unittest.main()
