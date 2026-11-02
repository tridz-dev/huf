"""Adversarial + behavioural test suite for ``huf.ai.graph.expressions`` (T-13).

**Frappe-free by design**, mirroring ``test_execution_sandbox_isolation.py``'s convention: the
module under test has zero frappe dependency, so this suite needs no live Frappe bench/site and runs
anywhere:

	python -m unittest huf.ai.graph.tests.test_graph_expressions -v
	# or: pytest huf/ai/graph/tests/test_graph_expressions.py -v

NOTE for this sandbox specifically: ``huf/__init__.py`` imports frappe unconditionally, so even
``import huf.ai.graph.expressions`` fails at package-init time here (no frappe installed). This
suite is written to run standalone against the module either via normal import (on a real bench,
where frappe is present) or, when that fails, by loading ``expressions.py`` directly off disk with
``importlib`` -- see the bottom of this file for the direct-load runner used in this environment.
"""

import math
import unittest

try:
	from huf.ai.graph import expressions as expr
except Exception:  # pragma: no cover - exercised in frappe-less sandboxes
	import importlib.util
	import os
	import sys

	_PATH = os.path.join(os.path.dirname(__file__), "..", "expressions.py")
	_spec = importlib.util.spec_from_file_location("huf_graph_expressions_standalone", _PATH)
	expr = importlib.util.module_from_spec(_spec)
	sys.modules[_spec.name] = expr
	_spec.loader.exec_module(expr)


def ev(source, bindings=None):
	return expr.evaluate_value(expr.parse_expression(source), bindings or {})


def evb(source, bindings=None):
	return expr.evaluate_bool(expr.parse_expression(source), bindings or {})


class TestLiteralsAndArithmetic(unittest.TestCase):
	def test_int_literal(self):
		self.assertEqual(ev("42"), 42)

	def test_string_literal(self):
		self.assertEqual(ev('"hello"'), "hello")

	def test_bool_and_none_literals(self):
		self.assertIs(ev("True"), True)
		self.assertIs(ev("False"), False)
		self.assertIsNone(ev("None"))

	def test_list_and_dict_literals(self):
		self.assertEqual(ev("[1, 2, 3]"), [1, 2, 3])
		self.assertEqual(ev('{"a": 1, "b": 2}'), {"a": 1, "b": 2})

	def test_tuple_literal(self):
		self.assertEqual(ev("(1, 2)"), (1, 2))

	def test_arithmetic(self):
		self.assertEqual(ev("2 + 3"), 5)
		self.assertEqual(ev("10 - 4"), 6)
		self.assertEqual(ev("3 * 4"), 12)
		self.assertEqual(ev("7 % 3"), 1)

	def test_division(self):
		self.assertEqual(ev("10 / 4"), 2.5)

	def test_division_by_zero_resolves_null_never_raises(self):
		self.assertIsNone(ev("1 / 0"))

	def test_unary_signed_literals(self):
		self.assertEqual(ev("-5"), -5)
		self.assertEqual(ev("+5"), 5)
		self.assertEqual(ev("-(2 + 3)"), -5)

	def test_no_pow_no_bitwise(self):
		with self.assertRaises(expr.ExpressionError):
			expr.parse_expression("2 ** 3")
		with self.assertRaises(expr.ExpressionError):
			expr.parse_expression("2 | 3")
		with self.assertRaises(expr.ExpressionError):
			expr.parse_expression("2 & 3")


class TestBooleanAndComparison(unittest.TestCase):
	def test_and_or_not(self):
		self.assertTrue(evb("True and True"))
		self.assertFalse(evb("True and False"))
		self.assertTrue(evb("False or True"))
		self.assertTrue(evb("not False"))

	def test_comparisons(self):
		self.assertTrue(evb("1 < 2"))
		self.assertTrue(evb("2 <= 2"))
		self.assertTrue(evb("3 > 2"))
		self.assertTrue(evb("3 >= 3"))
		self.assertTrue(evb("1 == 1"))
		self.assertTrue(evb("1 != 2"))

	def test_chained_comparison(self):
		self.assertTrue(evb("1 < 2 < 3"))
		self.assertFalse(evb("1 < 2 < 1"))

	def test_in_not_in(self):
		self.assertTrue(evb('"a" in ["a", "b"]'))
		self.assertTrue(evb('"c" not in ["a", "b"]'))

	def test_if_expression(self):
		self.assertEqual(ev("1 if True else 2"), 1)
		self.assertEqual(ev("1 if False else 2"), 2)

	def test_type_mismatched_comparison_resolves_null_not_raise(self):
		self.assertIsNone(ev('"a" < 3'))

	def test_type_mismatched_comparison_as_bool_is_falsy(self):
		self.assertFalse(evb('"a" < 3'))


