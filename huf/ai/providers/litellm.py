# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Unified LiteLLM Provider Implementation

This module provides a unified interface to 100+ LLM providers via LiteLLM.
It replaces the need for separate provider implementations while maintaining
100% backward compatibility with existing Huf configurations.

Features:
- Supports all LiteLLM providers (OpenAI, Anthropic, Google, OpenRouter, xAI, Mistral, etc.)
- Unified tool calling format (OpenAI-compatible)
- Built-in retry logic, cost tracking, and error handling
- Automatic model name normalization for seamless migration
"""

import asyncio
import base64
import json
import os
import re
import time
from types import SimpleNamespace

import frappe
import litellm
from litellm import InternalServerError, RateLimitError, APIError, BadRequestError, ContextWindowExceededError
from litellm.utils import trim_messages
from huf.ai.tool_serializer import serialize_tools
from huf.ai.prompt_cache_capabilities import model_supports_prompt_caching
from huf.ai.prompt_cache.capabilities import resolve_capabilities
from huf.ai.transaction import transaction_checkpoint
from huf.ai.cost_calculator import calculate_cost
from huf.ai.conversation_manager import repair_message_sequence
from huf.ai.usage_extraction import extract_round_usage, normalise_usage_payload
from huf.ai.reasoning import (
    ReasoningPolicy,
    ReasoningResolution,
    detect_model_capabilities,
    resolve_reasoning,
    build_reasoning_kwargs,
)

class _LazyLogger:
	"""Defer frappe.logger() until first use so test discovery can import this module."""

	def __getattr__(self, name):
		return getattr(frappe.logger("huf"), name)


logger = _LazyLogger()

# Default request timeout for LiteLLM completion calls (seconds), used as the
# ultimate fallback when a per-provider timeout_seconds is unavailable.
_DEFAULT_LITELLM_TIMEOUT = 180


def _provider_timeout(provider_doc) -> int:
    """Resolve the request timeout (seconds) for a given AI Provider doc.

    Prefers the provider's own `timeout_seconds` field; falls back to
    `_DEFAULT_LITELLM_TIMEOUT` when the doc is missing, has no value, or the
    field is falsy (0/None) so a misconfigured provider never ends up with a
    zero/no timeout.
    """
    if provider_doc is not None:
        value = provider_doc.get("timeout_seconds")
        if value:
            return value
    return _DEFAULT_LITELLM_TIMEOUT


class SimpleResult:
    """Result structure for provider responses"""

    def __init__(self, final_output, usage=None, new_items=None, cost=0.0):
        self.final_output = final_output
        self.usage = usage or {}
        self.new_items = new_items or []
        self.cost = cost


class ProviderUnavailableError(Exception):
    """Raised when the LLM provider cannot serve this request (conn refused, model missing,
    bad model prefix, auth). Distinct from content-level errors."""

    def __init__(self, public_message: str, *, log_message: str | None = None):
        super().__init__(public_message)
        self.public_message = public_message
        self.log_message = log_message or public_message


def _sanitize_provider_error_message(raw_message: str, normalized_model: str | None = None) -> str:
    """Return a user-safe provider error message with no LiteLLM/provider internals."""
    text = (raw_message or "").lower()

    if "api key not configured" in text or "password not found" in text or "invalid api key" in text:
        return "This provider is not configured correctly yet. Add or update its API key and try again."

    if any(marker in text for marker in (
        "no longer available",
        "model not found",
        "notfounderror",
        "unsupported model",
    )):
        return "The selected model is no longer available from this provider. Choose a different model and try again."

    if "ratelimit" in text or "rate limit" in text or "too many requests" in text:
        return "This provider is rate-limiting requests right now. Please wait a moment and try again."

    if "contextwindowexceedederror" in text or "context window" in text or "maximum context length" in text:
        return "This conversation is too large for the selected model. Start a new conversation or reduce the context and try again."

    if any(marker in text for marker in (
        "internalservererror",
        "server error",
        "service unavailable",
        "temporarily unavailable",
        "connection refused",
        "failed to connect",
        "connection error",
        "connection reset",
        "broken pipe",
        "unexpected eof",
    )):
        return "The AI provider is temporarily unavailable. Please try again in a moment."

    model_hint = f" for {normalized_model}" if normalized_model else ""
    return f"The AI provider could not complete this request{model_hint}. Please try again or choose a different model."


def _raise_provider_unavailable(raw_message: str, normalized_model: str | None = None):
    raise ProviderUnavailableError(
        _sanitize_provider_error_message(raw_message, normalized_model),
        log_message=raw_message,
    )


# High-performance in-memory cache for provider capabilities.
#
# This sits IN FRONT of Redis, so it has to honour the same expiry Redis does.
# It previously stored a bare flag with no expiry and no eviction: once a
# negative result was recorded, the Redis key could expire but the worker kept
# reading its own copy forever, and `frappe.cache().delete_value()` could not
# reach it. That reinstated exactly the permanent poisoning the Redis TTL was
# added to prevent, for the lifetime of the process.
#
# Entries are therefore (value, expires_at) and are keyed per site: frappe's own
# cache is site-scoped, but a worker process is shared across sites on a
# multi-tenant bench, so an unscoped key let one site's negative result suppress
# a parameter for every other site in that process.
_L1_CAPABILITY_CACHE: dict[str, tuple[object, float]] = {}
_L1_CAPABILITY_CACHE_MAX_ENTRIES = 2048


def _site_scoped_key(key: str) -> str:
    """Namespace a capability cache key by site, mirroring frappe.cache()."""
    site = getattr(frappe.local, "site", None) or "__no_site__"
    return f"{site}:{key}"


def _l1_get(key: str):
    """Read a non-expired L1 entry, or None."""
    entry = _L1_CAPABILITY_CACHE.get(key)
    if entry is None:
        return None
    value, expires_at = entry
    if expires_at <= time.time():
        _L1_CAPABILITY_CACHE.pop(key, None)
        return None
    return value


def _l1_set(key: str, value, ttl: int) -> None:
    """Record an L1 entry with the same lifetime as its Redis counterpart."""
    if len(_L1_CAPABILITY_CACHE) >= _L1_CAPABILITY_CACHE_MAX_ENTRIES:
        # Cheap bound: drop everything already expired, and if that frees
        # nothing, clear outright rather than grow without limit.
        now = time.time()
        for k in [k for k, (_, exp) in _L1_CAPABILITY_CACHE.items() if exp <= now]:
            _L1_CAPABILITY_CACHE.pop(k, None)
        if len(_L1_CAPABILITY_CACHE) >= _L1_CAPABILITY_CACHE_MAX_ENTRIES:
            _L1_CAPABILITY_CACHE.clear()
    _L1_CAPABILITY_CACHE[key] = (value, time.time() + ttl)


def _estimate_prefix_tokens(messages: list) -> int:
    """
    Estimate total tokens in all messages up to and including the last message.
    Used to check if the cacheable prefix meets the model's minimum threshold.

    This is a conservative estimate: 1 token per 4 characters of text.
    Actual token count may vary slightly per model.
    """
    total_chars = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text", "")
                    if isinstance(text, str):
                        total_chars += len(text)

    # Conservative estimate: 1 token per 4 characters
    # Add 10% margin for overhead (roles, formatting, etc.)
    return int(total_chars / 4 * 1.1)


def _is_transient_litellm_error(exc: Exception) -> bool:
    """Return True for transient network errors that a retry may resolve."""
    msg = str(exc).lower()
    if any(k in msg for k in (
        "broken pipe", "connection reset", "connection aborted",
        "connection error", "unexpected eof", "remote end closed",
        "connection refused", "failed to connect",
    )):
        return True
    if isinstance(exc, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
        return True
    return False


async def _litellm_completion_with_retry(**completion_kwargs):
    """Call litellm.completion with transient-error retries and backoff."""
    max_retries = completion_kwargs.pop("_huf_max_retries", 2)
    base_delay = completion_kwargs.pop("_huf_base_delay", 0.5)

    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return await asyncio.to_thread(litellm.completion, **completion_kwargs)
        except Exception as exc:
            # Broad catch so _is_transient_litellm_error can classify and retry only known transient failures.
            last_exc = exc
            if attempt < max_retries and _is_transient_litellm_error(exc):
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    f"LiteLLM transient error (attempt {attempt + 1}/{max_retries + 1}): {exc}. Retrying in {delay}s"
                )
                await asyncio.sleep(delay)
                continue
            raise
    raise last_exc


def _get_prompt_cache_options(context: dict | None) -> dict:
    if not isinstance(context, dict):
        return {}
    options = context.get("prompt_cache_options")
    return options if isinstance(options, dict) else {}


# --- Sampling parameter rejection detection -----------------------------------
#
# Providers reject an unsupported sampling parameter with a free-text message. A
# bare `"top_p" in err_msg` substring test is not safe: providers routinely list
# the parameters they DO accept after naming the one they actually rejected, e.g.
#     "Unsupported parameter: 'response_format' is not supported with this model.
#      Supported parameters: temperature, top_p, max_tokens."
# Reading that as a top_p rejection drops top_p, retries, fails again on the real
# cause, and poisons the negative cache for that model. So strip any trailing
# "supported parameters: ..." enumeration before looking for the parameter, and
# match the parameter as a whole word rather than a substring.

# Strip only the enumeration itself -- up to the next sentence end or newline --
# not the rest of the message. A greedy match to end-of-string erased any
# rejection that came AFTER the accepted-parameter list, e.g.
#   "unsupported parameter: 'response_format'. supported parameters: temperature,
#    max_tokens. additionally, top_p is not supported for this model."
# where the real top_p rejection is the final sentence.
_SUPPORTED_PARAMS_ENUMERATION_RE = re.compile(r"\bsupported parameters?\s*:[^.\n]*", re.IGNORECASE)

# URLs in error bodies routinely contain a parameter name as a doc anchor
# ("see https://docs.../api#top_p"). Matching that as a rejection would drop the
# parameter and cache a negative result for a model that supports it.
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_REJECTION_VERBS = (
    "deprecated",
    "unsupported",
    "not supported",
    "does not support",
    "does not accept",
    "not accepted",
    "not permitted",
    "not allowed",
)

# Negative capability results are cached so a known-bad combination does not pay a
# failed round-trip on every call. They expire so that a provider adding support --
# or a single false positive slipping through -- self-heals, instead of disabling
# the parameter for that model forever with no invalidation path.
_SAMPLING_NEGATIVE_CACHE_TTL = 60 * 60 * 24 * 7  # 7 days


def _param_rejected(err_msg: str, param: str) -> bool:
    """True when `err_msg` names `param` as the parameter the model rejected."""
    if not err_msg:
        return False
    subject = _URL_RE.sub("", err_msg)
    subject = _SUPPORTED_PARAMS_ENUMERATION_RE.sub("", subject)
    if not re.search(rf"\b{re.escape(param)}\b", subject):
        return False
    return any(verb in subject for verb in _REJECTION_VERBS)


# --- Prompt cache mode resolution -------------------------------------------------
#
# `Agent.prompt_cache_mode` (Select: Auto/Off/Advanced) is the single authority over
# prompt caching. The four legacy fields (enable_prompt_caching, cache_control_type,
# cache_system_message, cache_conversation_history) are read ONLY in Advanced mode.
#
# The crux: an Agent with mode=Auto caches even though its legacy
# `enable_prompt_caching` checkbox is 0 — Auto does not consult that field at all.
# A missing/blank/unrecognised mode resolves to Auto, never Off: the migration patch
# leaves prompt_cache_mode NULL on Agents that had no legacy caching data, and
# treating NULL as Off would silently switch caching off for exactly those rows.
#
# Both run() and run_stream() call _resolve_cache_settings(); neither reads the
# legacy fields directly any more. Routing both paths through one function is what
# makes sync/stream divergence structurally impossible.

PROMPT_CACHE_MODE_AUTO = "Auto"
PROMPT_CACHE_MODE_OFF = "Off"
PROMPT_CACHE_MODE_ADVANCED = "Advanced"

_PROMPT_CACHE_MODES = {
    "auto": PROMPT_CACHE_MODE_AUTO,
    "off": PROMPT_CACHE_MODE_OFF,
    "advanced": PROMPT_CACHE_MODE_ADVANCED,
}

# HUF's provider-appropriate defaults for Auto mode. Cache the instruction/system
# prefix and place the single moving boundary on the latest user message; the
# per-segment legacy checkboxes do not gate anything here.
_AUTO_CACHE_CONTROL_TYPE = "ephemeral"


def resolve_prompt_cache_mode(agent_doc) -> str:
    """Normalise Agent.prompt_cache_mode. Missing/blank/unknown -> Auto (never Off)."""
    raw = None
    if agent_doc is not None:
        try:
            raw = agent_doc.get("prompt_cache_mode")
        except AttributeError:
            raw = getattr(agent_doc, "prompt_cache_mode", None)
    if not isinstance(raw, str):
        return PROMPT_CACHE_MODE_AUTO
    return _PROMPT_CACHE_MODES.get(raw.strip().lower(), PROMPT_CACHE_MODE_AUTO)


class ResolvedCacheSettings:
    """Effective, mode-resolved prompt-cache settings for one provider call."""

    __slots__ = (
        "mode",
        "enabled",
        "cache_control_type",
        "cache_static_prefix",
        "cache_system_message",
        "cache_dynamic_content",
        "allow_provider_cache_params",
    )

    def __init__(
        self,
        mode,
        enabled,
        cache_control_type,
        cache_static_prefix,
        cache_system_message,
        cache_dynamic_content,
        allow_provider_cache_params,
    ):
        self.mode = mode
        self.enabled = enabled
        self.cache_control_type = cache_control_type
        self.cache_static_prefix = cache_static_prefix
        self.cache_system_message = cache_system_message
        self.cache_dynamic_content = cache_dynamic_content
        self.allow_provider_cache_params = allow_provider_cache_params

    def as_dict(self) -> dict:
        return {slot: getattr(self, slot) for slot in self.__slots__}

    def __eq__(self, other):
        if not isinstance(other, ResolvedCacheSettings):
            return NotImplemented
        return self.as_dict() == other.as_dict()

    def __repr__(self):
        return f"ResolvedCacheSettings({self.as_dict()})"


# Table/checkbox fields on Agent that can contribute a callable tool. Any one of
# them means a single user turn may run more than one provider round.
_AGENT_TOOL_BEARING_FIELDS = (
    "agent_tool",
    "agent_mcp_server",
    "agent_skill",
    "ssh_connections",
    "enable_lazy_tools",
    "enable_memory_search_tool",
    "enable_memory_write_tool",
)


def _agent_field(agent_doc, fieldname):
    """Read one field off an Agent that may be a dict, a Document, or a namespace."""
    if agent_doc is None:
        return None
    try:
        return agent_doc.get(fieldname)
    except (AttributeError, TypeError):
        return getattr(agent_doc, fieldname, None)


def _agent_can_tool_loop(agent_doc) -> bool:
    """True when this Agent can emit tool calls, i.e. one user turn can run
    several provider rounds.

    This is the gate for Auto's dynamic (latest-user-message) breakpoint. See
    _resolve_cache_settings() for the measurement that motivates it.
    """
    for fieldname in _AGENT_TOOL_BEARING_FIELDS:
        if _agent_field(agent_doc, fieldname):
            return True
    return False


def _resolve_cache_settings(
    agent_doc, prompt_cache_options=None, is_local_llm=False, agent_has_tools=None
):
    """Resolve prompt_cache_mode into the effective per-segment cache gates.

    Called from BOTH run() and run_stream() so the two paths can never diverge.

    Auto      -> caching on with HUF defaults; legacy fields and the granular
                 prompt_cache_options flags are ignored. The system/static
                 breakpoint is unconditional; the dynamic (latest-user-message)
                 breakpoint is placed ONLY when the Agent can emit tool calls.

                 Why the dynamic breakpoint is conditional (measured on
                 caching-phase0.local, claude-haiku-4-5, 23k-char system prompt):

                 * Across user TURNS the dynamic entry is never read back. The
                   latest user turn is sent as the enhanced_prompt wrapper
                   ("Current user message: ...") but re-enters the next request
                   from conversation history as the bare persisted text, so the
                   block sitting at the breakpoint differs on the very next call
                   and the longest matching prefix stops at the system block.
                   Measured on a fresh conversation with a strictly growing
                   history: cache_read stayed pinned at 5088 (the system prefix)
                   for four consecutive calls while cache_creation was paid every
                   call. Net effect for a tool-less agent: 53.6% saving with the
                   dynamic breakpoint vs 59.1% without it.
                 * Within ONE turn's tool loop the breakpoint IS read back: the
                   marked block is fixed while tool_calls/tool results append
                   after it. Measured over a forced 4-round turn: 11094 units
                   with the dynamic breakpoint vs 12182 without (8.9% cheaper).

                 The gate is derived from the Agent doc's tool-bearing
                 fields, NOT from the runtime `agent.tools` list: HUF attaches
                 the `get_result_context` internal-capability tool to every
                 agent, so `bool(agent.tools)` is unconditionally true and
                 cannot discriminate. `agent_has_tools` stays available for a
                 caller that has a better-filtered signal (and for tests).

                 This field alone (`cache_dynamic_content`) only says a turn
                 CAN loop, not that it WILL. A tool-bearing agent that resolves
                 in a single round still paid for a marker it never read back
                 within the turn: round 0 wrote it (1.25x on the dynamic
                 suffix) and there was no round 1 to read it. Because of that,
                 run()/run_stream() apply a SECOND, round-level gate on top of
                 this one: the dynamic marker is attached to the user message
                 only from round_num >= 1 onward (i.e. once a second provider
                 round is actually happening), never at round 0. Break-even is
                 3 rounds: the extra write costs write_rate/read_rate ~= 1.25x
                 once, and each later round that reads it back instead of
                 re-writing it saves ~1.25x - 0.10x = ~1.15x of that same
                 block, i.e. round 2 recoups most of the round-1 write and
                 round 3 is where the loop is unambiguously cheaper than never
                 marking at all. A single-round turn now costs nothing extra
                 for the dynamic breakpoint, regardless of this field's value.
    Off       -> full bypass; no HUF-injected cache_control markers and no
                 cache-related provider kwargs, whatever the legacy fields say.
    Advanced  -> the pre-existing behaviour: legacy `enable_prompt_caching` acts
                 as the sub-toggle, the legacy per-segment checkboxes and
                 cache_control_type apply, and prompt_cache_options'
                 cache_static_prefix / cache_dynamic_content overrides are honoured.
    """
    options = prompt_cache_options if isinstance(prompt_cache_options, dict) else {}
    mode = resolve_prompt_cache_mode(agent_doc)

    # Local providers (Ollama/LM Studio) do not support cache_control blocks.
    if mode == PROMPT_CACHE_MODE_OFF or is_local_llm:
        return ResolvedCacheSettings(
            mode=mode,
            enabled=False,
            cache_control_type=_AUTO_CACHE_CONTROL_TYPE,
            cache_static_prefix=False,
            cache_system_message=False,
            cache_dynamic_content=False,
            # Off must set no cache-related provider options at all. Local LLMs keep
            # the pre-existing behaviour of passing them through untouched.
            allow_provider_cache_params=(mode != PROMPT_CACHE_MODE_OFF),
        )

    if mode == PROMPT_CACHE_MODE_ADVANCED:
        enabled = bool(agent_doc.get("enable_prompt_caching", 0)) if agent_doc else False
        cache_control_type = (
            (agent_doc.get("cache_control_type") if agent_doc else None) or _AUTO_CACHE_CONTROL_TYPE
        )
        cache_system_message = bool(agent_doc.get("cache_system_message", 0)) if agent_doc else False
        cache_dynamic_content = (
            bool(agent_doc.get("cache_conversation_history", 0)) if agent_doc else False
        )
        override = options.get("cache_dynamic_content")
        if isinstance(override, bool):
            cache_dynamic_content = override
        return ResolvedCacheSettings(
            mode=mode,
            enabled=enabled,
            cache_control_type=cache_control_type,
            cache_static_prefix=bool(options.get("cache_static_prefix", True)),
            cache_system_message=cache_system_message,
            cache_dynamic_content=cache_dynamic_content,
            allow_provider_cache_params=True,
        )

    # Auto: HUF's provider-appropriate defaults. The dynamic breakpoint only
    # earns its 1.25x write when a turn can run more than one round.
    if isinstance(agent_has_tools, bool):
        can_tool_loop = agent_has_tools
    else:
        can_tool_loop = _agent_can_tool_loop(agent_doc)
    return ResolvedCacheSettings(
        mode=PROMPT_CACHE_MODE_AUTO,
        enabled=True,
        cache_control_type=_AUTO_CACHE_CONTROL_TYPE,
        cache_static_prefix=True,
        cache_system_message=True,
        cache_dynamic_content=can_tool_loop,
        allow_provider_cache_params=True,
    )


def _build_text_content(text: str, provider_name: str, cache_enabled: bool, cache_control_type: str):
    """Build provider-compatible message content payload with optional cache marker."""
    if not cache_enabled:
        return text

    if provider_name == "anthropic":
        return [{"type": "text", "text": text, "cache_control": {"type": cache_control_type}}]

    return [{"type": "text", "text": text}]


def _apply_dynamic_cache_marker(content, provider_name: str, cache_control_type: str):
    """Attach the dynamic (latest-user-message) cache_control marker to an
    already-built user message content payload, in place of building it fresh.

    Used by the round gate in run()/run_stream(): round 0's user content is
    always built marker-free (via _build_text_content(..., cache_enabled=False,
    ...)), and this function upgrades that same content once round_num >= 1,
    preserving any non-text parts (e.g. image blocks) already appended to it.

    Anthropic-only, mirroring _build_text_content: other providers' content is
    returned unchanged.
    """
    if provider_name != "anthropic":
        return content

    if isinstance(content, str):
        return [{"type": "text", "text": content, "cache_control": {"type": cache_control_type}}]

    if isinstance(content, list):
        new_content = list(content)
        for i, part in enumerate(new_content):
            if isinstance(part, dict) and part.get("type") == "text":
                marked = dict(part)
                marked["cache_control"] = {"type": cache_control_type}
                new_content[i] = marked
                return new_content
        # No text part to mark (unexpected shape) — leave content untouched
        # rather than guess where a marker would belong.
        return content

    return content


def _find_last_user_message_index(messages: list) -> int:
    """Scan `messages` backwards for the last entry with role == "user".

    Used by the dynamic-marker round gate in run()/run_stream() in place of a
    fixed index captured before trim_messages()/repair_message_sequence()
    ran. Those two calls can drop or rewrite entries (e.g.
    repair_message_sequence() strips an assistant message carrying
    unfulfilled tool_calls and inserts a synthetic one, which is exactly what
    a sliding-window get_conversation_history() produces when it cuts through
    a previous tool loop) — a captured-once index then points at the wrong
    message and the marker silently never applies. After round 0 only
    assistant/tool messages are appended, so at the point the gate fires the
    last user message in the current list is always the turn anchor; the
    scan is re-run fresh each time rather than trusting a stale offset.

    Returns -1 if no user message is found.
    """
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if isinstance(msg, dict) and msg.get("role") == "user":
            return i
    return -1


def _format_conversation_history(conversation_history: list) -> list:
    """Format conversation history messages without adding cache markers.

    Cache markers are applied only to the current user message, not to the history,
    to avoid wasting breakpoint budget and ensure the marker is placed on stable,
    reusable content (the latest user turn).

    Note: The provider_name and cache_control_type parameters have been removed
    since cache markers are now exclusively applied to the current user message.
    """
    if not conversation_history:
        return []

    formatted = [dict(msg) for msg in conversation_history]
    return formatted


def _file_dict_to_data_image_url(file_dict: dict) -> dict | None:
    """Embed a local Frappe file as a base64 data URI for multimodal LLM calls.

    Cloud providers cannot fetch localhost or authenticated /private/files/ URLs.
    """
    if not file_dict.get("is_image"):
        return None

    file_id = file_dict.get("file_id")
    file_url = file_dict.get("file_url")
    if not file_id and not file_url:
        return None

    try:
        from huf.ai.ocr_engine import _mime_type_and_extension, _resolve_file_doc

        file_doc = _resolve_file_doc(file_id=file_id, file_url=file_url)
        file_path = file_doc.get_full_path()
        if not os.path.exists(file_path):
            frappe.log_error(
                title="LiteLLM Image Embed",
                message=f"Image file not found on disk: {file_path}",
            )
            return None

        mime_type, _ = _mime_type_and_extension(file_path, file_doc.file_type)
        with open(file_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
        return {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded}"}}
    except (frappe.DoesNotExistError, frappe.ValidationError, ValueError, KeyError, TypeError, AttributeError) as e:
        logger.warning(f"Validation/Operation warning: {e!s}")
    except Exception as e:  # boundary exception handler: external provider/tool boundary
        logger.warning(f"Failed to embed image for LLM: {e}\n{frappe.get_traceback()}")
        return None


def _append_context_images_to_user_content(user_content, files: list):
    """Append base64-embedded image parts from context files to user message content."""
    image_parts = []
    for file_dict in files:
        part = _file_dict_to_data_image_url(file_dict)
        if part:
            image_parts.append(part)

    if not image_parts:
        return user_content

    if isinstance(user_content, str):
        user_content = [{"type": "text", "text": user_content}]
    elif isinstance(user_content, list):
        user_content = list(user_content)
    else:
        user_content = [{"type": "text", "text": str(user_content)}]

    user_content.extend(image_parts)
    return user_content


async def _execute_tool_call(tool, args_json, context=None, tool_call_id=None):
    """Execute a tool call and return the result.

    Huf passes a plain dict as ``context`` (conversation_id, agent_run_id, …). Tools built with
    the Agents SDK ``@function_tool`` expect a ``ToolContext`` with ``tool_name``; passing a dict
    causes 'dict' object has no attribute 'tool_name'. Wrap dicts in ``ToolContext`` while keeping
    the Huf payload on ``ToolContext.context`` so ``sdk_tools`` can still merge it into args.
    """
    args_str = args_json if isinstance(args_json, str) else json.dumps(args_json or {})

    invoke_ctx = context
    if isinstance(context, dict):
        from agents.tool_context import ToolContext
        from agents.usage import Usage

        invoke_ctx = ToolContext(
            context,
            usage=Usage(),
            tool_name=tool.name,
            tool_call_id=tool_call_id if tool_call_id is not None else "",
            tool_arguments=args_str,
        )

    return await tool.on_invoke_tool(invoke_ctx, args_str)


def _find_tool(agent, tool_name):
    """Find a tool by name in the agent's tools"""
    return next((t for t in agent.tools if t.name == tool_name), None)


