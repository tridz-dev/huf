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
