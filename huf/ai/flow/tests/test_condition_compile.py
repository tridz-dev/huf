"""Condition builder (UX-13): rules -> expression text, and that the real evaluator accepts and answers it correctly.

Frappe-free (the compile module and ``huf.ai.graph.expressions`` import nothing from frappe), so it also runs without a bench:

	python3 huf/ai/flow/tests/test_condition_compile.py
"""

import importlib.util
import json
import os
import sys
import unittest

try:
	from huf.ai.flow.support import condition_compile as cc
	from huf.ai.graph import expressions as expr
except Exception:  # pragma: no cover - frappe-less environments
	_HERE = os.path.dirname(os.path.abspath(__file__))

	def _load(name, *parts):
		spec = importlib.util.spec_from_file_location(name, os.path.join(_HERE, *parts))
		mod = importlib.util.module_from_spec(spec)
		sys.modules[name] = mod
		spec.loader.exec_module(mod)
		return mod

	cc = _load("huf_condition_compile_standalone", "..", "support", "condition_compile.py")
	expr = _load("huf_graph_expressions_standalone", "..", "..", "graph", "expressions.py")

_VECTORS = os.path.join(
	os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "frontend", "src", "lib", "flow-condition", "condition_vectors.json"
)
with open(_VECTORS, encoding="utf-8") as _f:
	VECTORS = json.load(_f)


def rule(field, op, value=None, **kw):
	r = {"type": "rule", "field": field, "op": op, **kw}
	if value is not None:
		r["value"] = value
	return r


def text(t):
	return {"kind": "text", "text": t}


def num(t):
	return {"kind": "number", "text": t}


def ref(r):
	return {"kind": "ref", "ref": r}


def lst(*items):
	return {"kind": "list", "items": list(items)}


def run(model, **inp):
	"""Compile, parse with the real parser, evaluate against ``input``. Returns the boolean."""
	source = cc.compile_condition(model)
	parsed = expr.parse_expression(source)  # must be accepted by the real evaluator
	return expr.evaluate_bool(parsed, {"input": inp, "trigger": inp, "n1": {"b": {"c": inp.get("other")}}})


def single(r, **inp):
	return run({"match": "all", "items": [r]}, **inp)


class TestGoldenVectors(unittest.TestCase):
	def test_every_vector_compiles_to_its_text(self):
		for v in VECTORS["vectors"] + VECTORS["compile_only"]:
			with self.subTest(v["name"]):
				self.assertEqual(cc.compile_condition(v["model"]), v["expression"])

	def test_every_vector_is_accepted_by_the_real_evaluator(self):
		for v in VECTORS["vectors"] + VECTORS["compile_only"]:
			if not v["expression"]:
				continue
			with self.subTest(v["name"]):
				expr.parse_expression(v["expression"])
				self.assertLessEqual(len(v["expression"]), expr.MAX_EXPRESSION_LENGTH)

	def test_hand_written_examples_are_not_ours(self):
		# Python only checks they are real expressions or real rejections; the browser decides they are "not rules".
		for source in VECTORS["hand_written_not_rules"]:
			with self.subTest(source):
				try:
					expr.parse_expression(source)
				except expr.ExpressionError:
					pass


class TestReferences(unittest.TestCase):
	def test_reference_expression(self):
		self.assertEqual(cc.reference_expression("input.customer.name"), "input['customer']['name']")
		self.assertEqual(cc.reference_expression("n1.items[0].sku"), "n1['items'][0]['sku']")
		self.assertEqual(cc.reference_expression("foreach.item"), "foreach['item']")
		self.assertEqual(cc.reference_expression("foreach.index"), "foreach['index']")
		self.assertEqual(cc.reference_expression("input"), "input")

	def test_not_a_reference(self):
		for bad in ("", "input.", "input..a", "input.a b", "input['a']", "1abc", "a-b", "x;y", None, 5):
			with self.subTest(bad):
				self.assertIsNone(cc.reference_expression(bad))

	def test_reference_cannot_carry_code(self):
		self.assertIsNone(cc.reference_expression("input.a'] or True or input['b"))


