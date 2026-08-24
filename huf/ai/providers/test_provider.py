# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Deterministic HUF Test Provider.

INTEGRATION POINT (corrected — read this before relying on the old fallback
description below): this module is invoked from INSIDE
`huf.ai.providers.litellm.run()` itself, near the very top of that coroutine
body, before any `frappe.get_doc`/network/LLM-SDK code runs:

    if provider and provider.lower() == "test_provider":
        from huf.ai.providers import test_provider as _test_provider
        return await _test_provider.run(agent, enhanced_prompt, provider, model, context=context)

Why not the `huf.ai.run.RunProvider.run()` custom-provider fallback branch
(`frappe.get_module(f"huf.ai.providers.{provider.lower()}")`), which this
module used to document as its integration point? Because
`huf.ai.providers.litellm.run()` is `async def`. Calling it —
`litellm.run(agent, enhanced_prompt, provider, model, context=context)` in
`RunProvider.run()` — does NOT execute its body or raise any exception from
inside that body; it only constructs and returns a coroutine object. The
actual execution (and any real litellm exception) happens later, when that
coroutine is awaited by the real caller in
`huf/ai/agent_integration.py:1620` (`await RunProvider.run(...)`) — which is
AFTER `RunProvider.run()`'s own `try/except` around `litellm.run(...)` has
already returned. So in a real Agent Run, that except block can only ever
fire on a synchronous failure to *construct* the coroutine (e.g. wrong
argument count/types) — never on a real litellm execution failure (network
error, bad provider, etc.). Routing the test provider through that fallback
branch would only ever be reachable by forcibly mocking `litellm.run` to
raise synchronously, which does not simulate anything a real Agent Run can
produce. Routing inside `litellm.run()` itself, before any real work happens,
guarantees this module is reached on the exact same code path (the same
coroutine, awaited by the same real caller) that a real provider call takes.

`huf.ai.run.RunProvider.run()`'s custom-provider fallback branch
(`frappe.get_module(f"huf.ai.providers.{provider.lower()}")`) is otherwise
unused on `develop` today: no `AI Provider` seed/test record uses a provider
name that would reach it (all routing goes through
`huf.ai.providers.litellm`; the standalone `openai.py`/`anthropic.py`/
`google.py`/`openrouter.py` provider modules are legacy files superseded by
`litellm.py`'s docstring — "Replaces: openai.py, anthropic.py, google.py,
openrouter.py" — and are not wired to any current provider config). We did
not change that fallback branch or its missing-`await` behavior in
`huf/ai/run.py`; this is a pre-existing latent issue in product code, called
out here rather than silently fixed, since fixing it is out of scope for
adding a test provider and touches real request-routing behavior.

To exercise this provider through the real routing path in tests, set the
`AI Provider` document's name (the `provider` argument routed all the way
from `RunProvider.run()` into `litellm.run()`) to something whose `.lower()`
is "test_provider" (e.g. `Test_Provider`).

Return contract (matches `huf.ai.providers.litellm.SimpleResult`, see
`huf/ai/providers/litellm.py:54-60` and the docstring on `litellm.run()` at
`huf/ai/providers/litellm.py:578-582`):

    result.final_output   -> str, the assistant's final text content
    result.usage           -> dict with at least "input_tokens"/"output_tokens"
                              keys (read via `usage.get("input_tokens", 0)` /
                              `usage.get("output_tokens", 0)` in
                              `agent_integration.py` around line 1791-1792)
    result.new_items        -> list of `SimpleNamespace` items with a `.type`
                              of "tool_call_item" / "tool_call_output_item",
                              consumed by the tool-call-loop persistence code
                              in `agent_integration.py` (~line 1620-1780).
                              TEST_TEXT never emits tool calls, so this is [].
    result.cost             -> float, read via `getattr(result, "cost", 0)`
                              in `agent_integration.py:1782`.

Triggering mechanism
---------------------
A scenario is selected by embedding an explicit, unambiguous marker anywhere
in `enhanced_prompt`:

    __TEST_SCENARIO__:TEST_TEXT

We search the whole prompt (not just a fixed prefix) because
`agent_integration.py::_execute_agent_run` wraps the raw user prompt inside a
larger "Current user message:\n{prompt}\n" template (and may prepend RAG/
knowledge-context text) before calling `RunProvider.run()` — so a caller who
sets `prompt = "__TEST_SCENARIO__:TEST_TEXT hello"` gets a marker that is no
longer literally at index 0 of `enhanced_prompt`, and a scan is required to be
robust to that wrapping/prefixing.

