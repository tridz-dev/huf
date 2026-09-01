# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Trace normalization layer for HUF's Golden Agent Scenarios (GOAL.md section 7).

WHAT THIS MODULE IS
--------------------
A pure, deterministic function/module that takes the raw artifacts of an
Agent Run — a doc-like ``agent`` object, a ``SimpleResult``-shaped provider
return (the exact shape ``huf.ai.providers.litellm.run()``/
``huf.ai.providers.test_provider.run()`` produce, see
`huf/ai/providers/test_provider.py`'s module docstring for the contract),
and optionally the ``Agent Run``/``Agent Message`` DB rows a real execution
would persist — and reduces them to a normalized, deterministic dict that is
safe to snapshot to disk and diff in code review.

WHAT GETS KEPT vs STRIPPED
---------------------------
Kept (semantically meaningful — a change here IS a behavioural change):
    - agent name/label, provider, model
    - system prompt / instructions (the resolved text, not a hash)
    - conversation messages: role + content, in order
    - injected context (RAG/knowledge context keys, if present)
    - tool definitions available to the agent (name + normalized schema)
    - tool call requests: tool name + normalized (parsed, key-sorted) args
    - tool call results: tool name + result payload
    - final assistant response text
    - usage numbers (input/output/cached/cache_creation/cache_miss tokens)
    - cost
    - terminal status ("Success"/"Failed"/error class + public message)
    - the state-transition sequence (e.g. ["queued", "started", "tool_call",
      "tool_result", "tool_call", "tool_result", "completed"])

Stripped / replaced with a stable placeholder (random or environment-derived,
would cause snapshot churn with zero behavioural meaning):
    - Agent Run doc name (e.g. "AGT-RUN-2026-00042") -> "<RUN_ID>"
    - Agent Message doc names -> "<MSG_ID:0>", "<MSG_ID:1>", ... (index-stable,
      not value-stable, so reordering IS caught but the literal autoname
      counter is not)
    - tool_call_id values from the provider (e.g. "test-tool-call-1") ->
      "<TOOL_CALL_ID:0>", "<TOOL_CALL_ID:1>", ... (same index-stable scheme;
      a real provider's IDs are opaque and provider-generated, so their
      literal value has no semantic meaning, only their *pairing* between a
      tool_call_item and its tool_call_output_item does — this normalizer
      keeps that pairing by giving both events in a pair the same placeholder)
    - any ISO timestamp / `frappe.utils.now()`-shaped string -> "<TIMESTAMP>"
    - wall-clock duration / elapsed-time fields -> "<DURATION>"

Example (before -> after), abbreviated:

    RAW:
        Agent Run "AGT-RUN-2026-00042", creation="2026-08-25 10:03:11.482910"
        Agent Message "AGT-MSG-2026-00981", kind="Tool Call",
            content: {"name": "get_weather", "arguments": "{\"city\": \"Bengaluru\"}",
                      "id": "test-tool-call-1"}
        result.usage = {"input_tokens": 20, "output_tokens": 15, ...}

    NORMALIZED:
        {
          "run_id": "<RUN_ID>",
          "creation": "<TIMESTAMP>",
          "messages": [
            {"id": "<MSG_ID:0>", "kind": "Tool Call",
             "tool_name": "get_weather",
             "tool_args": {"city": "Bengaluru"},   # parsed + key-sorted, not
                                                     # the raw JSON string
             "tool_call_id": "<TOOL_CALL_ID:0>"}
          ],
          "usage": {"input_tokens": 20, "output_tokens": 15, "cached_tokens": 0,
                     "cache_creation_tokens": 0, "cache_miss_tokens": 0}
        }

Tool arguments are parsed from JSON and key-sorted (not compared as a raw
string) so that a provider that emits semantically-identical arguments in a
different key order does not cause spurious snapshot churn; if the argument
string is not valid JSON, it is kept as-is (still semantically meaningful,
just not reorderable).

WHAT THIS MODULE DOES NOT DO (yet) — SCOPE / FOLLOW-UP
---------------------------------------------------------
This module normalizes whatever raw artifacts are handed to it. Today (no
live Frappe bench in this worktree — see docs/testing/CURRENT_STATE.md), the
only realistically-testable path is calling
`huf.ai.providers.test_provider.run()` directly with a hand-built minimal
fake ``agent`` object (a `SimpleNamespace` mirroring the exact attributes
real product code reads off a real `Agent` doc: `.name`, `.agent_name`,
`.provider`, `.model`, `.instructions`, `.max_turns` — see
`huf/ai/agent_integration.py:499` and `huf/ai/providers/litellm.py:688`),
NOT the full `_execute_agent_run`/`run_agent_sync` orchestration (which
needs a real Frappe DB to persist real `Agent Run`/`Agent Message` rows and
emit real lifecycle events).

`capture_provider_trace()` below reflects that today: it captures a
provider-level trace (agent config + provider call + usage + terminal
status), with a *synthesized* state-transition sequence and *synthesized*
Agent Message-shaped rows describing what a real orchestration would have
persisted around that provider call, per the documented contract in
`agent_integration.py` (history fetch -> provider invocation -> tool-call
loop over `result.new_items` -> usage/cost persistence -> final message
persist). It does NOT drive real DB rows.

A second, later pass — once a bench exists — should extend this harness to
drive the REAL `_execute_agent_run`/`run_agent_sync` path with a real
`IntegrationTestCase`, a real `Agent`/`Agent Run`/`Agent Message` set of
rows (via `huf.ai.tests.factories`), and feed those real rows into this same
`normalize_trace()` function (it does not care whether its input dicts came
from a real `frappe.get_doc(...).as_dict()` or from the synthesized shape
built here — the normalization contract is the same either way). That pass
should also capture the real realtime `agent_run_status` lifecycle events
(`_emit_run_lifecycle_event`, `agent_integration.py:535`) as the state
transitions, replacing the synthesized sequence.
"""

import json
import re

_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(\.\d+)?$"
)

_PLACEHOLDER_TIMESTAMP = "<TIMESTAMP>"
_PLACEHOLDER_RUN_ID = "<RUN_ID>"
_PLACEHOLDER_DURATION = "<DURATION>"


def _looks_like_timestamp(value):
    return isinstance(value, str) and bool(_TIMESTAMP_RE.match(value))


def _normalize_scalar(value):
    """Replace any bare timestamp-shaped string with the stable placeholder.
    Everything else (numbers, plain strings, bools, None) passes through
    unchanged — those are semantically meaningful."""
    if _looks_like_timestamp(value):
        return _PLACEHOLDER_TIMESTAMP
    return value


def normalize_tool_args(raw_args):
    """Parse a tool-call arguments string as JSON and key-sort it so
    semantically-identical arguments in a different key order do not cause
    snapshot churn. Falls back to the raw string if it is not valid JSON
    (still meaningful, just not reorderable)."""
    if raw_args is None:
        return None
    if not isinstance(raw_args, str):
        return raw_args
    try:
        parsed = json.loads(raw_args)
    except (TypeError, ValueError):
        return raw_args
    return _sort_recursively(parsed)


def _sort_recursively(value):
    if isinstance(value, dict):
        return {k: _sort_recursively(value[k]) for k in sorted(value.keys())}
    if isinstance(value, list):
        return [_sort_recursively(v) for v in value]
    return value


def normalize_tool_result(raw_result):
    """Tool results are opaque payloads (usually JSON strings from a real
    tool handler) — parse+key-sort them the same way as args when they are
    JSON, otherwise keep the raw value. Unlike args, a non-dict/non-JSON
    result (e.g. plain text) is common and fully meaningful as-is."""
    if isinstance(raw_result, str):
        try:
            parsed = json.loads(raw_result)
        except (TypeError, ValueError):
            return raw_result
        return _sort_recursively(parsed)
    return raw_result


def _normalize_new_items(new_items):
    """Walk `result.new_items` (a list of `SimpleNamespace` items shaped like
    `huf.ai.providers.litellm.run()` produces — see
    `huf/ai/providers/test_provider.py` module docstring's "Tool-call
    scenario contract" section) into a normalized list of tool-call/
    tool-result pairs. Real `tool_call_id` values are opaque and
    provider-generated; they are replaced with an index-stable placeholder,
    but the SAME placeholder is reused for a `tool_call_item` and its
    matching `tool_call_output_item` so the pairing itself (a real semantic
    fact) is preserved."""
    normalized = []
    id_placeholders = {}

    def _placeholder_for(call_id):
        if call_id not in id_placeholders:
            id_placeholders[call_id] = f"<TOOL_CALL_ID:{len(id_placeholders)}>"
        return id_placeholders[call_id]

    for item in new_items:
        item_type = getattr(item, "type", None)
        raw_item = getattr(item, "raw_item", None)

        if item_type == "tool_call_item":
            call_id = getattr(raw_item, "id", None)
            normalized.append(
                {
                    "type": "tool_call",
                    "tool_name": getattr(raw_item, "name", None),
                    "tool_args": normalize_tool_args(getattr(raw_item, "arguments", None)),
                    "tool_call_id": _placeholder_for(call_id),
                }
            )
        elif item_type == "tool_call_output_item":
            # raw_item is a plain dict for this item type (see test_provider.py).
            raw = raw_item if isinstance(raw_item, dict) else {}
            call_id = raw.get("id")
            normalized.append(
                {
                    "type": "tool_result",
                    "tool_name": raw.get("name"),
                    "tool_result": normalize_tool_result(raw.get("output")),
                    "tool_call_id": _placeholder_for(call_id),
                }
            )
        else:
            # Unknown/future item shape: keep type + a best-effort repr so a
            # new item kind is visible in the diff instead of silently
            # dropped, but does not crash normalization.
            normalized.append({"type": item_type or "<unknown>", "raw": repr(raw_item)})

    return normalized


def _normalize_usage(usage):
    if not usage:
        return {}
    keys = (
        "input_tokens",
        "output_tokens",
        "cached_tokens",
        "cache_creation_tokens",
        "cache_miss_tokens",
        "cache_skipped_unsupported_model",
    )
    return {k: usage.get(k, 0) for k in keys}


def normalize_agent_snapshot(agent):
    """Normalize the (fake or real) agent object's semantically-relevant
    fields. Reads exactly the attributes real product code reads off an
    `Agent` doc for a provider call: `agent_name`, `provider`, `model`,
    `instructions` (system prompt / Local-mode prompt body, see
    `huf/ai/prompt_resolver.py::resolve_prompt`), `max_turns`."""
    return {
        "agent_name": getattr(agent, "agent_name", None),
        "provider": getattr(agent, "provider", None),
        "model": getattr(agent, "model", None),
        "instructions": getattr(agent, "instructions", None),
        "max_turns": getattr(agent, "max_turns", None),
    }


def normalize_trace(raw_trace):
    """Produce the final normalized, snapshot-ready dict from a raw trace
    assembled by `capture_provider_trace()` (or, in a future DB-backed pass,
    from real `Agent Run`/`Agent Message` rows shaped the same way).

    `raw_trace` is a dict with keys:
        scenario            -> str, the golden scenario id (e.g. "AGENT-GOLDEN-001")
        agent                -> agent-like object (see `normalize_agent_snapshot`)
        prompt               -> str, the raw prompt sent (with the
                                 __TEST_SCENARIO__ marker — kept, it IS the
                                 semantically meaningful trigger for this trace)
        context               -> dict or None, injected context (RAG/knowledge)
        tool_definitions      -> list of dicts describing tools available to
                                 the agent for this scenario (name/description),
                                 or [] if none
        state_transitions     -> list of str, in order
        result                -> the `SimpleResult`-shaped object returned by
                                 the provider (has `.final_output`, `.usage`,
                                 `.new_items`, `.cost`), or None on failure
        error                 -> dict {"type": <exception class name>,
                                 "public_message": ..., "log_message": ...}
                                 or None on success
        terminal_status       -> str, "Success" or "Failed"
        messages              -> list of dicts, the synthesized/real
                                 Agent-Message-shaped rows (see module
                                 docstring)
        run_meta              -> dict of Agent-Run-shaped fields (name,
                                 creation, modified, status) to be normalized
                                 (ids/timestamps stripped)

    Returns a plain, JSON-serializable dict — safe to `json.dumps(...,
    indent=2, sort_keys=True)` and diff.
    """
    result = raw_trace.get("result")
    error = raw_trace.get("error")

    normalized = {
        "scenario": raw_trace["scenario"],
        "agent": normalize_agent_snapshot(raw_trace["agent"]),
        "prompt": raw_trace.get("prompt"),
        "context": raw_trace.get("context") or {},
        "tool_definitions": raw_trace.get("tool_definitions") or [],
        "state_transitions": list(raw_trace.get("state_transitions") or []),
        "terminal_status": raw_trace["terminal_status"],
        "run": {
            "run_id": _PLACEHOLDER_RUN_ID,
            "creation": _PLACEHOLDER_TIMESTAMP,
            "status": raw_trace.get("run_meta", {}).get("status"),
        },
        "messages": _normalize_messages(raw_trace.get("messages") or []),
    }

    if result is not None:
        normalized["final_output"] = getattr(result, "final_output", None)
        normalized["usage"] = _normalize_usage(getattr(result, "usage", None))
        normalized["cost"] = getattr(result, "cost", 0.0)
        normalized["tool_calls"] = _normalize_new_items(getattr(result, "new_items", None) or [])
        normalized["error"] = None
    else:
        normalized["final_output"] = None
        normalized["usage"] = {}
        normalized["cost"] = None
        normalized["tool_calls"] = []
        normalized["error"] = error

    return normalized


def _normalize_messages(messages):
    """Normalize a list of Agent-Message-shaped dicts: strip the doc name/
    timestamps to index-stable placeholders, keep role/kind/content. Tool
    Call / Tool Result message content dicts carry the same opaque
    provider-generated `id` field `_normalize_new_items` replaces with an
    index-stable placeholder — normalized here the same way (and kept
    consistent across the whole trace: the tool_call_id-to-placeholder
    mapping is shared with `_normalize_new_items` via `id_placeholders`, so a
    given real tool_call_id always maps to the same placeholder wherever it
    appears in the trace)."""
    normalized = []
    id_placeholders = {}

    def _placeholder_for(call_id):
        if call_id not in id_placeholders:
            id_placeholders[call_id] = f"<TOOL_CALL_ID:{len(id_placeholders)}>"
        return id_placeholders[call_id]

    for i, msg in enumerate(messages):
        entry = {
            "id": f"<MSG_ID:{i}>",
            "role": msg.get("role"),
            "kind": msg.get("kind"),
        }
        content = msg.get("content")
        if isinstance(content, str):
            content = _normalize_scalar(content)
        elif isinstance(content, dict) and "id" in content and msg.get("kind") in (
            "Tool Call",
            "Tool Result",
        ):
            content = dict(content)
            content["id"] = _placeholder_for(content["id"])
            if "arguments" in content:
                content["arguments"] = normalize_tool_args(content["arguments"])
            if "output" in content:
                content["output"] = normalize_tool_result(content["output"])
        entry["content"] = content
        normalized.append(entry)
    return normalized


def to_json(normalized_trace):
    """Deterministic JSON serialization for snapshotting: sorted keys, fixed
    indent, so byte-identical output across runs/machines for identical
    input (this is the whole point — see the module docstring)."""
    return json.dumps(normalized_trace, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