class TestStrings(unittest.TestCase):
	def roundtrip(self, s):
		parsed = expr.parse_expression(cc.py_string(s))
		return expr.evaluate_value(parsed, {})

	def test_awkward_strings_read_back_exactly(self):
		for s in ["", "plain", "it's", 'say "hi"', "back\\slash", "\\'", "'\\", "a\nb\r\nc\td", "\x00\x1f\x7f\x9f", "  ", "日本語 Zoë", "😀 emoji", "' or True or '", "\\\\", "%s {0} {x}"]:
			with self.subTest(repr(s)):
				self.assertEqual(self.roundtrip(s), s)

	def test_text_value_never_changes_the_logic(self):
		attack = "x' or True or 'y"
		m = {"match": "all", "items": [rule("input.a", "is", text(attack))]}
		self.assertFalse(run(m, a="something else"))
		self.assertTrue(run(m, a=attack))


class TestOperatorsOnTheRealEvaluator(unittest.TestCase):
	"""Each operator against ordinary and awkward data: None, '', 0, False, text that is or is not a number, other types."""

	def check(self, r, cases):
		for inp, want in cases:
			with self.subTest(op=r["op"], value=r.get("value"), input=inp):
				self.assertIs(single(r, **inp), want)

	def test_is_text(self):
		r = rule("input.s", "is", text("Paid"))
		self.check(r, [({"s": "Paid"}, True), ({"s": "paid"}, False), ({"s": ""}, False), ({"s": None}, False), ({}, False), ({"s": 0}, False), ({"s": ["Paid"]}, False)])

	def test_is_text_ignoring_case(self):
		r = rule("input.s", "is", text("Paid"), ignoreCase=True)
		self.check(r, [({"s": "PAID"}, True), ({"s": "paid"}, True), ({"s": "Pay"}, False), ({"s": None}, False), ({"s": 5}, False)])

	def test_is_not_text(self):
		r = rule("input.s", "is_not", text("Paid"))
		self.check(r, [({"s": "Open"}, True), ({"s": "Paid"}, False), ({"s": None}, True), ({}, True), ({"s": ""}, True)])

	def test_is_number_accepts_number_or_numeric_text(self):
		r = rule("input.n", "is", num("100"), numeric=True)
		self.check(r, [({"n": 100}, True), ({"n": 100.0}, True), ({"n": "100"}, True), ({"n": " 100 "}, True), ({"n": "100.0"}, True), ({"n": "abc"}, False), ({"n": ""}, False), ({"n": None}, False), ({"n": True}, False), ({"n": 0}, False), ({"n": "1,000"}, False)])

	def test_is_number_plain_is_strict_about_type(self):
		r = rule("input.n", "is", num("100"))
		self.check(r, [({"n": 100}, True), ({"n": "100"}, False)])

	def test_is_not_number(self):
		r = rule("input.n", "is_not", num("0"), numeric=True)
		self.check(r, [({"n": 5}, True), ({"n": 0}, False), ({"n": "0"}, False), ({"n": None}, True), ({"n": "abc"}, True)])

	def test_more_than(self):
		r = rule("input.n", "gt", num("100"), numeric=True)
		self.check(r, [({"n": 150}, True), ({"n": "150"}, True), ({"n": 100}, False), ({"n": 99.99}, False), ({"n": "abc"}, False), ({"n": None}, False), ({"n": ""}, False), ({"n": 0}, False), ({"n": -5}, False), ({"n": True}, False), ({"n": "1e3"}, False)])

	def test_less_than_at_least_at_most(self):
		self.check(rule("input.n", "lt", num("10"), numeric=True), [({"n": 9}, True), ({"n": "9"}, True), ({"n": 10}, False), ({"n": 0}, True), ({"n": ""}, False), ({"n": None}, False)])
		self.check(rule("input.n", "gte", num("10"), numeric=True), [({"n": 10}, True), ({"n": "10.5"}, True), ({"n": 9}, False)])
		self.check(rule("input.n", "lte", num("10"), numeric=True), [({"n": 10}, True), ({"n": "10"}, True), ({"n": 11}, False), ({"n": 0}, True), ({"n": "-3"}, True)])

	def test_more_than_without_number_wrapping_does_not_raise(self):
		r = rule("input.n", "gt", num("100"))
		self.check(r, [({"n": 150}, True), ({"n": "150"}, False), ({"n": None}, False)])

	def test_text_more_than_compares_dates_as_text(self):
		r = rule("input.d", "gt", text("2026-01-01"))
		self.check(r, [({"d": "2026-06-01"}, True), ({"d": "2025-12-31"}, False), ({"d": None}, False), ({"d": 5}, False)])

	def test_contains(self):
		r = rule("input.s", "contains", text("vip"))
		self.check(r, [({"s": "a vip b"}, True), ({"s": "VIP"}, False), ({"s": ""}, False), ({"s": None}, False), ({"s": 5}, False), ({"s": ["vip", "x"]}, True), ({"s": ["VIP"]}, False), ({"s": {"vip": 1}}, True)])

	def test_contains_ignoring_case(self):
		r = rule("input.s", "contains", text("VIP"), ignoreCase=True)
		self.check(r, [({"s": "a Vip b"}, True), ({"s": "vi p"}, False), ({"s": None}, False), ({"s": 5}, False)])

	def test_does_not_contain(self):
		r = rule("input.s", "not_contains", text("spam"))
		self.check(r, [({"s": "hello"}, True), ({"s": "spam!"}, False), ({"s": ""}, True), ({"s": None}, True), ({}, True), ({"s": 5}, True)])

	def test_starts_with_and_ends_with(self):
		self.check(rule("input.s", "starts_with", text("AB-")), [({"s": "AB-1"}, True), ({"s": "ab-1"}, False), ({"s": "xAB-"}, False), ({"s": ""}, False), ({"s": None}, False), ({"s": 5}, False)])
		self.check(rule("input.s", "starts_with", text("ab-"), ignoreCase=True), [({"s": "AB-1"}, True), ({"s": "Ab-1"}, True)])
		self.check(rule("input.s", "ends_with", text(".pdf")), [({"s": "a.pdf"}, True), ({"s": "a.PDF"}, False), ({"s": "a.pdf "}, False), ({"s": None}, False)])
		self.check(rule("input.s", "ends_with", text(".pdf"), ignoreCase=True), [({"s": "a.PDF"}, True)])

	def test_is_empty_and_is_not_empty(self):
		empty = rule("input.s", "is_empty")
		self.check(empty, [({"s": None}, True), ({}, True), ({"s": ""}, True), ({"s": []}, True), ({"s": {}}, True), ({"s": 0}, False), ({"s": False}, False), ({"s": " "}, False), ({"s": "a"}, False), ({"s": [0]}, False)])
		filled = rule("input.s", "is_not_empty")
		self.check(filled, [({"s": None}, False), ({}, False), ({"s": ""}, False), ({"s": 0}, True), ({"s": False}, True), ({"s": "a"}, True), ({"s": [1]}, True)])

	def test_is_yes_and_is_no(self):
		self.check(rule("input.v", "is_yes"), [({"v": True}, True), ({"v": False}, False), ({"v": None}, False), ({}, False), ({"v": "true"}, False), ({"v": 1}, True), ({"v": 0}, False)])
		self.check(rule("input.v", "is_no"), [({"v": False}, True), ({"v": True}, False), ({"v": None}, False), ({}, False), ({"v": 0}, True)])

	def test_one_of_and_none_of(self):
		r = rule("input.c", "one_of", lst(text("IN"), text("US")))
		self.check(r, [({"c": "IN"}, True), ({"c": "in"}, False), ({"c": "FR"}, False), ({"c": None}, False)])
		self.check(rule("input.c", "one_of", lst(text("IN"), text("US")), ignoreCase=True), [({"c": "in"}, True), ({"c": "Us"}, True), ({"c": "FR"}, False)])
		self.check(rule("input.c", "none_of", lst(text("IN"), text("US"))), [({"c": "FR"}, True), ({"c": "IN"}, False), ({"c": None}, True)])
		self.check(rule("input.c", "one_of", lst(num("1"), num("2")), numeric=True), [({"c": 1}, True), ({"c": "2"}, True), ({"c": "3"}, False), ({"c": "x"}, False)])

	def test_compare_with_another_field(self):
		r = rule("input.total", "gt", ref("input.limit"), numeric=True)
		self.check(r, [({"total": 5, "limit": 3}, True), ({"total": "5", "limit": "3"}, True), ({"total": 3, "limit": 5}, False), ({"total": 5, "limit": None}, False), ({"total": None, "limit": None}, False)])
		r = rule("input.a", "is", ref("n1.b.c"), ignoreCase=True)
		self.check(r, [({"a": "X", "other": "x"}, True), ({"a": "X", "other": "y"}, False), ({"a": None, "other": None}, True)])

	def test_missing_field_never_raises(self):
		for op in cc.OPERATORS:
			if op in cc.NO_VALUE:
				r = rule("input.deep.a.b", op)
			elif op in ("one_of", "none_of"):
				r = rule("input.deep.a.b", op, lst(text("x")))
			else:
				r = rule("input.deep.a.b", op, text("x"))
			with self.subTest(op):
				single(r)  # must be accepted and answer without raising


