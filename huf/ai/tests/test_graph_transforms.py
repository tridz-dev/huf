"""Tests for the frappe-free transform operation registry (T-12).

Runnable with NO bench, either way:

    python -m unittest huf.ai.tests.test_graph_transforms -v
    pytest huf/ai/tests/test_graph_transforms.py -v

``huf/__init__.py`` imports frappe unconditionally, so importing via the ``huf.ai.tests`` package path
fails outside a bench. This module therefore loads ``huf/ai/graph/transforms.py`` directly by file
path (bypassing package ``__init__``s entirely), exactly as documented in the T-12 task card, so it
runs identically under a bare ``python3`` with no frappe installed.
"""

import copy
import importlib.util
import itertools
import json
import os
import random
import sys
import unittest

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_TRANSFORMS_PATH = os.path.normpath(os.path.join(_THIS_DIR, "..", "graph", "transforms.py"))


def _load_transforms_module():
	module_name = "huf_graph_transforms_under_test"
	spec = importlib.util.spec_from_file_location(module_name, _TRANSFORMS_PATH)
	module = importlib.util.module_from_spec(spec)
	# Dataclasses look up their defining module in sys.modules (for typing/eval purposes); register
	# before exec so `@dataclass` works when this module is loaded outside a normal package import.
	sys.modules[module_name] = module
	spec.loader.exec_module(module)
	return module


T = _load_transforms_module()


def run(op, input_, limits=None):
	return T.run_transform(op, input_, limits)


class TestRegistryShape(unittest.TestCase):
	"""I3: the operation set is exactly the eleven names in the IR contract, statically knowable."""

	EXPECTED_OPS = {
		"select",
		"filter",
		"sort",
		"limit",
		"group_by",
		"aggregate",
		"join",
		"lookup",
		"batch",
		"distinct",
		"coalesce",
	}

	def test_registry_is_exactly_eleven_ops(self):
		self.assertEqual(set(T.REGISTRY), self.EXPECTED_OPS)
		self.assertEqual(len(T.REGISTRY), 11)

	def test_unknown_op_is_typed_failure_not_exception(self):
		result = run("does_not_exist", {"rows": []})
		self.assertFalse(result.ok)
		self.assertEqual(result.error.code, T.ERR_UNKNOWN_OP)

	def test_non_dict_input_is_typed_failure(self):
		result = run("select", "not-a-dict")
		self.assertFalse(result.ok)
		self.assertEqual(result.error.code, T.ERR_BAD_INPUT)

	def test_frappe_free_module(self):
		src = open(_TRANSFORMS_PATH, encoding="utf-8").read()
		self.assertNotIn("import frappe", src)
		self.assertNotIn("from frappe", src)


class TestSelect(unittest.TestCase):
	def test_projects_named_fields(self):
		result = run("select", {"rows": [{"a": 1, "b": 2}], "fields": ["a"]})
		self.assertTrue(result.ok)
		self.assertEqual(result.value, [{"a": 1}])

	def test_missing_field_is_null_not_error(self):
		result = run("select", {"rows": [{"a": 1}], "fields": ["a", "missing"]})
		self.assertTrue(result.ok)
		self.assertEqual(result.value, [{"a": 1, "missing": None}])

	def test_empty_rows(self):
		result = run("select", {"rows": [], "fields": ["a"]})
		self.assertTrue(result.ok)
		self.assertEqual(result.value, [])

	def test_bad_input_typed_failure(self):
		result = run("select", {"rows": "nope", "fields": ["a"]})
		self.assertFalse(result.ok)
		self.assertEqual(result.error.code, T.ERR_BAD_INPUT)


class TestFilter(unittest.TestCase):
	def test_keeps_truthy_rows(self):
		rows = [{"outstanding_amount": 5}, {"outstanding_amount": 0}, {"outstanding_amount": -1}]
		result = run("filter", {"rows": rows, "where": 'row["outstanding_amount"] > 0'})
		self.assertTrue(result.ok)
		self.assertEqual(result.value, [{"outstanding_amount": 5}])

	def test_type_mismatched_predicate_resolves_false_not_raise(self):
		rows = [{"a": "text"}, {"a": 5}]
		result = run("filter", {"rows": rows, "where": 'row["a"] > 3'})
		self.assertTrue(result.ok)
		self.assertEqual(result.value, [{"a": 5}])

	def test_missing_key_resolves_false(self):
		rows = [{"a": 1}]
		result = run("filter", {"rows": rows, "where": 'row["missing"] > 0'})
		self.assertTrue(result.ok)
		self.assertEqual(result.value, [])

	def test_disallowed_syntax_resolves_false_not_raise(self):
		rows = [{"a": 1}]
		result = run("filter", {"rows": rows, "where": "__import__('os').system('echo hi')"})
		self.assertTrue(result.ok)
		self.assertEqual(result.value, [])

	def test_empty_rows(self):
		result = run("filter", {"rows": [], "where": "True"})
		self.assertTrue(result.ok)
		self.assertEqual(result.value, [])


