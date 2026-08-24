"""Layer A (mocked-frappe, no bench) unit tests for the deterministic test
tool family (``huf/ai/test_tools.py``) and their ``Agent Tool Function``
factories (``huf/ai/tests/factories.py``).

These are real, invokable tool handlers (NOT the provider-level simulation
in ``huf/ai/providers/test_provider.py``). The tests here prove:

1. Each handler's direct behavior (echo/add/fail/slow).
2. The permission-protected handler's gate is checked using the REAL
   ``PermissionAwareToolRegistry`` resolution path from ``tool_registry.py``,
   fed the factory-built spec as a ``SimpleNamespace`` (attribute access,
   same shape ``frappe.get_cached_doc`` would return).
3. ``get_function_from_name``/``create_function_tool`` from ``sdk_tools.py``
   can resolve and wrap each handler exactly the way real tool assembly does
   (``AgentManager._setup_tools`` -> ``create_agent_tools`` ->
   ``create_function_tool``), and that the exception path in
   ``on_invoke_tool`` correctly converts ``deterministic_fail``'s raised
   exception into a ``{"error": ...}`` JSON string rather than crashing.

Run standalone (no bench) from the repo root:
    PYTHONPATH=. python3 huf/ai/tests/test_test_tools.py -v
"""

import asyncio
import json
import sys
import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

# Mirrors huf/ai/tests/conftest.py + test_test_provider.py's defensive stub,
# so this file is runnable standalone without a bench.
if "frappe" not in sys.modules:
    frappe_mock = MagicMock()
    frappe_mock.utils = MagicMock()
    frappe_mock._ = lambda x: x
    frappe_mock.logger = lambda *a, **k: MagicMock()
    sys.modules["frappe"] = frappe_mock
    sys.modules["frappe.utils"] = frappe_mock.utils
    sys.modules["frappe.utils.file_manager"] = MagicMock()
    sys.modules["frappe.utils.background_jobs"] = MagicMock()
    sys.modules["frappe.client"] = MagicMock()
    sys.modules["frappe.model"] = MagicMock()
    sys.modules["frappe.model.document"] = MagicMock()

import frappe  # noqa: E402

# huf.ai.sdk_tools imports the real `agents` (openai-agents SDK) package at
# module scope for FunctionTool. Stub it minimally, matching the real
# FunctionTool's public shape (name/description/params_json_schema/
# on_invoke_tool/strict_json_schema), so this file stays runnable without a
# bench/venv where that dependency is installed.
if "agents" not in sys.modules:
    class _FakeFunctionTool:
        def __init__(self, name, description, params_json_schema, on_invoke_tool, strict_json_schema=False):
            self.name = name
            self.description = description
            self.params_json_schema = params_json_schema
            self.on_invoke_tool = on_invoke_tool
            self.strict_json_schema = strict_json_schema

    agents_mock = MagicMock()
    agents_mock.FunctionTool = _FakeFunctionTool
    sys.modules["agents"] = agents_mock

from huf.ai import test_tools  # noqa: E402
from huf.ai.tests import factories  # noqa: E402
from huf.ai.tool_registry import PermissionAwareToolRegistry  # noqa: E402
from huf.ai.sdk_tools import get_function_from_name, create_function_tool  # noqa: E402


def _spec_to_namespace(spec: dict) -> SimpleNamespace:
    """Feed a factory dict spec to code that expects attribute access
    (the shape ``frappe.get_cached_doc``/``frappe.get_doc`` returns)."""
    return SimpleNamespace(**spec)


class TestEchoHandler(unittest.TestCase):
    def test_returns_input_unchanged(self):
        result = test_tools.echo(a=1, b="two", c=[3, 4])
        self.assertEqual(result, {"echoed": {"a": 1, "b": "two", "c": [3, 4]}})

    def test_empty_input_roundtrips(self):
        self.assertEqual(test_tools.echo(), {"echoed": {}})

    def test_result_is_json_serializable(self):
        result = test_tools.echo(x={"nested": True}, y=[1, 2, 3])
        json.dumps(result)  # must not raise


class TestDeterministicAddHandler(unittest.TestCase):
    def test_sums_numbers(self):
        result = test_tools.deterministic_add(numbers=[1, 2, 3, 4])
        self.assertEqual(result, {"success": True, "sum": 10, "count": 4})

    def test_empty_list_sums_to_zero(self):
        result = test_tools.deterministic_add(numbers=[])
        self.assertEqual(result["sum"], 0)

    def test_none_defaults_to_empty(self):
        result = test_tools.deterministic_add()
        self.assertEqual(result["sum"], 0)
        self.assertEqual(result["count"], 0)

    def test_deterministic_across_calls(self):
        numbers = [10, -3, 2.5]
        r1 = test_tools.deterministic_add(numbers=numbers)
        r2 = test_tools.deterministic_add(numbers=numbers)
        self.assertEqual(r1, r2)


class TestDeterministicFailHandler(unittest.TestCase):
    def test_raises_known_exception_type(self):
        with self.assertRaises(test_tools.DeterministicTestToolFailure):
            test_tools.deterministic_fail()

    def test_raises_known_message(self):
        with self.assertRaises(test_tools.DeterministicTestToolFailure) as ctx:
            test_tools.deterministic_fail(any_arg="ignored")
        self.assertIn("intentional test failure", str(ctx.exception))

    def test_exception_path_via_on_invoke_tool(self):
        """Prove the REAL handler-exception failure path: create_function_tool's
        on_invoke_tool closure (sdk_tools.py:506-510) must catch this raised
        exception and return {"error": ...} rather than letting it propagate
        out of the tool call.
        """
        tool = create_function_tool(
            name="test_deterministic_fail",
            description="fails",
            tool_name="huf.ai.test_tools.deterministic_fail",
            parameters={"type": "object", "properties": {}},
        )
        self.assertIsNotNone(tool)

        result_json = asyncio.run(tool.on_invoke_tool(None, "{}"))
        result = json.loads(result_json)
        self.assertIn("error", result)
        self.assertIn("intentional test failure", result["error"])


