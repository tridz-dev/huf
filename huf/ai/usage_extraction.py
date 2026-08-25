# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Single source of truth for per-round LLM usage extraction.

Usage payloads arrive from LiteLLM/OpenAI-style response objects, plain
dicts, or pydantic models, and different fields drift depending on the
provider (``prompt_tokens`` vs ``input_tokens``, ``cached_tokens`` vs
``cache_hit_tokens``, and so on). This extraction logic used to be copied
and independently patched in four places, and the copies had drifted out
of sync with each other:

  - huf/ai/providers/litellm.py (~lines 905-935) — round token counts fed
    into calculate_cost for the non-streaming completion path.
  - huf/ai/providers/litellm.py (~lines 995-1050) — accumulation of round
    usage into total_usage across multi-round tool-calling loops.
  - huf/ai/agent_integration.py (~lines 1830-1880) — sync-path re-extraction
    of usage from the agent run result.
  - huf/ai/agent_integration.py (~lines 2945-3000) — streaming-path
    re-extraction of usage from the agent run result.

Notably, the sync site fell back to a dict's ``input_tokens`` key while the
streaming site fell back to ``prompt_tokens`` — silently disagreeing about
which key wins when both key names could be present. This module resolves
that by accepting either as a fallback. It also deliberately does NOT read
``cache_miss_tokens`` as a cache-write source: that was a mislabelled
duplicate of the cache-creation value in some of the old sites, not a
genuine cache-write count, and folding it into ``cache_write_tokens`` here
would resurrect that bug.

Callers that used to inline this logic should call ``extract_round_usage``
instead and treat this module as canonical.
"""


def normalise_usage_payload(usage):
    """Return ``usage`` as a plain dict, or ``None`` if that is not possible.

    Accepts an already-plain dict (returned unchanged), a pydantic-style
    model exposing ``.dict()`` or ``.model_dump()``, or ``None``/anything
    else unsupported (returns ``None``).
    """
    if usage is None:
        return None
    if isinstance(usage, dict):
        return usage
    for method_name in ("model_dump", "dict"):
        method = getattr(usage, method_name, None)
        if callable(method):
            try:
                result = method()
            except Exception:
                continue
            if isinstance(result, dict):
                return result
    return None


def _as_int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _get(source, key):
    """Read ``key`` from ``source``, which may be a dict or an object."""
    if source is None:
        return None
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)


def _first(source, keys):
    """Return the first non-empty value among ``keys`` read off ``source``."""
    for key in keys:
        value = _get(source, key)
        if value:
            return value
    return None


def _extract_details(usage):
    """Fetch the nested prompt_tokens_details block, dict or object, or None."""
    details = _get(usage, "prompt_tokens_details")
    if not details:
        return None
    return details


def extract_round_usage(usage):
    """Extract a single round's token usage from a provider usage payload.

    ``usage`` may be a LiteLLM/OpenAI usage object, a plain dict, a
    pydantic model exposing ``.dict()``/``.model_dump()``, or ``None``.

    Always returns a dict with exactly these keys, each an ``int`` that
    defaults to ``0`` when the source value is missing or unparseable:

        input_tokens, output_tokens, cache_read_tokens, cache_write_tokens

    Never raises.
    """
    result = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    }
    if usage is None:
        return result

    try:
        result["input_tokens"] = _as_int(_first(usage, ("prompt_tokens", "input_tokens")))
        result["output_tokens"] = _as_int(_first(usage, ("completion_tokens", "output_tokens")))

        details = _extract_details(usage)

        result["cache_read_tokens"] = _as_int(
            _first(details, ("cached_tokens", "cache_hit_tokens"))
            or _first(usage, ("cached_tokens", "cache_hit_tokens"))
        )

        result["cache_write_tokens"] = _as_int(
            _first(
                details,
                (
                    "cache_creation_input_tokens",
                    "cache_write_tokens",
                    "cache_creation_tokens",
                ),
            )
            or _first(
                usage,
                (
                    "cache_creation_input_tokens",
                    "cache_write_input_tokens",
                    "cache_creation_tokens",
                ),
            )
        )
    except Exception:
        # Usage extraction is best-effort; never let a malformed payload
        # break the caller. Fall back to whatever fields were parsed so far.
        pass

    return result