We rejected two alternatives:

  - Keying off `agent.name` (or a dedicated Agent field): this would require
    a schema change to the `Agent` doctype (a new field / a reserved test
    agent name) purely to support tests, entangling test-only concerns with
    production schema. It is also less explicit at the call site — a reader
    of a test has to go look up which agent name means what, instead of
    seeing the scenario name inline in the prompt under test.
  - A marker required to be a strict *prefix*: brittle, because
    `enhanced_prompt` is always constructed by wrapping the caller's raw
    `prompt` (see above), so nothing this module receives is ever a bare,
    unwrapped string in production code paths.

Adding new scenarios (`TEST_TOOL_SINGLE`, `TEST_TOOL_MULTI`, etc.) later is a
matter of adding another `_SCENARIO_HANDLERS` entry below — the extraction
mechanism (`_extract_scenario`) does not change.
"""

import re
from types import SimpleNamespace

_SCENARIO_MARKER_RE = re.compile(r"__TEST_SCENARIO__:([A-Za-z0-9_]+)")

# Fixed, deterministic token counts for the TEST_TEXT scenario. Chosen to be
# realistic-shaped (nonzero, plausible magnitude) without depending on any
# real tokenizer, so results are 100% reproducible across runs/machines.
_TEST_TEXT_INPUT_TOKENS = 10
_TEST_TEXT_OUTPUT_TOKENS = 8

_TEST_TEXT_RESPONSE = "This is a deterministic TEST_TEXT response from the HUF test provider."


class UnknownTestScenarioError(Exception):
    """Raised when the prompt does not carry a recognized __TEST_SCENARIO__ marker."""


def _extract_scenario(enhanced_prompt):
    """Find the `__TEST_SCENARIO__:<NAME>` marker anywhere in the prompt.

    Returns the scenario name (e.g. "TEST_TEXT") or None if no marker is present.
    """
    if not enhanced_prompt:
        return None
    match = _SCENARIO_MARKER_RE.search(enhanced_prompt)
    return match.group(1) if match else None


def _run_test_text(agent, enhanced_prompt, provider, model, context=None):
    """TEST_TEXT scenario: a fixed assistant text reply, zero-cost, no tool calls."""
    usage = {
        "input_tokens": _TEST_TEXT_INPUT_TOKENS,
        "output_tokens": _TEST_TEXT_OUTPUT_TOKENS,
        "cached_tokens": 0,
        "cache_creation_tokens": 0,
        "cache_miss_tokens": 0,
        "cache_skipped_unsupported_model": False,
    }
    return SimpleNamespace(
        final_output=_TEST_TEXT_RESPONSE,
        usage=usage,
        new_items=[],
        cost=0.0,
    )


# Scenario name -> handler. Handlers share the exact signature of `run()`.
_SCENARIO_HANDLERS = {
    "TEST_TEXT": _run_test_text,
}


async def run(agent, enhanced_prompt, provider, model, context=None):
    """Deterministic stand-in for `huf.ai.providers.litellm.run()`.

    Invoked from inside `huf.ai.providers.litellm.run()` itself (see the
    `provider.lower() == "test_provider"` check near the top of that
    coroutine), and `return await test_provider.run(...)`-ed from there, so
    it is awaited by the same real call site that awaits a real litellm
    call: `await RunProvider.run(...)` in
    `huf/ai/agent_integration.py:1620`. See this module's top-level
    docstring for why this is the correct integration point instead of the
    `huf.ai.run.RunProvider.run()` custom-provider fallback branch.

    No network calls, no `frappe.get_doc`/DB access, no LLM SDK usage.
    """
    scenario = _extract_scenario(enhanced_prompt)
    if scenario is None:
        raise UnknownTestScenarioError(
            "huf.ai.providers.test_provider.run() requires a "
            "'__TEST_SCENARIO__:<NAME>' marker somewhere in enhanced_prompt; "
            "none was found."
        )

    handler = _SCENARIO_HANDLERS.get(scenario)
    if handler is None:
        raise UnknownTestScenarioError(
            f"Unknown test scenario '{scenario}'. Known scenarios: "
            f"{sorted(_SCENARIO_HANDLERS)}"
        )

    return handler(agent, enhanced_prompt, provider, model, context=context)
