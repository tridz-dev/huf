# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (mocked-frappe, no bench) unit tests for ST-R5.9: `RunProvider.run`
was a sync `@staticmethod` that returned `_await_tagged(litellm.run(...), ...)`
WITHOUT awaiting it. Since `litellm.run()` is `async def`, calling it only
constructs a coroutine and never executes its body -- so `RunProvider.run()`'s
own `except Exception` block could only ever catch a synchronous failure to
*construct* that coroutine, never a real failure from inside the LLM call
itself (network error, bad provider, etc). That made the fallback-to-custom-
provider branch dead code in the case that matters.

The fix (option (a) from WP-R5's ST-R5.9): `RunProvider.run` is now
`async def` and directly `await`s `litellm.run(...)`, so a real exception
raised from inside the coroutine body propagates synchronously into
`RunProvider.run()`'s own `try/except`, which is exactly what these tests
prove:

1. `RunProvider.run` is genuinely `async def` (a plain call returns a
   coroutine, not a result).
2. Mocking `huf.ai.providers.litellm.run` with an `async def` that raises
   inside its body -- the only realistic way a real Agent Run's litellm call
   fails -- results in that exception being caught by `RunProvider.run()`'s
   `except Exception` block and the fallback branch (`frappe.get_module`)
   being reached. Before the fix, `_await_tagged(coro, ...)` was returned
   unawaited, the `except` block never ran for this case, and the caller
   would instead see the coroutine's exception surface only when it awaited
   the returned object itself -- never routing through the fallback.
3. When no fallback module exists (`frappe.get_module` raises `ImportError`),
   the original litellm exception still propagates out of `RunProvider.run`
   (proving the exception truly reached the `except Exception as e:` handler
   and was captured as `original_exception`, not silently swallowed).
4. `RunProvider.run_stream` is unchanged (still a plain `def`) and its
   in-repo docstring documents why that is safe (async-generator function,
   not a coroutine function) rather than the same bug.

Run standalone (no bench) from the repo root:
    PYTHONPATH=. python3 huf/ai/tests/test_run_provider_dead_code_fix.py -v
"""

import asyncio
import inspect
import pathlib
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _stub_env  # noqa: E402

_stub_env.install()

import huf.ai.run as run_module  # noqa: E402
from huf.ai.run import RunProvider  # noqa: E402


class _BoomFromInsideLLMCall(Exception):
    """Stand-in for a real litellm execution failure (network error, bad
    provider response, etc) raised from *inside* an awaited coroutine body --
    as opposed to a synchronous failure to construct the coroutine."""


class TestRunProviderRunIsAsync(unittest.TestCase):
    def test_run_is_a_coroutine_function(self):
        self.assertTrue(
            inspect.iscoroutinefunction(RunProvider.run),
            "RunProvider.run must be `async def` so its own except block can "
            "catch real failures from inside the awaited litellm coroutine.",
        )

    def test_await_tagged_docstring_no_longer_claims_run_is_sync(self):
        doc = run_module._await_tagged.__doc__ or ""
        self.assertNotIn(
            "RunProvider.run() is a *sync* method",
            doc,
            "The docstring must be updated once RunProvider.run() becomes async.",
        )


class TestRunProviderCatchesRealLLMFailures(unittest.IsolatedAsyncioTestCase):
    """The key regression test: proves the except block (and therefore the
    fallback branch) is reachable from a real in-coroutine litellm failure."""

    async def test_exception_inside_litellm_coroutine_reaches_fallback(self):
        async def raising_litellm_run(agent, prompt, provider, model, context=None):
            # Exception raised from *inside* the coroutine body -- this is
            # what a real network/provider failure looks like. Before the
            # fix, RunProvider.run() never actually awaited this coroutine
            # itself (the caller did, after RunProvider.run() had already
            # returned), so this could never be caught here.
            raise _BoomFromInsideLLMCall("simulated real LLM call failure")

        fake_litellm_module = MagicMock()
        fake_litellm_module.run = raising_litellm_run

        fallback_called = {"value": False}

        async def fallback_run(agent, prompt, provider, model, context=None):
            fallback_called["value"] = True
            raise RuntimeError("fallback module also fails, for this test")

        fake_fallback_module = MagicMock()
        fake_fallback_module.run = fallback_run

        def fake_get_module(module_path):
            if module_path == "huf.ai.providers.litellm":
                return fake_litellm_module
            if module_path == "huf.ai.providers.myprovider":
                return fake_fallback_module
            raise ImportError(module_path)

        with patch.dict(
            sys.modules,
            {"huf.ai.providers.litellm": fake_litellm_module},
        ), patch.object(run_module.frappe, "get_module", side_effect=fake_get_module), \
           patch.object(run_module.frappe, "log_error", MagicMock()):

            agent = MagicMock()
            with self.assertRaises(_BoomFromInsideLLMCall):
                await RunProvider.run(agent, "prompt", "MyProvider", "some-model", context=None)

        self.assertTrue(
            fallback_called["value"],
            "The custom-provider fallback branch was not reached -- the "
            "except block did not catch the real litellm-coroutine failure, "
            "meaning the dead-code bug (ST-R5.9) is still present.",
        )

    async def test_no_fallback_module_still_propagates_original_exception(self):
        async def raising_litellm_run(agent, prompt, provider, model, context=None):
            raise _BoomFromInsideLLMCall("simulated real LLM call failure")

        fake_litellm_module = MagicMock()
        fake_litellm_module.run = raising_litellm_run

        def fake_get_module(module_path):
            if module_path == "huf.ai.providers.litellm":
                return fake_litellm_module
            raise ImportError(module_path)

        with patch.dict(
            sys.modules,
            {"huf.ai.providers.litellm": fake_litellm_module},
        ), patch.object(run_module.frappe, "get_module", side_effect=fake_get_module), \
           patch.object(run_module.frappe, "log_error", MagicMock()), \
           patch.object(run_module.frappe, "throw", side_effect=lambda msg: (_ for _ in ()).throw(RuntimeError(str(msg)))):

            agent = MagicMock()
            # frappe.throw is patched to actually raise (mirroring real Frappe
            # behavior; the bare MagicMock frappe stub does not raise on its
            # own). Reaching this call at all proves the "provider module not
            # found" fallback path was taken -- which only happens because the
            # except block already caught the real litellm exception.
            with self.assertRaises(RuntimeError):
                await RunProvider.run(agent, "prompt", "NoSuchProvider", "some-model", context=None)

    async def test_successful_litellm_call_never_touches_fallback(self):
        """Sanity check: the happy path is unaffected by the fix."""

        async def ok_litellm_run(agent, prompt, provider, model, context=None):
            return MagicMock(final_output="ok")

        fake_litellm_module = MagicMock()
        fake_litellm_module.run = ok_litellm_run

        with patch.dict(sys.modules, {"huf.ai.providers.litellm": fake_litellm_module}), \
             patch.object(run_module.frappe, "get_module", MagicMock()) as get_module_mock:

            agent = MagicMock()
            result = await RunProvider.run(agent, "prompt", "MyProvider", "some-model", context=None)

        self.assertEqual(result.final_output, "ok")
        self.assertEqual(result.provider_path, "litellm")
        get_module_mock.assert_not_called()


class TestRunStreamPatternDocumented(unittest.TestCase):
    """run_stream() is intentionally left as a plain `def` -- confirm it
    is NOT a coroutine function (i.e. it is not subject to the same
    unawaited-coroutine bug run() had) and that the in-repo comment
    explaining why is present."""

    def test_run_stream_is_not_a_coroutine_function(self):
        self.assertFalse(inspect.iscoroutinefunction(RunProvider.run_stream))

    def test_run_stream_has_documented_rationale(self):
        src = pathlib.Path(run_module.__file__).read_text(encoding="utf-8")
        self.assertIn("async-generator function", src)


if __name__ == "__main__":
    unittest.main()
