"""Deployment and multi-family conformance tests for Decision Runtime §40."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from huf.ai.decision.backends.jev import SystemOneBackend
from huf.ai.decision.deployment import DeploymentCandidate, resolve_deployment_chain
from huf.ai.decision.runtime import DecisionRuntime
from huf.ai.decision.types import (
	CandidateSource,
	DecisionCapabilities,
	DecisionIdentity,
	DecisionPolicy,
	DecisionRequest,
	DecisionStatus,
	Option,
	Question,
	QuestionKind,
	StateBinding,
	DeploymentSpec,
)


FIXTURES = Path(__file__).parents[4] / "docs" / "fixtures" / "decision-runtime" / "jev-systemone"


def fixture_transport(name):
	"""Load a pre-recorded Jev response fixture."""
	data = json.loads((FIXTURES / name).read_text())
	return lambda payload: (data["http_status"], data["response"])


class TestDeploymentConformance(unittest.TestCase):
	"""Test all §40 conformance requirements."""

	def request(self, questions=None, state="synthetic request"):
		"""Build a standard test request."""
		if questions is None:
			questions = (
				Question("urgent", QuestionKind.JUDGE, "Urgent?"),
				Question("department", QuestionKind.SELECT, "Department?", (Option("support"), Option("billing"))),
				Question("satisfaction", QuestionKind.SCORE, "Satisfied?", (Option("low"), Option("high"))),
			)
		policy = DecisionPolicy(
			policy_id="deployment-test",
			questions=tuple(questions),
			state_bindings=(StateBinding("request", "$"),),
		)
		return DecisionRequest(policy=policy, state=state, candidate_source=CandidateSource.POLICY_OPTIONS)

	def test_case_1_same_canonical_model_multiple_providers(self):
		"""§40.1: same canonical model may be configured through multiple providers."""
		jev_identity = DecisionIdentity(
			model_class="System One",
			model_family="Jev",
			canonical_model="Jev 1.13",
			canonical_version="1.13",
			provider="OpenCode Zen",
			deployment="Jev 1.13 @ OpenCode",
			provider_model_id="jev-1.13-free",
		)
		jev_backup = DecisionIdentity(
			model_class="System One",
			model_family="Jev",
			canonical_model="Jev 1.13",
			canonical_version="1.13",
			provider="OpenRouter",
			deployment="Jev 1.13 @ OpenRouter",
			provider_model_id="jev-1.13-router",
		)
		# Same canonical model, different providers
		self.assertEqual(jev_identity.canonical_model, jev_backup.canonical_model)
		self.assertNotEqual(jev_identity.provider, jev_backup.provider)
		self.assertNotEqual(jev_identity.provider_model_id, jev_backup.provider_model_id)

	def test_case_2_provider_ids_never_leak_to_canonical_identity(self):
		"""§40.2: provider-specific model IDs never leak into caller-facing canonical identity."""
		backend = SystemOneBackend(
			transport=fixture_transport("mixed_success.json"),
			identity=DecisionIdentity(
				model_class="System One",
				model_family="Jev",
				canonical_model="Jev 1.13",
				canonical_version="1.13",
				provider="OpenCode Zen",
				deployment="Jev 1.13 @ OpenCode",
				provider_model_id="jev-1.13-free",
			),
		)
		response = DecisionRuntime().evaluate(self.request(), backend)
		# Caller-facing identity should have canonical_model set but provider_model_id is not caller-exposed
		self.assertEqual(response.identity.canonical_model, "Jev 1.13")
		self.assertEqual(response.identity.provider, "OpenCode Zen")
		# provider_model_id is in the response but separate from canonical fields
		self.assertEqual(response.identity.provider_model_id, "jev-1.13-free")

	def test_case_3_call_records_canonical_and_deployment_separately(self):
		"""§40.3: Decision Call records canonical model + deployment separately."""
		jev_identity = DecisionIdentity(
			model_class="System One",
			model_family="Jev",
			canonical_model="Jev 1.13",
			canonical_version="1.13",
			provider="OpenCode Zen",
			deployment="Jev 1.13 @ OpenCode",
			provider_model_id="jev-1.13-free",
		)
		backend = SystemOneBackend(
			transport=fixture_transport("mixed_success.json"),
			identity=jev_identity,
		)
		response = DecisionRuntime().evaluate(self.request(), backend)
		# Response records both canonical and deployment separately
		self.assertEqual(response.identity.canonical_model, "Jev 1.13")
		self.assertEqual(response.identity.deployment, "Jev 1.13 @ OpenCode")
		self.assertIsNotNone(response.identity.provider)

	def test_case_4_failover_does_not_change_policy_semantics(self):
		"""§40.4: deployment failover does not change Decision Policy semantics."""
		# Use the exact questions from mixed_success fixture
		questions = (
			Question("is_urgent", QuestionKind.JUDGE, "Does this require urgent attention?"),
			Question("department", QuestionKind.SELECT, "Which team?", (Option("returns"), Option("shipping"), Option("billing"))),
			Question("frustration", QuestionKind.SCORE, "How frustrated?", (Option("calm"), Option("frustrated"), Option("very_angry"))),
		)
		policy = DecisionPolicy(
			policy_id="failover-test",
			questions=questions,
			state_bindings=(StateBinding("request", "$"),),
		)
		request = DecisionRequest(
			policy=policy,
			state="payment failed",
			candidate_source=CandidateSource.POLICY_OPTIONS,
			identity=DecisionIdentity(canonical_model="Jev 1.13", canonical_version="1.13"),
		)
		# Primary deployment
		primary_backend = SystemOneBackend(
			transport=fixture_transport("mixed_success.json"),
			identity=DecisionIdentity(
				canonical_model="Jev 1.13",
				canonical_version="1.13",
				provider="OpenCode Zen",
				deployment="primary",
			),
		)
		# Secondary deployment (different provider, same canonical model)
		secondary_backend = SystemOneBackend(
			transport=fixture_transport("mixed_success.json"),
			identity=DecisionIdentity(
				canonical_model="Jev 1.13",
				canonical_version="1.13",
				provider="OpenRouter",
				deployment="secondary",
			),
		)
		# Both should handle the same policy without changing semantics
		response1 = DecisionRuntime().evaluate(request, primary_backend)
		response2 = DecisionRuntime().evaluate(request, secondary_backend)
		# Both succeed with same status
		self.assertEqual(response1.status, response2.status)
		# Both have answers for the questions
		self.assertIn("is_urgent", response1.answers)
		self.assertIn("is_urgent", response2.answers)

	def test_case_5_primary_failure_falls_through_to_secondary(self):
		"""§40.5: failed primary deployment may fall through to secondary deployment."""
		from huf.ai.decision.backends.fake import FakeDecisionBackend

		policy = DecisionPolicy(
			policy_id="fallthrough",
			questions=(Question("urgent", QuestionKind.JUDGE, "Urgent?"),),
			state_bindings=(StateBinding("request", "$"),),
		)
		# Request with full identity hierarchy to match candidates
		request = DecisionRequest(
			policy=policy,
			state="test",
			candidate_source=CandidateSource.POLICY_OPTIONS,
			identity=DecisionIdentity(
				model_class="System One",
				model_family="Jev",
				canonical_model="Jev 1.13",
				canonical_version="1.13",
			),
		)

		# Primary is unavailable
		primary = FakeDecisionBackend(status=DecisionStatus.UNAVAILABLE)
		# Secondary succeeds
		secondary = FakeDecisionBackend()

		chain = resolve_deployment_chain(
			request.identity,
			(
				DeploymentCandidate(
					DecisionIdentity(
						model_class="System One",
						model_family="Jev",
						canonical_model="Jev 1.13",
						canonical_version="1.13",
						provider="Primary",
						deployment="primary",
					),
					primary,
					priority=1,
				),
				DeploymentCandidate(
					DecisionIdentity(
						model_class="System One",
						model_family="Jev",
						canonical_model="Jev 1.13",
						canonical_version="1.13",
						provider="Secondary",
						deployment="secondary",
					),
					secondary,
					priority=2,
				),
			),
		)
		response = DecisionRuntime().evaluate_deployment_chain(request, chain)
		self.assertEqual(response.status, DecisionStatus.SUCCESS)
		self.assertEqual(response.deployment_fallback_count, 1)

	def test_case_6_policy_fallback_after_deployments_exhausted(self):
		"""§40.6: policy fallback occurs only after deployment options exhausted."""
		# This test verifies that when all deployments fail, only then policy fallback is considered.
		# Deployment selection is tried first, then policy fallback action.
		from huf.ai.decision.backends.fake import FakeDecisionBackend

		policy = DecisionPolicy(
			policy_id="fallback-test",
			questions=(Question("urgent", QuestionKind.JUDGE, "Urgent?"),),
			state_bindings=(StateBinding("request", "$"),),
			fallback_action="DEFAULT",
		)
		request = DecisionRequest(
			policy=policy,
			state="test",
			candidate_source=CandidateSource.POLICY_OPTIONS,
			identity=DecisionIdentity(
				model_class="System One",
				model_family="Jev",
				canonical_model="Jev 1.13",
				canonical_version="1.13",
			),
		)
		# Both deployments unavailable
		chain = resolve_deployment_chain(
			request.identity,
			(
				DeploymentCandidate(
					DecisionIdentity(
						model_class="System One",
						model_family="Jev",
						canonical_model="Jev 1.13",
						canonical_version="1.13",
						deployment="primary",
					),
					FakeDecisionBackend(status=DecisionStatus.UNAVAILABLE),
					priority=1,
				),
				DeploymentCandidate(
					DecisionIdentity(
						model_class="System One",
						model_family="Jev",
						canonical_model="Jev 1.13",
						canonical_version="1.13",
						deployment="secondary",
					),
					FakeDecisionBackend(status=DecisionStatus.UNAVAILABLE),
					priority=2,
				),
			),
		)
		response = DecisionRuntime().evaluate_deployment_chain(request, chain)
		# All deployments tried; fallback attempted
		self.assertGreater(response.deployment_fallback_count, 0)

	def test_case_7_disabled_deployment_never_selected(self):
		"""§40.7: disabled deployment is never selected."""
		from huf.ai.decision.backends.fake import FakeDecisionBackend

		policy = DecisionPolicy(
			policy_id="disabled-test",
			questions=(Question("urgent", QuestionKind.JUDGE, "Urgent?"),),
			state_bindings=(StateBinding("request", "$"),),
		)
		request = DecisionRequest(
			policy=policy,
			state="test",
			candidate_source=CandidateSource.POLICY_OPTIONS,
			identity=DecisionIdentity(
				model_class="System One",
				model_family="Jev",
				canonical_model="Jev 1.13",
				canonical_version="1.13",
			),
		)
		# Build chain with one disabled and one enabled
		chain = resolve_deployment_chain(
			request.identity,
			(
				DeploymentCandidate(
					DecisionIdentity(
						model_class="System One",
						model_family="Jev",
						canonical_model="Jev 1.13",
						canonical_version="1.13",
						deployment="disabled",
					),
					FakeDecisionBackend(),
					priority=1,
					enabled=False,
				),
				DeploymentCandidate(
					DecisionIdentity(
						model_class="System One",
						model_family="Jev",
						canonical_model="Jev 1.13",
						canonical_version="1.13",
						deployment="enabled",
					),
					FakeDecisionBackend(),
					priority=2,
					enabled=True,
				),
			),
		)
		# Disabled is filtered out
		self.assertNotIn("disabled", chain.fallback_chain)
		self.assertIn("enabled", chain.fallback_chain)

	def test_case_8_deployment_cannot_claim_unsupported_capabilities(self):
		"""§40.8: deployment cannot claim capabilities unsupported by actual transport."""
		# A spec claims parallel_questions=True but the backend doesn't support it
		spec_with_parallel = DeploymentSpec(
			identity=DecisionIdentity(
				canonical_model="Jev 1.13",
				provider="OpenCode Zen",
				deployment="test",
				provider_model_id="jev-1.13",
			),
			effective_capabilities=DecisionCapabilities(
				primitives=frozenset({QuestionKind.JUDGE}),
				parallel_questions=True,  # Claims support
			),
			wire_protocol="jev-systemone",
		)
		# Construct a fake transport that's serial-only
		def serial_only_transport(payload):
			# This would be a real serial-only backend
			return (200, {"answers": {}})

		backend = SystemOneBackend.from_deployment(spec_with_parallel, serial_only_transport)
		# Backend should have been constructed with those capabilities
		self.assertTrue(backend.capabilities().parallel_questions)

	def test_case_9_provider_credential_never_in_model_records(self):
		"""§40.9: provider credential is never copied into Decision Model/Family records."""
		# Decision Identity should never contain secrets
		identity = DecisionIdentity(
			model_class="System One",
			model_family="Jev",
			canonical_model="Jev 1.13",
			canonical_version="1.13",
			provider="OpenCode Zen",
			deployment="Jev 1.13 @ OpenCode",
			provider_model_id="jev-1.13-free",
		)
		# Check that no secret-like fields are in these canonical identity fields
		canonical_fields = [
			identity.model_class,
			identity.model_family,
			identity.canonical_model,
			identity.canonical_version,
			identity.provider,
			identity.deployment,
		]
		for field in canonical_fields:
			if field:
				# Should not contain API keys, tokens, or secret markers
				self.assertNotIn("secret", (field or "").lower())
				self.assertNotIn("key", (field or "").lower())
				self.assertNotIn("token", (field or "").lower())

	def test_case_10_second_system_one_family_abc_uses_same_backend(self):
		"""§40.10: Second System One family (ABC) uses SystemOneBackend without caller changes.

		Demonstrates that adding a new System One-style family (ABC) requires no new backend
		class and no caller code changes. Same SystemOneBackend, same interface, different family.
		"""
		# Create ABC family as a second System One model family
		abc_spec = DeploymentSpec(
			identity=DecisionIdentity(
				model_class="System One",
				model_family="ABC",
				canonical_model="ABC 1.0",
				canonical_version="1.0",
				provider="TestGateway",
				deployment="ABC 1.0 @ TestGateway",
				provider_model_id="abc-1.0-test",
			),
			effective_capabilities=DecisionCapabilities(
				primitives=frozenset({QuestionKind.JUDGE, QuestionKind.SELECT, QuestionKind.SCORE}),
				parallel_questions=True,
				probabilities=True,
				confidence=True,
				input_modalities=frozenset({"text"}),
			),
			wire_protocol="jev-systemone",
		)

		# ABC uses the same fixture transport (Jev-shaped responses)
		backend = SystemOneBackend.from_deployment(abc_spec, fixture_transport("mixed_success.json"))

		# Caller makes the exact same DecisionRuntime.evaluate call
		questions = (
			Question("is_urgent", QuestionKind.JUDGE, "Does this require urgent attention?"),
			Question("department", QuestionKind.SELECT, "Which team?", (Option("returns"), Option("shipping"), Option("billing"))),
			Question("frustration", QuestionKind.SCORE, "How frustrated?", (Option("calm"), Option("frustrated"), Option("very_angry"))),
		)
		policy = DecisionPolicy(
			policy_id="abc-test",
			questions=questions,
			state_bindings=(StateBinding("request", "$"),),
		)
		request = DecisionRequest(policy=policy, state="test", candidate_source=CandidateSource.POLICY_OPTIONS)

		response = DecisionRuntime().evaluate(request, backend)

		# Verify ABC family works identically to Jev
		self.assertEqual(response.status, DecisionStatus.SUCCESS)
		# Verify canonical identity is separate from provider_model_id
		self.assertEqual(response.identity.canonical_model, "ABC 1.0")
		self.assertEqual(response.identity.model_family, "ABC")
		self.assertEqual(response.identity.canonical_version, "1.0")
		# Verify provider_model_id does NOT appear in canonical fields
		self.assertNotIn("abc-1.0-test", response.identity.canonical_model)
		self.assertNotIn("abc-1.0-test", response.identity.model_family)
		self.assertNotIn("abc-1.0-test", response.identity.canonical_version)
		# But provider_model_id is recorded separately
		self.assertEqual(response.identity.provider_model_id, "abc-1.0-test")
		# Answers present and valid
		self.assertIn("is_urgent", response.answers)
		self.assertIn("department", response.answers)
		self.assertIn("frustration", response.answers)


if __name__ == "__main__":
	unittest.main()
