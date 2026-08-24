# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (mocked-frappe, no bench) unit tests for the HUF Test Provider.

Covers:
- test_provider.run() directly, for the TEST_TEXT scenario: return shape
  matches the litellm.SimpleResult contract (final_output/usage/new_items/cost)
  and content is fixed/deterministic.
- Marker extraction is robust to the prompt-wrapping agent_integration.py
  actually does (marker not at prompt[0]).
- Unknown/missing scenario markers raise UnknownTestScenarioError.
- The REAL routing path this provider is actually reached through in
  production: `huf.ai.providers.litellm.run()`'s own
  `provider.lower() == "test_provider"` check, near the top of that
  coroutine, before any `frappe.get_doc`/network code. We import and call the
  real `litellm.run()` (with `frappe`/`litellm` package imports stubbed, since
  no bench is available here) and assert `frappe.get_doc` is never called -
  proving the test provider is reached without touching any real
  provider-doc/network code, on the exact same coroutine a real Agent Run
  awaits.

  We deliberately do NOT prove this by mocking `litellm.run` to raise
  synchronously and relying on `huf.ai.run.RunProvider.run()`'s
  custom-provider fallback branch: `litellm.run()` is `async def`, so calling
  it only constructs a coroutine - a real execution failure can only surface
  later, when the caller (`agent_integration.py:1620`,
  `await RunProvider.run(...)`) awaits it, which is after
  `RunProvider.run()`'s own try/except has already returned. A synchronous
  `side_effect` mock does not simulate anything a real Agent Run can produce;
  see `huf/ai/providers/test_provider.py`'s module docstring for the full
  analysis.

Run standalone (no bench) from the repo root:
    PYTHONPATH=. python3 huf/ai/tests/test_test_provider.py -v