class TestCombining(unittest.TestCase):
	def test_all_of(self):
		m = {"match": "all", "items": [rule("input.amount", "gt", num("100"), numeric=True), rule("input.status", "is", text("Paid"))]}
		self.assertTrue(run(m, amount=150, status="Paid"))
		self.assertFalse(run(m, amount=150, status="Open"))
		self.assertFalse(run(m, amount=50, status="Paid"))
		self.assertTrue(run(m, amount="150", status="Paid"))

	def test_any_of(self):
		m = {"match": "any", "items": [rule("input.a", "is", text("x")), rule("input.b", "is", text("y"))]}
		self.assertTrue(run(m, a="x", b="n"))
		self.assertTrue(run(m, a="n", b="y"))
		self.assertFalse(run(m, a="n", b="n"))

	def test_group_binds_tighter(self):
		m = {"match": "all", "items": [rule("input.amount", "gt", num("100"), numeric=True), {"type": "group", "match": "any", "items": [rule("input.s", "is", text("Paid")), rule("input.s", "is", text("Shipped"))]}]}
		self.assertTrue(run(m, amount=200, s="Shipped"))
		self.assertFalse(run(m, amount=50, s="Shipped"))
		self.assertFalse(run(m, amount=200, s="Open"))

	def test_nothing_complete_is_empty_text(self):
		self.assertEqual(cc.compile_condition({"match": "all", "items": []}), "")
		self.assertEqual(cc.compile_condition({"match": "all", "items": [rule("", "is", text("x"))]}), "")
		self.assertEqual(cc.compile_condition(None), "")
		self.assertEqual(cc.compile_condition({"items": "nope"}), "")

	def test_junk_model_never_raises(self):
		for junk in (5, [], {"items": [None, 5, "x", {"type": "rule"}, {"type": "group"}]}, {"items": [{"type": "rule", "field": "input.a", "op": "is", "value": 5}]}):
			with self.subTest(repr(junk)):
				cc.compile_condition(junk)


