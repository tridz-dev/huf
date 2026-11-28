"""``router.decision`` (switch): the first matching option routes, otherwise the default does."""

import unittest

from huf.ai.flow import engine as flow_engine
from huf.ai.graph.executor import GraphContext


class _Run:
	flow_id = "f"
	name = "FR"
	context_json = "{}"


def _settings(data):
	return flow_engine.FlowRunContext(context=GraphContext(data))


def _option(label, node_id, expression):
	return {"label": label, "node_id": node_id, "expression": expression}


class TestSwitch(unittest.TestCase):
	def _route(self, data, config):
		return flow_engine._exec_router_decision(_Run(), {"id": "sw"}, config, _settings(data))

	def test_first_matching_case_wins(self):
		cfg = {
			"options": [_option("big", "big_node", "input['amount'] > 100"), _option("huge", "huge_node", "input['amount'] > 10")],
			"default": "small_node",
		}
		out = self._route({"amount": 500}, cfg)
		self.assertEqual(out["status"], "success")
		self.assertEqual(out["next_node_id"], "big_node")

	def test_default_when_none_match(self):
		cfg = {"options": [_option("big", "big_node", "input['amount'] > 100")], "default": "small_node"}
		out = self._route({"amount": 5}, cfg)
		self.assertEqual(out["status"], "success")
		self.assertEqual(out["next_node_id"], "small_node")

	def test_bad_expression_fails_so_on_error_applies(self):
		cfg = {"options": [_option("bad", "bad_node", "input['amount' >")], "default": "small_node"}
		out = self._route({"amount": 5}, cfg)
		self.assertEqual(out["status"], "failed")
		self.assertNotIn("next_node_id", out)

	def test_missing_default_fails(self):
		cfg = {"options": [_option("big", "big_node", "input['amount'] > 100")]}
		out = self._route({"amount": 500}, cfg)
		self.assertEqual(out["status"], "failed")

	def test_case_output_exposes_case_label(self):
		cfg = {"options": [_option("big", "big_node", "input['amount'] > 100")], "default": "small_node"}
		out = self._route({"amount": 500}, cfg)
		self.assertEqual(out["output"]["case"], "big")
		self.assertEqual(out["output"]["node_id"], "big_node")

	def test_empty_options_goes_default(self):
		out = self._route({}, {"options": [], "default": "small_node"})
		self.assertEqual(out["status"], "success")
		self.assertEqual(out["next_node_id"], "small_node")

	def test_option_without_expression_never_matches(self):
		cfg = {"options": [{"label": "none", "node_id": "none_node"}], "default": "small_node"}
		out = self._route({}, cfg)
		self.assertEqual(out["next_node_id"], "small_node")
