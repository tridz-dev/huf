# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (mocked-frappe, no bench) unit tests for ST-R5.8: exponential backoff
on litellm RateLimitError (429) and 5xx server errors.

Covers:
- `_compute_rate_limit_backoff_delay()`: starts at 1s, doubles each attempt,
  caps at 60s, and prefers a `Retry-After` header (capped at 60s) when one is
  present on the exception.
- `_extract_retry_after_seconds()`: reads `Retry-After` off `exc.response.headers`
  (the shape litellm's provider exceptions typically carry) case-insensitively,
  and returns `None` when there is nothing to read.
- `_retry_after_rate_limit_or_5xx()`: retries via `_litellm_completion_with_retry`
  with backoff sleeps in between, succeeds once the mocked call stops raising,
  and re-raises the last exception once `_RATE_LIMIT_MAX_ATTEMPTS` (5) attempts
  are exhausted -- covering both `RateLimitError` and `InternalServerError`
  (5xx) as the triggering/retried exception type.

Run standalone (no bench) from the repo root:
    PYTHONPATH=. python3 huf/ai/tests/test_litellm_rate_limit_backoff.py -v
"""

import asyncio
import pathlib
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _stub_env  # noqa: E402

_stub_env.install()

from huf.ai.providers import litellm as litellm_module  # noqa: E402

RateLimitError = litellm_module.RateLimitError
InternalServerError = litellm_module.InternalServerError


def _exc_with_retry_after(exc_cls, seconds, header_name="Retry-After"):
    exc = exc_cls("rate limited")
    response = MagicMock()
    response.headers = {header_name: str(seconds)}
    exc.response = response
    return exc


class TestComputeBackoffDelay(unittest.TestCase):
    def test_doubles_from_one_second(self):
        exc = RateLimitError("rate limited")
        self.assertEqual(litellm_module._compute_rate_limit_backoff_delay(0, exc), 1)
        self.assertEqual(litellm_module._compute_rate_limit_backoff_delay(1, exc), 2)
        self.assertEqual(litellm_module._compute_rate_limit_backoff_delay(2, exc), 4)
        self.assertEqual(litellm_module._compute_rate_limit_backoff_delay(3, exc), 8)

    def test_caps_at_sixty_seconds(self):
        exc = RateLimitError("rate limited")
        # attempt index high enough that 2**attempt would blow well past 60
        self.assertEqual(litellm_module._compute_rate_limit_backoff_delay(10, exc), 60)

    def test_retry_after_header_honored(self):
        exc = _exc_with_retry_after(RateLimitError, 5)
        self.assertEqual(litellm_module._compute_rate_limit_backoff_delay(0, exc), 5)
        # Even on a later attempt, an explicit Retry-After wins over doubling.
        self.assertEqual(litellm_module._compute_rate_limit_backoff_delay(3, exc), 5)

    def test_retry_after_header_capped_at_sixty(self):
        exc = _exc_with_retry_after(RateLimitError, 500)
        self.assertEqual(litellm_module._compute_rate_limit_backoff_delay(0, exc), 60)


class TestExtractRetryAfterSeconds(unittest.TestCase):
    def test_reads_from_response_headers(self):
        exc = _exc_with_retry_after(RateLimitError, 30)
        self.assertEqual(litellm_module._extract_retry_after_seconds(exc), 30.0)

    def test_case_insensitive_header_name(self):
        exc = _exc_with_retry_after(RateLimitError, 12, header_name="retry-after")
        self.assertEqual(litellm_module._extract_retry_after_seconds(exc), 12.0)

    def test_returns_none_when_absent(self):
        exc = RateLimitError("rate limited")
        self.assertIsNone(litellm_module._extract_retry_after_seconds(exc))

    def test_returns_none_when_header_value_is_garbage(self):
        exc = _exc_with_retry_after(RateLimitError, "not-a-number")
        self.assertIsNone(litellm_module._extract_retry_after_seconds(exc))


class TestRetryAfterRateLimitOr5xx(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Never actually sleep in tests.
        self._sleep_patcher = patch("asyncio.sleep", new=AsyncMock(return_value=None))
        self._sleep_patcher.start()
        self.addAsyncCleanup(self._sleep_patcher.stop)

    async def test_succeeds_after_transient_rate_limit(self):
        calls = {"n": 0}

        async def flaky_completion(**kwargs):
            calls["n"] += 1
            if calls["n"] < 3:
                raise RateLimitError("rate limited")
            return "final-response"

        with patch.object(litellm_module, "_litellm_completion_with_retry", side_effect=flaky_completion):
            result = await litellm_module._retry_after_rate_limit_or_5xx(
                {"model": "gpt-4o-mini"}, RateLimitError("rate limited")
            )

        self.assertEqual(result, "final-response")
        # Two retries were needed beyond the exception that triggered the call.
        self.assertEqual(calls["n"], 3)

    async def test_retries_5xx_server_errors_too(self):
        calls = {"n": 0}

        async def flaky_completion(**kwargs):
            calls["n"] += 1
            if calls["n"] < 2:
                raise InternalServerError("server error")
            return "final-response"

        with patch.object(litellm_module, "_litellm_completion_with_retry", side_effect=flaky_completion):
            result = await litellm_module._retry_after_rate_limit_or_5xx(
                {"model": "gpt-4o-mini"}, InternalServerError("server error")
            )

        self.assertEqual(result, "final-response")
        self.assertEqual(calls["n"], 2)

    async def test_retry_after_header_is_honored_during_retries(self):
        seen_delays = []

        async def capture_sleep(delay):
            seen_delays.append(delay)

        async def flaky_completion(**kwargs):
            if len(seen_delays) < 1:
                raise _exc_with_retry_after(RateLimitError, 7)
            return "final-response"

        with patch("asyncio.sleep", new=capture_sleep), \
             patch.object(litellm_module, "_litellm_completion_with_retry", side_effect=flaky_completion):
            result = await litellm_module._retry_after_rate_limit_or_5xx(
                {"model": "gpt-4o-mini"}, _exc_with_retry_after(RateLimitError, 7)
            )

        self.assertEqual(result, "final-response")
        self.assertIn(7, seen_delays)

    async def test_exhausts_attempts_then_reraises(self):
        calls = {"n": 0}

        async def always_fails(**kwargs):
            calls["n"] += 1
            raise RateLimitError(f"rate limited attempt {calls['n']}")

        first_exc = RateLimitError("rate limited attempt 0")
        with patch.object(litellm_module, "_litellm_completion_with_retry", side_effect=always_fails):
            with self.assertRaises(RateLimitError):
                await litellm_module._retry_after_rate_limit_or_5xx({"model": "gpt-4o-mini"}, first_exc)

        # first_exc counts as attempt 1 of _RATE_LIMIT_MAX_ATTEMPTS (5); the
        # helper performs the remaining 4 attempts itself before giving up.
        self.assertEqual(calls["n"], litellm_module._RATE_LIMIT_MAX_ATTEMPTS - 1)

    async def test_max_attempts_is_five(self):
        self.assertEqual(litellm_module._RATE_LIMIT_MAX_ATTEMPTS, 5)


if __name__ == "__main__":
    unittest.main()
