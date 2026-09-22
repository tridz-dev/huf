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