def _tool_calls_signature(tool_calls_list: list) -> tuple:
    """Return a hashable signature for a list of tool calls.

    IDs are ignored so that repeated identical calls with fresh IDs are
    detected as loops.
    """
    parts = []
    for tc in tool_calls_list:
        fn = tc.get("function", {})
        args = fn.get("arguments", "")
        try:
            args = json.dumps(json.loads(args), sort_keys=True) if args else ""
        except Exception:
            args = str(args)
        parts.append((fn.get("name", ""), args))
    return tuple(parts)


def _get_agent_max_context_chars(agent_doc) -> int:
    """Return the agent's configured tool-result context threshold."""
    try:
        value = int(getattr(agent_doc, "max_context_chars", 2000) or 2000)
    except (ValueError, TypeError):
        value = 2000
    # Enforce a sensible floor so truncation notices still fit.
    return max(value, 500)


def _truncate_tool_result_for_context(result_content, max_context_chars: int = 2000) -> str:
    """
    Truncate a tool result before feeding it back to the LLM in the same run.

    Large tool results (e.g. full document payloads returned by custom functions)
    explode the context window and can confuse the agent into calling the same
    tool repeatedly.  We keep the full result in the Agent Tool Call record for
    audit / reference; the in-context copy is capped to ``max_context_chars``.
    """
    if result_content is None:
        return ""
    if not isinstance(result_content, str):
        result_content = str(result_content)

    # Defensive floor in case this helper is ever called directly.
    max_context_chars = max(max_context_chars, 500)

    if len(result_content) <= max_context_chars:
        return result_content

    notice = (
        f"\n\n... [Tool result truncated from {len(result_content)} characters "
        f"to {max_context_chars} characters to protect the context window.]"
    )
    keep = max(max_context_chars - len(notice), 200)
    return result_content[:keep] + notice


