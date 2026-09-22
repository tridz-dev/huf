"""Focused runtime contract tests for normalized decision results."""

from __future__ import annotations

import unittest

from huf.ai.decision.backends.fake import FakeDecisionBackend
from huf.ai.decision.runtime import DecisionRuntime
from huf.ai.decision.types import (
	CandidateSource,
	DecisionAnswer,
	DecisionCapabilities,
	DecisionIdentity,
	DecisionPolicy,
	DecisionRequest,
	DecisionResponse,
	DecisionStatus,
	Option,
	Question,
	QuestionKind,
	StateBinding,
)


def _select_question() -> Question:
	return Question(
		id="route",
		kind=QuestionKind.SELECT,
		instructions="Choose the best route",
		options=(Option("billing"), Option("shipping")),
	)


def _score_question() -> Question:
	return Question(
		id="priority",
		kind=QuestionKind.SCORE,
		instructions="Pick the matching priority",
		options=(Option("low"), Option("high")),
	)


def _policy(*questions: Question, **kwargs) -> DecisionPolicy:
	kwargs.setdefault("state_bindings", (StateBinding("request", "$"),))
	return DecisionPolicy(policy_id="runtime-contract", questions=questions or (_select_question(),), **kwargs)


def _request(*questions: Question, **kwargs) -> DecisionRequest:
	kwargs.setdefault("candidate_source", CandidateSource.POLICY_OPTIONS)
	return DecisionRequest(policy=_policy(*questions), state={"message": "please help"}, **kwargs)


class _RawResponseBackend(FakeDecisionBackend):
	def __init__(self, response: DecisionResponse):
		super().__init__()
		self._response = response

	def evaluate(self, request):
		self.call_count += 1
		self.last_request = request
		return self._response