class TestNameAndSubscriptResolution(unittest.TestCase):
	def test_bound_name(self):
		self.assertEqual(ev("input", {"input": {"x": 1}}), {"x": 1})

	def test_unbound_name_resolves_null(self):
		self.assertIsNone(ev("nonexistent", {"input": {}}))

	def test_dict_subscript(self):
		self.assertEqual(ev('input["x"]', {"input": {"x": 1}}), 1)

	def test_nested_dict_subscript(self):
		self.assertEqual(ev('input["a"]["b"]', {"input": {"a": {"b": 2}}}), 2)

	def test_missing_key_resolves_null_never_raises(self):
		self.assertIsNone(ev('input["missing"]', {"input": {}}))

	def test_list_indexing(self):
		self.assertEqual(ev('row["items"][0]', {"row": {"items": [10, 20]}}), 10)

	def test_negative_list_index(self):
		self.assertEqual(ev('row["items"][-1]', {"row": {"items": [10, 20]}}), 20)

	def test_out_of_range_index_resolves_null_never_raises(self):
		self.assertIsNone(ev('row["items"][5]', {"row": {"items": [10, 20]}}))

	def test_subscript_on_non_subscriptable_resolves_null(self):
		self.assertIsNone(ev('input["x"]', {"input": 5}))

	def test_subscript_root_missing_entirely(self):
		self.assertIsNone(ev('foreach["item"]', {}))


class TestTotalityOnOrdinaryData(unittest.TestCase):
	def test_evaluator_never_raises_for_a_battery_of_ordinary_inputs(self):
		cases = [
			("input", {}),
			('input["a"]["b"]["c"]', {"input": {}}),
			('row["items"][100]', {"row": {"items": []}}),
			("1 / 0", {}),
			('"x" + 1', {}),
			("None + 1", {}),
			('input["a"] == row["b"]', {"input": {}, "row": {}}),
		]
		for source, bindings in cases:
			with self.subTest(source=source):
				try:
					ev(source, bindings)
				except Exception as exc:  # pragma: no cover - failure path
					self.fail(f"evaluate_value raised {exc!r} for ordinary data: {source!r}")


class TestAdversarialRejectionAtParseTime(unittest.TestCase):
	"""Everything outside the allow-list must be rejected by parse_expression, not silently run."""

	def assert_rejected(self, source):
		with self.assertRaises(expr.ExpressionError):
			expr.parse_expression(source)

	def test_function_call_rejected(self):
		self.assert_rejected('print("x")')

	def test_builtin_call_rejected(self):
		self.assert_rejected("len([1, 2, 3])")

	def test_attribute_access_rejected(self):
		self.assert_rejected("input.x")

	def test_dunder_attribute_access_rejected(self):
		self.assert_rejected('"".__class__')

	def test_dunder_via_call_rejected(self):
		self.assert_rejected('().__class__.__bases__[0]')

	def test_import_statement_rejected(self):
		self.assert_rejected("__import__('os')")

	def test_import_syntax_rejected(self):
		self.assert_rejected("import os")

	def test_lambda_rejected(self):
		self.assert_rejected("(lambda: 1)()")

	def test_list_comprehension_rejected(self):
		self.assert_rejected("[x for x in [1, 2, 3]]")

	def test_dict_comprehension_rejected(self):
		self.assert_rejected("{x: x for x in [1, 2, 3]}")

	def test_generator_expression_rejected(self):
		self.assert_rejected("(x for x in [1, 2, 3])")

	def test_walrus_operator_rejected(self):
		self.assert_rejected("(x := 5)")

	def test_fstring_rejected(self):
		self.assert_rejected('f"{1}"')

	def test_assignment_rejected(self):
		self.assert_rejected("x = 1")

	def test_starred_expression_rejected(self):
		self.assert_rejected("[*[1, 2]]")

	def test_yield_rejected(self):
		self.assert_rejected("(yield 1)")

	def test_pow_rejected(self):
		self.assert_rejected("2 ** 10")

	def test_bitwise_or_rejected(self):
		self.assert_rejected("1 | 2")

	def test_bitshift_rejected(self):
		self.assert_rejected("1 << 2")

	def test_bytes_literal_rejected(self):
		self.assert_rejected("b'x'")

	def test_ellipsis_rejected(self):
		self.assert_rejected("...")

	def test_empty_string_rejected(self):
		self.assert_rejected("")

	def test_non_string_input_rejected(self):
		with self.assertRaises(expr.ExpressionError):
			expr.parse_expression(None)  # type: ignore[arg-type]

	def test_over_length_expression_rejected(self):
		long_expr = "1 + " * 200 + "1"
		self.assertGreater(len(long_expr), expr.MAX_EXPRESSION_LENGTH)
		self.assert_rejected(long_expr)

	def test_deeply_nested_expression_rejected(self):
		nested = "1"
		for _ in range(expr.MAX_EXPRESSION_DEPTH + 20):
			nested = f"[{nested}]"
		self.assert_rejected(nested)

	def test_syntax_error_rejected(self):
		self.assert_rejected("input[")

	def test_class_definition_rejected(self):
		self.assert_rejected("class X: pass")