def _normalize_model_name(model: str, provider: str, brand: str = None) -> str:
    """
    Normalize model name to LiteLLM format.

    If model already has provider prefix (e.g., "openai/gpt-4-turbo"), use as-is.
    Otherwise, infer the prefix from the provider brand (most reliable) and
    fall back to the provider name.

    This allows users to keep existing model names while supporting LiteLLM format.
    """
    provider_lower = provider.lower()
    if provider_lower == "openrouter":
        if model.startswith("openrouter/"):
            return model
        elif "/" in model:
            return f"openrouter/{model}"
        else:
            return f"openrouter/{model}"

    if "/" in model:
        # Already in LiteLLM format
        return model

    # Brand-based routing takes precedence over the provider doc name: any
    # provider with brand "ollama" routes through the ollama_chat endpoint
    # (required for reasoning models like gpt-oss with tools attached),
    # regardless of what the provider document is named.
    brand_prefix_map = {
        "ollama": "ollama_chat",
        "lmstudio": "openai",  # LM Studio exposes an OpenAI-compatible API
    }
    if brand and brand.lower() in brand_prefix_map:
        return f"{brand_prefix_map[brand.lower()]}/{model}"

    # Provider prefix mapping for auto-normalization
    provider_prefix_map = {
        "openai": "openai",
        "anthropic": "anthropic",
        "google": "gemini",
        "gemini": "gemini",
        "deepSeek": "deepSeek",
        "openrouter": "openrouter",
        "xai": "xai",  # Grok
        "grok": "xai",  # Alias
        "mistral": "mistral",
        "alibaba": "dashscope",  # Alibaba uses Dashscope
        "dashscope": "dashscope",
        "cohere": "cohere",
        "perplexity": "perplexity",
        "meta": "meta-llama",
        "ollama": "ollama_chat",  # chat endpoint required for reasoning models (e.g. gpt-oss) with tools
        "lmstudio": "openai",  # LM Studio exposes an OpenAI-compatible API
        "moonshot": "moonshot",
    }

    prefix = provider_prefix_map.get(provider.lower(), provider.lower())
    return f"{prefix}/{model}"


# Providers that need environment variables (LiteLLM requirement)
_ENV_VAR_PROVIDERS = {
    "openrouter": "OPENROUTER_API_KEY",
    "xai": "XAI_API_KEY",  # Grok
    "deepseek": "DEEPSEEK_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "dashscope": "DASHSCOPE_API_KEY",  # Alibaba
    "google": "GEMINI_API_KEY",  # Alternative to api_key param
    "cohere": "COHERE_API_KEY",
    "perplexity": "PERPLEXITY_API_KEY",
    "moonshot": "MOONSHOT_API_KEY",
}


# Some AI Provider `provider_brand` values don't match the LiteLLM-routing
# prefix _normalize_model_name() derives from them (see its own
# brand_prefix_map/provider_prefix_map) — e.g. brand "alibaba" routes through
# the "dashscope" prefix, brand "grok" through "xai". Without this alias step,
# _resolve_api_key() and _setup_api_key() would resolve DIFFERENT env var
# names for the same provider (one via raw brand, one via the routed
# prefix), so a real key sitting in the "correct" env var would never be
# found. Keep in sync with _normalize_model_name()'s own brand mappings.
_BRAND_TO_ENV_LOOKUP_KEY = {
    "alibaba": "dashscope",
    "grok": "xai",
}


def _env_var_name_for_provider(provider_brand: str) -> str:
    """Resolve the conventional environment variable name for a provider.

    Known providers (LiteLLM's own env var requirements) use the explicit
    mapping in `_ENV_VAR_PROVIDERS`, after normalizing any brand alias that
    routes to a differently-named prefix (see `_BRAND_TO_ENV_LOOKUP_KEY`).
    Unknown/new providers fall back to the heuristic `PROVIDER_API_KEY`
    shape, which already happens to match the standard env var names for
    OpenAI/Anthropic (OPENAI_API_KEY, ANTHROPIC_API_KEY). Handles an
    empty/None input gracefully, producing a harmless placeholder name that
    won't match anything real.
    """
    provider_brand = provider_brand or ""
    lookup_key = _BRAND_TO_ENV_LOOKUP_KEY.get(provider_brand, provider_brand)
    if lookup_key in _ENV_VAR_PROVIDERS:
        return _ENV_VAR_PROVIDERS[lookup_key]
    return f"{provider_brand.upper().replace('-', '_')}_API_KEY"


def _setup_api_key(provider_name: str, api_key: str, completion_kwargs: dict):
    """
    Setup API key for LiteLLM based on provider requirements.

    Some providers need environment variables, others accept api_key parameter.
    """
    if provider_name in _ENV_VAR_PROVIDERS:
        # Set environment variable for this request
        os.environ[_ENV_VAR_PROVIDERS[provider_name]] = api_key
        return

    # For known providers that accept an api_key parameter directly, prefer that.
    completion_kwargs["api_key"] = api_key

    # Unknown/new providers often expect a PROVIDER_API_KEY environment variable.
    # Set a heuristic env var as well so users don't have to wait for a code
    # change to try a new LiteLLM provider; the api_key param remains the primary
    # mechanism for providers that support it.
    os.environ[_env_var_name_for_provider(provider_name)] = api_key


# _setup_api_key() writes resolved DB keys into os.environ as a side effect
# (LiteLLM/some provider SDKs only accept certain providers' keys via env
# var, not a kwarg) and never clears them afterward. Reading live os.environ
# in _resolve_api_key() would mean an AI Provider record WITH a stored key
# could leave that key sitting in the process env, where a DIFFERENT AI
# Provider record of the same brand but a genuinely blank key would then
# silently "succeed" using the first record's key on a later call in the
# same worker process — a real cross-record/cross-request leak, and worse
# than the pre-fallback behavior (which correctly errored in that case).
# Snapshotting the environment once at import time — before any request has
# had a chance to run _setup_api_key() — means the fallback only ever sees
# keys that were genuinely present in the process environment from the
# start (e.g. an operator-set GEMINI_API_KEY), never ones this module wrote
# itself.
_BOOT_ENV = dict(os.environ)


def _resolve_api_key(provider_doc) -> str:
    """Resolve the API key for a provider, falling back to the environment.

    Reads the stored `api_key` from the AI Provider doc first. If that's
    blank, mirrors the DB-then-env fallback pattern used elsewhere in this
    codebase (see `huf/ai/tools/credentials.py::require_credential`) by
    checking the environment variable LiteLLM/the provider SDK would
    conventionally use for this provider's brand — read from a boot-time
    snapshot (see `_BOOT_ENV`), not live `os.environ`, so this can never
    pick up a key `_setup_api_key()` wrote for a different request.
    """
    api_key = provider_doc.get_password("api_key")
    if api_key:
        return api_key

    provider_brand = (provider_doc.get("provider_brand") or "").lower()
    if not provider_brand:
        # No brand to key an env var name off of — don't guess at a bare
        # "_API_KEY" placeholder that could coincidentally exist.
        return ""
    env_var_name = _env_var_name_for_provider(provider_brand)
    return _BOOT_ENV.get(env_var_name, "")


def _resolve_api_base(provider_doc) -> str | None:
    """Resolve a custom API base URL for a provider.

    Precedence: `api_base_url` field > `url`+`port` > None. When None is
    returned, LiteLLM uses the provider's default endpoint (or the relevant
    environment variable). This works for local providers (Ollama, vLLM, etc.)
    and for hosted providers that offer regional endpoints (e.g. Moonshot CN).
    """
    if not provider_doc:
        return None

    api_base = (provider_doc.get("api_base_url") or "").strip()
    if api_base:
        return api_base

    if not provider_doc.get("is_local_llm", 0):
        return None

    url = (provider_doc.get("url") or "").strip()
    if not url:
        return None

    url = url.rstrip("/")
    port = str(provider_doc.get("port") or "").strip()
    if port and not url.endswith(f":{port}"):
        return f"{url}:{port}"
    return url


def _finalize_usage_totals(usage_totals: dict) -> dict:
    """Populate back-compat alias keys on an accumulated usage dict.

    ``usage_totals`` must already carry the accumulated ``input_tokens`` and
    ``output_tokens`` (billed sums across all rounds), plus
    ``cached_tokens``, ``cache_creation_tokens``, ``peak_context_tokens``,
    ``round_count``, and ``cache_skipped_unsupported_model``. Adds
    ``prompt_tokens``/``completion_tokens`` (back-compat aliases for
    ``input_tokens``/``output_tokens``) and ``billed_input_tokens`` (the same
    value as ``input_tokens``, explicitly named so it is never confused with
    ``peak_context_tokens``). Mutates and returns ``usage_totals``.
    """
    usage_totals["prompt_tokens"] = usage_totals["input_tokens"]
    usage_totals["completion_tokens"] = usage_totals["output_tokens"]
    usage_totals["billed_input_tokens"] = usage_totals["input_tokens"]
    return usage_totals


def _accumulate_tool_exchange_tokens(usage_totals: dict, pricing_model: str, new_messages: list):
    """Best-effort accumulation of one round's tool-exchange token count into `usage_totals`.

    `new_messages` is only the messages appended THIS round (the assistant
    tool-call message plus its tool results) — never the whole growing
    message list — so counting stays O(rounds), not O(rounds^2). Imports
    context_segments lazily: that module imports `_normalize_model_name`
    from this one, so a module-level import here would be circular.

    Once a round's count fails, `tool_exchange_tokens` degrades to `None`
    for the rest of the run and stays there: a partial sum would understate
    the true figure, which is worse than an honest "unknown" for the
    reconciliation this feeds (see context_segments.reconcile_composition).
    """
    if usage_totals.get("tool_exchange_tokens") is None:
        return
    try:
        from huf.ai.context_segments import count_tool_exchange_tokens
        count = count_tool_exchange_tokens(pricing_model, new_messages)
    except Exception:
        count = None
    if count is None:
        usage_totals["tool_exchange_tokens"] = None
    else:
        usage_totals["tool_exchange_tokens"] += count