class TestDecisionRuntimeContract(unittest.TestCase):
	def test_response_answer_keys_and_order_must_match_policy_questions(self):
		questions = (_select_question(), _score_question())
		answers = {
			"priority": DecisionAnswer("priority", QuestionKind.SCORE, "high"),
			"route": DecisionAnswer("route", QuestionKind.SELECT, "billing"),
		}

		response = DecisionRuntime().evaluate(_request(*questions), FakeDecisionBackend(answers=answers))

		self.assertEqual(response.status, DecisionStatus.SUCCESS)
		self.assertEqual(tuple(response.answers), ("route", "priority"))
		self.assertEqual(response.answers["route"].value, "billing")
		self.assertEqual(response.answers["priority"].value, "high")

	def test_missing_or_extra_success_answers_are_invalid(self):
		questions = (_select_question(), _score_question())
		bad_payloads = (
			{"route": DecisionAnswer("route", QuestionKind.SELECT, "billing")},
			{
				"route": DecisionAnswer("route", QuestionKind.SELECT, "billing"),
				"priority": DecisionAnswer("priority", QuestionKind.SCORE, "high"),
				"extra": DecisionAnswer("extra", QuestionKind.SELECT, "billing"),
			},
		)

		for answers in bad_payloads:
			with self.subTest(keys=tuple(answers)):
				response = DecisionRuntime().evaluate(
					_request(*questions),
					_RawResponseBackend(DecisionResponse(status=DecisionStatus.SUCCESS, answers=answers)),
				)
				self.assertEqual(response.status, DecisionStatus.INVALID_RESPONSE)
				self.assertEqual(response.error_code, "DECISION_INVALID_RESPONSE")

	def test_score_answer_must_select_a_declared_rubric_option(self):
		response = DecisionRuntime().evaluate(
			_request(_score_question()),
			FakeDecisionBackend(answers={"priority": DecisionAnswer("priority", QuestionKind.SCORE, "medium")}),
		)

		self.assertEqual(response.status, DecisionStatus.INVALID_RESPONSE)
		self.assertEqual(response.error_code, "DECISION_INVALID_RESPONSE")

	def test_probabilities_and_confidence_require_declared_capabilities(self):
		request = _request(_select_question())
		answer = DecisionAnswer(
			"route",
			QuestionKind.SELECT,
			"billing",
			probabilities={"billing": 1.0, "shipping": 0.0},
			confidence=0.9,
		)
		capabilities = DecisionCapabilities(
			primitives=frozenset({QuestionKind.SELECT}),
			probabilities=False,
			confidence=False,
		)

		response = DecisionRuntime().evaluate(
			request,
			FakeDecisionBackend(answers={"route": answer}, capabilities=capabilities),
		)

		self.assertEqual(response.status, DecisionStatus.INVALID_RESPONSE)
		self.assertEqual(response.error_code, "DECISION_INVALID_RESPONSE")

	def test_backend_metadata_is_redacted_from_normalized_answers_and_telemetry(self):
		events = []
		response = DecisionRuntime(telemetry_sink=events.append).evaluate(
			_request(_select_question(), execution_context={"token": "secret-token"}),
			FakeDecisionBackend(
				answers={
					"route": DecisionAnswer(
						"route",
						QuestionKind.SELECT,
						"billing",
						backend_metadata={"raw_payload": "secret-token"},
					)
				}
			),
		)

		self.assertEqual(response.status, DecisionStatus.SUCCESS)
		self.assertEqual(response.answers["route"].backend_metadata, {})
		self.assertEqual(len(events), 1)
		self.assertNotIn("secret-token", repr(events[0]))

	def test_backend_request_excludes_execution_context(self):
		backend = FakeDecisionBackend()

		response = DecisionRuntime().evaluate(
			_request(_select_question(), execution_context={"workflow_run": "RUN-1", "api_key": "secret"}),
			backend,
		)

		self.assertEqual(response.status, DecisionStatus.SUCCESS)
		self.assertFalse(hasattr(backend.last_request, "execution_context"))
		self.assertEqual(backend.last_request.state, {"request": {"message": "please help"}})

	def test_non_success_status_maps_to_safe_error_without_backend_answers(self):
		response = DecisionRuntime().evaluate(
			_request(_select_question()),
			_RawResponseBackend(
				DecisionResponse(
					status=DecisionStatus.RATE_LIMITED,
					answers={"route": DecisionAnswer("route", QuestionKind.SELECT, "billing")},
					error_code="provider said quota: secret",
				)
			),
		)

		self.assertEqual(response.status, DecisionStatus.RATE_LIMITED)
		self.assertEqual(response.error_code, "DECISION_RATE_LIMITED")
		self.assertEqual(response.answers, {})

	def test_policy_fallback_waits_until_deployment_failover_is_exhausted(self):
		runtime = DecisionRuntime()
		policy = _policy(_select_question(), fallback_action="ask-human")
		response = DecisionResponse(
			status=DecisionStatus.UNAVAILABLE,
			requested_identity=DecisionIdentity(canonical_model="routing-v1"),
		)

		with self.assertRaises(ValueError):
			runtime.apply_policy_fallback(response, policy, deployments_exhausted=False)

		fallback_response = runtime.apply_policy_fallback(response, policy, deployments_exhausted=True)
		self.assertEqual(fallback_response.policy_fallback_action, "ask-human")
		self.assertIsNone(fallback_response.deployment_selection_source)

	def test_deployment_identity_does_not_rewrite_requested_model_identity(self):
		requested = DecisionIdentity(
			model_class="decision",
			model_family="routing",
			canonical_model="routing-v1",
			canonical_version="1",
			provider="primary-provider",
			deployment="primary",
			provider_model_id="primary/routing-v1",
		)
		resolved = DecisionIdentity(
			provider="backup-provider",
			deployment="backup",
			provider_model_id="backup/routing-v1",
		)

		response = DecisionRuntime().evaluate(
			_request(_select_question(), identity=requested),
			_RawResponseBackend(
				DecisionResponse(
					status=DecisionStatus.SUCCESS,
					answers={"route": DecisionAnswer("route", QuestionKind.SELECT, "billing")},
					identity=resolved,
					deployment_selection_source="failover",
					deployment_fallback_count=1,
					deployment_fallback_chain=("primary", "backup"),
				)
			),
		)

		self.assertEqual(response.status, DecisionStatus.SUCCESS)
		self.assertEqual(response.requested_identity, requested)
		self.assertEqual(response.identity.canonical_model, "routing-v1")
		self.assertEqual(response.identity.provider, "backup-provider")
		self.assertEqual(response.identity.deployment, "backup")
		self.assertEqual(response.deployment_fallback_count, 1)
		self.assertEqual(response.policy_fallback_action, None)


if __name__ == "__main__":
	unittest.main()
