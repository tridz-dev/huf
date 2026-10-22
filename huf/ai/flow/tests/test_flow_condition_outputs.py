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
	def test_condition_on_bool_output(self):
		settings, _ = _settings({}, {"has_order": True})
		cfg = {"expression": 'context["outputs"]["has_order"] == True', "on_true": "yes", "on_false": "no"}
		self.assertEqual(flow_engine._exec_condition(_Run(), {}, cfg, settings)["next_node_id"], "yes")

	def test_condition_on_nested_output(self):
		settings, _ = _settings({}, {"st": {"found": False, "value": None}})
		cfg = {"expression": 'context["outputs"]["st"]["found"]', "on_true": "yes", "on_false": "no"}
		self.assertEqual(flow_engine._exec_condition(_Run(), {}, cfg, settings)["next_node_id"], "no")

	def test_flat_context_still_works_and_wins_on_collision(self):
		settings, _ = _settings({"score": 9, "outputs": {"x": 1}}, {"x": 2})
		cfg = {"expression": 'context["outputs"]["x"] == 1 and context["score"] > 5', "on_true": "y", "on_false": "n"}
		self.assertEqual(flow_engine._exec_condition(_Run(), {}, cfg, settings)["next_node_id"], "y")

	def test_expression_edge_sees_outputs(self):
		_, ctx = _settings({}, {"has_order": True})
		edges = [{"from": "a", "to": "b", "type": "expression", "condition": 'context["outputs"]["has_order"]'}]
		self.assertEqual(flow_engine._evaluate_edges(_Run(), "a", {"status": "success"}, edges, context=ctx), "b")

	def test_outputs_not_written_back_to_context(self):
		settings, ctx = _settings({}, {"n": 1})
		flow_engine._exec_condition(_Run(), {}, {"expression": 'context["outputs"]["n"] == 1', "on_true": "y"}, settings)
		self.assertNotIn("outputs", ctx.as_dict())


if __name__ == "__main__":
	unittest.main()
