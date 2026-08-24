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

Tool-call scenario contract (`TEST_TOOL_SINGLE` / `TEST_TOOL_MULTI`)
---------------------------------------------------------------------
Decision: **the provider both decides AND executes tool calls, and returns
the fully-resolved round-trip in `new_items`** — it does NOT return a
"please call this tool" instruction for some outer loop to execute.

This is not a simplification for testing purposes; it is what the real
contract actually is. Per `docs/testing/CURRENT_STATE.md` section 4
("Tool-calling framework"): "Execution is NOT via the OpenAI Agents SDK
Runner — HUF's own loop in `huf/ai/providers/litellm.py::run()` (~lines
700-1170)". Reading that loop directly confirms it: inside
`huf/ai/providers/litellm.py::run()`, the per-round loop (~lines 1086-1182)
calls `_find_tool(agent, tool_name)` and `await _execute_tool_call(...)`
*itself*, appends a `tool_call_item` SimpleNamespace (`raw_item=SimpleNamespace
(name=..., arguments=..., id=...)`) immediately followed by a
`tool_call_output_item` SimpleNamespace (`raw_item={"name":..., "output":...,
"id":...}`) to `all_new_items`, feeds the tool result back into `messages` as
a `role: tool` message, and only then makes the *next* round's completion
call. There is no signal in `SimpleResult`/`new_items` meaning "outer caller,
please go execute this" — by the time `litellm.run()` returns, every tool
call in `new_items` has already been executed and paired with its output.
`agent_integration.py`'s tool-call-loop persistence code (~1620-1780) only
*replays* `result.new_items` after the fact to write `Agent Tool Call` /
`Agent Message` (kind="Tool Call") audit rows — it does not invoke tools
itself.

Consequently, `TEST_TOOL_SINGLE`/`TEST_TOOL_MULTI` fabricate a fixed,
deterministic sequence of already-resolved tool_call_item/tool_call_output_item
pairs (referencing a made-up but realistic tool name/args/result), exactly
mirroring the shape `litellm.run()` would have produced for a real agent
whose model chose to call a real tool. There is no real `Agent Tool Function`
invocation here, and no need for one: by the time `agent_integration.py`
consumes `result.new_items`, a real run's tool has *already* been executed by
`litellm.run()` — so a scenario faking that pre-executed shape is faithful to
the contract, not a shortcut around it.

`TEST_PROVIDER_TIMEOUT`
------------------------
Raises `huf.ai.providers.litellm.ProviderUnavailableError` — the exact
exception class a real timeout surfaces as. In `litellm.run()`, any
completion-call exception not explicitly matched by `InternalServerError`/
`RateLimitError`/`ContextWindowExceededError`/`APIError` (a real
`litellm.Timeout`/`openai.APITimeoutError` included) falls through to the
generic `except Exception as e` handler (~line 979), which calls
`_raise_provider_unavailable(raw_msg, normalized_model)` — and that
constructs a `ProviderUnavailableError(public_message, log_message=raw_msg)`
(see `litellm.py:113-117`). This scenario raises that same class with the
same two-attribute shape (`public_message`, `log_message`) so error-handling
code downstream (which per `litellm.py:1191` re-raises `ProviderUnavailableError`
unchanged, unlike other exception types) is exercised identically to a real
provider timeout.
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

# --- TEST_TOOL_SINGLE / TEST_TOOL_MULTI fixtures -----------------------
# Fixed, made-up-but-realistic tool name/args/result. No real `Agent Tool
# Function` is invoked (see module docstring: the provider already returns
# fully-executed tool calls, matching what litellm.run() itself produces).
_TOOL_NAME = "get_weather"
_TOOL_ARGS = '{"city": "Bengaluru"}'
_TOOL_RESULT = '{"city": "Bengaluru", "condition": "Sunny", "temp_c": 29}'
_TOOL_CALL_ID_1 = "test-tool-call-1"
_TOOL_CALL_ID_2 = "test-tool-call-2"

_TOOL_NAME_2 = "get_forecast"
_TOOL_ARGS_2 = '{"city": "Bengaluru", "days": 3}'
_TOOL_RESULT_2 = '{"city": "Bengaluru", "forecast": ["Sunny", "Cloudy", "Sunny"]}'

_TEST_TOOL_SINGLE_INPUT_TOKENS = 20
_TEST_TOOL_SINGLE_OUTPUT_TOKENS = 15
_TEST_TOOL_SINGLE_RESPONSE = (
    "Based on the tool result, it is currently Sunny at 29C in Bengaluru."
)

_TEST_TOOL_MULTI_INPUT_TOKENS = 32
_TEST_TOOL_MULTI_OUTPUT_TOKENS = 24
_TEST_TOOL_MULTI_RESPONSE = (
    "Based on both tool results, it is currently Sunny at 29C in Bengaluru, "
    "with a 3-day forecast of Sunny, Cloudy, Sunny."
)