async def run(agent, enhanced_prompt, provider, model, context=None):
    """
    Unified LiteLLM provider implementation.

        Replaces: openai.py, anthropic.py, google.py, openrouter.py

        Uses LiteLLM's unified interface to support:
        - OpenAI models (via OpenAI API or OpenRouter)
        - Anthropic Claude models (via Anthropic API or OpenRouter)
        - Google Gemini models (via Google API or OpenRouter)
        - OpenRouter (for access to 500+ models)
        - 100+ other providers automatically

        Features:
        - Built-in retry logic
        - Cost tracking
        - Unified error handling
        - OpenAI-compatible tool format (works with existing serialize_tools)

        Args:
                agent: Agent object from agents SDK with tools, instructions, model_settings
                enhanced_prompt: User prompt with conversation history
                provider: Provider name (e.g., "OpenAI", "Anthropic", "Google")
                model: Model name (e.g., "gpt-4-turbo", "claude-3-opus-20240229")
                context: Optional context dictionary (contains agent_name for accessing Agent DocType)

        Returns:
                SimpleResult: Result with final_output, usage, and new_items
    """
    # Deterministic HUF Test Provider routing. Checked first, before any
    # frappe.get_doc/network/LLM-SDK code below, so it is reached on the
    # exact same code path (this coroutine, once awaited by the real caller
    # in `agent_integration.py`) a real provider would take - not via the
    # `RunProvider.run()` custom-provider fallback branch in `huf/ai/run.py`,
    # which can only ever trigger on a synchronous failure to *construct*
    # this coroutine (this function is `async def`, so a real litellm
    # execution failure happens only when the caller awaits the returned
    # coroutine, after `RunProvider.run()` has already returned - see
    # `huf/ai/providers/test_provider.py`'s module docstring for the full
    # analysis). See `huf/ai/providers/test_provider.py` for scenario docs.
    if provider and provider.lower() == "test_provider":
        from huf.ai.providers import test_provider as _test_provider

        return await _test_provider.run(agent, enhanced_prompt, provider, model, context=context)

    try:
        # Configure LiteLLM to drop unsupported params (for models like gpt-5 that only support temperature=1)
        # This prevents errors when models don't support certain parameters
        litellm.drop_params = True

        # Enable graceful handling of missing Anthropic thinking blocks.
        # IMPORTANT: modify_params is a GLOBAL LiteLLM module setting and must NEVER be passed
        # per-request (which causes "Unsupported keyword arguments" errors).
        # This setting allows Anthropic to gracefully skip thinking blocks when the model doesn't
        # support them, rather than failing the entire completion request.
        # Reference: huf/ai/reasoning.py for context on thinking block handling.
        litellm.modify_params = True

        # Get Agent DocType directly to access temperature/top_p (most reliable source)
        # Each agent has its own temperature, prompt, and settings from the Agent DocType
        agent_doc = None
        if context and context.get("agent_name"):
            try:
                agent_doc = frappe.get_doc("Agent", context.get("agent_name"))
            except frappe.DoesNotExistError:
                # Will fall back to agent.model_settings if DocType load fails
                pass

		# Get API key from AI Provider doc (same as current implementation)
        provider_doc = frappe.get_doc("AI Provider", provider)
        api_key = _resolve_api_key(provider_doc)

        if not api_key:
            frappe.throw("API key not configured in AI Provider.")

        normalized_model = _normalize_model_name(model, provider, brand=provider_doc.get("provider_brand"))
        # Pricing/tokenizer-model name, computed the same way context_segments.py
        # computes it (no brand override) so tool-exchange counts use the same
        # tokenizer as the pre-call segment counts they're reconciled against.
        pricing_model = _normalize_model_name(model, provider)
        is_local_llm = bool(provider_doc.get("is_local_llm", 0))
        api_base = _resolve_api_base(provider_doc)

        # Check prompt caching configuration.
        # Agent.prompt_cache_mode is authoritative; the four legacy fields are read
        # only in Advanced mode. Resolution is shared by run() and run_stream() via
        # _resolve_cache_settings() so the two paths cannot drift apart.
        prompt_cache_options = _get_prompt_cache_options(context)
        static_prefix = (prompt_cache_options.get("static_prefix") or "").strip()
        dynamic_suffix = prompt_cache_options.get("dynamic_suffix")
        openai_prompt_cache_retention = prompt_cache_options.get("openai_prompt_cache_retention")
        gemini_cached_content = prompt_cache_options.get("gemini_cached_content")

        cache_settings = _resolve_cache_settings(
            agent_doc, prompt_cache_options, is_local_llm=is_local_llm
        )
        enable_prompt_caching = cache_settings.enabled
        cache_control_type = cache_settings.cache_control_type
        cache_static_prefix = cache_settings.cache_static_prefix
        cache_system_message = cache_settings.cache_system_message
        cache_dynamic_content = cache_settings.cache_dynamic_content

        if not cache_settings.allow_provider_cache_params:
            # Off means no HUF-injected cache controls of any kind.
            openai_prompt_cache_retention = None
            gemini_cached_content = None

        max_context_chars = _get_agent_max_context_chars(agent_doc)

        # Check if model supports prompt caching
        model_supports_caching = False
        cache_skipped_unsupported_model = False
        cache_skipped_below_min_tokens = False
        if enable_prompt_caching:
            try:
                model_supports_caching = model_supports_prompt_caching(model, provider)
                if not model_supports_caching:
                    cache_skipped_unsupported_model = True
            except (ImportError, AttributeError, ValueError, TypeError, RuntimeError):
                # Prompt-caching check failed; disable caching and log for investigation.
                model_supports_caching = False
                cache_skipped_unsupported_model = True
                frappe.log_error(
                    title="LiteLLM Prompt Caching",
                    message=f"Failed to check prompt caching support for model {normalized_model}",
                )

        # Resolve model capabilities to check minimum cacheable token threshold
        provider_brand = provider_doc.get("provider_brand") or normalized_model.split("/")[0]
        min_cacheable_tokens = None
        if model_supports_caching and enable_prompt_caching:
            try:
                capabilities = resolve_capabilities(provider_brand, model)
                min_cacheable_tokens = capabilities.min_cacheable_tokens
            except Exception as e:
                # Failure in resolve_capabilities should not break the completion.
                # Log and continue with caching enabled (assume adequate tokens).
                logger.warning(
                    f"Failed to resolve prompt cache capabilities for {provider_brand}/{model}: {e!s}"
                )

        if not isinstance(dynamic_suffix, str):
            dynamic_suffix = enhanced_prompt

        # Prepare messages with cache control/static-vs-dynamic segmentation
        messages = []
        provider_name = normalized_model.split("/")[0]

        if static_prefix:
            static_cache_enabled = (
                enable_prompt_caching and model_supports_caching and cache_static_prefix
            )
            messages.append(
                {
                    "role": "system",
                    "content": _build_text_content(
                        static_prefix, provider_name, static_cache_enabled, cache_control_type
                    ),
                }
            )
        
        if agent.instructions:
            system_cache_enabled = (
                enable_prompt_caching and model_supports_caching and cache_system_message
            )
            system_content = _build_text_content(
                agent.instructions, provider_name, system_cache_enabled, cache_control_type
            )
            messages.append({"role": "system", "content": system_content})
        
        # Insert Conversation History if available
        if context and context.get("conversation_history"):
            messages.extend(
                _format_conversation_history(
                    context["conversation_history"],
                )
            )
        
        # Add user message. cache_dynamic_content is resolved once by
        # _resolve_cache_settings() above (Auto -> tool-capable Agent,
        # Advanced -> legacy cache_conversation_history plus the
        # prompt_cache_options["cache_dynamic_content"] override, Off ->
        # forced off) but the marker itself is round-gated: it is never
        # placed at round 0, only from round 1 onward (see the round loop
        # below and _resolve_cache_settings()'s docstring for why).
        dynamic_cache_eligible = (
            enable_prompt_caching and model_supports_caching and cache_dynamic_content
        )
        user_content = _build_text_content(
            dynamic_suffix,
            provider_name,
            False,
            cache_control_type,
        )

        # Append images if any are passed in context (embedded as base64 data URIs)
        if context and context.get("files"):
            user_content = _append_context_images_to_user_content(user_content, context.get("files"))

        messages.append({"role": "user", "content": user_content})
        # messages is re-trimmed (deep-copied) and repaired every round below,
        # which can drop/rewrite entries (see _find_last_user_message_index's
        # docstring) — so the round gate re-scans for the last user message
        # fresh each time rather than trusting an index captured here.
        dynamic_marker_applied = False

        # Convert tools
        tools = None
        if getattr(agent, "tools", None):
            tools = serialize_tools(agent.tools)

        # Capability profile for local providers (probe results cached 1h by build_local_overrides).
        local_overrides = {}
        if is_local_llm:
            try:
                from huf.ai.local_runtime import build_local_overrides
                local_overrides = build_local_overrides(provider_doc, model)
            except Exception as e:
                logger.warning(f"Failed to build local overrides for '{provider}': {e!s}")

        total_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_tokens": 0,
            "cache_creation_tokens": 0,
            "billed_input_tokens": 0,
            "peak_context_tokens": 0,
            "round_count": 0,
            "cache_skipped_unsupported_model": cache_skipped_unsupported_model,
            "cache_skipped_below_min_tokens": cache_skipped_below_min_tokens,
            # Tokens contributed by tool-call requests/results across all rounds
            # (see context_segments.count_tool_exchange_tokens); None if any
            # round's count failed. round_prompt_tokens is the per-round
            # prompt-size growth shape, taken from round_usage["input_tokens"]
            # at no extra tokenizer cost.
            "tool_exchange_tokens": 0,
            "round_prompt_tokens": [],
        }
        total_cost = 0.0
        all_new_items = []

        MAX_ROUNDS = getattr(agent, "max_turns", 10) or 10

        # Tool-call loop guard for non-streaming path (same rationale as run_stream).
        last_tool_signature = None
        tool_loop_repeats = 0
        MAX_TOOL_LOOP_REPEATS = 1

        for round_num in range(MAX_ROUNDS):

            # Round gate for the dynamic (latest-user-message) cache marker:
            # attach it only once a second provider round is actually
            # happening (round_num >= 1), never at round 0. Applied at most
            # once — after that the marker rides along in `messages` (and
            # through each round's deep-copy/repair below) without being
            # rebuilt. See _resolve_cache_settings()'s docstring.
            if dynamic_cache_eligible and not dynamic_marker_applied and round_num >= 1:
                _dynamic_idx = _find_last_user_message_index(messages)
                if _dynamic_idx >= 0:
                    target = dict(messages[_dynamic_idx])
                    target["content"] = _apply_dynamic_cache_marker(
                        target["content"], provider_name, cache_control_type
                    )
                    messages[_dynamic_idx] = target
                    dynamic_marker_applied = True

            # Temperature / Top P
            # Note: Agent.temperature and Agent.top_p have doctype defaults of 1.0.
            # We treat 1.0 as "not explicitly configured" and only send if != 1.0.
            # This prevents sending unsupported parameters to newer Claude models
            # and avoids conflicts when both are sent together.
            temperature = None
            top_p = None

            if agent_doc:
                temperature = agent_doc.temperature
                top_p = agent_doc.top_p

            if (
                temperature is None
                and hasattr(agent, "model_settings")
                and agent.model_settings
            ):
                temperature = getattr(agent.model_settings, "temperature", None)
                if top_p is None:
                    top_p = getattr(agent.model_settings, "top_p", None)

            # Treat doctype default (1.0) as "not explicitly set"
            if temperature == 1.0:
                temperature = None
            if top_p == 1.0:
                top_p = None

            # Apply sampling parameter precedence: if both are set, send only temperature
            if temperature is not None and top_p is not None:
                top_p = None  # temperature wins

            # Build completion params
            completion_kwargs = {
                "model": normalized_model,
                "timeout": _provider_timeout(provider_doc),
            }

            # Only add temperature if explicitly configured and not already known
            # (from a prior call this process, or a prior worker via frappe.cache())
            # to be rejected by this model. Mirrors the tool/json capability_cache_key
            # pattern above/below: skip the failed round-trip once the negative
            # result is known. See the BadRequestError handler below, which is what
            # first discovers and caches this.
            temperature_cache_key = _site_scoped_key(f"litellm_temperature_unsupported:{normalized_model}")
            top_p_cache_key = _site_scoped_key(f"litellm_top_p_unsupported:{normalized_model}")
            if temperature is not None:
                _temp_unsupported = _l1_get(temperature_cache_key)
                if _temp_unsupported is None:
                    _temp_unsupported = frappe.cache().get_value(temperature_cache_key)
                    if _temp_unsupported:
                        _l1_set(temperature_cache_key, 1, _SAMPLING_NEGATIVE_CACHE_TTL)
                if not _temp_unsupported:
                    completion_kwargs["temperature"] = temperature

            if api_base:
                completion_kwargs["api_base"] = api_base

            # Trim messages to fit context window, then sanitize tool-call pairs.
            # Local model tokenizers are unknown to LiteLLM — skip trimming and rely
            # on the char-based tool-result limiting (max_context_chars) instead.
            if not is_local_llm:
                try:
                    messages = trim_messages(messages=messages, model=normalized_model)
                except Exception as e:
                    logger.warning(
                        f"Failed to trim messages: {e!s}; continuing with untrimmed messages\n{frappe.get_traceback()}"
                    )
                    # Continue with untrimmed messages if trimming fails
                    pass

            messages = repair_message_sequence(
                messages,
                conversation_name=context.get("conversation_id") if context else None,
            )
            completion_kwargs["messages"] = messages

            if context and context.get("response_format"):
                completion_kwargs["response_format"] = context.get("response_format")

            if openai_prompt_cache_retention:
                completion_kwargs["prompt_cache_retention"] = openai_prompt_cache_retention

            if gemini_cached_content:
                completion_kwargs["cached_content"] = gemini_cached_content

            # Only add top_p if explicitly configured and not overridden by temperature
            if top_p is not None:
                _tp_unsupported = _l1_get(top_p_cache_key)
                if _tp_unsupported is None:
                    _tp_unsupported = frappe.cache().get_value(top_p_cache_key)
                    if _tp_unsupported:
                        _l1_set(top_p_cache_key, 1, _SAMPLING_NEGATIVE_CACHE_TTL)
                if not _tp_unsupported:
                    completion_kwargs["top_p"] = top_p

            provider_name = normalized_model.split("/")[0]
            _setup_api_key(provider_name, api_key, completion_kwargs)

            # Resolve provider-aware reasoning parameters
            reasoning_policy_data = None
            if context and context.get("reasoning_policy"):
                reasoning_policy_data = context["reasoning_policy"]
            elif agent_doc:
                reasoning_policy_data = {
                    "mode": agent_doc.get("reasoning_mode"),
                    "effort": agent_doc.get("reasoning_effort"),
                    "budget_tokens": agent_doc.get("reasoning_budget_tokens"),
                    "summary": agent_doc.get("reasoning_summary"),
                }
            elif hasattr(agent, "reasoning_mode"):
                reasoning_policy_data = {
                    "mode": getattr(agent, "reasoning_mode", "auto"),
                    "effort": getattr(agent, "reasoning_effort", "auto"),
                    "budget_tokens": getattr(agent, "reasoning_budget_tokens", None),
                    "summary": getattr(agent, "reasoning_summary", "none"),
                }

            ai_model_doc = None
            if model:
                try:
                    ai_model_doc = frappe.get_doc("AI Model", model)
                except Exception:
                    pass

            r_policy = ReasoningPolicy.from_dict(reasoning_policy_data)
            r_caps = detect_model_capabilities(normalized_model, provider, ai_model_doc=ai_model_doc)
            r_res = resolve_reasoning(r_policy, r_caps, provider=provider, model_name=normalized_model)
            if context is not None:
                context["reasoning_resolution"] = r_res

            completion_kwargs.update(build_reasoning_kwargs(r_res))

            capability_cache_key = _site_scoped_key(f"litellm_tool_json_conflict:{provider_name}")
            
            known_conflict = _l1_get(capability_cache_key)
             
            if known_conflict is None:
                known_conflict = frappe.cache().get_value(capability_cache_key)
                if known_conflict:
                    _l1_set(capability_cache_key, 1, _SAMPLING_NEGATIVE_CACHE_TTL)
            
            is_json_mode = context and context.get("response_format")
            
            if tools and is_json_mode and known_conflict:
                tools = None
            
            if tools and local_overrides.get("supports_tools") is False:
                # Model does not support tool calling — strip tools and continue
                # instead of letting the provider fail with a cryptic 400.
                frappe.log_error(
                    message=f"Model '{normalized_model}' does not support tools; continuing without tools.",
                    title="LiteLLM Local Overrides"
                )
                if isinstance(context, dict):
                    context.setdefault("local_llm_warnings", []).append(
                        f"Model '{normalized_model}' does not support tool calling; tools were disabled for this run."
                    )
                tools = None

            if tools:
                completion_kwargs["tools"] = tools
                completion_kwargs["tool_choice"] = "auto"

            # Check if cacheable prefix meets model's minimum token threshold
            # (only on first round; once set, the flag persists across rounds).
            # Wrapped in its own try/except — same shape as run_stream()'s
            # equivalent block below — so a failure in the (best-effort, regex-free)
            # estimator degrades identically in both paths: caching just proceeds
            # unflagged, the completion is never broken by a diagnostic check.
            if (
                enable_prompt_caching
                and model_supports_caching
                and not cache_skipped_below_min_tokens
                and min_cacheable_tokens is not None
            ):
                try:
                    estimated_prefix_tokens = _estimate_prefix_tokens(completion_kwargs.get("messages", []))
                    if estimated_prefix_tokens < min_cacheable_tokens:
                        cache_skipped_below_min_tokens = True
                        # total_usage was built before the round loop with the initial
                        # (False) value; mutate it now so the determination actually
                        # reaches the returned usage dict. Guarded by the `not
                        # cache_skipped_below_min_tokens` check above, so this only
                        # fires once and the True value persists across later rounds.
                        total_usage["cache_skipped_below_min_tokens"] = True
                        logger.info(
                            f"Prompt caching disabled: cacheable prefix is {estimated_prefix_tokens} tokens "
                            f"but model {normalized_model} requires minimum {min_cacheable_tokens} tokens"
                        )
                except Exception as e:
                    logger.warning(
                        f"Failed to estimate cacheable prefix tokens for {normalized_model}: {e!s}"
                    )

            # LiteLLM call
            try:
                try:
                    response = await _litellm_completion_with_retry(**completion_kwargs)
                except BadRequestError as e:
                    err_msg = str(e).lower()
                    conflict_keywords = [
                        "response_format",
                        "response mime type",
                        "tool",
                        "function calling",
                        "json",
                        "unsupported"
                    ]

                    is_config_conflict = (
                        completion_kwargs.get("tools")
                        and completion_kwargs.get("response_format")
                        and any(k in err_msg for k in conflict_keywords)
                    )

                    # Model-specific: newer Claude models (e.g. claude-sonnet-5) reject
                    # any explicit non-1.0 temperature outright ("`temperature` is
                    # deprecated for this model"), unlike claude-opus-4-5 which accepts
                    # it — so this must be a live retry-and-cache, not a blanket drop.
                    # Mirrors get_simple_completion()'s fallback in this same file.
                    is_temperature_conflict = (
                        completion_kwargs.get("temperature") is not None
                        and _param_rejected(err_msg, "temperature")
                    )

                    is_top_p_conflict = (
                        completion_kwargs.get("top_p") is not None
                        and _param_rejected(err_msg, "top_p")
                    )

                    if is_config_conflict:
                        _l1_set(capability_cache_key, 1, _SAMPLING_NEGATIVE_CACHE_TTL)
                        frappe.cache().set_value(capability_cache_key, 1, expires_in_sec=_SAMPLING_NEGATIVE_CACHE_TTL)

                        frappe.log_error(
                            title="LiteLLM Auto-Recovery",
                            message=f"Provider '{provider}' returned bad request. Retrying without tools and caching capability limitation. Error: {str(e)}",
                        )
                        completion_kwargs.pop("tools", None)
                        completion_kwargs.pop("tool_choice", None)

                        response = await _litellm_completion_with_retry(**completion_kwargs)
                    elif is_temperature_conflict:
                        _l1_set(temperature_cache_key, 1, _SAMPLING_NEGATIVE_CACHE_TTL)
                        frappe.cache().set_value(temperature_cache_key, 1, expires_in_sec=_SAMPLING_NEGATIVE_CACHE_TTL)

                        frappe.log_error(
                            title="LiteLLM Auto-Recovery",
                            message=f"Model '{normalized_model}' rejected temperature. Retrying without it and caching capability limitation. Error: {str(e)}",
                        )
                        completion_kwargs.pop("temperature", None)

                        response = await _litellm_completion_with_retry(**completion_kwargs)
                    elif is_top_p_conflict:
                        _l1_set(top_p_cache_key, 1, _SAMPLING_NEGATIVE_CACHE_TTL)
                        frappe.cache().set_value(top_p_cache_key, 1, expires_in_sec=_SAMPLING_NEGATIVE_CACHE_TTL)

                        frappe.log_error(
                            title="LiteLLM Auto-Recovery",
                            message=f"Model '{normalized_model}' rejected top_p. Retrying without it and caching capability limitation. Error: {str(e)}",
                        )
                        completion_kwargs.pop("top_p", None)

                        response = await _litellm_completion_with_retry(**completion_kwargs)
                    else:
                        raise e

            except InternalServerError as e:
                raw_msg = (
                    f"OpenAI API server error with model '{normalized_model}'. "
                    f"This may be temporary. Details: {str(e)}"
                )
                frappe.log_error(message=raw_msg, title="LiteLLM Provider")
                _raise_provider_unavailable(raw_msg, normalized_model)

            except RateLimitError as e:
                title = f"LiteLLM RateLimit: {normalized_model}"[:140]

                try:
                    full_trace = frappe.get_traceback()
                except (AttributeError, TypeError, RuntimeError):
                    full_trace = str(e)

                frappe.log_error(message=full_trace, title=title)
                raise e

            except ContextWindowExceededError as e:
                frappe.log_error(message=f"LiteLLM ContextWindowExceededError for model '{normalized_model}': {str(e)}", title="LiteLLM Provider")
                raise e

            except APIError as e:
                raw_msg = f"API error for model '{normalized_model}': {str(e)}"
                frappe.log_error(message=raw_msg, title="LiteLLM Provider")
                _raise_provider_unavailable(raw_msg, normalized_model)

            except Exception as e:
                raw_msg = f"LiteLLM error for model '{normalized_model}': {str(e)}"
                frappe.log_error(
                    message=f"{raw_msg}\n\n{frappe.get_traceback()}",
                    title="LiteLLM Provider"
                )
                if "ContextWindowExceededError" in str(e) or "RateLimitError" in str(e):
                    raise e

                _raise_provider_unavailable(raw_msg, normalized_model)

            # Empty-response guard: reasoning models (e.g. gpt-oss) on the 'ollama/'
            # endpoint can return empty content with no tool calls. Retry the completion
            # once; if still empty, fail loudly instead of storing an empty reply.
            for _empty_check in range(2):
                _choice = response.choices[0].message
                if getattr(_choice, "tool_calls", None) or (_choice.content or "").strip():
                    break
                if _empty_check == 0:
                    frappe.log_error(
                        message=f"Model '{normalized_model}' returned an empty response; retrying the completion once.",
                        title="LiteLLM Empty Response"
                    )
                    response = await _litellm_completion_with_retry(**completion_kwargs)
                else:
                    raw_msg = (
                        f"Model '{normalized_model}' returned an empty response. "
                        "Known issue with reasoning models (e.g. gpt-oss) on the 'ollama/' "
                        "endpoint — use the 'ollama_chat/' prefix or check the model."
                    )
                    raise ProviderUnavailableError(raw_msg, log_message=raw_msg)

            # Extract response
            choice = response.choices[0].message

            # Single extraction of this round's usage, shared by cost calculation
            # and accumulation into total_usage (see huf/ai/usage_extraction.py).
            round_usage = extract_round_usage(response.usage)
            total_usage["input_tokens"] += round_usage["input_tokens"]
            total_usage["output_tokens"] += round_usage["output_tokens"]
            total_usage["cached_tokens"] += round_usage["cache_read_tokens"]
            total_usage["cache_creation_tokens"] += round_usage["cache_write_tokens"]
            total_usage["round_count"] += 1
            total_usage["peak_context_tokens"] = max(
                total_usage["peak_context_tokens"], round_usage["input_tokens"]
            )
            total_usage["round_prompt_tokens"].append(round_usage["input_tokens"])

            try:
                round_cost, _cost_source = calculate_cost(
                    model_name=model,
                    input_tokens=round_usage["input_tokens"],
                    output_tokens=round_usage["output_tokens"],
                    cached_tokens=round_usage["cache_read_tokens"],
                    cache_creation_tokens=round_usage["cache_write_tokens"],
                    litellm_response=response,
                )
                total_cost += round_cost
            except (ValueError, TypeError, AttributeError, KeyError):
                # Cost calculation is best-effort; ignore rounding failures.
                pass

            assistant_message = {
                "role": "assistant",
                "content": choice.content,
            }

            if hasattr(choice, "tool_calls") and choice.tool_calls:
                assistant_message["tool_calls"] = choice.tool_calls

            if getattr(choice, "thinking_blocks", None):
                assistant_message["thinking_blocks"] = choice.thinking_blocks
            elif getattr(choice, "reasoning_content", None):
                assistant_message["reasoning_content"] = choice.reasoning_content

            messages.append(assistant_message)

            # No tool call — return final result
            if not (hasattr(choice, "tool_calls") and choice.tool_calls):
                return SimpleResult(
                    choice.content or "", _finalize_usage_totals(total_usage), all_new_items, cost=total_cost
                )

            # Handle tool calls
            tool_results = []

            # Loop detection: identical signatures in consecutive rounds
            # indicate a stuck local model.
            tool_calls_list = []
            for tc in choice.tool_calls:
                tool_calls_list.append({
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                })
            signature = _tool_calls_signature(tool_calls_list)
            if signature == last_tool_signature:
                tool_loop_repeats += 1
            else:
                last_tool_signature = signature
                tool_loop_repeats = 0

            if tool_loop_repeats > MAX_TOOL_LOOP_REPEATS:
                msg = (
                    "The model kept calling the same tool(s) repeatedly "
                    "without producing a final answer. This can happen with "
                    "local models that do not reliably consume tool results."
                )
                frappe.log_error(
                    message=f"Tool-call loop detected for model '{normalized_model}'",
                    title="LiteLLM Tool Loop"
                )
                raise ProviderUnavailableError(msg)

            for tool_call in choice.tool_calls:
                function_call = tool_call.function
                tool_name = function_call.name
                tool_args = function_call.arguments

                all_new_items.append(
                    SimpleNamespace(
                        type="tool_call_item",
                        raw_item=SimpleNamespace(name=tool_name, arguments=tool_args, id=tool_call.id),
                    )
                )

                tool_to_run = _find_tool(agent, tool_name)
                result_content = ""

                if tool_to_run:
                    try:
                        # Emit socket event for tool execution start BEFORE executing
                        if context and context.get("conversation_id"):
                            frappe.publish_realtime(
                                event=f'conversation:{context.get("conversation_id")}',
                                message={
                                    "type": "tool_call_started",
                                    "conversation_id": context.get("conversation_id"),
                                    "agent_run_id": context.get("agent_run_id"),
                                    "tool_call_id": tool_call.id,  # Use LLM's tool_call.id as temporary ID
                                    "message_id": tool_call.id,  # Temporary ID, will be updated after message creation
                                    "tool_name": tool_name,
                                    "tool_status": "Queued",
                                    "tool_args": tool_args if isinstance(tool_args, dict) else json.loads(tool_args) if isinstance(tool_args, str) else {},
                                },
                                user=frappe.session.user,
                                after_commit=False
                            )
                            transaction_checkpoint(reason="agent_streaming_progress")
                        
                        result_content = await _execute_tool_call(
                            tool_to_run, tool_args, context, tool_call.id
                        )
                    except Exception as e:
                        frappe.log_error(
                            message=f"Error executing tool {tool_name}: {str(e)}\n\n{frappe.get_traceback()}",
                            title="LiteLLM Tool Execution Error"
                        )
                        result_content = f"Error executing tool {tool_name}: {str(e)}"
                else:
                    result_content = f"Tool '{tool_name}' not found."

                all_new_items.append(
                    SimpleNamespace(
                        type="tool_call_output_item",
                        raw_item={"name": tool_name, "output": result_content, "id": tool_call.id},
                    )
                )

                tool_results.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": _truncate_tool_result_for_context(result_content, max_context_chars),
                    }
                )

            messages.extend(tool_results)

            # Accumulate just this round's growth (the assistant tool-call
            # request plus its results) — never re-tokenise the whole
            # `messages` list, which would make this O(rounds^2).
            _accumulate_tool_exchange_tokens(
                total_usage, pricing_model, [assistant_message] + tool_results
            )

        return SimpleResult(
            "Agent stopped after max rounds of tool calls.",
            _finalize_usage_totals(total_usage),
            all_new_items,
            cost=total_cost,
        )

    except ProviderUnavailableError:
        raise
    except (frappe.DoesNotExistError, frappe.PermissionError, frappe.ValidationError) as e:
        frappe.logger("huf").warning(f"Expected failure: {e!s}")
    except Exception as e:  # boundary exception handler: unexpected system error boundary
        msg = f"LiteLLM Provider Error: {str(e)}"
        frappe.log_error(
            message=f"{msg}\n\n{frappe.get_traceback()}",
            title="LiteLLM Provider"
        )

        if "ContextWindowExceededError" in str(e) or "RateLimitError" in str(e):
            raise e

        _raise_provider_unavailable(msg)


