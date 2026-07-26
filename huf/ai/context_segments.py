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
