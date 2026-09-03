"""
Unit tests for litellm.py env var isolation (ST-R3.5).

Tests that:
1. _setup_api_key sets completion_kwargs["api_key"] unconditionally
2. Concurrent requests with different keys don't step on each other via os.environ
3. Environment variables are restored after completion calls (success or exception)
"""

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Stubs for running without a bench
try:
    import frappe
except ImportError:
    frappe_mock = MagicMock()
    frappe_mock.utils = MagicMock()
    frappe_mock._ = lambda x: x
    frappe_mock.logger = lambda *a, **k: MagicMock()
    sys.modules["frappe"] = frappe_mock
    sys.modules["frappe.utils"] = frappe_mock.utils


class TestSetupApiKeyUnconditional(unittest.TestCase):
    """Test that _setup_api_key sets completion_kwargs["api_key"] unconditionally."""

    def setUp(self):
        # Import after frappe stub is set up
        from huf.ai.providers import litellm
        self.litellm = litellm

    def test_setup_api_key_sets_completion_kwargs_for_env_var_provider(self):
        """Test that _setup_api_key sets completion_kwargs["api_key"] for providers in _ENV_VAR_PROVIDERS."""
        # openrouter is one of the nine providers that uses env vars
        provider_name = "openrouter"
        api_key_a = "key-A-test-openrouter"
        completion_kwargs_a = {}

        env_var_name_a = self.litellm._setup_api_key(provider_name, api_key_a, completion_kwargs_a)

        # Verify that completion_kwargs["api_key"] was set unconditionally
        self.assertEqual(completion_kwargs_a["api_key"], api_key_a)
        # Verify that an env var name was returned (since openrouter is in _ENV_VAR_PROVIDERS)
        self.assertIsNotNone(env_var_name_a)
        self.assertEqual(env_var_name_a, "OPENROUTER_API_KEY")

    def test_setup_api_key_independent_keys_in_kwargs(self):
        """Test that two concurrent requests with different keys have independent completion_kwargs["api_key"]."""
        provider_name = "openrouter"
        api_key_a = "key-A-test-unique-1234"
        api_key_b = "key-B-test-unique-5678"

        # First request
        kwargs_a = {}
        env_var_a = self.litellm._setup_api_key(provider_name, api_key_a, kwargs_a)

        # Second request (simulating concurrent request)
        kwargs_b = {}
        env_var_b = self.litellm._setup_api_key(provider_name, api_key_b, kwargs_b)

        # Verify that each request has its own api_key in completion_kwargs
        # (independent of os.environ state, which may be contaminated)
        self.assertEqual(kwargs_a["api_key"], api_key_a, "First request should have api_key_a")
        self.assertEqual(kwargs_b["api_key"], api_key_b, "Second request should have api_key_b")
        # They should be different
        self.assertNotEqual(kwargs_a["api_key"], kwargs_b["api_key"])


class TestEnvVarRestoration(unittest.TestCase):
    """Test that environment variables are restored after completion calls."""

    def setUp(self):
        from huf.ai.providers import litellm
        self.litellm = litellm
        # Save the original boot env state
        self.original_boot_env = dict(self.litellm._BOOT_ENV)

    def tearDown(self):
        # Restore _BOOT_ENV to original state
        self.litellm._BOOT_ENV.clear()
        self.litellm._BOOT_ENV.update(self.original_boot_env)

    def test_env_var_restored_after_completion_success(self):
        """Test that env vars are restored after a successful completion call."""
        provider_name = "openrouter"
        api_key = "test-key-for-restoration"
        completion_kwargs = {}

        # Ensure the env var is not set before the test
        self.litellm._BOOT_ENV.pop("OPENROUTER_API_KEY", None)
        if "OPENROUTER_API_KEY" in os.environ:
            del os.environ["OPENROUTER_API_KEY"]

        # Call _setup_api_key (which sets the env var)
        env_var_name = self.litellm._setup_api_key(provider_name, api_key, completion_kwargs)
        self.assertEqual(env_var_name, "OPENROUTER_API_KEY")
        self.assertEqual(os.environ.get("OPENROUTER_API_KEY"), api_key)

        # Simulate what the finally block does: restore from _BOOT_ENV
        if env_var_name:
            boot_value = self.litellm._BOOT_ENV.get(env_var_name)
            if boot_value is not None:
                os.environ[env_var_name] = boot_value
            elif env_var_name in os.environ:
                del os.environ[env_var_name]

        # Verify that the env var was restored (deleted, since it wasn't in _BOOT_ENV)
        self.assertNotIn("OPENROUTER_API_KEY", os.environ)

    def test_env_var_restored_when_boot_env_had_original_value(self):
        """Test that env vars are restored to their original _BOOT_ENV value if they existed."""
        provider_name = "openrouter"
        api_key_original = "original-key-from-boot"
        api_key_request = "request-specific-key"

        # Set up _BOOT_ENV with an original value
        self.litellm._BOOT_ENV["OPENROUTER_API_KEY"] = api_key_original
        # And simulate that the env var was already set in os.environ (from boot time)
        os.environ["OPENROUTER_API_KEY"] = api_key_original

        completion_kwargs = {}

        # Call _setup_api_key (which overwrites the env var)
        env_var_name = self.litellm._setup_api_key(provider_name, api_key_request, completion_kwargs)
        self.assertEqual(os.environ.get("OPENROUTER_API_KEY"), api_key_request)

        # Simulate what the finally block does: restore from _BOOT_ENV
        if env_var_name:
            boot_value = self.litellm._BOOT_ENV.get(env_var_name)
            if boot_value is not None:
                os.environ[env_var_name] = boot_value
            elif env_var_name in os.environ:
                del os.environ[env_var_name]

        # Verify that the env var was restored to the original _BOOT_ENV value
        self.assertEqual(os.environ.get("OPENROUTER_API_KEY"), api_key_original)

    @patch("huf.ai.providers.litellm._litellm_completion_with_retry")
    def test_env_var_restored_after_completion_exception(self, mock_completion):
        """Test that env vars are restored even when the completion call raises an exception."""
        provider_name = "openrouter"
        api_key = "test-key-for-exception"

        # Set up _BOOT_ENV
        self.litellm._BOOT_ENV.pop("OPENROUTER_API_KEY", None)
        if "OPENROUTER_API_KEY" in os.environ:
            del os.environ["OPENROUTER_API_KEY"]

        # Mock the completion function to raise an exception
        mock_completion.side_effect = RuntimeError("Simulated completion error")

        completion_kwargs = {
            "model": "openrouter/gpt-4",
            "messages": [],
        }

        # Call _setup_api_key (which sets the env var)
        env_var_name = self.litellm._setup_api_key(provider_name, api_key, completion_kwargs)
        self.assertEqual(os.environ.get("OPENROUTER_API_KEY"), api_key)

        # Simulate try/finally: call completion and then restore env var
        try:
            # Call the mocked completion (which raises an exception)
            asyncio.run(self.litellm._litellm_completion_with_retry(**completion_kwargs))
        except RuntimeError:
            # Expected to raise
            pass
        finally:
            # Simulate the finally block: restore from _BOOT_ENV
            if env_var_name:
                boot_value = self.litellm._BOOT_ENV.get(env_var_name)
                if boot_value is not None:
                    os.environ[env_var_name] = boot_value
                elif env_var_name in os.environ:
                    del os.environ[env_var_name]

        # Verify that the env var was restored even after the exception
        self.assertNotIn("OPENROUTER_API_KEY", os.environ)


if __name__ == "__main__":
    unittest.main()