class TestEvaluationNeverRaisesAfterParse(unittest.TestCase):
	"""Once parse_expression succeeds, evaluate_value/evaluate_bool must never raise, regardless of
	what bindings are supplied at runtime -- including deliberately hostile bindings.
	"""

	def test_hostile_binding_type_confusion(self):
		parsed = expr.parse_expression('input["a"] + input["b"]')
		self.assertIsNone(expr.evaluate_value(parsed, {"input": {"a": "x", "b": 1}}))

	def test_hostile_binding_not_a_dict(self):
		parsed = expr.parse_expression('input["a"]')
		self.assertIsNone(expr.evaluate_value(parsed, "not a dict"))  # type: ignore[arg-type]

	def test_hostile_binding_none(self):
		parsed = expr.parse_expression("input")
		self.assertIsNone(expr.evaluate_value(parsed, None))  # type: ignore[arg-type]

	def test_bool_used_as_subscript_key_is_not_treated_as_int_index(self):
		parsed = expr.parse_expression("row[True]")
		self.assertIsNone(expr.evaluate_value(parsed, {"row": [1, 2, 3]}))


class TestEvaluatePredicateForT12Integration(unittest.TestCase):
	"""The entry point T-12's transforms.py `filter` op is expected to switch to."""

	def test_true_predicate(self):
		self.assertTrue(expr.evaluate_predicate('row["status"] == "open"', {"status": "open"}))

	def test_false_predicate(self):
		self.assertFalse(expr.evaluate_predicate('row["status"] == "open"', {"status": "closed"}))

	def test_missing_field_is_falsy_not_raising(self):
		self.assertFalse(expr.evaluate_predicate('row["missing"] == "open"', {}))

	def test_malformed_expression_resolves_false_not_raising(self):
		self.assertFalse(expr.evaluate_predicate("row[", {"status": "open"}))

	def test_disallowed_construct_resolves_false_not_raising(self):
		self.assertFalse(expr.evaluate_predicate('row.__class__', {"status": "open"}))

	def test_non_dict_row_resolves_false_not_raising(self):
		self.assertFalse(expr.evaluate_predicate('row["x"] == 1', "not a dict"))  # type: ignore[arg-type]

	def test_type_mismatch_resolves_false_not_raising(self):
		self.assertFalse(expr.evaluate_predicate('row["amount"] > "ten"', {"amount": 5}))

	def test_numeric_row_predicate(self):
		self.assertTrue(expr.evaluate_predicate('row["amount"] > 10', {"amount": 15}))

	def test_nested_row_field(self):
		self.assertTrue(
			expr.evaluate_predicate('row["customer"]["tier"] == "gold"', {"customer": {"tier": "gold"}})
		)


class TestResolvePath(unittest.TestCase):
	def test_dotted_path(self):
		self.assertEqual(expr.resolve_path({"input": {"a": {"b": 1}}}, "input.a.b"), 1)

	def test_list_index_segment(self):
		self.assertEqual(expr.resolve_path({"row": {"items": [1, 2, 3]}}, "row.items[1]"), 2)

	def test_missing_root_resolves_null(self):
		self.assertIsNone(expr.resolve_path({}, "input.a"))

	def test_missing_segment_resolves_null(self):
		self.assertIsNone(expr.resolve_path({"input": {}}, "input.missing.deeper"))

	def test_out_of_range_index_resolves_null(self):
		self.assertIsNone(expr.resolve_path({"row": {"items": [1]}}, "row.items[9]"))

	def test_bare_root(self):
		self.assertEqual(expr.resolve_path({"trigger": {"x": 1}}, "trigger"), {"x": 1})