class TestSort(unittest.TestCase):
	def test_stable_ascending(self):
		rows = [{"k": 2, "tag": "a"}, {"k": 1, "tag": "b"}, {"k": 1, "tag": "c"}]
		result = run("sort", {"rows": rows, "key": "k", "order": "asc"})
		self.assertTrue(result.ok)
		self.assertEqual([r["tag"] for r in result.value], ["b", "c", "a"])

	def test_descending(self):
		rows = [{"k": 1}, {"k": 3}, {"k": 2}]
		result = run("sort", {"rows": rows, "key": "k", "order": "desc"})
		self.assertTrue(result.ok)
		self.assertEqual([r["k"] for r in result.value], [3, 2, 1])

	def test_missing_key_sorts_last_regardless_of_order(self):
		rows = [{"k": 1}, {"other": True}, {"k": 3}]
		asc = run("sort", {"rows": rows, "key": "k", "order": "asc"}).value
		desc = run("sort", {"rows": rows, "key": "k", "order": "desc"}).value
		self.assertEqual(asc[-1], {"other": True})
		self.assertEqual(desc[-1], {"other": True})

	def test_mixed_types_never_raises(self):
		rows = [{"k": 1}, {"k": "text"}, {"k": None}, {"k": [1, 2]}]
		result = run("sort", {"rows": rows, "key": "k", "order": "asc"})
		self.assertTrue(result.ok)  # must not raise TypeError comparing int < str


class TestLimitOps(unittest.TestCase):
	def test_first_n(self):
		result = run("limit", {"rows": [1, 2, 3, 4], "count": 2})
		self.assertEqual(result.value, [1, 2])

	def test_count_beyond_length_is_noop(self):
		result = run("limit", {"rows": [1, 2], "count": 50})
		self.assertTrue(result.ok)
		self.assertEqual(result.value, [1, 2])

	def test_zero_count(self):
		result = run("limit", {"rows": [1, 2], "count": 0})
		self.assertEqual(result.value, [])

	def test_negative_count_bad_input(self):
		result = run("limit", {"rows": [1, 2], "count": -1})
		self.assertFalse(result.ok)
		self.assertEqual(result.error.code, T.ERR_BAD_INPUT)


class TestGroupBy(unittest.TestCase):
	def test_groups_and_missing_key_is_null_group(self):
		rows = [{"c": "x", "v": 1}, {"c": "y", "v": 2}, {"v": 3}, {"c": "x", "v": 4}]
		result = run("group_by", {"rows": rows, "key": "c"})
		self.assertTrue(result.ok)
		keys = [g["key"] for g in result.value]
		self.assertEqual(keys, ["x", "y", None])
		x_group = next(g for g in result.value if g["key"] == "x")
		self.assertEqual([r["v"] for r in x_group["rows"]], [1, 4])

	def test_empty(self):
		result = run("group_by", {"rows": [], "key": "c"})
		self.assertEqual(result.value, [])

	def test_deterministic_group_order_independent_of_dict_construction(self):
		rows_a = [{"c": "b"}, {"c": "a"}, {"c": "b"}]
		rows_b = [dict(reversed(list(r.items()))) for r in rows_a]  # same data, different key order
		result_a = run("group_by", {"rows": rows_a, "key": "c"})
		result_b = run("group_by", {"rows": rows_b, "key": "c"})
		self.assertEqual([g["key"] for g in result_a.value], [g["key"] for g in result_b.value])


