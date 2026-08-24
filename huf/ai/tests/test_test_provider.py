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
- The real RunProvider.run() fallback-routing path (huf/ai/run.py) actually
  dispatches to this module when litellm.run() fails and the provider name
  lowercases to "test_provider" - proving the routing contract, not just the
  module in isolation.

Run standalone (no bench):
    python3 -m pytest huf/ai/tests/test_test_provider.py -v
"""

import asyncio
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# huf/ai/tests/conftest.py stubs sys.modules['frappe'] with a MagicMock when
# frappe isn't importable (no bench available). Do the same defensively here
# so this file can also be run outside that conftest's collection scope.
if "frappe" not in sys.modules:
    sys.modules["frappe"] = MagicMock()

from huf.ai.providers import test_provider  # noqa: E402


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


class TestRunProviderRoutingToTestProvider(unittest.TestCase):
    """Prove the real huf.ai.run.RunProvider.run() fallback path actually
    dispatches to huf.ai.providers.test_provider - not just that the module
    works when imported and called directly.
    """

    def test_run_provider_falls_back_to_test_provider_module(self):
        from huf.ai import run as run_module

        agent = _make_agent()
        prompt = "__TEST_SCENARIO__:TEST_TEXT"

        # Force the litellm branch to fail with a generic (non-ImportError)
        # exception, exactly like RunProvider.run's own docstring/behavior:
        # "Generic error from LiteLLM: log it, but allow fallback to custom
        # provider module" (huf/ai/run.py:46-52).
        fake_litellm_module = MagicMock()
        fake_litellm_module.run = MagicMock(side_effect=RuntimeError("boom - forcing fallback"))

        # frappe.get_module("huf.ai.providers.test_provider") must resolve to
        # the REAL module (not a mock) so we prove actual routing, not a stub.
        def fake_get_module(module_path):
            if module_path == "huf.ai.providers.test_provider":
                return test_provider
            raise ImportError(module_path)

        with patch.dict(sys.modules, {"huf.ai.providers.litellm": fake_litellm_module}), \
             patch.object(run_module, "frappe") as fake_frappe:
            fake_frappe.get_module.side_effect = fake_get_module
            fake_frappe.log_error = MagicMock()
            # frappe.throw in real frappe raises; our mock must too, or
            # RunProvider.run would silently continue past a throw() call.
            fake_frappe.throw = MagicMock(side_effect=Exception("frappe.throw() called"))

            result_coro = run_module.RunProvider.run(
                agent, prompt, "Test_Provider", "test-model", context=None
            )
            # RunProvider.run's fallback branch does `return module.run(...)`;
            # since test_provider.run is `async def`, this yields a coroutine
            # that the real caller (agent_integration.py) awaits.
            result = asyncio.run(result_coro)

        self.assertEqual(result.final_output, test_provider._TEST_TEXT_RESPONSE)
        self.assertEqual(result.cost, 0.0)
        fake_frappe.get_module.assert_called_once_with("huf.ai.providers.test_provider")


if __name__ == "__main__":
    unittest.main()
