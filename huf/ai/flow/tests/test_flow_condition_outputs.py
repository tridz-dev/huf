"""Condition nodes and expression edges can read earlier node outputs via ``context["outputs"]``."""

import unittest

from huf.ai.flow import engine as flow_engine
from huf.ai.graph.executor import GraphContext


class _Run:
	flow_id = "f"
	name = "FR"
	context_json = "{}"


def _settings(data, outputs):
	ctx = GraphContext(data)
	for node_id, out in outputs.items():
		ctx.record_output(node_id, out)
	return flow_engine.FlowRunContext(context=ctx), ctx


class TestConditionSeesOutputs(unittest.TestCase):
	"""A condition reads earlier nodes by node id and the run input via ``input[...]``."""

	def test_condition_on_bool_output(self):
		settings, _ = _settings({}, {"has_order": True})
		cfg = {"expression": "has_order == True", "on_true": "yes", "on_false": "no"}
		self.assertEqual(flow_engine._exec_condition(_Run(), {}, cfg, settings)["next_node_id"], "yes")

	def test_condition_on_nested_output(self):
		settings, _ = _settings({}, {"st": {"found": False, "value": None}})
		cfg = {"expression": "st['found']", "on_true": "yes", "on_false": "no"}
		self.assertEqual(flow_engine._exec_condition(_Run(), {}, cfg, settings)["next_node_id"], "no")

	def test_input_and_outputs_combine(self):
		settings, _ = _settings({"score": 9}, {"x": {"n": 1}})
		cfg = {"expression": "x['n'] == 1 and input['score'] > 5", "on_true": "y", "on_false": "n"}
		self.assertEqual(flow_engine._exec_condition(_Run(), {}, cfg, settings)["next_node_id"], "y")

	def test_outputs_not_written_back_to_context(self):
		settings, ctx = _settings({}, {"n": 1})
		cfg = {"expression": "n == 1", "on_true": "y", "on_false": "z"}
		flow_engine._exec_condition(_Run(), {}, cfg, settings)
		self.assertNotIn("n", ctx.as_dict())


if __name__ == "__main__":
	unittest.main()
