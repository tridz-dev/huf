"""
Security-focused unit tests for huf.ai.flow_eval.safe_eval_expression.

Layer A: pure unit tests against the AST-walking evaluator. No Frappe
site/bench/database is required to exercise the evaluator logic itself,
but `frappe.throw`/`frappe.ValidationError` are part of the real Frappe
package, so this module still imports `frappe` (no site connection is
made).

Run with:
  bench --site <site> run-tests --app huf --module huf.ai.tests.test_flow_eval_security
"""
import unittest

import frappe

from huf.ai.flow_eval import safe_eval_expression


class TestFlowEvalSafeCases(unittest.TestCase):
    """Expressions that flow authors are expected to write must still work."""

    def test_simple_equality(self):
        self.assertTrue(safe_eval_expression('context["status"] == "done"', {"status": "done"}))
        self.assertFalse(safe_eval_expression('context["status"] == "done"', {"status": "pending"}))

    def test_nested_dict_access(self):
        ctx = {"user": {"role": "admin"}}
        self.assertTrue(safe_eval_expression('context["user"]["role"] == "admin"', ctx))

    def test_boolean_operators(self):
        ctx = {"a": 1, "b": 2}
        self.assertTrue(safe_eval_expression('context["a"] == 1 and context["b"] == 2', ctx))
        self.assertTrue(safe_eval_expression('context["a"] == 5 or context["b"] == 2', ctx))
        self.assertFalse(safe_eval_expression('not (context["a"] == 1)', ctx))

    def test_comparisons_and_arithmetic(self):
        ctx = {"count": 5}
        self.assertTrue(safe_eval_expression('context["count"] > 3', ctx))
        self.assertTrue(safe_eval_expression('context["count"] + 1 == 6', ctx))
        self.assertTrue(safe_eval_expression('context["count"] % 2 == 1', ctx))

    def test_in_operator(self):
        ctx = {"tags": ["a", "b", "c"]}
        self.assertTrue(safe_eval_expression('"a" in context["tags"]', ctx))
        self.assertTrue(safe_eval_expression('"z" not in context["tags"]', ctx))

    def test_if_expression_and_literals(self):
        ctx = {"x": 10}
        self.assertTrue(safe_eval_expression('(1 if context["x"] > 5 else 0) == 1', ctx))

    def test_missing_key_is_none_not_error(self):
        # Subscript on a missing key returns None rather than raising, so
        # conditions can be written defensively (context["k"] == None).
        self.assertTrue(safe_eval_expression('context["missing"] == None', {}))


class TestFlowEvalRejectsEscapes(unittest.TestCase):
    """Plausible sandbox-escape attempts must be rejected with ValidationError."""

    def _assert_blocked(self, expr, context=None):
        with self.assertRaises(frappe.ValidationError, msg=f"expression not blocked: {expr}"):
            safe_eval_expression(expr, context or {})

    def test_dunder_import_call_blocked(self):
        # Calls are blocked outright (ast.Call), so __import__(...) can never
        # be reached regardless of dunder name resolution.
        self._assert_blocked('__import__("os").system("id")')

    def test_function_call_blocked(self):
        self._assert_blocked('len(context)')
        self._assert_blocked('context["x"]()', {"x": 1})

    def test_attribute_access_blocked(self):
        # This is the classic new-style-class sandbox escape
        # ().__class__.__bases__[0].__subclasses__() -- blocked because any
        # ast.Attribute node is rejected before a Call is even considered.
        self._assert_blocked('().__class__')
        self._assert_blocked('context.__class__')
        self._assert_blocked('context.get')

    def test_getattr_blocked(self):
        # getattr is a function call -> ast.Call -> rejected.
        self._assert_blocked('getattr(context, "__class__")')

    def test_lambda_blocked(self):
        self._assert_blocked('(lambda: 1)()')

    def test_exec_eval_blocked(self):
        self._assert_blocked('exec("1")')
        self._assert_blocked('eval("1")')

    def test_unknown_name_blocked(self):
        # Only the literal name 'context' is bound in the evaluation env.
        self._assert_blocked('os.system("id")')
        self._assert_blocked('__builtins__')

    def test_import_statement_unparseable_in_eval_mode(self):
        # `ast.parse(..., mode="eval")` itself rejects statements (import,
        # assignment) as a SyntaxError before _eval_node ever runs.
        with self.assertRaises(frappe.ValidationError):
            safe_eval_expression('import os', {})

    def test_assignment_blocked(self):
        with self.assertRaises(frappe.ValidationError):
            safe_eval_expression('context["x"] = 1', {"x": 1})

    def test_comprehension_blocked(self):
        # List/dict/set/generator comprehensions are not handled by any
        # _eval_node branch, so they fall through to the generic
        # "Unsupported expression element" throw.
        self._assert_blocked('[x for x in context["items"]]', {"items": [1, 2, 3]})

    def test_subscript_only_allowed_on_dict_or_list(self):
        # Subscripting a non-dict/list value (e.g. a string) is explicitly
        # rejected rather than silently falling through to Python's own
        # str.__getitem__.
        self._assert_blocked('context["s"][0]', {"s": "hello"})

    def test_expression_length_limit_enforced(self):
        long_expr = "context[\"x\"] == " + "1" * 600
        with self.assertRaises(frappe.ValidationError):
            safe_eval_expression(long_expr, {"x": 1})


if __name__ == "__main__":
    unittest.main()
