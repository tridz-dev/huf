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
