"""Deterministic deployment selection and failover-chain tests."""

from __future__ import annotations

import unittest

from huf.ai.decision.deployment import DeploymentCandidate, resolve_deployment_chain
from huf.ai.decision.types import DecisionIdentity


class TestDeploymentResolver(unittest.TestCase):
	def test_same_canonical_model_can_have_ordered_provider_deployments(self):
		requested = DecisionIdentity(canonical_model="Jev 1.13", canonical_version="1.13")
		candidates = (
			DeploymentCandidate(DecisionIdentity(canonical_model="Jev 1.13", canonical_version="1.13", provider="OpenRouter", deployment="backup"), object(), priority=20),
			DeploymentCandidate(DecisionIdentity(canonical_model="Jev 1.13", canonical_version="1.13", provider="OpenCode", deployment="primary"), object(), priority=10),
		)
		chain = resolve_deployment_chain(requested, candidates)
		self.assertEqual(chain.fallback_chain, ("primary", "backup"))
		self.assertEqual(chain.fallback_count, 1)
		self.assertEqual(chain.requested_identity.canonical_model, "Jev 1.13")

	def test_disabled_unhealthy_and_wrong_canonical_models_are_excluded(self):
		requested = DecisionIdentity(canonical_model="Jev 1.13", canonical_version="1.13")
		candidates = (
			DeploymentCandidate(DecisionIdentity(canonical_model="Jev 1.12", canonical_version="1.12", deployment="old"), object()),
			DeploymentCandidate(DecisionIdentity(canonical_model="Jev 1.13", canonical_version="1.13", deployment="bad"), object(), health_status="unhealthy"),
			DeploymentCandidate(DecisionIdentity(canonical_model="Jev 1.13", canonical_version="1.13", deployment="off"), object(), enabled=False),
		)
		self.assertEqual(resolve_deployment_chain(requested, candidates).candidates, ())


if __name__ == "__main__":
	unittest.main()

class TestDeploymentExecution(unittest.TestCase):
	def test_runtime_records_failover_and_keeps_canonical_identity(self):
		from huf.ai.decision.backends.fake import FakeDecisionBackend
		from huf.ai.decision.runtime import DecisionRuntime
		from huf.ai.decision.types import CandidateSource, DecisionPolicy, DecisionRequest, DecisionStatus, Question, QuestionKind, StateBinding

		policy = DecisionPolicy(policy_id="support", questions=(Question("urgent", QuestionKind.JUDGE, "Urgent?"),), state_bindings=(StateBinding("request", "$"),))
		request = DecisionRequest(policy=policy, state="payment failed", candidate_source=CandidateSource.POLICY_OPTIONS, identity=DecisionIdentity(canonical_model="Jev 1.13", canonical_version="1.13"))
		primary = FakeDecisionBackend(status=DecisionStatus.UNAVAILABLE)
		secondary = FakeDecisionBackend()
		chain = resolve_deployment_chain(request.identity, (
			DeploymentCandidate(DecisionIdentity(canonical_model="Jev 1.13", canonical_version="1.13", provider="OpenCode", deployment="primary"), primary, priority=1),
			DeploymentCandidate(DecisionIdentity(canonical_model="Jev 1.13", canonical_version="1.13", provider="OpenRouter", deployment="backup"), secondary, priority=2),
		))
		response = DecisionRuntime().evaluate_deployment_chain(request, chain)
		self.assertEqual(response.status, DecisionStatus.SUCCESS)
		self.assertEqual(response.deployment_fallback_count, 1)
		self.assertEqual(response.deployment_fallback_chain, ("primary", "backup"))
		self.assertEqual(response.requested_model, "Jev 1.13")

	def test_deadline_stops_trying_candidates_and_returns_timeout(self):
		import time
		from huf.ai.decision.backends.fake import FakeDecisionBackend
		from huf.ai.decision.runtime import DecisionRuntime
		from huf.ai.decision.types import CandidateSource, DecisionPolicy, DecisionRequest, DecisionStatus, Question, QuestionKind, StateBinding

		policy = DecisionPolicy(policy_id="support", questions=(Question("urgent", QuestionKind.JUDGE, "Urgent?"),), state_bindings=(StateBinding("request", "$"),))
		request = DecisionRequest(policy=policy, state="payment failed", candidate_source=CandidateSource.POLICY_OPTIONS, identity=DecisionIdentity(canonical_model="Jev 1.13", canonical_version="1.13"))
		# Create backends that would succeed but we'll hit deadline before completing them
		backend1 = FakeDecisionBackend()
		backend2 = FakeDecisionBackend()
		backend3 = FakeDecisionBackend()
		chain = resolve_deployment_chain(request.identity, (
			DeploymentCandidate(DecisionIdentity(canonical_model="Jev 1.13", canonical_version="1.13", provider="OpenCode", deployment="primary"), backend1, priority=1),
			DeploymentCandidate(DecisionIdentity(canonical_model="Jev 1.13", canonical_version="1.13", provider="OpenRouter", deployment="secondary"), backend2, priority=2),
			DeploymentCandidate(DecisionIdentity(canonical_model="Jev 1.13", canonical_version="1.13", provider="Custom", deployment="tertiary"), backend3, priority=3),
		))
		# Set deadline to past (immediate timeout)
		deadline = time.monotonic() - 1
		response = DecisionRuntime().evaluate_deployment_chain(request, chain, deadline=deadline)
		self.assertEqual(response.status, DecisionStatus.TIMEOUT)
		self.assertEqual(response.requested_model, "Jev 1.13")

	def test_deadline_none_behaves_like_no_deadline(self):
		from huf.ai.decision.backends.fake import FakeDecisionBackend
		from huf.ai.decision.runtime import DecisionRuntime
		from huf.ai.decision.types import CandidateSource, DecisionPolicy, DecisionRequest, DecisionStatus, Question, QuestionKind, StateBinding

		policy = DecisionPolicy(policy_id="support", questions=(Question("urgent", QuestionKind.JUDGE, "Urgent?"),), state_bindings=(StateBinding("request", "$"),))
		request = DecisionRequest(policy=policy, state="payment failed", candidate_source=CandidateSource.POLICY_OPTIONS, identity=DecisionIdentity(canonical_model="Jev 1.13", canonical_version="1.13"))
		primary = FakeDecisionBackend(status=DecisionStatus.UNAVAILABLE)
		secondary = FakeDecisionBackend()
		chain = resolve_deployment_chain(request.identity, (
			DeploymentCandidate(DecisionIdentity(canonical_model="Jev 1.13", canonical_version="1.13", provider="OpenCode", deployment="primary"), primary, priority=1),
			DeploymentCandidate(DecisionIdentity(canonical_model="Jev 1.13", canonical_version="1.13", provider="OpenRouter", deployment="backup"), secondary, priority=2),
		))
		# Call with deadline=None (should behave same as no deadline)
		response = DecisionRuntime().evaluate_deployment_chain(request, chain, deadline=None)
		self.assertEqual(response.status, DecisionStatus.SUCCESS)
		self.assertEqual(response.deployment_fallback_count, 1)