class TestAggregate(unittest.TestCase):
	def test_count_of_empty_is_zero(self):
		result = run("aggregate", {"rows": [], "op": "count"})
		self.assertEqual(result.value, 0)

	def test_sum_of_empty_is_zero(self):
		result = run("aggregate", {"rows": [], "op": "sum", "field": "v"})
		self.assertEqual(result.value, 0)

	def test_avg_min_max_of_empty_is_null(self):
		for op in ("avg", "min", "max"):
			result = run("aggregate", {"rows": [], "op": op, "field": "v"})
			self.assertIsNone(result.value, msg=op)

	def test_non_numeric_values_skipped(self):
		rows = [{"v": 1}, {"v": "text"}, {"v": 3}]
		result = run("aggregate", {"rows": rows, "op": "sum", "field": "v"})
		self.assertEqual(result.value, 4)

	def test_avg(self):
		rows = [{"v": 2}, {"v": 4}]
		result = run("aggregate", {"rows": rows, "op": "avg", "field": "v"})
		self.assertEqual(result.value, 3)

	def test_field_required_except_count(self):
		result = run("aggregate", {"rows": [], "op": "sum"})
		self.assertFalse(result.ok)
		self.assertEqual(result.error.code, T.ERR_BAD_INPUT)


class TestJoin(unittest.TestCase):
	def test_inner_join_merges_with_right_prefix(self):
		left = [{"name": "INV-1"}, {"name": "INV-2"}]
		right = [{"reference_invoice": "INV-1", "amount": 100}]
		result = run(
			"join",
			{"left": left, "right": right, "left_key": "name", "right_key": "reference_invoice", "how": "inner"},
		)
		self.assertTrue(result.ok)
		self.assertEqual(result.value, [{"name": "INV-1", "right_reference_invoice": "INV-1", "right_amount": 100}])

	def test_left_join_keeps_unmatched_with_null_right_fields(self):
		left = [{"name": "INV-1"}, {"name": "INV-2"}]
		right = [{"reference_invoice": "INV-1", "amount": 100}]
		result = run(
			"join",
			{"left": left, "right": right, "left_key": "name", "right_key": "reference_invoice", "how": "left"},
		)
		self.assertTrue(result.ok)
		unmatched = next(r for r in result.value if r["name"] == "INV-2")
		self.assertIsNone(unmatched["right_amount"])
		self.assertIsNone(unmatched["right_reference_invoice"])

	def test_empty_sides(self):
		result = run("join", {"left": [], "right": [], "left_key": "a", "right_key": "b", "how": "inner"})
		self.assertTrue(result.ok)
		self.assertEqual(result.value, [])


class TestLookup(unittest.TestCase):
	def test_attaches_first_match(self):
		rows = [{"name": "C1"}]
		frm = [{"customer": "C1", "amount": 10}, {"customer": "C1", "amount": 20}]
		result = run("lookup", {"rows": rows, "from": frm, "key": "name", "on": "customer", "as": "last_payment"})
		self.assertTrue(result.ok)
		self.assertEqual(result.value[0]["last_payment"], {"customer": "C1", "amount": 10})

	def test_no_match_is_null_not_error(self):
		rows = [{"name": "C1"}]
		result = run("lookup", {"rows": rows, "from": [], "key": "name", "on": "customer", "as": "x"})
		self.assertTrue(result.ok)
		self.assertIsNone(result.value[0]["x"])


class TestBatch(unittest.TestCase):
	def test_chunks_with_smaller_last(self):
		result = run("batch", {"rows": [1, 2, 3, 4, 5], "size": 2})
		self.assertEqual(result.value, [[1, 2], [3, 4], [5]])

	def test_empty(self):
		result = run("batch", {"rows": [], "size": 2})
		self.assertEqual(result.value, [])

	def test_size_zero_bad_input(self):
		result = run("batch", {"rows": [1], "size": 0})
		self.assertFalse(result.ok)


class TestDistinct(unittest.TestCase):
	def test_dedupe_by_key_keeps_first(self):
		rows = [{"c": "a", "v": 1}, {"c": "a", "v": 2}, {"c": "b", "v": 3}]
		result = run("distinct", {"rows": rows, "key": "c"})
		self.assertEqual(result.value, [{"c": "a", "v": 1}, {"c": "b", "v": 3}])

	def test_dedupe_without_key_uses_canonical_json(self):
		rows = [{"a": 1, "b": 2}, {"b": 2, "a": 1}, {"a": 3}]
		result = run("distinct", {"rows": rows})
		self.assertEqual(len(result.value), 2)