_TEST_TIMEOUT_MESSAGE = (
    "The AI provider could not complete this request for test-model. "
    "Please try again or choose a different model."
)
_TEST_TIMEOUT_LOG_MESSAGE = (
    "LiteLLM error for model 'test-model': Deterministic TEST_PROVIDER_TIMEOUT "
    "simulated timeout (Read timed out)."
)


def _tool_call_item(tool_name, tool_args, tool_call_id):
    """Mirror the exact shape `litellm.run()` appends for a decided tool call
    (see `litellm.py` ~line 1123-1128)."""
    return SimpleNamespace(
        type="tool_call_item",
        raw_item=SimpleNamespace(name=tool_name, arguments=tool_args, id=tool_call_id),
    )


def _tool_call_output_item(tool_name, output, tool_call_id):
    """Mirror the exact shape `litellm.run()` appends for an already-executed
    tool's result (see `litellm.py` ~line 1166-1171)."""
    return SimpleNamespace(
        type="tool_call_output_item",
        raw_item={"name": tool_name, "output": output, "id": tool_call_id},
    )


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


def _run_test_tool_single(agent, enhanced_prompt, provider, model, context=None):
    """TEST_TOOL_SINGLE scenario: one already-executed tool call round-trip,
    then a final text response referencing the tool result. See the module
    docstring's "Tool-call scenario contract" section for why `new_items`
    already contains the executed tool_call_item/tool_call_output_item pair
    (this is what `litellm.run()` itself would have produced by the time it
    returns, not an instruction for some outer loop to execute)."""
    usage = {
        "input_tokens": _TEST_TOOL_SINGLE_INPUT_TOKENS,
        "output_tokens": _TEST_TOOL_SINGLE_OUTPUT_TOKENS,
        "cached_tokens": 0,
        "cache_creation_tokens": 0,
        "cache_miss_tokens": 0,
        "cache_skipped_unsupported_model": False,
    }
    new_items = [
        _tool_call_item(_TOOL_NAME, _TOOL_ARGS, _TOOL_CALL_ID_1),
        _tool_call_output_item(_TOOL_NAME, _TOOL_RESULT, _TOOL_CALL_ID_1),
    ]
    return SimpleNamespace(
        final_output=_TEST_TOOL_SINGLE_RESPONSE,
        usage=usage,
        new_items=new_items,
        cost=0.0,
    )


def _run_test_tool_multi(agent, enhanced_prompt, provider, model, context=None):
    """TEST_TOOL_MULTI scenario: two sequential already-executed tool call
    round-trips (one agent turn, matching the real per-round loop in
    `litellm.run()` which keeps calling until a round with no tool_calls),
    then a final text response referencing both tool results."""
    usage = {
        "input_tokens": _TEST_TOOL_MULTI_INPUT_TOKENS,
        "output_tokens": _TEST_TOOL_MULTI_OUTPUT_TOKENS,
        "cached_tokens": 0,
        "cache_creation_tokens": 0,
        "cache_miss_tokens": 0,
        "cache_skipped_unsupported_model": False,
    }
    new_items = [
        _tool_call_item(_TOOL_NAME, _TOOL_ARGS, _TOOL_CALL_ID_1),
        _tool_call_output_item(_TOOL_NAME, _TOOL_RESULT, _TOOL_CALL_ID_1),
        _tool_call_item(_TOOL_NAME_2, _TOOL_ARGS_2, _TOOL_CALL_ID_2),
        _tool_call_output_item(_TOOL_NAME_2, _TOOL_RESULT_2, _TOOL_CALL_ID_2),
    ]
    return SimpleNamespace(
        final_output=_TEST_TOOL_MULTI_RESPONSE,
        usage=usage,
        new_items=new_items,
        cost=0.0,
    )


def _run_test_provider_timeout(agent, enhanced_prompt, provider, model, context=None):
    """TEST_PROVIDER_TIMEOUT scenario: raise the exact exception class/shape
    a real litellm timeout raises in `litellm.run()` — `ProviderUnavailableError`
    with a `public_message`/`log_message` pair (see `litellm.py:64-71,113-117`
    and this module's "TEST_PROVIDER_TIMEOUT" docstring section above).

    Imported lazily (not at module scope) to avoid any import-order coupling
    with `litellm.py`, which imports *this* module lazily from inside its own
    `run()` body.
    """
    from huf.ai.providers.litellm import ProviderUnavailableError

    raise ProviderUnavailableError(
        _TEST_TIMEOUT_MESSAGE,
        log_message=_TEST_TIMEOUT_LOG_MESSAGE,
    )


# Scenario name -> handler. Handlers share the exact signature of `run()`.
_SCENARIO_HANDLERS = {
    "TEST_TEXT": _run_test_text,
    "TEST_TOOL_SINGLE": _run_test_tool_single,
    "TEST_TOOL_MULTI": _run_test_tool_multi,
    "TEST_PROVIDER_TIMEOUT": _run_test_provider_timeout,
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
