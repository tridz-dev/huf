# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (mocked-frappe, no bench) unit tests for ST-R5.7: per-provider
`timeout_seconds` on litellm calls.

Covers:
- `_provider_timeout()` resolves an AI Provider doc's `timeout_seconds` when
  present and truthy, and falls back to `_DEFAULT_LITELLM_TIMEOUT` (180) when
  the doc is missing, has no value, or the field is falsy (0/None) -- a
  misconfigured provider must never end up with a zero/no request timeout.
- A behavioural check that `litellm.run()`'s completion kwargs actually carry
  the provider's configured timeout, by mocking `_litellm_completion_with_retry`
  (the sole choke point that reaches the real litellm SDK) and inspecting the
  kwargs it was called with -- proving the value is threaded all the way from
  the AI Provider doc into the outgoing request, not just resolved in
  isolation.
- Structural (AST) confirmation that all four request-building sites in
  `litellm.py` (the two non-streaming completion builders, the simple-
  completion helper, and the streaming builder) use `_provider_timeout(...)`
  rather than the bare `_DEFAULT_LITELLM_TIMEOUT` constant.

Run standalone (no bench) from the repo root:
    PYTHONPATH=. python3 huf/ai/tests/test_ai_provider_timeout.py -v
"""

import ast
import asyncio
import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _stub_env  # noqa: E402

_stub_env.install()

from huf.ai.providers import litellm as litellm_module  # noqa: E402

_LITELLM_SRC = pathlib.Path(__file__).resolve().parents[1] / "providers" / "litellm.py"


class _FakeProviderDoc:
    """Minimal stand-in for a `frappe.get_doc("AI Provider", ...)` result."""

    def __init__(self, **fields):
        self._fields = fields

    def get(self, key, default=None):
        return self._fields.get(key, default)


class TestProviderTimeoutHelper(unittest.TestCase):
    """Direct tests of `_provider_timeout()`."""

    def test_uses_configured_timeout(self):
        doc = _FakeProviderDoc(timeout_seconds=60)
        self.assertEqual(litellm_module._provider_timeout(doc), 60)

    def test_falls_back_when_field_missing(self):
        doc = _FakeProviderDoc()
        self.assertEqual(
            litellm_module._provider_timeout(doc), litellm_module._DEFAULT_LITELLM_TIMEOUT
        )

    def test_falls_back_when_field_falsy(self):
        for falsy in (0, None, ""):
            with self.subTest(falsy=falsy):
                doc = _FakeProviderDoc(timeout_seconds=falsy)
                self.assertEqual(
                    litellm_module._provider_timeout(doc), litellm_module._DEFAULT_LITELLM_TIMEOUT
                )

    def test_falls_back_when_doc_is_none(self):
        self.assertEqual(
            litellm_module._provider_timeout(None), litellm_module._DEFAULT_LITELLM_TIMEOUT
        )

    def test_default_is_180(self):
        self.assertEqual(litellm_module._DEFAULT_LITELLM_TIMEOUT, 180)


class TestProviderTimeoutThreadedIntoCompletionCall(unittest.TestCase):
    """Prove `AI Provider.timeout_seconds` actually reaches the outgoing
    litellm completion call, not just the helper in isolation."""

    def _make_agent(self):
        return SimpleNamespace(instructions="You are a test agent.", tools=[], max_turns=1)

    def test_custom_timeout_passed_to_completion_kwargs(self):
        provider_doc = _FakeProviderDoc(
            provider_brand="openai",
            timeout_seconds=60,
            is_local_llm=0,
        )

        fake_response = MagicMock()
        fake_response.choices = [MagicMock()]
        fake_response.choices[0].message = SimpleNamespace(content="hello", tool_calls=None)
        fake_response.usage = SimpleNamespace(
            prompt_tokens=10, completion_tokens=5, total_tokens=15
        )

        captured_kwargs = {}

        async def fake_completion_with_retry(**kwargs):
            captured_kwargs.update(kwargs)
            return fake_response

        with patch.object(litellm_module.frappe, "get_doc", return_value=provider_doc), \
             patch.object(litellm_module, "_resolve_api_key", return_value="fake-key"), \
             patch.object(litellm_module, "_litellm_completion_with_retry", side_effect=fake_completion_with_retry), \
             patch.object(litellm_module, "trim_messages", side_effect=lambda messages, model: messages), \
             patch.object(litellm_module, "extract_round_usage", return_value={"input_tokens": 10, "output_tokens": 5}), \
             patch.object(litellm_module, "calculate_cost", return_value=0.0):

            agent = self._make_agent()
            messages_or_prompt = "hello"

            try:
                asyncio.run(
                    litellm_module.run(
                        agent, messages_or_prompt, "My_Provider", "gpt-4o-mini", context=None
                    )
                )
            except Exception:
                # The full run() pipeline touches many collaborators (cost
                # calc, caching, etc.) that aren't all stubbed here; what
                # this test cares about is only whether the completion call
                # itself received the configured timeout, which is captured
                # before any of that downstream code runs.
                pass

        self.assertIn("timeout", captured_kwargs)
        self.assertEqual(captured_kwargs["timeout"], 60)

    def test_default_timeout_used_when_unset(self):
        provider_doc = _FakeProviderDoc(provider_brand="openai", is_local_llm=0)

        fake_response = MagicMock()
        fake_response.choices = [MagicMock()]
        fake_response.choices[0].message = SimpleNamespace(content="hello", tool_calls=None)
        fake_response.usage = SimpleNamespace(
            prompt_tokens=10, completion_tokens=5, total_tokens=15
        )

        captured_kwargs = {}

        async def fake_completion_with_retry(**kwargs):
            captured_kwargs.update(kwargs)
            return fake_response

        with patch.object(litellm_module.frappe, "get_doc", return_value=provider_doc), \
             patch.object(litellm_module, "_resolve_api_key", return_value="fake-key"), \
             patch.object(litellm_module, "_litellm_completion_with_retry", side_effect=fake_completion_with_retry), \
             patch.object(litellm_module, "trim_messages", side_effect=lambda messages, model: messages), \
             patch.object(litellm_module, "extract_round_usage", return_value={"input_tokens": 10, "output_tokens": 5}), \
             patch.object(litellm_module, "calculate_cost", return_value=0.0):

            agent = self._make_agent()
            try:
                asyncio.run(
                    litellm_module.run(agent, "hello", "My_Provider", "gpt-4o-mini", context=None)
                )
            except Exception:
                pass

        self.assertIn("timeout", captured_kwargs)
        self.assertEqual(captured_kwargs["timeout"], litellm_module._DEFAULT_LITELLM_TIMEOUT)


class TestTimeoutCallSitesUseHelper(unittest.TestCase):
    """Structural check: every `"timeout": ...` kwarg in litellm.py's request
    builders resolves via `_provider_timeout(provider_doc)`, not the bare
    module-level constant -- guards against a future edit reintroducing the
    hard-coded default at one of the sites."""

    @classmethod
    def setUpClass(cls):
        cls.src = _LITELLM_SRC.read_text(encoding="utf-8")

    def test_no_bare_default_timeout_in_request_kwargs(self):
        self.assertNotIn('"timeout": _DEFAULT_LITELLM_TIMEOUT', self.src)

    def test_provider_timeout_helper_used_at_least_four_times(self):
        self.assertGreaterEqual(self.src.count("_provider_timeout(provider_doc)"), 4)


if __name__ == "__main__":
    unittest.main()