class TestHelperFunctions(unittest.TestCase):
	"""The only calls the evaluator allows: number, lower, startswith, endswith."""

	def ev(self, source, **inp):
		return expr.evaluate_value(expr.parse_expression(source), {"input": inp})

	def test_number(self):
		for v, want in [(5, 5), (2.5, 2.5), ("5", 5), ("2.5", 2.5), (" 7 ", 7), ("-3", -3), ("+3", 3), (".5", 0.5), ("5.", 5.0), ("abc", None), ("", None), ("1,000", None), ("1e3", None), ("nan", None), ("inf", None), (None, None), (True, None), ([1], None), ({}, None), ("9" * 5000, None)]:
			with self.subTest(repr(v)[:20]):
				self.assertEqual(self.ev("number(input['v'])", v=v), want)

	def test_lower(self):
		self.assertEqual(self.ev("lower(input['v'])", v="AbC"), "abc")
		self.assertEqual(self.ev("lower(input['v'])", v=5), 5)
		self.assertIsNone(self.ev("lower(input['v'])", v=None))

	def test_startswith_endswith_only_for_text(self):
		self.assertIs(self.ev("startswith(input['v'], 'a')", v="abc"), True)
		self.assertIs(self.ev("startswith(input['v'], 'a')", v=None), False)
		self.assertIs(self.ev("startswith(input['v'], input['w'])", v="abc", w=None), False)
		self.assertIs(self.ev("endswith(input['v'], 'c')", v="abc"), True)

	def test_other_calls_stay_rejected(self):
		for source in ["print('x')", "len([1])", "__import__('os')", "number()", "number(1, 2)", "number(x=1)", "lower(*[1])", "input['a']()", "(lambda: 1)()", "number.__call__(1)", "input.get('a')", "startswith('a')", "str(1)", "open('f')", "number(1)(2)"]:
			with self.subTest(source):
				with self.assertRaises(expr.ExpressionError):
					expr.parse_expression(source)

	def test_helper_names_are_not_values(self):
		self.assertIsNone(self.ev("number"))


if __name__ == "__main__":
	unittest.main()
