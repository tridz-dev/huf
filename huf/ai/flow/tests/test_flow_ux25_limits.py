"""Security round 2 (DECISIONS 13): an expression that would exhaust memory fails the step in plain words."""

import unittest

from huf.ai.flow import engine as flow_engine
from huf.ai.flow.eval import safe_eval_expression
from huf.ai.graph.executor import GraphContext

import frappe


class _Run:
	flow_id = "f"
	name = "FR"
	context_json = "{}"


def _settings(data):
	return flow_engine.FlowRunContext(context=GraphContext(data))


class TestExpressionLimitsFailTheStep(unittest.TestCase):
	TECHNICAL = ("MemoryError", "OverflowError", "Traceback", "ast.", "BinOp")

	def _cond(self, expression, data=None):
		cfg = {"expression": expression, "on_true": "yes", "on_false": "no"}
		return flow_engine._exec_condition(_Run(), {}, cfg, _settings(data or {}))

	def test_condition_repeating_text_fails(self):
		out = self._cond('"x" * 1000000000 == "y"')
		self.assertEqual(out["status"], "failed")
		self.assertIn("too large", out["error"])
		for word in self.TECHNICAL:
			self.assertNotIn(word, out["error"])

	def test_condition_with_huge_run_data_fails(self):
		out = self._cond("input['n'] * input['n'] > 5", {"n": 10**30})
		self.assertEqual(out["status"], "failed")
		self.assertIn("too large", out["error"])

	def test_condition_with_list_repetition_from_run_data_fails(self):
		out = self._cond("input['rows'] * input['n'] == 1", {"rows": [1, 2, 3], "n": 10**9})
		self.assertEqual(out["status"], "failed")

	def test_normal_condition_still_branches(self):
		self.assertEqual(self._cond("input['a'] * 2 > 5", {"a": 4})["next_node_id"], "yes")
		self.assertEqual(self._cond("input['a'] * 2 > 5", {"a": 1})["next_node_id"], "no")

	def test_validate_step_fails_plainly(self):
		node = {"id": "v1", "type": "validate", "config": {}}
		cfg = {"assertions": [{"code": "c", "message": "m", "expression": '"x" * 999999999 == "y"'}]}
		out = flow_engine._exec_validate(_Run(), node, cfg, _settings({}))
		self.assertEqual(out["status"], "failed")
		self.assertIn("too large", out["error"])

	def test_legacy_evaluator_has_the_same_limits(self):
		with self.assertRaises(frappe.ValidationError):
			safe_eval_expression('context["s"] * 1000000000 == "a"', {"s": "ab"})
		with self.assertRaises(frappe.ValidationError):
			safe_eval_expression('context["n"] * context["n"] > 1', {"n": 10**30})
		self.assertTrue(safe_eval_expression('context["n"] * 2 == 8', {"n": 4}))
