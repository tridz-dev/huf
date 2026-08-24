# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Golden Agent Scenarios harness (GOAL.md section 7 — "Golden Agent Scenarios").

WHAT THIS IS
-------------
A versioned suite of semantic execution scenarios (AGENT-GOLDEN-001,
AGENT-GOLDEN-002, ...) that each:

    1. Construct a minimal deterministic world: a fake ``agent`` object
       carrying exactly the attributes real product code reads off a real
       `Agent` doc for a provider call (`agent_name`, `provider`, `model`,
       `instructions`, `max_turns` — see `huf/ai/agent_integration.py:499`
       and `huf/ai/providers/litellm.py:688`), wired to provider
       "test_provider" with the right `__TEST_SCENARIO__:<NAME>` marker
       (see `huf/ai/providers/test_provider.py`'s module docstring for the
       full triggering-mechanism contract).
    2. Call `huf.ai.providers.test_provider.run()` directly (this is the
       exact function `huf.ai.providers.litellm.run()` delegates to for
       `provider.lower() == "test_provider"`, awaited from the same real
       call site a real provider call is — see that module's docstring for
       why this is the correct integration point).
    3. Capture the actual returned `SimpleResult`-shaped object (or the
       raised exception, for the failure scenario) plus a synthesized
       Agent-Run-lifecycle trace matching the documented execution steps in
       `agent_integration.py::_execute_agent_run` (history fetch -> provider
       invocation -> tool-call-loop persistence over `result.new_items` ->
       usage/cost persistence -> final message persist).
    4. Normalize that trace via `huf.ai.tests.golden_trace.normalize_trace`
       and compare it against a versioned snapshot file in
       `huf/ai/tests/golden_traces/<SCENARIO_ID>.json`.

WHY NOT THE REAL `_execute_agent_run`/`run_agent_sync` ORCHESTRATION
----------------------------------------------------------------------
There is no live Frappe bench in this worktree today (see
`docs/testing/CURRENT_STATE.md`) — `_execute_agent_run` needs a real
Frappe DB (`frappe.get_doc`, `Agent Run`/`Agent Message` inserts, redis
locks, realtime socket emission). This harness deliberately stops at the
level that IS realistically testable without one: the provider call itself,
plus a hand-built, clearly-labeled synthesis of the surrounding lifecycle
shape. Every synthesized field is documented inline below as synthesized,
not asserted as "this is what the DB would literally contain."

