import unittest
from types import SimpleNamespace

from huf.ai.decision.hub_routing import get_routeable_agents, resolve_hub_route
from huf.ai.decision.types import DecisionAnswer, DecisionIdentity, DecisionResponse, DecisionStatus, QuestionKind


class TestHubRouting(unittest.TestCase):
	def test_candidates_are_authorized_and_deduplicated(self):
		result = get_routeable_agents([SimpleNamespace(name="billing", agent_name="Billing"), SimpleNamespace(name="billing")])
		self.assertEqual([(item.agent_name, item.display_name) for item in result], [("billing", "Billing")])

	def test_invalid_or_failed_route_clarifies(self):
		response = DecisionResponse(status=DecisionStatus.SUCCESS, identity=DecisionIdentity(), answers={"agent": DecisionAnswer("agent", QuestionKind.SELECT, "unknown")})
		result = resolve_hub_route(response, get_routeable_agents([SimpleNamespace(name="billing")]))
		self.assertEqual(result, {"route": "clarify", "reason": "invalid_or_missing_agent"})

	def test_route_request_uses_only_authorized_agents(self):
		from huf.ai.decision.backends.fake import FakeDecisionBackend
		from huf.ai.decision.hub_service import route_request
		from huf.ai.decision.runtime import DecisionRuntime
		from huf.ai.decision.types import DecisionPolicy, DecisionRequest, Option, Question, QuestionKind, StateBinding
		policy = DecisionPolicy(policy_id="hub", questions=(Question("agent", QuestionKind.SELECT, "Choose an Agent", (Option("billing"), Option("support"))),), state_bindings=(StateBinding("request", "$"),))
		route, response = route_request(DecisionRuntime(), DecisionRequest(policy=policy, state="billing issue"), FakeDecisionBackend(), [SimpleNamespace(name="billing")])
		self.assertEqual(response.status.value, "success")
		self.assertEqual(route["route"], "billing")