class TestResourceLimits(unittest.TestCase):
	"""Security round 2 (DECISIONS 13): no expression or run data may allocate unbounded memory."""

	REFUSED = [
		'"x" * 1000000000',
		'1000000000 * "x"',
		"[0] * 1000000000",
		"(1, 2) * 99999999999",
		'True * "abc"',
		'"%999999999d" % 1',
		'"ab" * 3',
		"input['n'] * input['text']",
		"input['text'] * input['n']",
		"input['items'] * input['n']",
		"1000000000000000000 + 1",
		"999999999999 * 999999999999",
		"-1000000000000000000 - 1",
		"input['big'] + 1",
		"input['big'] * 0",
		"-input['big']",
		"input['big'] - input['big']",
	]
	DATA = {"input": {"n": 10**9, "text": "ab", "items": [1, 2], "big": 10**40}}

	def test_refused_resolve_none(self):
		for src in self.REFUSED:
			with self.subTest(src=src):
				self.assertIsNone(ev(src, self.DATA))
				self.assertFalse(evb(src, self.DATA))

	def test_refused_raise_when_asked(self):
		for src in self.REFUSED:
			with self.subTest(src=src):
				parsed = expr.parse_expression(src)
				with self.assertRaises(expr.ExpressionLimitError):
					expr.evaluate_value(parsed, self.DATA, raise_limits=True)
				with self.assertRaises(expr.ExpressionLimitError):
					expr.evaluate_bool(parsed, self.DATA, raise_limits=True)

	def test_message_is_plain(self):
		try:
			expr.evaluate_value(expr.parse_expression('"x" * 99'), {}, raise_limits=True)
		except expr.ExpressionLimitError as exc:
			text = str(exc)
		self.assertIn("too large", text)
		self.assertNotIn("Traceback", text)
		self.assertNotIn("MemoryError", text)

	def test_memory_and_overflow_errors_are_caught(self):
		original = expr._BIN_OPS[expr.ast.Add]
		for exc_type in (MemoryError, OverflowError):
			def boom(a, b, _t=exc_type):
				raise _t()
			expr._BIN_OPS[expr.ast.Add] = boom
			try:
				parsed = expr.parse_expression("1 + 2")
				self.assertIsNone(expr.evaluate_value(parsed, {}))
				with self.assertRaises(expr.ExpressionLimitError):
					expr.evaluate_value(parsed, {}, raise_limits=True)
			finally:
				expr._BIN_OPS[expr.ast.Add] = original

	def test_ordinary_arithmetic_still_works(self):
		self.assertEqual(ev("3 * 4"), 12)
		self.assertEqual(ev("2.5 * 2"), 5.0)
		self.assertEqual(ev("999999999999999999 + 0"), 999999999999999999)
		self.assertEqual(ev("input['a'] * input['b']", {"input": {"a": 6, "b": 7}}), 42)
		self.assertEqual(ev('"ab" + "cd"'), "abcd")
		self.assertEqual(ev("[1] + [2]"), [1, 2])
		self.assertEqual(ev("7 % 4"), 3)
		self.assertIsNone(ev("1000000000 * 1000000000"))  # exactly 10**18 is over the cap
		self.assertEqual(ev("999999999 * 1000000000"), 999999999000000000)

	def test_concatenation_is_capped(self):
		big = "a" * (expr.MAX_SEQUENCE_RESULT // 2 + 1)
		self.assertIsNone(ev("input['s'] + input['s']", {"input": {"s": big}}))
		with self.assertRaises(expr.ExpressionLimitError):
			expr.evaluate_value(expr.parse_expression("input['s'] + input['s']"), {"input": {"s": big}}, raise_limits=True)

	def test_floats_never_raise(self):
		self.assertEqual(ev("1e308 * 10"), float("inf"))
		self.assertIsNone(ev("input['f'] * 2", {"input": {"f": 10**400}}))

	def test_long_multiplication_chain_stays_bounded(self):
		src = " * ".join(["999999"] * 30)  # would reach ~1e360 without the cap
		self.assertIsNone(ev(src))

	def test_fuzz_never_hangs_or_ooms(self):
		import random
		import time

		rng = random.Random(1307)
		atoms = ['"ab"', "[1, 2]", "(1,)", "3", "999999999999", "10", "0", "-7", "1.5", "True", "None", "input['t']", "input['n']", "input['l']"]
		ops = ["*", "+", "-", "%", "/"]
		data = {"input": {"t": "xyz", "n": 10**30, "l": [1] * 50}}
		started = time.time()
		for _ in range(4000):
			size = rng.randint(2, 9)
			src = str(rng.choice(atoms))
			for _ in range(size):
				src += f" {rng.choice(ops)} {rng.choice(atoms)}"
			parsed = expr.parse_expression(src)
			result = expr.evaluate_value(parsed, data)
			if isinstance(result, (str, list, tuple)):
				self.assertLessEqual(len(result), expr.MAX_SEQUENCE_RESULT)
			if isinstance(result, int) and not isinstance(result, bool):
				self.assertLess(abs(result), expr.MAX_INT_MAGNITUDE)
		self.assertLess(time.time() - started, 10)


if __name__ == "__main__":
	unittest.main()
