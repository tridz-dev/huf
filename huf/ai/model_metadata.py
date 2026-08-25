"""Shared model-metadata resolution — currently just the context window.

Used by both the read-side context API (``agent_run_context_api.py``, for
runs that predate the ``model_context_window`` snapshot column or whose
snapshot is unset) and the write-side run persistence (``agent_integration.py``,
to snapshot the window at call time so later AI Model edits cannot rewrite
history).
"""

from __future__ import annotations

import re

import frappe

from huf.ai.providers.litellm import _normalize_model_name


def _context_window_from_litellm(model_name, provider_name, provider_brand):
    """Best-effort context-window lookup from LiteLLM's model-cost table.

    Mirrors the normalisation used to price a run (``_normalize_model_name``,
    also used by ``context_segments.py``) and the segment-aware key matching
    used by ``prompt_cache_capabilities.py`` to tolerate provider/vendor
    prefixes in LiteLLM's key names (Azure, Vertex, Bedrock, ...).

    Returns an int, or ``None`` if the model can't be resolved. Never raises
    — this backs a read-only analytics endpoint and a missing metadata entry
    must not fail the page.
    """
    if not model_name:
        return None

    try:
        import litellm

        normalized = _normalize_model_name(model_name, provider_name or "", brand=provider_brand)

        entry = litellm.model_cost.get(normalized)
        if entry is None:
            # normalized is "<prefix>/<model>"; the raw model name alone is
            # also a common key (e.g. "gpt-4-turbo" without "openai/").
            entry = litellm.model_cost.get(model_name)

        if entry is None:
            # Segment-aware fallback for keys LiteLLM prefixes with vendor
            # routing info that isn't captured by our own prefix mapping
            # (e.g. bedrock/, azure_ai/, region qualifiers).
            target = model_name.split("/", 1)[-1].lower()
            escaped_target = re.escape(target)
            segment_pattern = re.compile(rf"(^|[/\-.:@]){escaped_target}([/\-:@]|$)")
            for db_key, db_entry in litellm.model_cost.items():
                if segment_pattern.search(db_key.lower()):
                    entry = db_entry
                    break

        if not entry:
            return None

        context_window = entry.get("max_input_tokens")
        return int(context_window) if context_window else None
    except Exception:
        return None


def resolve_model_context_window(model_name, provider_name=None, provider_brand=None):
    """Resolve a model's context window, independent of any particular run.

    ``model_name`` is an ``AI Model`` link (its docname, which — per the
    doctype's ``field:model_name`` autoname — is normally the same string
    as its ``model_name`` field).

    Resolution order, most-authoritative first:
      1. ``AI Model.context_window`` — explicit metadata on the model record.
      2. LiteLLM's model-cost table, for models that don't carry an explicit
         value on the AI Model record.
      3. ``None`` — explicitly "unknown". Never falls back to a guessed
         constant: an unmeasured context window must render as unmeasured,
         not as a confident, likely-wrong number.

    A field is treated as "set" only when it is a truthy, non-zero int; 0
    and NULL both mean "not set" per the AI Model field convention.

    Never raises; returns ``None`` on any failure.
    """
    if not model_name:
        return None

    try:
        model_doc = frappe.get_cached_doc("AI Model", model_name)
    except Exception:
        return _context_window_from_litellm(model_name, provider_name, provider_brand)

    if model_doc.get("context_window"):
        return model_doc.context_window

    return _context_window_from_litellm(
        model_doc.get("model_name"), provider_name, provider_brand
    )