class TestCoalesce(unittest.TestCase):
	def test_first_non_null(self):
		result = run("coalesce", {"values": [None, None, 5, 6]})
		self.assertEqual(result.value, 5)

	def test_all_null(self):
		result = run("coalesce", {"values": [None, None]})
		self.assertIsNone(result.value)

	def test_empty_values(self):
		result = run("coalesce", {"values": []})
		self.assertIsNone(result.value)


class TestBoundsEnforcement(unittest.TestCase):
	def test_max_rows_fails_closed(self):
		rows = [{"v": i} for i in range(10)]
		result = run("select", {"rows": rows, "fields": ["v"]}, T.Limits(max_rows=5))
		self.assertFalse(result.ok)
		self.assertEqual(result.error.code, T.ERR_ROWS_LIMIT_EXCEEDED)

	def test_max_rows_exact_boundary_ok(self):
		rows = [{"v": i} for i in range(5)]
		result = run("select", {"rows": rows, "fields": ["v"]}, T.Limits(max_rows=5))
		self.assertTrue(result.ok)

	def test_max_output_bytes_fails_closed(self):
		rows = [{"v": "x" * 100} for _ in range(50)]
		result = run("select", {"rows": rows, "fields": ["v"]}, T.Limits(max_rows=1000, max_output_bytes=100))
		self.assertFalse(result.ok)
		self.assertEqual(result.error.code, T.ERR_OUTPUT_LIMIT_EXCEEDED)

	def test_join_output_growth_bounded(self):
		# A many-to-many join can blow up row count even though both inputs are individually small.
		left = [{"k": "a"} for _ in range(5)]
		right = [{"k": "a"} for _ in range(5)]
		join_input = {"left": left, "right": right, "left_key": "k", "right_key": "k"}
		result = run("join", join_input, T.Limits(max_rows=10))
		self.assertFalse(result.ok)
		self.assertEqual(result.error.code, T.ERR_ROWS_LIMIT_EXCEEDED)


class TestDeterminism(unittest.TestCase):
	"""Same input -> same output across repeated runs and across differing dict insertion orders."""

	def _sample_rows(self):
		return [
			{"customer": "C1", "amount": 30, "status": "open"},
			{"customer": "C2", "amount": 10, "status": "open"},
			{"customer": "C1", "amount": 20, "status": "closed"},
			{"customer": "C3", "amount": 40},
		]

	def test_repeated_runs_identical(self):
		rows = self._sample_rows()
		results = []
		for _ in range(20):
			r = run("sort", {"rows": copy.deepcopy(rows), "key": "amount", "order": "asc"})
			results.append(json.dumps(r.value, sort_keys=True, default=str))
		self.assertEqual(len(set(results)), 1)

	def test_dict_insertion_order_does_not_affect_output(self):
		rows = self._sample_rows()
		permuted = []
		for row in rows:
			items = list(row.items())
			random.Random(42).shuffle(items)
			permuted.append(dict(items))
		out_a = run("group_by", {"rows": rows, "key": "customer"}).value
		out_b = run("group_by", {"rows": permuted, "key": "customer"}).value
		self.assertEqual(
			json.dumps(out_a, sort_keys=True, default=str), json.dumps(out_b, sort_keys=True, default=str)
		)

	def test_filter_then_sort_pipeline_deterministic_across_orderings(self):
		rows = self._sample_rows()
		for perm in itertools.islice(itertools.permutations(rows), 6):
			filtered = run("filter", {"rows": list(perm), "where": 'row["amount"] > 15'}).value
			sorted_out = run("sort", {"rows": filtered, "key": "customer", "order": "asc"}).value
			names = [r["customer"] for r in sorted_out]
			self.assertEqual(names, sorted(names))


class TestResolvePath(unittest.TestCase):
	def test_dotted_and_bracket_paths(self):
		row = {"a": {"b": [10, 20, {"c": 5}]}}
		self.assertEqual(T.resolve_path(row, "a.b[2].c"), 5)

	def test_missing_and_out_of_range_are_none(self):
		row = {"a": [1, 2]}
		self.assertIsNone(T.resolve_path(row, "missing"))
		self.assertIsNone(T.resolve_path(row, "a[10]"))

	def test_non_dict_row_never_raises(self):
		self.assertIsNone(T.resolve_path("not-a-dict", "a"))
		self.assertIsNone(T.resolve_path(None, "a"))
		self.assertIsNone(T.resolve_path(42, "a"))


if __name__ == "__main__":
	unittest.main()