async def get_simple_completion(model: str, messages: list, provider: str) -> str:
    """
    Lightweight wrapper for simple completion tasks (like summarization).
    Bypasses Agent logic for direct LLM access.
    """
    try:
        litellm.drop_params = True
        
        provider_doc = frappe.get_doc("AI Provider", provider)
        api_key = _resolve_api_key(provider_doc)
        
        normalized_model = _normalize_model_name(model, provider, brand=provider_doc.get("provider_brand"))
        provider_name = normalized_model.split("/")[0]
        
        completion_kwargs = {
            "model": normalized_model,
            "messages": messages,
            "temperature": 0.3,
            "timeout": _provider_timeout(provider_doc),
        }

        api_base = _resolve_api_base(provider_doc)
        if api_base:
            completion_kwargs["api_base"] = api_base
        
        _setup_api_key(provider_name, api_key, completion_kwargs)
        
        try:
            response = await _litellm_completion_with_retry(**completion_kwargs)
        except BadRequestError as e:
            if "unsupported value" in str(e).lower() and "temperature" in str(e).lower():
                completion_kwargs.pop("temperature", None)
                response = await _litellm_completion_with_retry(**completion_kwargs)
            else:
                raise e
        
        return response.choices[0].message.content
        
    except (frappe.DoesNotExistError, frappe.ValidationError, ValueError, KeyError, TypeError, AttributeError) as e:
        logger.warning(f"Validation/Operation warning: {e!s}")
    except Exception as e:  # boundary exception handler: external provider/tool boundary
        logger.warning(f"LiteLLM simple completion failed: {e!s}\n{frappe.get_traceback()}")
        return ""


