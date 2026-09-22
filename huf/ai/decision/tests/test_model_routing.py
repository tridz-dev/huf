import unittest
from types import SimpleNamespace

from huf.ai.decision.model_routing import get_routeable_models


class TestModelRouting(unittest.TestCase):
	def test_automatic_candidates_come_from_allowed_model_table(self):
		agent = SimpleNamespace(model="default", allowed_models=[SimpleNamespace(model="fast", provider="p1"), SimpleNamespace(model="fast", provider="p2")])
		models = get_routeable_models(agent, user="u", run_context={})
		self.assertEqual([(m.model, m.provider) for m in models], [("fast", "p1")])

	def test_availability_resolver_is_authoritative(self):
		agent = SimpleNamespace(model="default", allowed_models=[SimpleNamespace(model="raw")])
		models = get_routeable_models(agent, availability=lambda *_: [SimpleNamespace(model="healthy")])
		self.assertEqual([m.model for m in models], ["healthy"])

	def test_selection_stays_within_routeable_models(self):
		from huf.ai.decision.backends.fake import FakeDecisionBackend
		from huf.ai.decision.model_routing import RouteableModel, select_routeable_model
		from huf.ai.decision.runtime import DecisionRuntime
		from huf.ai.decision.types import DecisionPolicy, DecisionRequest, Option, Question, QuestionKind, StateBinding
		policy = DecisionPolicy(policy_id="route", questions=(Question("model", QuestionKind.SELECT, "Pick model", (Option("fast"), Option("safe"))),), state_bindings=(StateBinding("request", "$"),))
		request = DecisionRequest(policy=policy, state="route")
		selected, response = select_routeable_model(DecisionRuntime(), request, FakeDecisionBackend(), (RouteableModel("fast"), RouteableModel("safe")))
		self.assertEqual(response.status.value, "success")
		self.assertIn(selected.model, {"fast", "safe"})
