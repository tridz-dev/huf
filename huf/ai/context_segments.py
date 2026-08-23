# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Per-run context composition (segment_tokens) and cache prefix fingerprints
(prefix_breakpoints) for context/cache observability.

Token-counts each piece of a run's assembled prompt at the point where the
pieces still exist as separate objects. Knowledge context in particular is
fused into the user message string before it reaches the provider call and
cannot be recovered afterwards, so counting has to happen here, before that
fusion, not downstream in providers/litellm.py.

Breakpoint hashing mirrors the same three cache-control gates evaluated in
providers/litellm.py (static prefix is a runtime/context option, not an
Agent setting, so it is not reproduced here — see AGENTS.md notes on
prompt_cache_options). Per-breakpoint cache-hit attribution is deliberately
not attempted: providers report one aggregate cache_read count per run, not
per-block hits, and a wrong per-block guess is worse than an honest gap.

Two distinct measurement points, not one:

  - `compute_segment_tokens()` is called ONCE, pre-call, from
    agent_integration.py, before the LLM is invoked. It describes round 1's
    pre-call composition only: system, tools, knowledge, history, and the
    outgoing user message, as they exist before that first completion.
  - A single Agent Run can perform up to `max_turns` LLM completions. Every
    round after round 1 carries a message list that has grown by the
    assistant's tool-call request and every tool result from prior rounds —
    content `compute_segment_tokens()` never sees and that no other segment
    accounts for either. `count_tool_exchange_tokens()` measures exactly
    that growth, and `reconcile_composition()` compares the two measurement
    points (segments + tool exchange vs. the provider's own reported
    `prompt_tokens`) to surface when they diverge, i.e. when some other,
    still-uninstrumented context source exists. Conflating these two points
    — treating segment_tokens as if it described the whole run — is the
    defect this module now guards against.
