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

Error scenarios (`TEST_PROVIDER_429` / `TEST_PROVIDER_400` /
`TEST_PROVIDER_401` / `TEST_PROVIDER_500`)
---------------------------------------------------------------------
Each mirrors a distinct real-world failure surfaced by `litellm.run()`'s own
error handling, not a single generic "provider failed" bucket:

  - `TEST_PROVIDER_429` (rate limit): in `litellm.run()`'s per-round
    `except RateLimitError as e:` clause (`litellm.py` ~line 959-968), a real
    429 is logged and then **re-raised unchanged** (`raise e`) — it is the
    one error class in that block that is *not* passed through
    `_raise_provider_unavailable`/wrapped in `ProviderUnavailableError`. The
    outer `except Exception as e:` boundary handler (~line 1195-1205)
    explicitly re-raises it too ("if... 'RateLimitError' in str(e): raise
    e") instead of converting it. So the real, final contract for a 429 is:
    callers see a bare `litellm.RateLimitError` propagate all the way out —
    this scenario raises exactly that (imported lazily from the `litellm`
    package, matching `TEST_PROVIDER_TIMEOUT`'s lazy-import pattern).

  - `TEST_PROVIDER_401` (invalid credentials): `_sanitize_provider_error_message`
    (`litellm.py` ~line 78-79) special-cases this: if the raw message
    contains "invalid api key" / "api key not configured" / "password not
    found", the sanitized `ProviderUnavailableError.public_message` becomes
    "This provider is not configured correctly yet. Add or update its API
    key and try again." This scenario raises `ProviderUnavailableError` with
    that exact public message, and a `log_message` containing "invalid api
    key" so the bucketing contract is unambiguous.

  - `TEST_PROVIDER_500` (generic server error): the explicit
    `except InternalServerError as e:` clause (`litellm.py` ~line 951-957)
    builds `raw_msg = f"OpenAI API server error with model '...'. This may
    be temporary. Details: {e}"` and calls `_raise_provider_unavailable`.
    `_sanitize_provider_error_message` (~line 95-107) matches "server
    error" and returns "The AI provider is temporarily unavailable. Please
    try again in a moment." This scenario raises `ProviderUnavailableError`
    with that exact public message.

  - `TEST_PROVIDER_400` (bad request / invalid input): a real `BadRequestError`
    that isn't a recognized tools/response_format capability conflict is
    re-raised as-is (`litellm.py` ~line 896-926, `else: raise e`), is not
    caught by any of the round loop's other named `except` clauses
    (`InternalServerError`/`RateLimitError`/`ContextWindowExceededError`/
    `APIError`), and so falls through to the generic
    `except Exception as e:` boundary handler (~line 979-988), which calls
    `_raise_provider_unavailable(raw_msg, normalized_model)`. Because a
    generic bad-request message matches none of `_sanitize_provider_error_message`'s
    specific buckets, it falls through to that function's final default
    (~line 109-110): "The AI provider could not complete this request for
    {model}. Please try again or choose a different model." — the exact
    same message shape `TEST_PROVIDER_TIMEOUT` also produces (both fall
    through to the identical default bucket; only their `log_message`
    differs). This scenario raises `ProviderUnavailableError` with that
    default-bucket public message.

`TEST_STRUCTURED_OUTPUT`
------------------------
Mirrors `litellm.run()`'s `response_format`-aware path: when
`context.get("response_format")` is set, it is passed straight through as
`completion_kwargs["response_format"]` (`litellm.py` ~line 812-813) — there is
no separate "structured output" result shape. The final result is built as
`SimpleResult(choice.content or "", total_usage, all_new_items,
cost=total_cost)` (`litellm.py` ~line 1082-1083): `final_output` is simply
whatever text the model returned, which — when `response_format` requested
JSON — happens to be a JSON-formatted string. This scenario returns a fixed,
valid JSON string as `final_output` (parseable via `json.loads`), matching
that contract exactly rather than inventing a `structured_output` field the
real code has no equivalent for.

`TEST_CACHED_USAGE`
--------------------
A `TEST_TEXT`-shaped scenario whose `usage` dict has nonzero cache-related
fields. The exact field names come directly from `litellm.run()`'s own
`total_usage` accounting (`litellm.py` ~line 1061-1063):

    total_usage["cached_tokens"] += (round_cached or 0)
    total_usage["cache_creation_tokens"] += (round_creation or 0)
    total_usage["cache_miss_tokens"] += (round_creation or 0)

(`round_cached` is read from a real completion response's
`usage.prompt_tokens_details.cached_tokens` / `.cache_hit_tokens`, see
`litellm.py` ~line 1022-1037.) This scenario sets `cached_tokens` to a
nonzero, deterministic value (simulating a cache hit) while leaving
`cache_creation_tokens`/`cache_miss_tokens` at 0, and reuses the same
`_TEST_TEXT_RESPONSE` text and `cost=0.0` as `TEST_TEXT`.

`TEST_STREAM_INTERRUPT` and the `run_stream` export
-----------------------------------------------------
`litellm.run()` and `litellm.run_stream()` are separate coroutine functions
with different shapes — `run()` returns a single `SimpleResult`; `run_stream()`
is an `async def` **generator** (contains `yield`) that yields dicts shaped
`{"type": "delta"/"reasoning"/"tool_call"/"complete"/"error", ...}` (see
`litellm.py` ~line 1338-1344 docstring and the actual yields at ~1648,
~1661-1665, ~2027-2033). A real mid-stream interruption (any exception raised
while iterating the provider's stream, e.g. a dropped connection) is caught by
`run_stream()`'s own outer `except Exception as e:` boundary handler
(`litellm.py` ~line 2038-2043), which does **not** re-raise — it yields one
final chunk `{"type": "error", "error": f"LiteLLM Streaming Error: {e}"}` and
the generator simply ends (implicit `return` after the `except` block; no
further chunks). Because `run()` and `run_stream()` are different callables,
this module needs its own `run_stream()` export (`litellm.py::run_stream()`'s
early `provider.lower() == "test_provider"` check delegates to it, re-yielding
every chunk, since `run_stream()`'s own early check can't `return await` a
generator function the way `run()`'s early check does) and its own
`_STREAM_SCENARIO_HANDLERS` dispatch table, kept separate from
`_SCENARIO_HANDLERS` because the two functions' return shapes (single result
vs. yielded chunks) are fundamentally different. `TEST_STREAM_INTERRUPT`
yields a couple of normal `delta` chunks, then yields exactly one
`{"type": "error", ...}` chunk with that same "LiteLLM Streaming Error: ..."
prefix and stops — never raising out of the generator, matching the real
contract precisely.

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

# --- TEST_PROVIDER_429 / _400 / _401 / _500 fixtures -------------------
# Public/log message pairs mirroring the exact bucketing
# `_sanitize_provider_error_message`/the per-round `except` clauses in
# `litellm.py::run()` produce for each real error class (see this module's
# "Error scenarios" docstring section above for the full citation).
_TEST_401_MESSAGE = "This provider is not configured correctly yet. Add or update its API key and try again."
_TEST_401_LOG_MESSAGE = (
    "LiteLLM error for model 'test-model': Deterministic TEST_PROVIDER_401 "
    "simulated authentication failure (Invalid API key provided)."
)

_TEST_500_MESSAGE = "The AI provider is temporarily unavailable. Please try again in a moment."
_TEST_500_LOG_MESSAGE = (
    "OpenAI API server error with model 'test-model'. This may be temporary. "
    "Details: Deterministic TEST_PROVIDER_500 simulated internal server error."
)

_TEST_400_MESSAGE = (
    "The AI provider could not complete this request for test-model. "
    "Please try again or choose a different model."
)
_TEST_400_LOG_MESSAGE = (
    "LiteLLM error for model 'test-model': Deterministic TEST_PROVIDER_400 "
    "simulated bad request (Invalid input: malformed request payload)."
)

_TEST_429_LOG_MESSAGE = (
    "Deterministic TEST_PROVIDER_429 simulated rate limit "
    "(RateLimitError: You exceeded your current quota)."
)

# --- TEST_STRUCTURED_OUTPUT fixture -------------------------------------
# A fixed, valid JSON string - `final_output` is just `choice.content`
# (litellm.py ~line 1082-1083), so "structured output" has no separate
# result shape; it is only ever JSON-formatted text in `final_output`.
_TEST_STRUCTURED_OUTPUT_RESPONSE = '{"city": "Bengaluru", "condition": "Sunny", "temp_c": 29}'
_TEST_STRUCTURED_OUTPUT_INPUT_TOKENS = 12
_TEST_STRUCTURED_OUTPUT_OUTPUT_TOKENS = 9

# --- TEST_CACHED_USAGE fixture -------------------------------------------
# Same response text/cost as TEST_TEXT; only usage differs, with a nonzero
# `cached_tokens` simulating a cache hit (field names per litellm.py ~1061-1063).
_TEST_CACHED_USAGE_INPUT_TOKENS = 10
_TEST_CACHED_USAGE_OUTPUT_TOKENS = 8
_TEST_CACHED_USAGE_CACHED_TOKENS = 6

# --- TEST_STREAM_INTERRUPT fixtures --------------------------------------
_STREAM_INTERRUPT_CHUNKS = ("The weather ", "in Bengaluru ")
_STREAM_INTERRUPT_ERROR_MESSAGE = (
    "LiteLLM Streaming Error: Deterministic TEST_STREAM_INTERRUPT simulated "
    "mid-stream connection drop (Connection reset by peer)."
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


def _run_test_provider_429(agent, enhanced_prompt, provider, model, context=None):
    """TEST_PROVIDER_429 scenario: raise the real `litellm.RateLimitError`
    class, unwrapped - `litellm.run()`'s own `except RateLimitError as e:`
    clause re-raises it as-is (`raise e`, litellm.py ~line 959-968), and the
    outer boundary handler explicitly re-raises it too instead of converting
    it to `ProviderUnavailableError`. So the real, final contract for a 429
    is a bare `RateLimitError` propagating out unchanged - this scenario
    raises exactly that.

    Imported lazily, mirroring `_run_test_provider_timeout`'s lazy import of
    `ProviderUnavailableError` (avoids import-order coupling with `litellm.py`).
    """
    from litellm import RateLimitError

    raise RateLimitError(
        _TEST_429_LOG_MESSAGE,
        llm_provider=provider,
        model=model,
    )


def _run_test_provider_400(agent, enhanced_prompt, provider, model, context=None):
    """TEST_PROVIDER_400 scenario: a genuine bad-request/invalid-input error
    that is not a recognized tools/response_format capability conflict falls
    through to `litellm.run()`'s generic `except Exception as e:` boundary
    handler and is converted via `_raise_provider_unavailable`, landing on
    `_sanitize_provider_error_message`'s final default bucket (the same
    default `TEST_PROVIDER_TIMEOUT` lands on)."""
    from huf.ai.providers.litellm import ProviderUnavailableError

    raise ProviderUnavailableError(
        _TEST_400_MESSAGE,
        log_message=_TEST_400_LOG_MESSAGE,
    )


def _run_test_provider_401(agent, enhanced_prompt, provider, model, context=None):
    """TEST_PROVIDER_401 scenario: raise `ProviderUnavailableError` with the
    exact public message `_sanitize_provider_error_message` produces for an
    "invalid api key" / "api key not configured" raw message
    (litellm.py ~line 78-79)."""
    from huf.ai.providers.litellm import ProviderUnavailableError

    raise ProviderUnavailableError(
        _TEST_401_MESSAGE,
        log_message=_TEST_401_LOG_MESSAGE,
    )


def _run_test_provider_500(agent, enhanced_prompt, provider, model, context=None):
    """TEST_PROVIDER_500 scenario: raise `ProviderUnavailableError` with the
    exact public message produced for a real `InternalServerError`
    (litellm.py ~line 951-957, sanitized via the "server error" bucket at
    ~line 95-107)."""
    from huf.ai.providers.litellm import ProviderUnavailableError

    raise ProviderUnavailableError(
        _TEST_500_MESSAGE,
        log_message=_TEST_500_LOG_MESSAGE,
    )


def _run_test_structured_output(agent, enhanced_prompt, provider, model, context=None):
    """TEST_STRUCTURED_OUTPUT scenario: `final_output` is a fixed, valid
    JSON string - matching `litellm.run()`'s real contract that
    `response_format`-requested output has no separate result shape; it is
    simply `choice.content` (litellm.py ~line 1082-1083), which happens to be
    JSON-formatted text."""
    usage = {
        "input_tokens": _TEST_STRUCTURED_OUTPUT_INPUT_TOKENS,
        "output_tokens": _TEST_STRUCTURED_OUTPUT_OUTPUT_TOKENS,
        "cached_tokens": 0,
        "cache_creation_tokens": 0,
        "cache_miss_tokens": 0,
        "cache_skipped_unsupported_model": False,
    }
    return SimpleNamespace(
        final_output=_TEST_STRUCTURED_OUTPUT_RESPONSE,
        usage=usage,
        new_items=[],
        cost=0.0,
    )


def _run_test_cached_usage(agent, enhanced_prompt, provider, model, context=None):
    """TEST_CACHED_USAGE scenario: a TEST_TEXT-shaped result whose usage dict
    has a nonzero `cached_tokens` value, using the exact field names
    `litellm.run()`'s own `total_usage` accounting produces
    (litellm.py ~line 1061-1063)."""
    usage = {
        "input_tokens": _TEST_CACHED_USAGE_INPUT_TOKENS,
        "output_tokens": _TEST_CACHED_USAGE_OUTPUT_TOKENS,
        "cached_tokens": _TEST_CACHED_USAGE_CACHED_TOKENS,
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
    "TEST_TOOL_SINGLE": _run_test_tool_single,
    "TEST_TOOL_MULTI": _run_test_tool_multi,
    "TEST_PROVIDER_TIMEOUT": _run_test_provider_timeout,
    "TEST_PROVIDER_429": _run_test_provider_429,
    "TEST_PROVIDER_400": _run_test_provider_400,
    "TEST_PROVIDER_401": _run_test_provider_401,
    "TEST_PROVIDER_500": _run_test_provider_500,
    "TEST_STRUCTURED_OUTPUT": _run_test_structured_output,
    "TEST_CACHED_USAGE": _run_test_cached_usage,
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

    result = handler(agent, enhanced_prompt, provider, model, context=context)
    _fill_missing_usage_fields(result)
    return result


def _fill_missing_usage_fields(result):
    """Backfill usage keys that `litellm.run()` always populates but that
    scenario handlers above predate (e.g. `peak_context_tokens`, added by
    the prompt-cache-auto-mode work in `providers/litellm.py` ~line 1494-1495
    as `max(peak_context_tokens, round_input_tokens)`). `Agent Run.
    peak_context_tokens` is an Int column with a DB-level `NOT NULL DEFAULT
    0`; agent_integration.py reads it via `usage_payload.get(...)`, which
    returns `None` for an absent key, and inserting an explicit `None`
    overrides that DEFAULT and fails the query with
    `(1048, "Column 'peak_context_tokens' cannot be null")` -- found by
    running this suite against a real bench post-merge. A single-round test
    scenario's peak context is just its own input token count, mirroring
    the real accounting for a one-round call.
    """
    usage = getattr(result, "usage", None)
    if isinstance(usage, dict) and "peak_context_tokens" not in usage:
        usage["peak_context_tokens"] = usage.get("input_tokens", 0)


# --- Streaming scenarios (`run_stream`) --------------------------------
# `litellm.run_stream()` is a separate `async def` *generator* function
# (contains `yield`) with a different return shape than `run()` - it yields
# dicts shaped `{"type": "delta"/"reasoning"/"tool_call"/"complete"/"error",
# ...}` (see `litellm.py` ~line 1338-1344 and this module's top-level
# docstring's "TEST_STREAM_INTERRUPT and the run_stream export" section for
# the full citation). Streaming scenario handlers are therefore async
# generators too, and are kept in their own dispatch table
# (`_STREAM_SCENARIO_HANDLERS`), separate from `_SCENARIO_HANDLERS`.


async def _stream_test_stream_interrupt(agent, enhanced_prompt, provider, model, context=None):
    """TEST_STREAM_INTERRUPT scenario: yield a couple of normal `delta`
    chunks, then yield exactly one `{"type": "error", ...}` chunk shaped like
    `litellm.run_stream()`'s own outer boundary handler produces for a real
    mid-stream failure (`litellm.py` ~line 2038-2043:
    `yield {"type": "error", "error": f"LiteLLM Streaming Error: {e}"}`), and
    stop - never raising an exception out of the generator, matching the
    real contract exactly (a real mid-stream exception is caught internally
    by `run_stream()` and converted to this same error-chunk shape; it never
    propagates to the caller as a raised exception)."""
    full_response = ""
    for chunk_text in _STREAM_INTERRUPT_CHUNKS:
        full_response += chunk_text
        yield {
            "type": "delta",
            "content": chunk_text,
            "full_response": full_response,
        }

    yield {"type": "error", "error": _STREAM_INTERRUPT_ERROR_MESSAGE}


# Stream scenario name -> async-generator handler. Handlers share the exact
# signature of `run_stream()`.
_STREAM_SCENARIO_HANDLERS = {
    "TEST_STREAM_INTERRUPT": _stream_test_stream_interrupt,
}


async def run_stream(agent, enhanced_prompt, provider, model, context=None):
    """Deterministic stand-in for `huf.ai.providers.litellm.run_stream()`.

    Invoked from inside `huf.ai.providers.litellm.run_stream()` itself (see
    the `provider.lower() == "test_provider"` check mirroring `run()`'s own,
    near the top of that async-generator function), and re-yielded
    chunk-by-chunk from there via `async for _chunk in
    test_provider.run_stream(...): yield _chunk`. See this module's
    top-level docstring's "TEST_STREAM_INTERRUPT and the run_stream export"
    section for why `run_stream()` needs its own export and dispatch table
    distinct from `run()`'s.

    No network calls, no `frappe.get_doc`/DB access, no LLM SDK usage.
    """
    scenario = _extract_scenario(enhanced_prompt)
    if scenario is None:
        raise UnknownTestScenarioError(
            "huf.ai.providers.test_provider.run_stream() requires a "
            "'__TEST_SCENARIO__:<NAME>' marker somewhere in enhanced_prompt; "
            "none was found."
        )

    handler = _STREAM_SCENARIO_HANDLERS.get(scenario)
    if handler is None:
        raise UnknownTestScenarioError(
            f"Unknown streaming test scenario '{scenario}'. Known streaming "
            f"scenarios: {sorted(_STREAM_SCENARIO_HANDLERS)}"
        )

    async for chunk in handler(agent, enhanced_prompt, provider, model, context=context):
        yield chunk
