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
	policy_fields = {
		key: kwargs.pop(key)
		for key in ("minimum_confidence", "fallback_action", "store_state")
		if key in kwargs
	}
	return DecisionRequest(policy=_policy(*questions, **policy_fields), state={"message": "please help"}, **kwargs)


class _RawResponseBackend(FakeDecisionBackend):
	def __init__(self, response: DecisionResponse):
		super().__init__()
		self._response = response

	def evaluate(self, request):
		self.call_count += 1
		self.last_request = request
		return self._response


class TestDecisionRuntimeContract(unittest.TestCase):
	def test_timeouts_and_provider_unavailability_keep_safe_statuses(self):
		for status, error_code in (
			(DecisionStatus.TIMEOUT, "DECISION_TIMEOUT"),
			(DecisionStatus.UNAVAILABLE, "DECISION_PROVIDER_UNAVAILABLE"),
			(DecisionStatus.AUTHENTICATION_FAILED, "DECISION_AUTHENTICATION_FAILED"),
			(DecisionStatus.RATE_LIMITED, "DECISION_RATE_LIMITED"),
		):
			with self.subTest(status=status):
				response = DecisionRuntime().evaluate(
					_request(_select_question()),
					_RawResponseBackend(
						DecisionResponse(
							status=status,
							answers={"route": DecisionAnswer("route", QuestionKind.SELECT, "billing")},
						)
					),
				)
				self.assertEqual(response.status, status)
				self.assertEqual(response.error_code, error_code)
				self.assertEqual(response.answers, {})

	def test_candidate_caps_are_checked_before_dispatch(self):
		request = _request(
			_select_question(),
			candidates=(Option("billing"), Option("shipping"), Option("returns")),
			candidate_source=CandidateSource.ROUTEABLE_MODELS,
		)
		backend = FakeDecisionBackend(
			capabilities=DecisionCapabilities(
				primitives=frozenset({QuestionKind.SELECT}),
				max_candidates_per_select=2,
			)
		)

		response = DecisionRuntime().evaluate(request, backend)

		self.assertEqual(response.error_code, "DECISION_CANDIDATE_LIMIT_EXCEEDED")
		self.assertEqual(backend.call_count, 0)

	def test_candidate_source_must_be_a_closed_enum(self):
		request = _request(_select_question(), candidate_source="raw_agent_config")
		backend = FakeDecisionBackend()

		response = DecisionRuntime().evaluate(request, backend)

		self.assertEqual(response.error_code, "DECISION_CANDIDATE_INVALID")
		self.assertEqual(backend.call_count, 0)

	def test_confidence_threshold_requires_confidence_capability_before_dispatch(self):
		request = _request(_select_question(), minimum_confidence=0.7)
		backend = FakeDecisionBackend(
			capabilities=DecisionCapabilities(primitives=frozenset({QuestionKind.SELECT}), confidence=False)
		)

		response = DecisionRuntime().evaluate(request, backend)

		self.assertEqual(response.error_code, "DECISION_UNSUPPORTED_CAPABILITY")
		self.assertEqual(backend.call_count, 0)

	def test_missing_confidence_makes_threshold_uncertain(self):
		request = _request(_select_question(), minimum_confidence=0.7)
		response = DecisionRuntime().evaluate(
			request,
			_RawResponseBackend(
				DecisionResponse(
					status=DecisionStatus.SUCCESS,
					answers={"route": DecisionAnswer("route", QuestionKind.SELECT, "billing")},
				)
			),
		)
		self.assertEqual(response.status, DecisionStatus.SUCCESS)
		self.assertEqual(response.gate_result, "uncertain")
	def test_response_answer_keys_and_order_must_match_policy_questions(self):
		questions = (_select_question(), _score_question())
		answers = {
			"priority": DecisionAnswer("priority", QuestionKind.SCORE, "high"),
			"route": DecisionAnswer("route", QuestionKind.SELECT, "billing"),
		}

		response = DecisionRuntime().evaluate(
			_request(*questions),
			_RawResponseBackend(DecisionResponse(status=DecisionStatus.SUCCESS, answers=answers)),
		)

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

	def test_malformed_success_answer_container_is_invalid(self):
		response = DecisionRuntime().evaluate(
			_request(_select_question()),
			_RawResponseBackend(DecisionResponse(status=DecisionStatus.SUCCESS, answers=None)),
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

	def test_allow_none_still_rejects_probability_keys_outside_candidate_set(self):
		question = Question(
			id="route",
			kind=QuestionKind.SELECT,
			instructions="Choose a route or none",
			options=(Option("billing"), Option("shipping")),
			allow_none=True,
		)
		backend = FakeDecisionBackend(
			answers={
				"route": DecisionAnswer(
					"route", QuestionKind.SELECT, "none", probabilities={"unauthorized": 1.0}
				)
			}
		)
		response = DecisionRuntime().evaluate(_request(question), backend)
		self.assertEqual(response.status, DecisionStatus.FAILED)
		self.assertEqual(response.error_code, "DECISION_CANDIDATE_INVALID")

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

	def test_telemetry_request_labels_are_bounded_and_redacted(self):
		events = []
		request = _request(
			_select_question(),
			execution_context={},
		)
		request = DecisionRequest(
			policy=DecisionPolicy(
				policy_id="api_key=leaked",
				questions=request.policy.questions,
				state_bindings=request.policy.state_bindings,
			),
			state=request.state,
			surface="token=also-leaked",
			candidate_source=CandidateSource.POLICY_OPTIONS,
		)
		DecisionRuntime(telemetry_sink=events.append).evaluate(request, FakeDecisionBackend())
		self.assertEqual(events[0].policy_id, "unknown")
		self.assertEqual(events[0].surface, "generic")
		self.assertNotIn("leaked", repr(events[0]))

	def test_structured_credentials_are_redacted_before_dispatch_and_audit(self):
		policy = _policy(_select_question(), store_state=True)
		request = DecisionRequest(
			policy=policy,
			state={"message": "please help", "api_key": "never-send-me", "nested": {"password": "hidden"}},
			candidate_source=CandidateSource.POLICY_OPTIONS,
		)
		backend = FakeDecisionBackend()
		events = []
		response = DecisionRuntime(telemetry_sink=events.append).evaluate(request, backend)
		self.assertEqual(response.status, DecisionStatus.SUCCESS)
		self.assertEqual(backend.last_request.state["request"]["api_key"], "[REDACTED]")
		self.assertEqual(events[0].state_snapshot["request"]["nested"]["password"], "[REDACTED]")
		self.assertNotIn("never-send-me", repr(events[0]))

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
		events = []
		runtime = DecisionRuntime(telemetry_sink=events.append)
		policy = _policy(_select_question(), fallback_action="ask-human")
		request = DecisionRequest(
			policy=policy,
			state={"message": "please help"},
			candidate_source=CandidateSource.POLICY_OPTIONS,
		)
		response = DecisionResponse(
			status=DecisionStatus.UNAVAILABLE,
			requested_identity=DecisionIdentity(canonical_model="routing-v1"),
		)

		with self.assertRaises(ValueError):
			runtime.apply_policy_fallback(request, response, deployments_exhausted=False)

		fallback_response = runtime.apply_policy_fallback(request, response, deployments_exhausted=True)
		self.assertEqual(fallback_response.policy_fallback_action, "ask-human")
		self.assertIsNone(fallback_response.deployment_selection_source)
		self.assertEqual(events[-1].policy_fallback_action, "ask-human")

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

	def test_credential_shaped_identity_and_fallback_labels_are_redacted(self):
		response = DecisionRuntime().evaluate(
			_request(_select_question()),
			_RawResponseBackend(
				DecisionResponse(
					status=DecisionStatus.SUCCESS,
					answers={"route": DecisionAnswer("route", QuestionKind.SELECT, "billing")},
					identity=DecisionIdentity(
						provider="primary",
						provider_model_id="token=private-value",
					),
					deployment_fallback_chain=("primary", "token=private-value"),
				)
			),
		)
		self.assertEqual(response.identity.provider, "primary")
		self.assertIsNone(response.identity.provider_model_id)
		self.assertEqual(response.deployment_fallback_chain, ("primary",))


if __name__ == "__main__":
	unittest.main()
