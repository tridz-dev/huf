# Copyright (c) 2025, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""
Contract tests for provider failure surfacing (P0) and local-LLM routing (P1/P2).

Covers:
- run() raises ProviderUnavailableError on connection-type provider failures
  instead of returning the error text as a successful SimpleResult.
- run() retries an empty response once, then raises ProviderUnavailableError
  instead of returning an empty final_output.
- _resolve_api_base precedence: api_base_url field > url+port > None.
- _normalize_model_name maps ollama -> ollama_chat/ and lmstudio -> openai/.
- _is_transient_litellm_error treats connection refused / failed to connect
  as transient (retryable).

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_provider_error_contract
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from huf.ai.providers import litellm as litellm_module
from huf.ai.providers.litellm import (
    ProviderUnavailableError,
    _is_transient_litellm_error,
    _normalize_model_name,
    _resolve_api_base,
    run,
)


class _FakeDoc:
    def __init__(self, **fields):
        for k, v in fields.items():
            setattr(self, k, v)

    def get_password(self, field):
        return getattr(self, field, None)

    def get(self, field, default=None):
        return getattr(self, field, default)


def _make_agent():
    return SimpleNamespace(
        instructions="You are a test agent.",
        tools=[],
        max_turns=1,
    )


def _make_provider_doc(**overrides):
    fields = {
        "provider_name": "Ollama",
        "api_key": "dummy-key",
        "is_local_llm": 1,
        "api_base_url": "http://localhost:11434",
    }
    fields.update(overrides)
    return _FakeDoc(**fields)


def _run_patches(provider_doc, completion_mock):
    """Common patches that keep run() hermetic (no DB, no network, no tokenizers)."""
    return [
        patch.object(litellm_module.litellm, "completion", completion_mock),
        patch("huf.ai.providers.litellm.frappe.get_doc", return_value=provider_doc),
        patch("huf.ai.providers.litellm.frappe.log_error"),
        patch("huf.ai.local_runtime.build_local_overrides", return_value={}),
    ]


class TestProviderFailureContract(FrappeTestCase):
    """Provider failures must raise, never be returned as a successful SimpleResult."""

    def test_connection_error_raises_provider_unavailable(self):
        from unittest.mock import MagicMock

        provider_doc = _make_provider_doc()
        completion_mock = MagicMock(side_effect=ConnectionError("Connection refused"))

        patches = _run_patches(provider_doc, completion_mock)
        for p in patches:
            p.start()
        try:
            with self.assertRaises(ProviderUnavailableError) as ctx:
                asyncio.run(run(_make_agent(), "hello", "Ollama", "gpt-oss:20b", context={}))
        finally:
            for p in patches:
                p.stop()

        self.assertIn("gpt-oss:20b", str(ctx.exception))
        # "connection refused" is transient: 1 initial call + 2 retries.
        self.assertEqual(completion_mock.call_count, 3)

    def test_empty_response_retries_once_then_raises(self):
        from unittest.mock import MagicMock

        empty_response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=""))],
            usage=SimpleNamespace(
                prompt_tokens=1, completion_tokens=0, prompt_tokens_details=None
            ),
        )
        provider_doc = _make_provider_doc()
        completion_mock = MagicMock(return_value=empty_response)

        patches = _run_patches(provider_doc, completion_mock)
        for p in patches:
            p.start()
        try:
            with self.assertRaises(ProviderUnavailableError) as ctx:
                asyncio.run(run(_make_agent(), "hello", "Ollama", "gpt-oss:20b", context={}))
        finally:
            for p in patches:
                p.stop()

        # One retry of the empty completion, then a loud failure.
        self.assertEqual(completion_mock.call_count, 2)
        self.assertIn("empty response", str(ctx.exception))
        self.assertIn("ollama_chat/", str(ctx.exception))


class TestResolveApiBase(FrappeTestCase):
    def test_api_base_url_field_wins(self):
        doc = _FakeDoc(
            is_local_llm=1,
            api_base_url="http://host.docker.internal:11434",
            url="http://ignored",
            port=1234,
        )
        self.assertEqual(_resolve_api_base(doc), "http://host.docker.internal:11434")

    def test_url_and_port_joined(self):
        doc = _FakeDoc(is_local_llm=1, url="http://host.docker.internal", port=11434)
        self.assertEqual(_resolve_api_base(doc), "http://host.docker.internal:11434")

    def test_url_with_port_not_doubled(self):
        doc = _FakeDoc(is_local_llm=1, url="http://host.docker.internal:11434", port=11434)
        self.assertEqual(_resolve_api_base(doc), "http://host.docker.internal:11434")

    def test_not_local_returns_none(self):
        doc = _FakeDoc(is_local_llm=0, api_base_url="http://host.docker.internal:11434")
        self.assertIsNone(_resolve_api_base(doc))

    def test_local_without_any_url_returns_none(self):
        self.assertIsNone(_resolve_api_base(_FakeDoc(is_local_llm=1)))
        self.assertIsNone(_resolve_api_base(None))


class TestNormalizeModelName(FrappeTestCase):
    def test_ollama_maps_to_chat_endpoint(self):
        self.assertEqual(
            _normalize_model_name("gpt-oss:20b", "Ollama"), "ollama_chat/gpt-oss:20b"
        )
        self.assertEqual(
            _normalize_model_name("gemma4:latest", "ollama"), "ollama_chat/gemma4:latest"
        )

    def test_lmstudio_maps_to_openai_compatible(self):
        self.assertEqual(_normalize_model_name("qwen3", "lmstudio"), "openai/qwen3")

    def test_already_prefixed_names_pass_through(self):
        self.assertEqual(
            _normalize_model_name("ollama/gpt-oss:20b", "Ollama"), "ollama/gpt-oss:20b"
        )
        self.assertEqual(_normalize_model_name("openai/gpt-4o", "OpenAI"), "openai/gpt-4o")


class TestTransientRetryKeywords(FrappeTestCase):
    def test_connection_refused_is_transient(self):
        self.assertTrue(
            _is_transient_litellm_error(
                Exception("litellm.APIConnectionError: Connection refused")
            )
        )
        self.assertTrue(_is_transient_litellm_error(ConnectionRefusedError("Connection refused")))

    def test_failed_to_connect_is_transient(self):
        self.assertTrue(
            _is_transient_litellm_error(Exception("Failed to connect to Ollama at http://localhost:11434"))
        )

    def test_non_transient_errors_unchanged(self):
        self.assertFalse(_is_transient_litellm_error(Exception("invalid api key")))
        self.assertFalse(_is_transient_litellm_error(Exception("model not found")))