async def get_simple_completion_with_usage(
    model: str,
    messages: list,
    provider: str,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> dict:
    """
    Like get_simple_completion, but also returns token usage and cost.
    Bypasses Agent logic for direct LLM access.
    """
    result = {"response": "", "input_tokens": 0, "output_tokens": 0, "cost": 0.0}
    try:
        litellm.drop_params = True

        provider_doc = frappe.get_doc("AI Provider", provider)
        api_key = _resolve_api_key(provider_doc)

        normalized_model = _normalize_model_name(model, provider, brand=provider_doc.get("provider_brand"))
        provider_name = normalized_model.split("/")[0]

        completion_kwargs = {
            "model": normalized_model,
            "messages": messages,
            "temperature": 0.3 if temperature is None else temperature,
            "timeout": _provider_timeout(provider_doc),
        }
        if max_tokens:
            completion_kwargs["max_tokens"] = max_tokens

        api_base = _resolve_api_base(provider_doc)
        if api_base:
            completion_kwargs["api_base"] = api_base

        _setup_api_key(provider_name, api_key, completion_kwargs)

        try:
            response = await _litellm_completion_with_retry(**completion_kwargs)
        except BadRequestError as e:
            if "unsupported value" in str(e).lower() and "temperature" in str(e).lower():
                completion_kwargs.pop("temperature", None)
                response = await _litellm_completion_with_retry(**completion_kwargs)
            else:
                raise e

        result["response"] = response.choices[0].message.content

        usage = response.usage
        result["input_tokens"] = int(getattr(usage, "prompt_tokens", 0) or 0)
        result["output_tokens"] = int(getattr(usage, "completion_tokens", 0) or 0)

        try:
            cost, _cost_source = calculate_cost(
                model_name=model,
                input_tokens=result["input_tokens"],
                output_tokens=result["output_tokens"],
                litellm_response=response,
            )
            result["cost"] = round(float(cost), 6)
        except (ValueError, TypeError, AttributeError, KeyError):
            # Cost calculation is best-effort; ignore failures.
            pass

    except (frappe.DoesNotExistError, frappe.ValidationError, ValueError, KeyError, TypeError, AttributeError) as e:
        logger.warning(f"Validation/Operation warning: {e!s}")
    except Exception as e:  # boundary exception handler: external provider/tool boundary
        logger.warning(f"LiteLLM simple completion failed: {e!s}\n{frappe.get_traceback()}")

    return result


async def run_stream(agent, enhanced_prompt, provider, model, context=None):
    """
    Streaming version of LiteLLM provider implementation.

    Yields chunks of the response as they arrive from the LLM.
    For tool calls, buffers the complete tool call before yielding.

    Args:
            agent: Agent object from agents SDK with tools, instructions, model_settings
            enhanced_prompt: User prompt with conversation history
            provider: Provider name (e.g., "OpenAI", "Anthropic", "Google")
            model: Model name (e.g., "gpt-4-turbo", "claude-3-opus-20240229")
            context: Optional context dictionary (contains agent_name for accessing Agent DocType)

    Yields:
            dict: Streaming chunks with structure:
                    - type: "delta" | "complete" | "tool_call" | "error"
                    - content: str (for delta)
                    - full_response: str (accumulated response)
                    - tool_call: dict (for tool_call type)
                    - error: str (for error type)
    """
    # Deterministic HUF Test Provider routing, mirroring the early check in
    # `run()` above (see that check's comment and
    # `huf/ai/providers/test_provider.py`'s module docstring for the full
    # analysis of why this must happen before any real work below). Since
    # this function is an async generator (contains `yield`), we cannot
    # `return await` a delegate call the way `run()` does - instead we
    # delegate to `test_provider.run_stream()` (itself an async generator)
    # and re-yield every chunk it produces, then return.
    if provider and provider.lower() == "test_provider":
        from huf.ai.providers import test_provider as _test_provider

        async for _chunk in _test_provider.run_stream(
            agent, enhanced_prompt, provider, model, context=context
        ):
            yield _chunk
        return

    try:
        litellm.drop_params = True

        # Get Agent DocType for settings
        agent_doc = None
        if context and context.get("agent_name"):
            try:
                agent_doc = frappe.get_doc("Agent", context.get("agent_name"))
            except frappe.DoesNotExistError:
                # Will fall back to agent.model_settings if DocType load fails
                pass

        max_context_chars = _get_agent_max_context_chars(agent_doc)

        # Get API key
        provider_doc = frappe.get_doc("AI Provider", provider)
        api_key = _resolve_api_key(provider_doc)

        if not api_key:
            yield {"type": "error", "error": "API key not configured in AI Provider."}
            return

        normalized_model = _normalize_model_name(model, provider, brand=provider_doc.get("provider_brand"))
        # Pricing/tokenizer-model name, computed the same way context_segments.py
        # computes it (no brand override) so tool-exchange counts use the same
        # tokenizer as the pre-call segment counts they're reconciled against.
        pricing_model = _normalize_model_name(model, provider)
        is_local_llm = bool(provider_doc.get("is_local_llm", 0))
        api_base = _resolve_api_base(provider_doc)

        # Check prompt caching configuration.
        # Agent.prompt_cache_mode is authoritative; the four legacy fields are read
        # only in Advanced mode. Resolution is shared by run() and run_stream() via
        # _resolve_cache_settings() so the two paths cannot drift apart.
        prompt_cache_options = _get_prompt_cache_options(context)
        static_prefix = (prompt_cache_options.get("static_prefix") or "").strip()
        dynamic_suffix = prompt_cache_options.get("dynamic_suffix")
        openai_prompt_cache_retention = prompt_cache_options.get("openai_prompt_cache_retention")
        gemini_cached_content = prompt_cache_options.get("gemini_cached_content")

        cache_settings = _resolve_cache_settings(
            agent_doc, prompt_cache_options, is_local_llm=is_local_llm
        )
        enable_prompt_caching = cache_settings.enabled
        cache_control_type = cache_settings.cache_control_type
        cache_static_prefix = cache_settings.cache_static_prefix
        cache_system_message = cache_settings.cache_system_message
        cache_dynamic_content = cache_settings.cache_dynamic_content

        if not cache_settings.allow_provider_cache_params:
            # Off means no HUF-injected cache controls of any kind.
            openai_prompt_cache_retention = None
            gemini_cached_content = None

        # Check if model supports prompt caching
        model_supports_caching = False
        cache_skipped_unsupported_model = False
        cache_skipped_below_min_tokens = False
        if enable_prompt_caching:
            try:
                model_supports_caching = model_supports_prompt_caching(model, provider)
                if not model_supports_caching:
                    cache_skipped_unsupported_model = True
            except (ImportError, AttributeError, ValueError, TypeError, RuntimeError):
                # Prompt-caching check failed; disable caching and log for investigation.
                model_supports_caching = False
                cache_skipped_unsupported_model = True
                frappe.log_error(
                    message=f"Failed to check prompt caching support for model {normalized_model}",
                    title="LiteLLM Prompt Caching"
                )

        # Resolve model capabilities to check minimum cacheable token threshold
        # (mirrors run()'s equivalent block above).
        provider_brand = provider_doc.get("provider_brand") or normalized_model.split("/")[0]
        min_cacheable_tokens = None
        if model_supports_caching and enable_prompt_caching:
            try:
                capabilities = resolve_capabilities(provider_brand, model)
                min_cacheable_tokens = capabilities.min_cacheable_tokens
            except Exception as e:
                # Failure in resolve_capabilities should not break the completion.
                # Log and continue with caching enabled (assume adequate tokens).
                logger.warning(
                    f"Failed to resolve prompt cache capabilities for {provider_brand}/{model}: {e!s}"
                )

        if not isinstance(dynamic_suffix, str):
            dynamic_suffix = enhanced_prompt

        # Prepare messages with cache control/static-vs-dynamic segmentation
        messages = []
        provider_name = normalized_model.split("/")[0]

        if static_prefix:
            static_cache_enabled = (
                enable_prompt_caching and model_supports_caching and cache_static_prefix
            )
            messages.append(
                {
                    "role": "system",
                    "content": _build_text_content(
                        static_prefix, provider_name, static_cache_enabled, cache_control_type
                    ),
                }
            )
        
        if agent.instructions:
            system_cache_enabled = (
                enable_prompt_caching and model_supports_caching and cache_system_message
            )
            system_content = _build_text_content(
                agent.instructions, provider_name, system_cache_enabled, cache_control_type
            )
            messages.append({"role": "system", "content": system_content})
        
        # Insert Conversation History if available
        if context and context.get("conversation_history"):
            messages.extend(
                _format_conversation_history(
                    context["conversation_history"],
                )
            )
        
        # cache_dynamic_content is resolved once by _resolve_cache_settings() above
        # (Auto -> tool-capable Agent, Advanced -> legacy
        # cache_conversation_history plus the
        # prompt_cache_options["cache_dynamic_content"] override, Off -> forced
        # off) but the marker itself is round-gated: it is never placed at
        # round 0, only from round 1 onward (see the round loop below and
        # _resolve_cache_settings()'s docstring for why).
        dynamic_cache_eligible = (
            enable_prompt_caching and model_supports_caching and cache_dynamic_content
        )
        user_content = _build_text_content(
            dynamic_suffix,
            provider_name,
            False,
            cache_control_type,
        )

        # Append images if any are passed in context (embedded as base64 data URIs)
        if context and context.get("files"):
            user_content = _append_context_images_to_user_content(user_content, context.get("files"))

        messages.append({"role": "user", "content": user_content})
        # Unlike run(), messages here is only trimmed/repaired ONCE before the
        # round loop (see below) and then mutated in place — appended to, not
        # replaced — across subsequent rounds. That one-time repair can still
        # drop/rewrite entries (see _find_last_user_message_index's
        # docstring), so the round gate re-scans for the last user message
        # fresh each time rather than trusting an index captured before repair ran.
        dynamic_marker_applied = False

        # Convert tools to OpenAI format
        tools = None
        if getattr(agent, "tools", None):
            tools = serialize_tools(agent.tools)

        # Capability profile for local providers (probe results cached 1h by build_local_overrides).
        local_overrides = {}
        if is_local_llm:
            try:
                from huf.ai.local_runtime import build_local_overrides
                local_overrides = build_local_overrides(provider_doc, model)
            except Exception as e:
                logger.warning(f"Failed to build local overrides for '{provider}': {e!s}")

        # Get temperature and top_p
        # Note: Agent.temperature and Agent.top_p have doctype defaults of 1.0.
        # We treat 1.0 as "not explicitly configured" and only send if != 1.0.
        # This prevents sending unsupported parameters to newer Claude models
        # and avoids conflicts when both are sent together.
        temperature = None
        top_p = None

        if agent_doc:
            temperature = agent_doc.temperature
            top_p = agent_doc.top_p

        if (
            temperature is None
            and hasattr(agent, "model_settings")
            and agent.model_settings
        ):
            temperature = getattr(agent.model_settings, "temperature", None)
            top_p = (
                getattr(agent.model_settings, "top_p", None) if top_p is None else top_p
            )

        # Treat doctype default (1.0) as "not explicitly set"
        if temperature == 1.0:
            temperature = None
        if top_p == 1.0:
            top_p = None

        # Apply sampling parameter precedence: if both are set, send only temperature
        if temperature is not None and top_p is not None:
            top_p = None  # temperature wins

        completion_kwargs = {
            "model": normalized_model,
            "messages": messages,
            "stream": True,  # Enable streaming
            "stream_options": {"include_usage": True}, # Request usage stats in stream
            "timeout": _provider_timeout(provider_doc),
        }

        # Only add temperature if explicitly configured and not already known
        # (from a prior call this process, or a prior worker via frappe.cache())
        # to be rejected by this model. See the BadRequestError handler around
        # the streaming completion call below, which is what first discovers
        # and caches this. Mirrors run()'s equivalent block.
        temperature_cache_key = _site_scoped_key(f"litellm_temperature_unsupported:{normalized_model}")
        top_p_cache_key = _site_scoped_key(f"litellm_top_p_unsupported:{normalized_model}")
        if temperature is not None:
            _temp_unsupported = _l1_get(temperature_cache_key)
            if _temp_unsupported is None:
                _temp_unsupported = frappe.cache().get_value(temperature_cache_key)
                if _temp_unsupported:
                    _l1_set(temperature_cache_key, 1, _SAMPLING_NEGATIVE_CACHE_TTL)
            if not _temp_unsupported:
                completion_kwargs["temperature"] = temperature

        if api_base:
            completion_kwargs["api_base"] = api_base

        # Trim messages to fit context window, then sanitize tool-call pairs.
        # Local model tokenizers are unknown to LiteLLM — skip trimming and rely
        # on the char-based tool-result limiting (max_context_chars) instead.
        if not is_local_llm:
            try:
                messages = trim_messages(messages=messages, model=normalized_model)
            except Exception as e:
                logger.warning(
                    f"Failed to trim messages: {e!s}; continuing with untrimmed messages\n{frappe.get_traceback()}"
                )
                pass

        messages = repair_message_sequence(
            messages,
            conversation_name=context.get("conversation_id") if context else None,
        )
        completion_kwargs["messages"] = messages

        # Only add top_p if explicitly configured and not overridden by temperature
        if top_p is not None:
            _tp_unsupported = _l1_get(top_p_cache_key)
            if _tp_unsupported is None:
                _tp_unsupported = frappe.cache().get_value(top_p_cache_key)
                if _tp_unsupported:
                    _l1_set(top_p_cache_key, 1, _SAMPLING_NEGATIVE_CACHE_TTL)
            if not _tp_unsupported:
                completion_kwargs["top_p"] = top_p

        if openai_prompt_cache_retention:
            completion_kwargs["prompt_cache_retention"] = openai_prompt_cache_retention

        if gemini_cached_content:
            completion_kwargs["cached_content"] = gemini_cached_content

        provider_name = normalized_model.split("/")[0]
        _setup_api_key(provider_name, api_key, completion_kwargs)

        # Resolve provider-aware reasoning parameters
        reasoning_policy_data = None
        if context and context.get("reasoning_policy"):
            reasoning_policy_data = context["reasoning_policy"]
        elif agent_doc:
            reasoning_policy_data = {
                "mode": agent_doc.get("reasoning_mode"),
                "effort": agent_doc.get("reasoning_effort"),
                "budget_tokens": agent_doc.get("reasoning_budget_tokens"),
                "summary": agent_doc.get("reasoning_summary"),
            }
        elif hasattr(agent, "reasoning_mode"):
            reasoning_policy_data = {
                "mode": getattr(agent, "reasoning_mode", "auto"),
                "effort": getattr(agent, "reasoning_effort", "auto"),
                "budget_tokens": getattr(agent, "reasoning_budget_tokens", None),
                "summary": getattr(agent, "reasoning_summary", "none"),
            }

        ai_model_doc = None
        if model:
            try:
                ai_model_doc = frappe.get_doc("AI Model", model)
            except Exception:
                pass

        r_policy = ReasoningPolicy.from_dict(reasoning_policy_data)
        r_caps = detect_model_capabilities(normalized_model, provider, ai_model_doc=ai_model_doc)
        r_res = resolve_reasoning(r_policy, r_caps, provider=provider, model_name=normalized_model)
        if context is not None:
            context["reasoning_resolution"] = r_res

        completion_kwargs.update(build_reasoning_kwargs(r_res))

        if tools and local_overrides.get("supports_tools") is False:
            # Model does not support tool calling — strip tools and continue
            # instead of letting the provider fail with a cryptic 400.
            frappe.log_error(
                message=f"Model '{normalized_model}' does not support tools; continuing without tools.",
                title="LiteLLM Local Overrides"
            )
            if isinstance(context, dict):
                context.setdefault("local_llm_warnings", []).append(
                    f"Model '{normalized_model}' does not support tool calling; tools were disabled for this run."
                )
            tools = None

        if tools:
            completion_kwargs["tools"] = tools
            completion_kwargs["tool_choice"] = "auto"

        # Stream response
        full_response = ""
        had_tool_calls = False
        MAX_ROUNDS = getattr(agent, "max_turns", 10) or 10

        # Tool-call loop guard: some local models (e.g. gemma4 via Ollama)
        # call the same tool repeatedly with new IDs and never produce a final
        # answer. Detect consecutive identical signatures and stop early.
        last_tool_signature = None
        tool_loop_repeats = 0
        MAX_TOOL_LOOP_REPEATS = 1  # allow one retry, stop on the second repeat

        # Usage/cost accumulator across all rounds of this streaming run. Unlike the
        # per-round `stream_usage` capture below (reset every round), this survives
        # the whole loop — see huf/ai/usage_extraction.py for why per-round
        # extraction must never be conflated with a running total.
        stream_total_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_tokens": 0,
            "cache_creation_tokens": 0,
            "billed_input_tokens": 0,
            "peak_context_tokens": 0,
            "round_count": 0,
            "cache_skipped_unsupported_model": cache_skipped_unsupported_model,
            "cache_skipped_below_min_tokens": cache_skipped_below_min_tokens,
            # See the matching fields in run()'s total_usage init for what
            # these mean and why tool_exchange_tokens can degrade to None.
            "tool_exchange_tokens": 0,
            "round_prompt_tokens": [],
        }
        stream_total_cost = 0.0

        for round_num in range(MAX_ROUNDS):
            # Round gate for the dynamic (latest-user-message) cache marker:
            # attach it only once a second provider round is actually
            # happening (round_num >= 1), never at round 0. Applied at most
            # once — `messages` is the same list object mutated in place
            # across rounds here (see the append above), so this reaches
            # completion_kwargs["messages"] without reassigning it. See
            # _resolve_cache_settings()'s docstring.
            if dynamic_cache_eligible and not dynamic_marker_applied and round_num >= 1:
                _dynamic_idx = _find_last_user_message_index(messages)
                if _dynamic_idx >= 0:
                    target = dict(messages[_dynamic_idx])
                    target["content"] = _apply_dynamic_cache_marker(
                        target["content"], provider_name, cache_control_type
                    )
                    messages[_dynamic_idx] = target
                    dynamic_marker_applied = True

            try:
                # Check if cacheable prefix meets model's minimum token threshold
                # (mirrors run()'s equivalent check; once set, the flag persists
                # across rounds via the `not cache_skipped_below_min_tokens` guard).
                # Wrapped in its own try/except — deliberately narrower than the
                # round-level try below — so an estimator failure is logged and
                # skipped here, never misreported by the broad API-error handlers
                # further down (which would otherwise abort the whole round as if
                # the LLM call itself had failed).
                if (
                    enable_prompt_caching
                    and model_supports_caching
                    and not cache_skipped_below_min_tokens
                    and min_cacheable_tokens is not None
                ):
                    try:
                        estimated_prefix_tokens = _estimate_prefix_tokens(completion_kwargs.get("messages", []))
                        if estimated_prefix_tokens < min_cacheable_tokens:
                            cache_skipped_below_min_tokens = True
                            stream_total_usage["cache_skipped_below_min_tokens"] = True
                            logger.info(
                                f"Prompt caching disabled: cacheable prefix is {estimated_prefix_tokens} tokens "
                                f"but model {normalized_model} requires minimum {min_cacheable_tokens} tokens"
                            )
                    except Exception as e:
                        logger.warning(
                            f"Failed to estimate cacheable prefix tokens for {normalized_model}: {e!s}"
                        )

                # Use LiteLLM completion with stream=True
                # LiteLLM completion() supports streaming when stream=True
                try:
                    stream = await _litellm_completion_with_retry(**completion_kwargs)
                except BadRequestError as e:
                    err_msg = str(e).lower()
                    # Model-specific: newer Claude models (e.g. claude-sonnet-5) reject
                    # any explicit non-1.0 temperature outright ("`temperature` is
                    # deprecated for this model"), unlike claude-opus-4-5 which accepts
                    # it — so this must be a live retry-and-cache, not a blanket drop.
                    # Mirrors get_simple_completion()'s fallback in this same file, and
                    # run()'s equivalent handler.
                    is_temperature_conflict = (
                        completion_kwargs.get("temperature") is not None
                        and _param_rejected(err_msg, "temperature")
                    )

                    is_top_p_conflict = (
                        completion_kwargs.get("top_p") is not None
                        and _param_rejected(err_msg, "top_p")
                    )
                    if is_temperature_conflict:
                        _l1_set(temperature_cache_key, 1, _SAMPLING_NEGATIVE_CACHE_TTL)
                        frappe.cache().set_value(temperature_cache_key, 1, expires_in_sec=_SAMPLING_NEGATIVE_CACHE_TTL)

                        frappe.log_error(
                            title="LiteLLM Auto-Recovery",
                            message=f"Model '{normalized_model}' rejected temperature. Retrying without it and caching capability limitation. Error: {str(e)}",
                        )
                        completion_kwargs.pop("temperature", None)

                        stream = await _litellm_completion_with_retry(**completion_kwargs)
                    elif is_top_p_conflict:
                        _l1_set(top_p_cache_key, 1, _SAMPLING_NEGATIVE_CACHE_TTL)
                        frappe.cache().set_value(top_p_cache_key, 1, expires_in_sec=_SAMPLING_NEGATIVE_CACHE_TTL)

                        frappe.log_error(
                            title="LiteLLM Auto-Recovery",
                            message=f"Model '{normalized_model}' rejected top_p. Retrying without it and caching capability limitation. Error: {str(e)}",
                        )
                        completion_kwargs.pop("top_p", None)

                        stream = await _litellm_completion_with_retry(**completion_kwargs)
                    else:
                        raise e

                # Buffer for tool calls and thinking blocks
                current_tool_calls = {}
                streaming_content = ""
                accumulated_thinking_blocks = []
                accumulated_reasoning_content = ""

                # Process streaming chunks
                stream_usage = None
                is_stop = False
                
                for chunk in stream:
                    # Capture usage if present (often in last chunk)
                    chunk_usage = getattr(chunk, "usage", None)
                    if not chunk_usage and isinstance(chunk, dict):
                        chunk_usage = chunk.get("usage")
                        
                    if chunk_usage:
                        stream_usage = chunk_usage
                
                    if not chunk.choices:
                        if chunk_usage:
                             stream_usage = chunk_usage
                        continue

                    delta = chunk.choices[0].delta

                    # Handle content delta
                    if hasattr(delta, "content") and delta.content:
                        streaming_content += delta.content
                        full_response += delta.content

                        yield {
                            "type": "delta",
                            "content": delta.content,
                            "full_response": full_response,
                        }

                    # Handle thinking / reasoning deltas
                    if hasattr(delta, "thinking_blocks") and delta.thinking_blocks:
                        accumulated_thinking_blocks.extend(delta.thinking_blocks)
                        for block in delta.thinking_blocks:
                            block_text = block.get("thinking") if isinstance(block, dict) else getattr(block, "thinking", None)
                            if block_text:
                                accumulated_reasoning_content += str(block_text)
                                yield {
                                    "type": "reasoning",
                                    "content": str(block_text),
                                    "full_reasoning": accumulated_reasoning_content,
                                }
                    if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                        accumulated_reasoning_content += str(delta.reasoning_content)
                        yield {
                            "type": "reasoning",
                            "content": str(delta.reasoning_content),
                            "full_reasoning": accumulated_reasoning_content,
                        }

                    # Handle tool call delta
                    if hasattr(delta, "tool_calls") and delta.tool_calls:
                        for tool_call_delta in delta.tool_calls:
                            idx = tool_call_delta.index

                            if idx not in current_tool_calls:
                                current_tool_calls[idx] = {
                                    "id": "",
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""},
                                }

                            tc = current_tool_calls[idx]

                            if tool_call_delta.id:
                                tc["id"] = tool_call_delta.id

                            if hasattr(tool_call_delta, "function"):
                                if tool_call_delta.function.name:
                                    tc["function"][
                                        "name"
                                    ] = tool_call_delta.function.name
                                if tool_call_delta.function.arguments:
                                    tc["function"][
                                        "arguments"
                                    ] += tool_call_delta.function.arguments

                    # Check if chunk is complete
                    if chunk.choices[0].finish_reason:
                        finish_reason = chunk.choices[0].finish_reason

                        # If tool calls are present, execute them.
                        # Local models (e.g. gemma4 via Ollama) may emit tool-call
                        # deltas but finish with reason "stop" instead of
                        # "tool_calls", so trigger execution whenever we have
                        # buffered tool calls at the end of a generation.
                        if current_tool_calls and finish_reason in ("tool_calls", "stop"):
                            had_tool_calls = True
                            # Yield tool calls
                            tool_calls_list = list(current_tool_calls.values())

                            # Loop detection: identical signatures in
                            # consecutive rounds indicate a stuck local model.
                            signature = _tool_calls_signature(tool_calls_list)
                            if signature == last_tool_signature:
                                tool_loop_repeats += 1
                            else:
                                last_tool_signature = signature
                                tool_loop_repeats = 0

                            if tool_loop_repeats > MAX_TOOL_LOOP_REPEATS:
                                msg = (
                                    "The model kept calling the same tool(s) "
                                    "repeatedly without producing a final answer. "
                                    "This can happen with local models that do not "
                                    "reliably consume tool results."
                                )
                                frappe.log_error(
                                    message=f"Tool-call loop detected for model '{normalized_model}'",
                                    title="LiteLLM Tool Loop"
                                )
                                yield {"type": "error", "error": msg}
                                return

                            for tool_call in tool_calls_list:
                                yield {
                                    "type": "tool_call",
                                    "tool_call": tool_call,
                                }

                            # Execute tool calls
                            tool_results = []
                            for tool_call in tool_calls_list:
                                function_call = tool_call["function"]
                                tool_name = function_call["name"]
                                tool_args = function_call["arguments"]

                                tool_to_run = _find_tool(agent, tool_name)
                                result_content = ""

                                if tool_to_run:
                                    # Emit tool_call_started before execution
                                    if context and context.get("conversation_id"):
                                        frappe.publish_realtime(
                                            event=f'conversation:{context.get("conversation_id")}',
                                            message={
                                                "type": "tool_call_started",
                                                "conversation_id": context.get("conversation_id"),
                                                "agent_run_id": context.get("agent_run_id"),
                                                "tool_call_id": tool_call["id"],
                                                "message_id": tool_call["id"],
                                                "tool_name": tool_name,
                                                "tool_status": "Queued",
                                                "tool_args": tool_args if isinstance(tool_args, dict) else json.loads(tool_args) if isinstance(tool_args, str) else {},
                                            },
                                            user=frappe.session.user,
                                            after_commit=False
                                        )
                                        transaction_checkpoint(reason="agent_streaming_progress")

                                    try:
                                        result_content = await _execute_tool_call(
                                            tool_to_run, tool_args, context, tool_call.get("id")
                                        )
                                    except Exception as e:
                                        frappe.log_error(
                                            message=f"Error executing tool {tool_name}: {str(e)}\n\n{frappe.get_traceback()}",
                                            title="LiteLLM Streaming Tool Execution Error"
                                        )
                                        result_content = f"Error executing tool {tool_name}: {str(e)}"

                                    # Update Agent Tool Call with result (runs even if tool raised)
                                    if context and context.get("conversation_id"):
                                        conv_id = context.get("conversation_id")
                                        call_id = tool_call.get("id")
                                        agent_run_id = context.get("agent_run_id")
                                        try:
                                            tool_call_doc = frappe.db.get_value("Agent Tool Call", {
                                                "conversation": conv_id,
                                                "call_id": call_id
                                            }, "name")

                                            if tool_call_doc:
                                                tc_doc = frappe.get_doc("Agent Tool Call", tool_call_doc)
                                                tc_doc.status = "Completed"
                                                # JSON field: store valid JSON (dict)
                                                if isinstance(result_content, (dict, list)):
                                                    tc_doc.tool_result = result_content
                                                else:
                                                    tc_doc.tool_result = {"output": str(result_content)[:140000]}
                                                # Tool-call audit records are updated by the provider
                                                # during execution. Authenticated users use standard
                                                # permissions; Guest/system paths bypass permissions.
                                                if frappe.session.user == "Guest":
                                                    tc_doc.save(ignore_permissions=True)
                                                else:
                                                    if not frappe.has_permission("Agent Tool Call", "write", doc=tc_doc):
                                                        frappe.throw(_("Not permitted to update Agent Tool Call"), frappe.PermissionError)
                                                    tc_doc.save()

                                                # Find the Agent Message to update. Prefer the in-memory
                                                # map passed via context, then fall back to DB lookups.
                                                tool_call_message_map = context.get("_tool_call_message_map") or {}
                                                message_name = tool_call_message_map.get(call_id)

                                                if not message_name and tool_call_doc:
                                                    message_name = frappe.db.get_value(
                                                        "Agent Message", {"tool_call": tool_call_doc}, "name"
                                                    )

                                                if not message_name and call_id:
                                                    message_name = frappe.db.get_value(
                                                        "Agent Message", {"tool_call_id": call_id}, "name"
                                                    )

                                                if not message_name and call_id and agent_run_id:
                                                    message_name = frappe.db.get_value(
                                                        "Agent Message",
                                                        {
                                                            "conversation": conv_id,
                                                            "agent_run": agent_run_id,
                                                            "kind": "Tool Call",
                                                            "tool_call_id": call_id,
                                                        },
                                                        "name",
                                                        order_by="creation desc",
                                                    )

                                                if message_name:
                                                    from huf.ai.conversation_manager import update_tool_call_message
                                                    updated = update_tool_call_message(
                                                        message_name=message_name,
                                                        tool_call_id=call_id,
                                                        tool_call=[tool_call],
                                                        result_content=result_content,
                                                        agent_doc=agent_doc,
                                                    )
                                                    if not updated:
                                                        message_name = None
                                                        frappe.log_error(
                                                            title="Tool Call Message Update",
                                                            message=f"Failed to update tool call message for call_id={call_id}, tool_call_doc={tool_call_doc}",
                                                        )
                                                else:
                                                    frappe.log_error(
                                                        title="Tool Call Message Update",
                                                        message=f"No Agent Message found for tool call call_id={call_id}, tool_call_doc={tool_call_doc}",
                                                    )

                                                tool_result_for_socket = (
                                                    result_content
                                                    if isinstance(result_content, (dict, list))
                                                    else {"output": str(result_content)[:140000]}
                                                )
                                                frappe.publish_realtime(
                                                    event=f'conversation:{context.get("conversation_id")}',
                                                    message={
                                                        "type": "tool_call_completed",
                                                        "conversation_id": context.get("conversation_id"),
                                                        "agent_run_id": context.get("agent_run_id"),
                                                        "message_id": message_name,
                                                        "tool_call_id": tool_call["id"],
                                                        "tool_name": tool_name,
                                                        "tool_status": "Completed",
                                                        "status": "Completed",
                                                        "tool_result": tool_result_for_socket,
                                                        "result": json.dumps(tool_result_for_socket) if isinstance(tool_result_for_socket, (dict, list)) else str(result_content)[:1000],
                                                    },
                                                    user=frappe.session.user,
                                                    after_commit=False
                                                )
                                                if getattr(frappe.local, "_realtime_log", None) is None:
                                                    frappe.local._realtime_log = []
                                                transaction_checkpoint(reason="agent_streaming_progress")
                                        except Exception as e:
                                            frappe.log_error(
                                                message=f"Error updating tool call result for call_id={call_id}: {e}\n\n{frappe.get_traceback()}",
                                                title="Tool Call Message Update"
                                            )
                                else:
                                    result_content = f"Tool '{tool_name}' not found."

                                tool_results.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": tool_call["id"],
                                        "name": tool_name,
                                        "content": _truncate_tool_result_for_context(result_content, max_context_chars),
                                    }
                                )

                            # Add tool results to messages and continue
                            assistant_msg = {
                                "role": "assistant",
                                "content": streaming_content,
                                "tool_calls": tool_calls_list,
                            }
                            if accumulated_thinking_blocks:
                                assistant_msg["thinking_blocks"] = accumulated_thinking_blocks
                            if accumulated_reasoning_content:
                                assistant_msg["reasoning_content"] = accumulated_reasoning_content

                            messages.append(assistant_msg)
                            messages.extend(tool_results)

                            # Accumulate just this round's growth (the assistant
                            # tool-call request plus its results) — never
                            # re-tokenise the whole `messages` list, which would
                            # make this O(rounds^2).
                            _accumulate_tool_exchange_tokens(
                                stream_total_usage, pricing_model, [assistant_msg] + tool_results
                            )

                            # Reset for next round
                            streaming_content = ""
                            current_tool_calls = {}
                            break

                        if finish_reason == "stop":
                            is_stop = True

                # Accumulate this round's usage/cost into the running totals. This
                # runs on every path that completes a round: the tool-call branch
                # above (which `break`s out of the chunk loop but falls through to
                # here), a "stop" finish reason, and plain stream exhaustion.
                round_payload = normalise_usage_payload(stream_usage)
                round_usage = extract_round_usage(round_payload)
                stream_total_usage["input_tokens"] += round_usage["input_tokens"]
                stream_total_usage["output_tokens"] += round_usage["output_tokens"]
                stream_total_usage["cached_tokens"] += round_usage["cache_read_tokens"]
                stream_total_usage["cache_creation_tokens"] += round_usage["cache_write_tokens"]
                stream_total_usage["round_count"] += 1
                stream_total_usage["peak_context_tokens"] = max(
                    stream_total_usage["peak_context_tokens"], round_usage["input_tokens"]
                )
                stream_total_usage["round_prompt_tokens"].append(round_usage["input_tokens"])

                try:
                    round_cost, _cost_source = calculate_cost(
                        model_name=model,
                        input_tokens=round_usage["input_tokens"],
                        output_tokens=round_usage["output_tokens"],
                        cached_tokens=round_usage["cache_read_tokens"],
                        cache_creation_tokens=round_usage["cache_write_tokens"],
                    )
                    stream_total_cost += round_cost
                except (ValueError, TypeError, AttributeError, KeyError):
                    # Cost calculation is best-effort; ignore rounding failures.
                    pass

                if is_stop:
                    break

            except InternalServerError as e:
                raw_msg = f"LiteLLM error for model '{normalized_model}': {str(e)}"
                yield {"type": "error", "error": _sanitize_provider_error_message(raw_msg, normalized_model)}
                return
            except RateLimitError as e:
                raw_msg = f"LiteLLM error for model '{normalized_model}': {str(e)}"
                yield {"type": "error", "error": _sanitize_provider_error_message(raw_msg, normalized_model)}
                return
            except ContextWindowExceededError as e:
                raw_msg = f"LiteLLM error for model '{normalized_model}': {str(e)}"
                yield {"type": "error", "error": _sanitize_provider_error_message(raw_msg, normalized_model)}
                return
            except APIError as e:
                raw_msg = f"LiteLLM error for model '{normalized_model}': {str(e)}"
                yield {"type": "error", "error": _sanitize_provider_error_message(raw_msg, normalized_model)}
                return
            except Exception as e:
                frappe.log_error(
                    message=f"LiteLLM streaming round error: {str(e)}\n\n{frappe.get_traceback()}",
                    title="LiteLLM Streaming"
                )
                raw_msg = f"LiteLLM error for model '{normalized_model}': {str(e)}"
                yield {"type": "error", "error": _sanitize_provider_error_message(raw_msg, normalized_model)}
                return

        # Max rounds reached (or the loop broke via is_stop). Finalize the
        # accumulated per-round totals — never the last round's usage alone.
        _finalize_usage_totals(stream_total_usage)

        # Never report an empty response as a successful completion.
        if not full_response.strip() and not had_tool_calls:
            if normalized_model.startswith("ollama/"):
                msg = (
                    f"Model '{normalized_model}' returned an empty response. "
                    "Reasoning models such as gpt-oss require the Ollama chat "
                    "endpoint. Use the 'ollama_chat/' model prefix (e.g. "
                    "'ollama_chat/gpt-oss:20b') or select a provider whose brand "
                    "is 'Ollama' so Huf normalizes the prefix automatically."
                )
            else:
                msg = (
                    f"Model '{normalized_model}' returned an empty response. "
                    "Verify the model is loaded, the provider is reachable, and "
                    "the request is supported by this model."
                )
            frappe.log_error(message=msg, title="LiteLLM Empty Response")
            yield {"type": "error", "error": msg}
            return

        yield {
            "type": "complete",
            "full_response": full_response or "Agent stopped after max rounds.",
            "usage": stream_total_usage,
            "cost": stream_total_cost,
            "reasoning_content": accumulated_reasoning_content or None,
        }


    except (frappe.DoesNotExistError, frappe.PermissionError, frappe.ValidationError) as e:
        frappe.logger("huf").warning(f"Expected failure: {e!s}")
    except Exception as e:  # boundary exception handler: unexpected system error boundary
        frappe.log_error(
            message=f"LiteLLM Streaming Error: {str(e)}\n\n{frappe.get_traceback()}",
            title="LiteLLM Streaming"
        )
        yield {"type": "error", "error": f"LiteLLM Streaming Error: {str(e)}",}
