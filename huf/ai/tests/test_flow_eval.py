# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import unittest

import frappe

from huf.ai.flow_eval import MAX_EXPRESSION_LENGTH, safe_eval_expression


class TestSafeEvalExpression(unittest.TestCase):
	"""safe_eval_expression is a security-critical sandboxed evaluator for
	Flow Definition expression edges (see flow_definition.py's
	ALLOWED_EDGE_TYPES = {..., "expression", ...}) — it must permit the
	documented safe subset and reject everything else, especially anything
	that could reach Python internals."""

	# ------------------------------------------------------------------
	# Allowed: literals, subscript, comparisons, boolean/arithmetic ops
	# ------------------------------------------------------------------

	def test_dict_subscript_comparison(self):
		self.assertTrue(safe_eval_expression('context["status"] == "done"', {"status": "done"}))
		self.assertFalse(safe_eval_expression('context["status"] == "done"', {"status": "pending"}))

	def test_nested_subscript(self):
		context = {"user": {"role": "admin"}}
		self.assertTrue(safe_eval_expression('context["user"]["role"] == "admin"', context))

	def test_missing_key_returns_none_not_error(self):
		# _eval_node's Subscript branch catches KeyError/IndexError -> None,
		# rather than raising, so comparisons against a missing key are False
		# rather than a hard failure.
		self.assertFalse(safe_eval_expression('context["missing"] == "x"', {}))

	def test_list_subscript_and_in_operator(self):
		context = {"tags": ["a", "b", "c"]}
		self.assertTrue(safe_eval_expression('"b" in context["tags"]', context))
		self.assertFalse(safe_eval_expression('"z" in context["tags"]', context))

	def test_boolean_and_or(self):
		context = {"a": True, "b": False}
		self.assertFalse(safe_eval_expression('context["a"] and context["b"]', context))
		self.assertTrue(safe_eval_expression('context["a"] or context["b"]', context))

	def test_not_operator(self):
		self.assertTrue(safe_eval_expression('not context["flag"]', {"flag": False}))

	def test_arithmetic_and_comparison(self):
		context = {"count": 5}
		self.assertTrue(safe_eval_expression('context["count"] + 1 == 6', context))
		self.assertTrue(safe_eval_expression('context["count"] % 2 == 1', context))

	def test_chained_comparison(self):
		context = {"n": 5}
		self.assertTrue(safe_eval_expression('0 < context["n"] < 10', context))

	def test_if_expression(self):
		context = {"n": 5}
		# `if` expression result truthiness still gets coerced to bool by
		# safe_eval_expression's return.
		self.assertTrue(safe_eval_expression('True if context["n"] > 0 else False', context))

	def test_list_and_dict_literals_as_operands(self):
		self.assertTrue(safe_eval_expression('context["x"] in [1, 2, 3]', {"x": 2}))

	def test_result_coerced_to_bool(self):
		# A bare truthy/falsy value (not a comparison) is coerced via bool().
		self.assertTrue(safe_eval_expression('context["count"]', {"count": 5}))
		self.assertFalse(safe_eval_expression('context["count"]', {"count": 0}))

	# ------------------------------------------------------------------
	# Rejected: the security boundary
	# ------------------------------------------------------------------

	def test_empty_expression_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			safe_eval_expression("", {})

	def test_non_string_expression_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			safe_eval_expression(None, {})

	def test_expression_too_long_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			safe_eval_expression("1 == " + "1" * MAX_EXPRESSION_LENGTH, {})

	def test_syntax_error_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			safe_eval_expression("context[", {})

	def test_unknown_variable_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			safe_eval_expression('some_other_var == 1', {})

	def test_function_call_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			safe_eval_expression('len(context["tags"])', {"tags": [1, 2]})

	def test_attribute_access_rejected(self):
		# The whole point of forcing subscript notation: no dot-access, which
		# would otherwise open a path to dunder attributes.
		with self.assertRaises(frappe.ValidationError):
			safe_eval_expression('context.get("x")', {"x": 1})

	def test_import_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			safe_eval_expression('__import__("os")', {})

	def test_lambda_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			safe_eval_expression('(lambda: 1)()', {})

	def test_assignment_rejected(self):
		# Assignment isn't valid in `eval` mode at all, so this is a
		# SyntaxError -> ValidationError, same outward behavior as the other
		# rejections.
		with self.assertRaises(frappe.ValidationError):
			safe_eval_expression('context["x"] = 1', {})

	def test_subscript_on_non_dict_non_list_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			safe_eval_expression('context["n"]["x"]', {"n": 5})