FOLLOW-UP (not in this pass)
------------------------------
Once a bench exists, a second pass should:
    - Use `huf.ai.tests.factories.make_agent`/`make_agent_conversation`/
      `make_agent_run` to build REAL doc rows (still wired to provider
      "test_provider" so scenarios stay deterministic).
    - Drive the REAL `huf.ai.agent_integration.run_agent_sync`/
      `_execute_agent_run` path (as an `IntegrationTestCase`, per this
      repo's existing test convention, see `huf/huf/doctype/agent/
      test_agent.py`).
    - Feed the REAL `Agent Run`/`Agent Message` rows produced (via
      `.as_dict()`) into the SAME `normalize_trace()` function used here —
      it does not care whether its input came from a real DB row or from
      this module's synthesized shape, so the snapshot format does not need
      to change, only how the raw trace is assembled.
    - Replace the synthesized `state_transitions` list with the real
      `agent_run_status` realtime lifecycle events emitted by
      `_emit_run_lifecycle_event` (`agent_integration.py:535`).

RUNNING THIS FILE
------------------
This file has NO Frappe/bench dependency (it does not import `frappe`, does
not touch a DB) and is runnable directly:

    python3 -m unittest huf.ai.tests.test_golden_scenarios -v

The FIRST run in a fresh checkout writes the initial snapshot files under
`huf/ai/tests/golden_traces/*.json` if they do not yet exist (this is
intentional and logged loudly — see `_compare_or_write_snapshot` below).
Every subsequent run compares against the committed snapshot and fails
loudly with a full diff on any drift, per GOAL.md section 7: "A changed
golden trace is a meaningful behavioural change, not something an agent
automatically accepts." Golden trace snapshot files must be code reviewed
like any other behavioural assertion — never regenerate one to "make a
test pass" without checking is why it changed.
"""

import asyncio
import os
import sys
import unittest
from types import ModuleType, SimpleNamespace

_GOLDEN_TRACES_DIR = os.path.join(os.path.dirname(__file__), "golden_traces")
_HUF_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _bootstrap_bare_environment():
    """This worktree has no live Frappe bench (see docs/testing/CURRENT_STATE.md
    and this file's module docstring). `huf/__init__.py` does an unconditional
    `import frappe` at package-import time, and
    `huf.ai.providers.test_provider`'s error scenarios lazily
    `from huf.ai.providers.litellm import ProviderUnavailableError` — which in
    turn pulls in the real `litellm` pip package plus a long transitive chain
    of `huf.ai.*` modules that themselves import `frappe`. None of that is
    installed in this sandbox.

    If a real `frappe` install IS available (the future bench-backed pass,
    or CI), this function is a complete no-op: the `import frappe` probe
    below succeeds and nothing is stubbed, so `huf.ai.providers.test_provider`
    and `huf.ai.providers.litellm` import and behave exactly as real product
    code.

    Otherwise, we pre-seed `sys.modules` with minimal stand-ins so that
    `huf`/`huf.ai`/`huf.ai.providers` resolve to their REAL on-disk packages
    (via `__path__`, so `test_provider.py`'s actual file is still what gets
    imported and executed — nothing about `test_provider.py`'s own logic is
    faked), while short-circuiting the one transitive dependency this
    harness's scenarios actually touch: `huf.ai.providers.litellm`'s
    `ProviderUnavailableError` class, stood in with an identical
    `(public_message, log_message=None)` shape (see that class's real
    definition cited in `huf/ai/providers/test_provider.py`'s module
    docstring, "Error scenarios" section). This does NOT change what
    `test_provider.py` does — it only lets Python resolve one import name
    without needing the real `litellm` pip package or the rest of `huf.ai`'s
    transitive import graph, which this harness's provider-level scenarios
    do not exercise.
    """
    try:
        import frappe  # noqa: F401

        return  # real bench present; nothing to stub
    except ImportError:
        pass

    def _stub_package(dotted_name, real_subdir):
        if dotted_name in sys.modules:
            return
        mod = ModuleType(dotted_name)
        mod.__path__ = [real_subdir]
        sys.modules[dotted_name] = mod

    _stub_package("huf", _HUF_ROOT)
    _stub_package("huf.ai", os.path.join(_HUF_ROOT, "ai"))
    _stub_package("huf.ai.providers", os.path.join(_HUF_ROOT, "ai", "providers"))
    _stub_package("huf.ai.tests", os.path.join(_HUF_ROOT, "ai", "tests"))

    if "huf.ai.providers.litellm" not in sys.modules:
        fake_litellm_provider = ModuleType("huf.ai.providers.litellm")

        class ProviderUnavailableError(Exception):
            """Stand-in for the real `huf.ai.providers.litellm.ProviderUnavailableError`
            (see that class's real definition/contract cited in
            `test_provider.py`'s module docstring) — same
            `(public_message, log_message=None)` shape, same two readable
            attributes. Only used so this bare-environment harness can
            exercise `TEST_PROVIDER_500` without the real `litellm` pip
            package / `huf.ai.*` transitive import graph installed."""

            def __init__(self, public_message, log_message=None):
                super().__init__(public_message)
                self.public_message = public_message
                self.log_message = log_message

        fake_litellm_provider.ProviderUnavailableError = ProviderUnavailableError
        sys.modules["huf.ai.providers.litellm"] = fake_litellm_provider


_bootstrap_bare_environment()

from huf.ai.providers import test_provider  # noqa: E402
from huf.ai.tests.golden_trace import normalize_trace, to_json  # noqa: E402


def _make_fake_agent(agent_name, instructions, max_turns=10):
    """A minimal fake `Agent`-doc-like object carrying exactly the
    attributes real code reads off a real Agent doc for a provider call
    (see this module's docstring). Deliberately NOT a `frappe.get_doc(...)`
    call — no DB in this worktree today."""
    return SimpleNamespace(
        name=f"test-agent-{agent_name}",
        agent_name=agent_name,
        provider="Test_Provider",
        model="test-model",
        instructions=instructions,
        max_turns=max_turns,
    )


def _run_provider(agent, prompt, context=None):
    """Call `test_provider.run()` synchronously (it's a coroutine function;
    there is no running event loop in a plain unittest run)."""
    return asyncio.run(test_provider.run(agent, prompt, agent.provider, agent.model, context=context))


def _synthesize_messages(agent, prompt, result):
    """Synthesize the Agent-Message-shaped rows a real `_execute_agent_run`
    would persist for this provider call, per the documented sequence in
    `agent_integration.py`: a user message, then one (kind="Tool Call")
    message per tool_call_item/tool_call_output_item pair in
    `result.new_items`, then the final assistant message. This is a
    synthesis of the documented persistence contract, not a real DB read —
    see module docstring."""
    messages = [{"role": "user", "kind": "Message", "content": prompt}]

    for item in getattr(result, "new_items", None) or []:
        item_type = getattr(item, "type", None)
        raw_item = getattr(item, "raw_item", None)
        if item_type == "tool_call_item":
            messages.append(
                {
                    "role": "assistant",
                    "kind": "Tool Call",
                    "content": {
                        "name": getattr(raw_item, "name", None),
                        "arguments": getattr(raw_item, "arguments", None),
                        "id": getattr(raw_item, "id", None),
                    },
                }
            )
        elif item_type == "tool_call_output_item":
            raw = raw_item if isinstance(raw_item, dict) else {}
            messages.append(
                {
                    "role": "tool",
                    "kind": "Tool Result",
                    "content": {
                        "name": raw.get("name"),
                        "output": raw.get("output"),
                        "id": raw.get("id"),
                    },
                }
            )

    messages.append({"role": "assistant", "kind": "Message", "content": getattr(result, "final_output", None)})
    return messages


def _synthesize_state_transitions(has_tool_calls, succeeded):
    """Synthesize the state-transition sequence a real Agent Run goes
    through, per the documented lifecycle in `agent_integration.py` (queue
    -> start -> [tool_call -> tool_result]* -> complete, or -> failed)."""
    transitions = ["queued", "started"]
    if has_tool_calls:
        transitions += ["tool_call", "tool_result"]
    transitions.append("completed" if succeeded else "failed")
    return transitions


def _build_success_trace(scenario, agent, prompt, result):
    has_tool_calls = bool(getattr(result, "new_items", None))
    return {
        "scenario": scenario,
        "agent": agent,
        "prompt": prompt,
        "context": None,
        "tool_definitions": [],
        "state_transitions": _synthesize_state_transitions(has_tool_calls, succeeded=True),
        "terminal_status": "Success",
        "result": result,
        "error": None,
        "messages": _synthesize_messages(agent, prompt, result),
        "run_meta": {"status": "Success"},
    }


def _build_failure_trace(scenario, agent, prompt, exc):
    error = {
        "type": type(exc).__name__,
        "public_message": getattr(exc, "public_message", str(exc)),
        "log_message": getattr(exc, "log_message", None),
    }
    return {
        "scenario": scenario,
        "agent": agent,
        "prompt": prompt,
        "context": None,
        "tool_definitions": [],
        "state_transitions": _synthesize_state_transitions(has_tool_calls=False, succeeded=False),
        "terminal_status": "Failed",
        "result": None,
        "error": error,
        "messages": [{"role": "user", "kind": "Message", "content": prompt}],
        "run_meta": {"status": "Failed"},
    }


def _compare_or_write_snapshot(test_case, scenario_id, normalized):
    """Compare `normalized` (already run through `to_json`) against the
    committed snapshot file, or write it if this is the first run in a
    fresh checkout (loudly, via a printed message — this is an intentional,
    reviewable act, not silent drift per GOAL.md section 7)."""
    path = os.path.join(_GOLDEN_TRACES_DIR, f"{scenario_id}.json")
    actual_json = to_json(normalized)

    if not os.path.exists(path):
        os.makedirs(_GOLDEN_TRACES_DIR, exist_ok=True)
        with open(path, "w") as f:
            f.write(actual_json)
        print(f"\n[golden-trace] WROTE initial snapshot for {scenario_id} at {path}")
        print(
            f"[golden-trace] This is expected on a fresh checkout. Review this file "
            f"before committing it — a golden trace snapshot IS a behavioural assertion."
        )
        return

    with open(path) as f:
        expected_json = f.read()

    test_case.assertEqual(
        expected_json,
        actual_json,
        msg=(
            f"\nGolden trace '{scenario_id}' DRIFTED from its committed snapshot at {path}.\n"
            f"Per GOAL.md section 7, this is a meaningful behavioural change, not something "
            f"to auto-accept: inspect the diff above, confirm the new behavior is intentional "
            f"and correct, then update the snapshot file deliberately (with code review) if so."
        ),
    )


class TestGoldenScenarios(unittest.TestCase):
    """One test method per golden scenario id. See module docstring."""

    def test_agent_golden_001_basic_text_completion(self):
        """AGENT-GOLDEN-001: basic text completion (TEST_TEXT)."""
        agent = _make_fake_agent("golden-001-text-agent", "You are a deterministic test agent.")
        prompt = "Current user message:\n__TEST_SCENARIO__:TEST_TEXT Hello, how are you?\n"

        result = _run_provider(agent, prompt)

        self.assertEqual(result.new_items, [])
        self.assertTrue(result.final_output)

        raw_trace = _build_success_trace("AGENT-GOLDEN-001", agent, prompt, result)
        normalized = normalize_trace(raw_trace)
        _compare_or_write_snapshot(self, "AGENT-GOLDEN-001", normalized)

    def test_agent_golden_002_tool_call_single(self):
        """AGENT-GOLDEN-002: tool call -> result -> final response (TEST_TOOL_SINGLE)."""
        agent = _make_fake_agent("golden-002-tool-agent", "You are a deterministic test agent with tools.")
        prompt = "Current user message:\n__TEST_SCENARIO__:TEST_TOOL_SINGLE What's the weather in Bengaluru?\n"

        result = _run_provider(agent, prompt)

        self.assertEqual(len(result.new_items), 2)
        self.assertEqual(result.new_items[0].type, "tool_call_item")
        self.assertEqual(result.new_items[1].type, "tool_call_output_item")

        raw_trace = _build_success_trace("AGENT-GOLDEN-002", agent, prompt, result)
        normalized = normalize_trace(raw_trace)
        _compare_or_write_snapshot(self, "AGENT-GOLDEN-002", normalized)

    def test_agent_golden_003_tool_call_multi(self):
        """AGENT-GOLDEN-003: two sequential tool calls (TEST_TOOL_MULTI)."""
        agent = _make_fake_agent("golden-003-multi-tool-agent", "You are a deterministic test agent with tools.")
        prompt = (
            "Current user message:\n"
            "__TEST_SCENARIO__:TEST_TOOL_MULTI What's the weather and 3-day forecast for Bengaluru?\n"
        )

        result = _run_provider(agent, prompt)

        self.assertEqual(len(result.new_items), 4)
        types = [item.type for item in result.new_items]
        self.assertEqual(
            types,
            ["tool_call_item", "tool_call_output_item", "tool_call_item", "tool_call_output_item"],
        )

        raw_trace = _build_success_trace("AGENT-GOLDEN-003", agent, prompt, result)
        normalized = normalize_trace(raw_trace)
        _compare_or_write_snapshot(self, "AGENT-GOLDEN-003", normalized)

    def test_agent_golden_006_provider_failure(self):
        """AGENT-GOLDEN-006: provider failure (TEST_PROVIDER_500)."""
        from huf.ai.providers.litellm import ProviderUnavailableError

        agent = _make_fake_agent("golden-006-failure-agent", "You are a deterministic test agent.")
        prompt = "Current user message:\n__TEST_SCENARIO__:TEST_PROVIDER_500 Do something.\n"

        with self.assertRaises(ProviderUnavailableError) as ctx:
            _run_provider(agent, prompt)

        raw_trace = _build_failure_trace("AGENT-GOLDEN-006", agent, prompt, ctx.exception)
        normalized = normalize_trace(raw_trace)
        _compare_or_write_snapshot(self, "AGENT-GOLDEN-006", normalized)


if __name__ == "__main__":
    unittest.main()
