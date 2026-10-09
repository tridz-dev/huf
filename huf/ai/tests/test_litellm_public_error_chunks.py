# Copyright (c) 2025, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""
The stream forwarder replaces any error chunk's text with a generic message
unless the chunk carries ``"public": True``. These tests pin which
``run_stream`` error producers are marked public (curated fixed templates only)
and that the catch-all chunk, which interpolates raw exception text, is not.
"""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from huf.ai.providers import litellm as litellm_module
from huf.ai.providers.litellm import _sanitize_provider_error_message, run_stream

SECRET = "sk-secret-123 invalid"


def _patches(api_key="test-key"):
    return [
        patch("huf.ai.providers.litellm.calculate_cost", return_value=(0.001, "test")),
        patch("huf.ai.providers.litellm.extract_round_usage", return_value={
            "input_tokens": 1, "output_tokens": 1, "cache_read_tokens": 0, "cache_write_tokens": 0,
        }),
        patch("huf.ai.providers.litellm.normalise_usage_payload", return_value={
            "input_tokens": 1, "output_tokens": 1, "cache_read_tokens": 0, "cache_write_tokens": 0,
        }),
        patch("huf.ai.providers.litellm.build_reasoning_kwargs", return_value={}),
        patch("huf.ai.providers.litellm.resolve_reasoning", return_value=Mock(resolved={})),
        patch("huf.ai.providers.litellm.detect_model_capabilities", return_value=Mock()),
        patch("huf.ai.providers.litellm.resolve_capabilities", return_value=Mock(min_cacheable_tokens=1)),
        patch("huf.ai.providers.litellm.model_supports_prompt_caching", return_value=True),
        patch("huf.ai.providers.litellm.serialize_tools", return_value=None),
        patch("huf.ai.providers.litellm.repair_message_sequence", side_effect=lambda messages, conversation_name: messages),
        patch("huf.ai.providers.litellm.trim_messages", side_effect=lambda messages, model: messages),
        patch("huf.ai.providers.litellm._resolve_api_base", return_value=None),
        patch("huf.ai.providers.litellm._normalize_model_name", return_value="anthropic/claude-haiku"),
        patch("huf.ai.providers.litellm._resolve_api_key", return_value=api_key),
    ]


def _stop_chunks(content):
    d1 = SimpleNamespace(content=content, thinking_blocks=None, reasoning_content=None, tool_calls=None)
    c1 = SimpleNamespace(usage=None, choices=[SimpleNamespace(delta=d1, finish_reason=None)])
    d2 = SimpleNamespace(content=None, thinking_blocks=None, reasoning_content=None, tool_calls=None)
    c2 = SimpleNamespace(usage=Mock(), choices=[SimpleNamespace(delta=d2, finish_reason="stop")])
    return [c1, c2]


def _tool_chunks():
    tc = SimpleNamespace(index=0, id="tc1", function=SimpleNamespace(name="nonexistent_tool", arguments="{}"))
    d1 = SimpleNamespace(content=None, thinking_blocks=None, reasoning_content=None, tool_calls=[tc])
    c1 = SimpleNamespace(usage=None, choices=[SimpleNamespace(delta=d1, finish_reason=None)])
    d2 = SimpleNamespace(content=None, thinking_blocks=None, reasoning_content=None, tool_calls=None)
    c2 = SimpleNamespace(usage=Mock(), choices=[SimpleNamespace(delta=d2, finish_reason="tool_calls")])
    return [c1, c2]


class TestPublicErrorChunks(unittest.TestCase):
    def _run(self, completion, api_key="test-key", get_doc_side_effect=None):
        agent = Mock()
        agent.instructions = "Hi"
        agent.tools = []
        agent.max_turns = 20
        agent.model_settings = None
        agent_doc = Mock()
        agent_doc.temperature = 1.0
        agent_doc.top_p = 1.0
        agent_doc.get = Mock(side_effect=lambda key, default=None: {
            "prompt_cache_mode": "Off", "enable_prompt_caching": False,
        }.get(key, default))
        provider_doc = Mock()
        provider_doc.get = Mock(return_value=None)

        patches = _patches(api_key)
        retry = patch("huf.ai.providers.litellm._litellm_completion_with_retry", side_effect=completion)
        mock_frappe = patch("huf.ai.providers.litellm.frappe")
        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            stack.enter_context(retry)
            frappe_mock = stack.enter_context(mock_frappe)
            frappe_mock.get_doc = Mock(
                side_effect=get_doc_side_effect
                or (lambda doctype, name: {"Agent": agent_doc, "AI Provider": provider_doc}.get(doctype))
            )
            frappe_mock.cache = Mock(return_value=Mock(get_value=Mock(return_value=None)))
            frappe_mock.has_permission = Mock(return_value=True)
            frappe_mock.session = Mock(user="test")
            frappe_mock.logger = Mock(return_value=Mock())
            # Keep the real exception classes so `except (frappe.X, ...)` works.
            import frappe as real_frappe
            frappe_mock.DoesNotExistError = real_frappe.DoesNotExistError
            frappe_mock.PermissionError = real_frappe.PermissionError
            frappe_mock.ValidationError = real_frappe.ValidationError

            async def _collect():
                return [e async for e in run_stream(
                    agent, "hi", "Anthropic", "claude-haiku", context={"agent_name": "TestAgent"},
                )]

            return asyncio.run(_collect())

    @staticmethod
    def _errors(chunks):
        return [c for c in chunks if c.get("type") == "error"]

    def _assert_public_no_secret(self, chunks):
        errs = self._errors(chunks)
        self.assertEqual(len(errs), 1, chunks)
        self.assertIs(errs[0].get("public"), True)
        self.assertNotIn("sk-secret", errs[0]["error"])
        self.assertNotIn("invalid", errs[0]["error"].lower().replace("invalid api key", ""))
        return errs[0]

    def test_missing_api_key_is_public(self):
        async def never(**kw):
            raise AssertionError("should not be called")

        errs = self._errors(self._run(never, api_key=None))
        self.assertEqual(len(errs), 1)
        self.assertIs(errs[0].get("public"), True)
        self.assertEqual(errs[0]["error"], "API key not configured in AI Provider.")

    def _round_exception_case(self, exc):
        async def boom(**kw):
            raise exc

        return self._assert_public_no_secret(self._run(boom))

    def test_sanitized_provider_exceptions_are_public_and_leak_nothing(self):
        mod = litellm_module
        excs = [
            mod.InternalServerError(SECRET, "anthropic", "claude-haiku"),
            mod.RateLimitError(SECRET, "anthropic", "claude-haiku"),
            mod.ContextWindowExceededError(SECRET, "claude-haiku", "anthropic"),
            mod.APIError(500, SECRET, "anthropic", "claude-haiku"),
            RuntimeError(SECRET),
        ]
        for exc in excs:
            with self.subTest(exc=type(exc).__name__):
                self._round_exception_case(exc)

    def test_empty_response_is_public(self):
        async def empty(**kw):
            return _stop_chunks(None)

        errs = self._errors(self._run(empty))
        self.assertEqual(len(errs), 1)
        self.assertIs(errs[0].get("public"), True)
        self.assertIn("returned an empty response", errs[0]["error"])

    def test_tool_loop_is_public(self):
        async def loop(**kw):
            return _tool_chunks()

        errs = self._errors(self._run(loop))
        self.assertEqual(len(errs), 1)
        self.assertIs(errs[0].get("public"), True)
        self.assertIn("kept calling the same tool", errs[0]["error"])

    def test_catch_all_streaming_error_is_not_public(self):
        def get_doc(doctype, name):
            if doctype == "AI Provider":
                raise RuntimeError(SECRET)
            return Mock()

        async def never(**kw):
            raise AssertionError("should not be called")

        errs = self._errors(self._run(never, get_doc_side_effect=get_doc))
        self.assertEqual(len(errs), 1)
        self.assertNotIn("public", errs[0])
        self.assertTrue(errs[0]["error"].startswith("LiteLLM Streaming Error:"))

    def test_sanitizer_returns_fixed_templates_only(self):
        for raw in (SECRET, f"LiteLLM error for model 'm': {SECRET}", "rate limit " + SECRET):
            self.assertNotIn("sk-secret", _sanitize_provider_error_message(raw, "m"))
