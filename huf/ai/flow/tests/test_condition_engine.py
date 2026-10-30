"""Condition builder (UX-13): a rules model, compiled, decides the real Condition step the way the sentence says.

Runs the flow engine's own ``_exec_condition`` (the code a run uses) on text the builder writes, for every operator and for the
awkward data the screen allows: nothing at all, empty text, 0, text that is or is not a number, other types, capital letters.
"""

import unittest

from huf.ai.flow.support.condition import condition_compile as cc
from huf.ai.flow.tests.test_flow_engine import FakeFlowRun, _ctx, flow_engine


def decide(rule, **data):
	"""'t' (Yes) or 'f' (No) for a single rule applied to the trigger data."""
	flow_run = FakeFlowRun()
	_ctx(flow_run, **data)
	expression = cc.compile_condition({"match": "all", "items": [rule]})
	result = flow_engine._exec_condition(flow_run, {}, {"expression": expression, "on_true": "t", "on_false": "f"}, {})
	assert result["status"] == "success", (expression, result)
	return result["next_node_id"]


def text(t):
	return {"kind": "text", "text": t}


def num(t):
	return {"kind": "number", "text": t}


def rule(op, value=None, field="input.v", **flags):
	r = {"type": "rule", "field": field, "op": op, **flags}
	if value is not None:
		r["value"] = value
	return r


CASES = [
	# (rule, data, expected path)
	(rule("is", text("Paid")), {"v": "Paid"}, "t"),
	(rule("is", text("Paid")), {"v": "paid"}, "f"),
	(rule("is", text("Paid"), ignoreCase=True), {"v": "pAiD"}, "t"),
	(rule("is", text("Paid")), {}, "f"),
	(rule("is_not", text("Paid")), {}, "t"),
	(rule("is_not", text("Paid")), {"v": "Paid"}, "f"),
	(rule("is", num("100"), numeric=True), {"v": "100"}, "t"),
	(rule("is", num("100"), numeric=True), {"v": 100.0}, "t"),
	(rule("is", num("0"), numeric=True), {"v": 0}, "t"),
	(rule("is", num("0"), numeric=True), {"v": ""}, "f"),
	(rule("is", num("0"), numeric=True), {"v": None}, "f"),
	(rule("gt", num("100"), numeric=True), {"v": 150}, "t"),
	(rule("gt", num("100"), numeric=True), {"v": "150"}, "t"),
	(rule("gt", num("100"), numeric=True), {"v": "abc"}, "f"),
	(rule("gt", num("100"), numeric=True), {"v": None}, "f"),
	(rule("gt", num("100"), numeric=True), {"v": 100}, "f"),
	(rule("lt", num("100"), numeric=True), {"v": 99}, "t"),
	(rule("lt", num("100"), numeric=True), {"v": "abc"}, "f"),
	(rule("gte", num("100"), numeric=True), {"v": 100}, "t"),
	(rule("lte", num("100"), numeric=True), {"v": 100}, "t"),
	(rule("lte", num("100"), numeric=True), {"v": 101}, "f"),
	(rule("contains", text("vip")), {"v": "a vip b"}, "t"),
	(rule("contains", text("vip")), {"v": "VIP"}, "f"),
	(rule("contains", text("vip"), ignoreCase=True), {"v": "VIP"}, "t"),
	(rule("contains", text("vip")), {"v": ["vip"]}, "t"),
	(rule("contains", text("vip")), {"v": None}, "f"),
	(rule("not_contains", text("vip")), {"v": None}, "t"),
	(rule("not_contains", text("vip")), {"v": "xvipx"}, "f"),
	(rule("starts_with", text("AB")), {"v": "AB-1"}, "t"),
	(rule("starts_with", text("AB")), {"v": "xAB"}, "f"),
	(rule("starts_with", text("AB")), {"v": 5}, "f"),
	(rule("ends_with", text(".pdf"), ignoreCase=True), {"v": "A.PDF"}, "t"),
	(rule("ends_with", text(".pdf")), {"v": None}, "f"),
	(rule("is_empty"), {}, "t"),
	(rule("is_empty"), {"v": ""}, "t"),
	(rule("is_empty"), {"v": []}, "t"),
	(rule("is_empty"), {"v": 0}, "f"),
	(rule("is_empty"), {"v": False}, "f"),
	(rule("is_not_empty"), {"v": 0}, "t"),
	(rule("is_not_empty"), {"v": ""}, "f"),
	(rule("is_yes"), {"v": True}, "t"),
	(rule("is_yes"), {"v": "true"}, "f"),
	(rule("is_no"), {"v": False}, "t"),
	(rule("is_no"), {}, "f"),
	(rule("one_of", {"kind": "list", "items": [text("IN"), text("US")]}), {"v": "US"}, "t"),
	(rule("one_of", {"kind": "list", "items": [text("IN"), text("US")]}, ignoreCase=True), {"v": "us"}, "t"),
	(rule("none_of", {"kind": "list", "items": [text("IN"), text("US")]}), {"v": "FR"}, "t"),
	(rule("none_of", {"kind": "list", "items": [text("IN"), text("US")]}), {"v": "IN"}, "f"),
	(rule("is", {"kind": "ref", "ref": "input.w"}, ignoreCase=True), {"v": "A", "w": "a"}, "t"),
	(rule("gt", {"kind": "ref", "ref": "input.w"}, numeric=True), {"v": "5", "w": 3}, "t"),
	(rule("is", text("x"), field="input.a.b[1].c"), {"a": {"b": [0, {"c": "x"}]}}, "t"),
	(rule("is", text("x"), field="input.a.b[5].c"), {"a": {"b": [0]}}, "f"),
]


class TestConditionStepDecides(unittest.TestCase):
	def test_every_case(self):
		for r, data, want in CASES:
			with self.subTest(op=r["op"], value=r.get("value"), flags=(r.get("numeric"), r.get("ignoreCase")), data=data):
				self.assertEqual(decide(r, **data), want)

	def test_every_operator_is_covered(self):
		self.assertEqual({r["op"] for r, _d, _w in CASES}, set(cc.OPERATORS))

	def test_all_of_and_any_of_and_a_group(self):
		model = {"match": "all", "items": [
			rule("gt", num("100"), field="input.amount", numeric=True),
			{"type": "group", "match": "any", "items": [rule("is", text("Paid"), field="input.status", ignoreCase=True), rule("is", text("Shipped"), field="input.status")]},
		]}
		expression = cc.compile_condition(model)

		def run(**data):
			flow_run = FakeFlowRun()
			_ctx(flow_run, **data)
			return flow_engine._exec_condition(flow_run, {}, {"expression": expression, "on_true": "t", "on_false": "f"}, {})["next_node_id"]

		self.assertEqual(run(amount="150", status="PAID"), "t")
		self.assertEqual(run(amount=150, status="Shipped"), "t")
		self.assertEqual(run(amount=150, status="Open"), "f")
		self.assertEqual(run(amount=50, status="Paid"), "f")
		self.assertEqual(run(), "f")

	def test_a_value_typed_like_code_is_only_text(self):
		attack = "x' or True or 'y"
		r = rule("is", text(attack))
		self.assertEqual(decide(r, v="anything"), "f")
		self.assertEqual(decide(r, v=attack), "t")


if __name__ == "__main__":
	unittest.main()