"""

import hashlib

import frappe
from litellm import token_counter

from huf.ai.prompt_cache_capabilities import model_supports_prompt_caching
from huf.ai.providers.litellm import _normalize_model_name
from huf.ai.tool_serializer import serialize_tools


def _count(pricing_model, text):
    if not text:
        return 0
    try:
        return token_counter(model=pricing_model, text=text)
    except Exception:
        return None


def _hash_prefix(text):
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16]


def compute_segment_tokens(agent_doc, agent, resolved_model, resolved_provider, history, knowledge_context, prompt):
    """Best-effort token count per composition segment.

    Returns a dict with keys system/tools/knowledge/history/message. A
    segment is `None` (not 0) when it could not be counted — callers must
    not treat a missing segment as zero-cost.
    """
    pricing_model = _normalize_model_name(resolved_model, resolved_provider)

    system_text = "\n".join(filter(None, [getattr(agent, "instructions", None)]))

    try:
        tools_schema = serialize_tools(getattr(agent, "tools", None) or [])
        tools_text = frappe.as_json(tools_schema) if tools_schema else ""
    except Exception:
        tools_text = None

    knowledge_text = (knowledge_context or {}).get("context_text") if knowledge_context else ""

    try:
        history_text = "\n".join(
            str(item.get("content", "")) for item in (history or []) if isinstance(item, dict)
        )
    except Exception:
        history_text = None

    return {
        "system": _count(pricing_model, system_text),
        "tools": _count(pricing_model, tools_text) if tools_text is not None else None,
        "knowledge": _count(pricing_model, knowledge_text) if knowledge_text is not None else None,
        "history": _count(pricing_model, history_text) if history_text is not None else None,
        "message": _count(pricing_model, prompt),
    }


def compute_prefix_breakpoints(agent_doc, agent, resolved_model, resolved_provider, history):
    """Fingerprint the cache-control breakpoints this run's settings would gate.

    Mirrors the enable_prompt_caching / cache_system_message /
    cache_conversation_history gates in providers/litellm.py without
    threading state through the provider call. One entry per active
    breakpoint; empty list when caching is off or unsupported.
    """
    if not agent_doc or not agent_doc.get("enable_prompt_caching"):
        return []

    try:
        if not model_supports_prompt_caching(resolved_model, resolved_provider):
            return []
    except Exception:
        return []

    breakpoints = []

    if agent_doc.get("cache_system_message") and getattr(agent, "instructions", None):
        prefix_hash = _hash_prefix(agent.instructions)
        if prefix_hash:
            breakpoints.append({"marker": "instructions", "prefix_hash": prefix_hash})

    if agent_doc.get("cache_conversation_history") and history:
        last_content = history[-1].get("content") if isinstance(history[-1], dict) else None
        prefix_hash = _hash_prefix(last_content if isinstance(last_content, str) else None)
        if prefix_hash:
            breakpoints.append({"marker": "history", "prefix_hash": prefix_hash})

    return breakpoints


def _extract_message_text(content):
    """Flatten a message's `content` to plain text for token counting.

    `content` is usually a plain string, but this codebase also produces
    the multimodal list-of-content-blocks shape via `_build_text_content`
    (e.g. `[{"type": "text", "text": "...", "cache_control": {...}}]`).
    Non-text blocks (e.g. image_url parts) contribute no text here.
    """
    if not content:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text")
                if text:
                    parts.append(str(text))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content)


def _normalize_tool_call(tool_call):
    """Reduce one tool call (dict or SDK object) to a plain {name, arguments} dict.

    litellm's non-streaming path attaches SDK objects (e.g.
    ChatCompletionMessageToolCall) to `assistant_message["tool_calls"]`; the
    streaming path attaches plain dicts assembled from delta chunks. Both
    shapes occur in practice and are normalized here so serialisation is
    uniform regardless of which provider loop produced the message.
    """
    if isinstance(tool_call, dict):
        function = tool_call.get("function") or {}
        return {
            "name": function.get("name") if isinstance(function, dict) else None,
            "arguments": function.get("arguments") if isinstance(function, dict) else None,
        }
    function = getattr(tool_call, "function", None)
    return {
        "name": getattr(function, "name", None) if function is not None else None,
        "arguments": getattr(function, "arguments", None) if function is not None else None,
    }


def count_tool_exchange_tokens(pricing_model, messages):
    """Best-effort token count of the tool exchange within `messages`.

    `messages` is the running message list from the provider loop (or, for
    O(rounds) accumulation, just the slice appended in the current round —
    see providers/litellm.py). Counts exactly two things:

      - assistant messages carrying `tool_calls`: the serialised tool-call
        payload (name + arguments), not the message's `content` — a
        tool-calling assistant turn's content is frequently empty and is
        not the thing we're trying to measure here.
      - messages with role == "tool": the tool result content.

    Deliberately does NOT count the system message, the original user
    message, or ordinary assistant prose — those are already covered by
    `compute_segment_tokens()`'s five categories, and double-counting them
    would make composition percentages wrong.

    Returns an int (0 for an empty/no-op exchange), or `None` if counting
    failed for any message — same discipline as `_count`; a partial count
    would understate the true figure and mislead reconciliation more than
    an honest "unknown".
    """
    if not messages:
        return 0

    total = 0
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = message.get("role")

        if role == "assistant" and message.get("tool_calls"):
            try:
                normalized_calls = [_normalize_tool_call(tc) for tc in message["tool_calls"]]
                payload = frappe.as_json(normalized_calls)
            except Exception:
                return None
            count = _count(pricing_model, payload)
            if count is None:
                return None
            total += count

        elif role == "tool":
            text = _extract_message_text(message.get("content"))
            if not text:
                continue
            count = _count(pricing_model, text)
            if count is None:
                return None
            total += count

    return total


def reconcile_composition(segment_tokens, tool_exchange_tokens, provider_prompt_tokens, tolerance=0.15):
    """Compare counted context composition against the provider's reported prompt size.

    Compares `sum(segment_tokens.values()) + tool_exchange_tokens`
    against `provider_prompt_tokens` for the same measurement point.
    Divergence beyond `tolerance` (a fraction of `provider_prompt_tokens`)
    signals an uninstrumented context source — something contributing to
    the provider's prompt that no segment and no tool-exchange count
    accounts for. Logs a warning naming both figures in that case; never
    raises and never fails a run.

    An unknown input makes the whole comparison unknown, and each returns
    `None` rather than being coerced to 0:

      - any `None` in `segment_tokens` (a segment that could not be counted),
      - `tool_exchange_tokens` of `None` (the tool exchange could not be
        counted) — summing it as 0 would understate `counted` and report a
        divergence that is purely an artefact of the failed count,
      - a falsy `provider_prompt_tokens` (nothing to compare against).

    A `tool_exchange_tokens` of 0 is a real measurement, not an unknown: a
    single-round run genuinely has no tool exchange, and it reconciles normally.

    Returns a dict with keys `counted`, `reported`, `delta_ratio`,
    `within_tolerance`, or `None` when the comparison could not be made.
    """
    try:
        if not provider_prompt_tokens:
            return None
        if not isinstance(segment_tokens, dict) or not segment_tokens:
            return None
        if any(value is None for value in segment_tokens.values()):
            return None
        if tool_exchange_tokens is None:
            # Unknown, not zero: summing it as 0 would understate `counted` and
            # report a divergence that is an artefact of the failed count.
            return None

        counted = sum(segment_tokens.values()) + tool_exchange_tokens
        reported = provider_prompt_tokens
        delta_ratio = abs(counted - reported) / reported
        within_tolerance = delta_ratio <= tolerance

        if not within_tolerance:
            frappe.logger("huf").warning(
                "Context composition mismatch: counted %s tokens (segments + tool exchange) "
                "vs provider-reported prompt_tokens=%s (delta_ratio=%.2f%%, tolerance=%.0f%%). "
                "This suggests an uninstrumented context source.",
                counted, reported, delta_ratio * 100, tolerance * 100,
            )

        return {
            "counted": counted,
            "reported": reported,
            "delta_ratio": delta_ratio,
            "within_tolerance": within_tolerance,
        }
    except Exception:
        # Reconciliation is diagnostic-only; never let it break a run.
        return None