"""

import asyncio
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

# huf/ai/tests/conftest.py stubs sys.modules['frappe'] with a MagicMock when
# frappe isn't importable (no bench available). Do the same defensively here
# so this file can also be run outside that conftest's collection scope.
if "frappe" not in sys.modules:
    frappe_mock = MagicMock()
    frappe_mock.utils = MagicMock()
    frappe_mock._ = lambda x: x
    sys.modules["frappe"] = frappe_mock
    sys.modules["frappe.utils"] = frappe_mock.utils

# `huf.ai.providers.litellm` imports the real `litellm` PyPI package at
# module scope. Stub it too, so this file stays runnable without a bench
# (which is where that dependency is actually installed).
if "litellm" not in sys.modules:
    litellm_pkg_mock = MagicMock()
    for _exc_name in (
        "InternalServerError",
        "RateLimitError",
        "APIError",
        "BadRequestError",
        "ContextWindowExceededError",
    ):
        setattr(litellm_pkg_mock, _exc_name, type(_exc_name, (Exception,), {}))
    sys.modules["litellm"] = litellm_pkg_mock
    sys.modules["litellm.utils"] = MagicMock()

from huf.ai.providers import test_provider  # noqa: E402
from huf.ai.providers import litellm as litellm_module  # noqa: E402


def _make_agent(**overrides):
    """Minimal fake `agent` object exposing only the attributes litellm.run()
    actually reads (instructions/tools/max_turns) - test_provider.run() does
    not read any of them for TEST_TEXT, but we mirror the shape so this fake
    is interchangeable with the one used in test_provider_error_contract.py.
    """
    fields = {
        "instructions": "You are a test agent.",
        "tools": [],
        "max_turns": 1,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


class TestTestProviderDirect(unittest.TestCase):
    """Exercise huf.ai.providers.test_provider.run() directly."""

    def test_test_text_scenario_returns_litellm_shaped_result(self):
        agent = _make_agent()
        prompt = "__TEST_SCENARIO__:TEST_TEXT"

        result = asyncio.run(
            test_provider.run(agent, prompt, "Test_Provider", "test-model", context=None)
        )

        # Shape: matches litellm.SimpleResult's public contract exactly.
        self.assertTrue(hasattr(result, "final_output"))
        self.assertTrue(hasattr(result, "usage"))
        self.assertTrue(hasattr(result, "new_items"))
        self.assertTrue(hasattr(result, "cost"))

        # Content: fixed and deterministic.
        self.assertEqual(result.final_output, test_provider._TEST_TEXT_RESPONSE)
        self.assertEqual(result.new_items, [])
        self.assertEqual(result.cost, 0.0)

        # Usage: realistic-shaped, zero-cost, fixed token counts, and read
        # the same way agent_integration.py reads it (dict.get, not getattr -
        # see huf/ai/agent_integration.py:1791-1792).
        self.assertIsInstance(result.usage, dict)
        self.assertEqual(result.usage.get("input_tokens"), test_provider._TEST_TEXT_INPUT_TOKENS)
        self.assertEqual(result.usage.get("output_tokens"), test_provider._TEST_TEXT_OUTPUT_TOKENS)

    def test_marker_found_even_when_not_at_prompt_start(self):
        """agent_integration.py wraps the raw prompt inside a larger template
        ("Current user message:\n{prompt}\n"), so the marker is never
        literally prefix-of-string in production. Prove the scan handles that.
        """
        agent = _make_agent()
        wrapped_prompt = (
            "Some RAG context here.\n\n"
            "Current user message:\n"
            "__TEST_SCENARIO__:TEST_TEXT please respond\n"
        )

        result = asyncio.run(
            test_provider.run(agent, wrapped_prompt, "Test_Provider", "test-model")
        )
        self.assertEqual(result.final_output, test_provider._TEST_TEXT_RESPONSE)

    def test_missing_marker_raises(self):
        agent = _make_agent()
        with self.assertRaises(test_provider.UnknownTestScenarioError):
            asyncio.run(test_provider.run(agent, "no marker here", "Test_Provider", "test-model"))

    def test_unknown_scenario_name_raises(self):
        agent = _make_agent()
        prompt = "__TEST_SCENARIO__:NOT_A_REAL_SCENARIO"
        with self.assertRaises(test_provider.UnknownTestScenarioError):
            asyncio.run(test_provider.run(agent, prompt, "Test_Provider", "test-model"))

    def test_repeated_calls_are_deterministic(self):
        """Same input -> byte-identical output, every time (no randomness, no clock)."""
        agent = _make_agent()
        prompt = "__TEST_SCENARIO__:TEST_TEXT"

        first = asyncio.run(test_provider.run(agent, prompt, "Test_Provider", "test-model"))
        second = asyncio.run(test_provider.run(agent, prompt, "Test_Provider", "test-model"))

        self.assertEqual(first.final_output, second.final_output)
        self.assertEqual(first.usage, second.usage)
        self.assertEqual(first.cost, second.cost)


class TestTestProviderToolScenarios(unittest.TestCase):
    """Exercise TEST_TOOL_SINGLE / TEST_TOOL_MULTI / TEST_PROVIDER_TIMEOUT
    directly, proving their shape matches litellm.run()'s real
    success/error paths (see test_provider.py's "Tool-call scenario
    contract" docstring section for the contract this asserts against).
    """

    def _assert_tool_call_item_shape(self, item, expected_name, expected_args, expected_id):
        self.assertEqual(item.type, "tool_call_item")
        self.assertEqual(item.raw_item.name, expected_name)
        self.assertEqual(item.raw_item.arguments, expected_args)
        self.assertEqual(item.raw_item.id, expected_id)

    def _assert_tool_call_output_item_shape(self, item, expected_name, expected_output, expected_id):
        self.assertEqual(item.type, "tool_call_output_item")
        self.assertIsInstance(item.raw_item, dict)
        self.assertEqual(item.raw_item["name"], expected_name)
        self.assertEqual(item.raw_item["output"], expected_output)
        self.assertEqual(item.raw_item["id"], expected_id)

    def test_tool_single_returns_one_executed_tool_call_round_trip(self):
        agent = _make_agent()
        prompt = "__TEST_SCENARIO__:TEST_TOOL_SINGLE"

        result = asyncio.run(
            test_provider.run(agent, prompt, "Test_Provider", "test-model", context=None)
        )

        # Shape: matches litellm.SimpleResult's public contract exactly.
        self.assertTrue(hasattr(result, "final_output"))
        self.assertTrue(hasattr(result, "usage"))
        self.assertTrue(hasattr(result, "new_items"))
        self.assertTrue(hasattr(result, "cost"))

        self.assertEqual(result.final_output, test_provider._TEST_TOOL_SINGLE_RESPONSE)
        self.assertEqual(result.cost, 0.0)
        self.assertIsInstance(result.usage, dict)
        self.assertEqual(
            result.usage.get("input_tokens"), test_provider._TEST_TOOL_SINGLE_INPUT_TOKENS
        )
        self.assertEqual(
            result.usage.get("output_tokens"), test_provider._TEST_TOOL_SINGLE_OUTPUT_TOKENS
        )

        # new_items: exactly one already-executed tool_call_item/
        # tool_call_output_item pair, matching what litellm.run()'s real
        # per-round loop appends (litellm.py ~1123-1171) - not an
        # instruction for some outer loop to go execute a tool.
        self.assertEqual(len(result.new_items), 2)
        self._assert_tool_call_item_shape(
            result.new_items[0], test_provider._TOOL_NAME, test_provider._TOOL_ARGS,
            test_provider._TOOL_CALL_ID_1,
        )
        self._assert_tool_call_output_item_shape(
            result.new_items[1], test_provider._TOOL_NAME, test_provider._TOOL_RESULT,
            test_provider._TOOL_CALL_ID_1,
        )

    def test_tool_multi_returns_two_executed_tool_call_round_trips(self):
        agent = _make_agent()
        prompt = "__TEST_SCENARIO__:TEST_TOOL_MULTI"

        result = asyncio.run(
            test_provider.run(agent, prompt, "Test_Provider", "test-model", context=None)
        )

        self.assertEqual(result.final_output, test_provider._TEST_TOOL_MULTI_RESPONSE)
        self.assertEqual(result.cost, 0.0)

        # Two full round-trips = four new_items, alternating call/output,
        # each pair matching litellm.run()'s per-round-loop append shape.
        self.assertEqual(len(result.new_items), 4)
        self._assert_tool_call_item_shape(
            result.new_items[0], test_provider._TOOL_NAME, test_provider._TOOL_ARGS,
            test_provider._TOOL_CALL_ID_1,
        )
        self._assert_tool_call_output_item_shape(
            result.new_items[1], test_provider._TOOL_NAME, test_provider._TOOL_RESULT,
            test_provider._TOOL_CALL_ID_1,
        )
        self._assert_tool_call_item_shape(
            result.new_items[2], test_provider._TOOL_NAME_2, test_provider._TOOL_ARGS_2,
            test_provider._TOOL_CALL_ID_2,
        )
        self._assert_tool_call_output_item_shape(
            result.new_items[3], test_provider._TOOL_NAME_2, test_provider._TOOL_RESULT_2,
            test_provider._TOOL_CALL_ID_2,
        )

    def test_provider_timeout_raises_provider_unavailable_error(self):
        """Must raise the exact same exception class litellm.run() raises for
        a real timeout (litellm_module.ProviderUnavailableError), with the
        same public_message/log_message attribute shape - see
        `litellm.py:64-71` and `litellm.py`'s generic `except Exception`
        fallback (~line 979-988) that a real litellm.Timeout falls through to.
        """
        agent = _make_agent()
        prompt = "__TEST_SCENARIO__:TEST_PROVIDER_TIMEOUT"

        with self.assertRaises(litellm_module.ProviderUnavailableError) as ctx:
            asyncio.run(
                test_provider.run(agent, prompt, "Test_Provider", "test-model", context=None)
            )

        exc = ctx.exception
        self.assertTrue(hasattr(exc, "public_message"))
        self.assertTrue(hasattr(exc, "log_message"))
        self.assertEqual(exc.public_message, test_provider._TEST_TIMEOUT_MESSAGE)
        self.assertEqual(exc.log_message, test_provider._TEST_TIMEOUT_LOG_MESSAGE)
        self.assertEqual(str(exc), test_provider._TEST_TIMEOUT_MESSAGE)

    def test_provider_timeout_via_real_litellm_routing(self):
        """Exercise the exact same real routing path as TEST_TEXT's routing
        test, proving the timeout scenario raises identically whether reached
        directly or via `litellm.run()`'s `provider.lower() == "test_provider"`
        dispatch.
        """
        agent = _make_agent()
        prompt = "__TEST_SCENARIO__:TEST_PROVIDER_TIMEOUT"

        with self.assertRaises(litellm_module.ProviderUnavailableError):
            asyncio.run(
                litellm_module.run(agent, prompt, "Test_Provider", "test-model", context=None)
            )


class TestLiteLLMRunRoutesToTestProvider(unittest.TestCase):
    """Prove the REAL routing path: `huf.ai.providers.litellm.run()`'s own
    `provider.lower() == "test_provider"` check dispatches to
    `huf.ai.providers.test_provider`, before any `frappe.get_doc`/network
    code in `litellm.run()` executes.

    This exercises the exact coroutine `RunProvider.run()` returns and the
    real caller (`agent_integration.py:1620`) awaits - not a mocked
    synchronous failure of `litellm.run` routed through the
    `huf.ai.run.RunProvider.run()` custom-provider fallback branch (which,
    per this module's and `test_provider.py`'s docstrings, is not reachable
    on a real litellm execution failure since `litellm.run` is `async def`).
    """

    def test_litellm_run_dispatches_to_test_provider_before_any_real_work(self):
        agent = _make_agent()
        prompt = "__TEST_SCENARIO__:TEST_TEXT"

        # frappe.get_doc is the first real-provider-doc access litellm.run()
        # performs (to load the "AI Provider" doc / API key). It must NEVER
        # be called when routing to the test provider - proving the early
        # return happens before any real work.
        litellm_module.frappe.get_doc.reset_mock()

        result = asyncio.run(
            litellm_module.run(agent, prompt, "Test_Provider", "test-model", context=None)
        )

        self.assertEqual(result.final_output, test_provider._TEST_TEXT_RESPONSE)
        self.assertEqual(result.cost, 0.0)
        litellm_module.frappe.get_doc.assert_not_called()

    def test_litellm_run_provider_name_matching_is_case_insensitive(self):
        """`provider.lower() == "test_provider"` - exercise a mixed-case
        `AI Provider` document name, matching how `RunProvider.run()` and
        `litellm.run()` both lowercase the provider argument before use.
        """
        agent = _make_agent()
        prompt = "__TEST_SCENARIO__:TEST_TEXT"

        result = asyncio.run(
            litellm_module.run(agent, prompt, "TEST_PROVIDER", "test-model", context=None)
        )
        self.assertEqual(result.final_output, test_provider._TEST_TEXT_RESPONSE)

    def test_real_provider_name_does_not_route_to_test_provider(self):
        """Sanity check the routing check is scoped: a real provider name
        must NOT be diverted into the test provider and must proceed into
        litellm.run()'s real body (asserted here by it reaching frappe.get_doc,
        which we make raise to keep this test hermetic - no network/DB).
        """
        agent = _make_agent()
        litellm_module.frappe.get_doc.reset_mock()
        litellm_module.frappe.get_doc.side_effect = RuntimeError("reached real provider doc lookup")

        # We only care that the real (non-test-provider) path was reached -
        # i.e. frappe.get_doc got called - not the specific exception type
        # that eventually surfaces (with fully-mocked frappe/litellm modules,
        # the real body's own exception handling can itself raise a
        # different, unrelated TypeError further down; that's an artifact of
        # this hermetic stubbing, not something this test is about).
        with self.assertRaises(Exception):
            asyncio.run(
                litellm_module.run(agent, "hello", "OpenAI", "gpt-4-turbo", context=None)
            )

        litellm_module.frappe.get_doc.assert_called_once()
        litellm_module.frappe.get_doc.side_effect = None


if __name__ == "__main__":
    unittest.main()