class TestSlowOrTimeoutHandler(unittest.TestCase):
    def test_sleeps_requested_duration(self):
        start = time.monotonic()
        result = test_tools.slow_or_timeout(duration=0.05)
        elapsed = time.monotonic() - start
        self.assertGreaterEqual(elapsed, 0.05)
        self.assertEqual(result["slept_duration"], 0.05)
        self.assertFalse(result["capped"])

    def test_caps_at_max_sleep_seconds(self):
        result = test_tools.slow_or_timeout(duration=999)
        self.assertEqual(result["slept_duration"], test_tools.MAX_SLEEP_SECONDS)
        self.assertTrue(result["capped"])
        self.assertEqual(result["requested_duration"], 999)

    def test_negative_duration_clamped_to_zero(self):
        result = test_tools.slow_or_timeout(duration=-5)
        self.assertEqual(result["slept_duration"], 0.0)

    def test_invalid_duration_falls_back_to_default(self):
        result = test_tools.slow_or_timeout(duration="not-a-number")
        self.assertEqual(result["requested_duration"], 0.1)


class TestPermissionProtectedMutationHandler(unittest.TestCase):
    def test_denied_when_no_write_permission(self):
        frappe.has_permission = MagicMock(return_value=False)
        result = test_tools.permission_protected_mutation(record_id="X", value="v")
        self.assertFalse(result["success"])
        self.assertTrue(result["permission_denied"])

    def test_allowed_when_write_permission_present(self):
        frappe.has_permission = MagicMock(return_value=True)
        result = test_tools.permission_protected_mutation(record_id="X", value="v")
        self.assertTrue(result["success"])
        self.assertEqual(result["record_id"], "X")
        self.assertEqual(result["value"], "v")


class TestFactories(unittest.TestCase):
    def test_all_specs_buildable_and_shaped(self):
        specs = factories.build_all_test_tool_specs()
        self.assertEqual(
            set(specs.keys()),
            {"echo", "deterministic_add", "deterministic_fail",
             "permission_protected_mutation", "slow_or_timeout"},
        )
        for name, spec in specs.items():
            self.assertEqual(spec["doctype"], "Agent Tool Function")
            self.assertEqual(spec["types"], "Custom Function")
            self.assertTrue(spec["function_path"].startswith("huf.ai.test_tools."))
            json.loads(spec["params"])  # must be valid JSON

    def test_permission_protected_spec_has_required_permission_and_reference_doctype(self):
        spec = factories.build_permission_protected_mutation_tool_spec()
        self.assertEqual(spec["required_permission"], "write")
        self.assertEqual(spec["reference_doctype"], "ToDo")

    def test_resolved_handler_matches_factory_function_path(self):
        for name, builder in factories.TEST_TOOL_SPEC_BUILDERS.items():
            spec = builder()
            fn = get_function_from_name(spec["function_path"])
            self.assertIsNotNone(fn, f"could not resolve {spec['function_path']}")
            self.assertEqual(fn.__module__, "huf.ai.test_tools")


class TestPermissionGateRealPath(unittest.TestCase):
    """Exercise the REAL PermissionAwareToolRegistry._can_use_tool gate
    (tool_registry.py:70-106) against the permission_protected_mutation
    fixture, standalone.
    """

    def test_gate_blocks_guest_mutation(self):
        spec = factories.build_permission_protected_mutation_tool_spec()
        tool_doc = _spec_to_namespace(spec)
        allowed = PermissionAwareToolRegistry._can_use_tool(tool_doc, "Guest")
        self.assertFalse(allowed)

    def test_gate_checks_required_permission_via_has_permission(self):
        spec = factories.build_permission_protected_mutation_tool_spec()
        tool_doc = _spec_to_namespace(spec)

        frappe.has_permission = MagicMock(return_value=False)
        self.assertFalse(PermissionAwareToolRegistry._can_use_tool(tool_doc, "some_user@example.com"))
        frappe.has_permission.assert_called_with(doctype="ToDo", ptype="write", user="some_user@example.com")

        frappe.has_permission = MagicMock(return_value=True)
        self.assertTrue(PermissionAwareToolRegistry._can_use_tool(tool_doc, "some_user@example.com"))

    def test_gate_allows_echo_readonly_tool_for_guest_when_marked_allowed(self):
        spec = factories.build_echo_tool_spec(allowed_for_guest=1)
        tool_doc = _spec_to_namespace(spec)
        self.assertTrue(PermissionAwareToolRegistry._can_use_tool(tool_doc, "Guest"))

    def test_gate_blocks_echo_for_guest_when_not_allowed(self):
        # echo is not in MUTATING_TOOL_TYPES (it's "Custom Function"), and the
        # registry's Guest branch returns False for any non-explicitly-allowed
        # Guest access regardless of mutating status (tool_registry.py:78-88).
        spec = factories.build_echo_tool_spec()
        tool_doc = _spec_to_namespace(spec)
        self.assertFalse(PermissionAwareToolRegistry._can_use_tool(tool_doc, "Guest"))


if __name__ == "__main__":
    unittest.main()
