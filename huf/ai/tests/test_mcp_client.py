# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (mocked-frappe, no bench) unit tests for:

- ST-R5.5: de-duplication of MCP tool names after sanitization/truncation
  in `huf.ai.mcp_client._create_mcp_function_tool` / `_dedupe_tool_name`.
- ST-R5.6: bounded exponential backoff for 429/5xx errors in
  `huf.ai.mcp_client.execute_with_mcp_session`, alongside the existing
  OAuth-401 retry behavior.

Run standalone (no bench) from the repo root:
    PYTHONPATH=. python3 huf/ai/tests/test_mcp_client.py -v
"""

import asyncio
import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _stub_env  # noqa: E402

_stub_env.install()

from huf.ai import mcp_client  # noqa: E402


def _make_mcp_server(name="MCP-1", server_name="Server One", tool_namespace=None, auth_type="none"):
    return SimpleNamespace(
        name=name,
        server_name=server_name,
        tool_namespace=tool_namespace,
        auth_type=auth_type,
    )


class TestDedupeToolName(unittest.TestCase):
    def test_no_collision_returns_name_unchanged(self):
        seen = set()
        self.assertEqual(mcp_client._dedupe_tool_name("my_tool", seen), "my_tool")
        self.assertIn("my_tool", seen)

    def test_collision_gets_numeric_suffix(self):
        seen = {"my_tool"}
        result = mcp_client._dedupe_tool_name("my_tool", seen)
        self.assertEqual(result, "my_tool_1")
        self.assertIn("my_tool_1", seen)

    def test_multiple_collisions_increment_suffix(self):
        seen = {"my_tool", "my_tool_1", "my_tool_2"}
        result = mcp_client._dedupe_tool_name("my_tool", seen)
        self.assertEqual(result, "my_tool_3")

    def test_dedup_respects_64_char_limit(self):
        base = "a" * 64
        seen = {base}
        result = mcp_client._dedupe_tool_name(base, seen)
        self.assertLessEqual(len(result), 64)
        self.assertEqual(result, ("a" * 62) + "_1")

    def test_dedup_respects_64_char_limit_with_double_digit_suffix(self):
        base = "b" * 64
        seen = {base} | {("b" * 62) + f"_{i}" for i in range(1, 10)}
        result = mcp_client._dedupe_tool_name(base, seen)
        self.assertLessEqual(len(result), 64)
        self.assertEqual(result, ("b" * 61) + "_10")

    def test_none_seen_set_is_noop(self):
        self.assertEqual(mcp_client._dedupe_tool_name("my_tool", None), "my_tool")

    def test_two_colliding_tool_defs_get_unique_suffixed_names(self):
        """Two MCP tools whose sanitized/truncated names collide (e.g. two
        long names that only differ after the 64-char truncation point) end
        up with `_1`/`_2` suffixes rather than one silently shadowing the
        other."""
        mcp_server = _make_mcp_server()
        seen_names = set()

        long_prefix = "x" * 70
        tool_def_a = {"name": f"{long_prefix}-a", "description": "Tool A", "parameters": {}}
        tool_def_b = {"name": f"{long_prefix}-b", "description": "Tool B", "parameters": {}}

        tool_a = mcp_client._create_mcp_function_tool(mcp_server, tool_def_a, seen_names)
        tool_b = mcp_client._create_mcp_function_tool(mcp_server, tool_def_b, seen_names)

        self.assertIsNotNone(tool_a)
        self.assertIsNotNone(tool_b)
        # Both truncate to the same 64-char prefix before dedup.
        self.assertNotEqual(tool_a.name, tool_b.name)
        self.assertTrue(tool_b.name.endswith("_1"))
        self.assertLessEqual(len(tool_a.name), 64)
        self.assertLessEqual(len(tool_b.name), 64)


class _RetryableError(Exception):
    """Mimics an httpx-style error carrying a status code and a response
    with headers, the shape `_has_status_code`/`_extract_retry_after_seconds`
    inspect."""

    def __init__(self, status_code, retry_after=None):
        super().__init__(f"Error code: {status_code} - upstream failure")
        headers = {"Retry-After": str(retry_after)} if retry_after is not None else {}
        self.response = SimpleNamespace(headers=headers, text="")


class TestExecuteWithMcpSessionBackoff(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(mcp_client, "_build_mcp_headers", return_value={})
        self.addCleanup(patcher.stop)
        patcher.start()

        evict_patcher = patch.object(mcp_client, "_evict_pooled_session")
        self.addCleanup(evict_patcher.stop)
        evict_patcher.start()

        sleep_patcher = patch.object(mcp_client.asyncio, "sleep", new=AsyncMock())
        self.addCleanup(sleep_patcher.stop)
        self.mock_sleep = sleep_patcher.start()

        frappe_patcher = patch.object(mcp_client, "frappe", MagicMock())
        self.addCleanup(frappe_patcher.stop)
        frappe_patcher.start()

    def _run(self, coro):
        return asyncio.run(coro)

    def test_429_then_success_retries_with_backoff(self):
        mcp_server = _make_mcp_server(auth_type="none")
        operation = MagicMock()
        do_execute = AsyncMock(side_effect=[_RetryableError(429), "ok"])

        with patch.object(mcp_client, "_do_execute_mcp_session", do_execute):
            result = self._run(mcp_client.execute_with_mcp_session(mcp_server, operation))

        self.assertEqual(result, "ok")
        self.assertEqual(do_execute.call_count, 2)
        self.mock_sleep.assert_awaited()

    def test_5xx_then_success_retries_with_backoff(self):
        mcp_server = _make_mcp_server(auth_type="none")
        operation = MagicMock()
        do_execute = AsyncMock(side_effect=[_RetryableError(503), "ok"])

        with patch.object(mcp_client, "_do_execute_mcp_session", do_execute):
            result = self._run(mcp_client.execute_with_mcp_session(mcp_server, operation))

        self.assertEqual(result, "ok")
        self.assertEqual(do_execute.call_count, 2)

    def test_retry_after_header_is_honored(self):
        mcp_server = _make_mcp_server(auth_type="none")
        operation = MagicMock()
        do_execute = AsyncMock(side_effect=[_RetryableError(429, retry_after=7), "ok"])

        with patch.object(mcp_client, "_do_execute_mcp_session", do_execute):
            self._run(mcp_client.execute_with_mcp_session(mcp_server, operation))

        self.mock_sleep.assert_awaited_once_with(7.0)

    def test_backoff_doubles_when_no_retry_after_header(self):
        mcp_server = _make_mcp_server(auth_type="none")
        operation = MagicMock()
        do_execute = AsyncMock(
            side_effect=[_RetryableError(500), _RetryableError(500), "ok"]
        )

        with patch.object(mcp_client, "_do_execute_mcp_session", do_execute):
            self._run(mcp_client.execute_with_mcp_session(mcp_server, operation))

        first_wait = self.mock_sleep.await_args_list[0].args[0]
        second_wait = self.mock_sleep.await_args_list[1].args[0]
        self.assertEqual(first_wait, 1)
        self.assertEqual(second_wait, 2)

    def test_exhausts_five_attempts_then_raises(self):
        mcp_server = _make_mcp_server(auth_type="none")
        operation = MagicMock()
        do_execute = AsyncMock(side_effect=[_RetryableError(429) for _ in range(5)])

        with patch.object(mcp_client, "_do_execute_mcp_session", do_execute):
            with self.assertRaises(Exception):
                self._run(mcp_client.execute_with_mcp_session(mcp_server, operation))

        self.assertEqual(do_execute.call_count, 5)

    def test_non_retryable_error_raises_immediately(self):
        mcp_server = _make_mcp_server(auth_type="none")
        operation = MagicMock()
        do_execute = AsyncMock(side_effect=[_RetryableError(400)])

        with patch.object(mcp_client, "_do_execute_mcp_session", do_execute):
            with self.assertRaises(Exception):
                self._run(mcp_client.execute_with_mcp_session(mcp_server, operation))

        self.assertEqual(do_execute.call_count, 1)
        self.mock_sleep.assert_not_awaited()

    def test_oauth_401_retry_still_works(self):
        mcp_server = _make_mcp_server(auth_type="oauth")
        operation = MagicMock()
        do_execute = AsyncMock(side_effect=[_RetryableError(401), "ok"])

        mcp_oauth_module = MagicMock()
        mcp_oauth_module.refresh_oauth_token = MagicMock()

        with patch.object(mcp_client, "_do_execute_mcp_session", do_execute), patch.dict(
            sys.modules, {"huf.ai.mcp_oauth": mcp_oauth_module}
        ):
            result = self._run(mcp_client.execute_with_mcp_session(mcp_server, operation))

        self.assertEqual(result, "ok")
        mcp_oauth_module.refresh_oauth_token.assert_called_once_with(mcp_server.name)
        self.assertEqual(do_execute.call_count, 2)
        # OAuth-401 handling is a single immediate retry, not the backoff path.
        self.mock_sleep.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
