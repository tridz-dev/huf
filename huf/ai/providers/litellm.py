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
from types import SimpleNamespace

import frappe
import litellm
from litellm import InternalServerError, RateLimitError, APIError, BadRequestError, ContextWindowExceededError
from litellm.utils import trim_messages
from huf.ai.tool_serializer import serialize_tools
from huf.ai.prompt_cache_capabilities import model_supports_prompt_caching
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

# Default request timeout for LiteLLM completion calls (seconds)
_DEFAULT_LITELLM_TIMEOUT = 180


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


# High-performance in-memory cache for provider capabilities
# Stores capability flags to avoid Redis hits on every request
_L1_CAPABILITY_CACHE = {}


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


def _build_text_content(text: str, provider_name: str, cache_enabled: bool, cache_control_type: str):
    """Build provider-compatible message content payload with optional cache marker."""
    if not cache_enabled:
        return text

    if provider_name == "anthropic":
        return [{"type": "text", "text": text, "cache_control": {"type": cache_control_type}}]

    return [{"type": "text", "text": text}]


def _format_conversation_history(
    conversation_history: list,
    provider_name: str,
    cache_enabled: bool,
    cache_control_type: str,
) -> list:
    """Format conversation history messages, applying cache_control to the history prefix breakpoint if enabled."""
    if not conversation_history:
        return []

    formatted = [dict(msg) for msg in conversation_history]
    if not cache_enabled:
        return formatted

    last_msg = dict(formatted[-1])
    content = last_msg.get("content")

    if isinstance(content, str):
        last_msg["content"] = _build_text_content(content, provider_name, True, cache_control_type)
    elif isinstance(content, list) and len(content) > 0:
        content_copy = [dict(b) if isinstance(b, dict) else b for b in content]
        last_block = content_copy[-1]
        if isinstance(last_block, dict):
            last_block_copy = dict(last_block)
            if provider_name == "anthropic":
                last_block_copy["cache_control"] = {"type": cache_control_type}
            content_copy[-1] = last_block_copy
        last_msg["content"] = content_copy
    elif content is None or content == "":
        if provider_name == "anthropic":
            last_msg["content"] = [{"type": "text", "text": "", "cache_control": {"type": cache_control_type}}]

    formatted[-1] = last_msg
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
            frappe.log_error(f"Image file not found on disk: {file_path}", "LiteLLM Image Embed")
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
    try:
        # Configure LiteLLM to drop unsupported params (for models like gpt-5 that only support temperature=1)
        # This prevents errors when models don't support certain parameters
        litellm.drop_params = True

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
        is_local_llm = bool(provider_doc.get("is_local_llm", 0))
        api_base = _resolve_api_base(provider_doc)

        # Check prompt caching configuration
        enable_prompt_caching = False
        cache_control_type = "ephemeral"
        cache_system_message = False
        cache_conversation_history = False
        prompt_cache_options = _get_prompt_cache_options(context)
        static_prefix = (prompt_cache_options.get("static_prefix") or "").strip()
        dynamic_suffix = prompt_cache_options.get("dynamic_suffix")
        openai_prompt_cache_retention = prompt_cache_options.get("openai_prompt_cache_retention")
        gemini_cached_content = prompt_cache_options.get("gemini_cached_content")
        cache_static_prefix = bool(prompt_cache_options.get("cache_static_prefix", True))
        cache_dynamic_content_override = prompt_cache_options.get("cache_dynamic_content")
        
        if agent_doc:
            enable_prompt_caching = bool(agent_doc.get("enable_prompt_caching", 0))
            cache_control_type = agent_doc.get("cache_control_type") or "ephemeral"
            cache_system_message = bool(agent_doc.get("cache_system_message", 0))
            cache_conversation_history = bool(agent_doc.get("cache_conversation_history", 0))

        if is_local_llm:
            # Local providers (Ollama/LM Studio) do not support prompt-caching cache_control blocks.
            enable_prompt_caching = False

        max_context_chars = _get_agent_max_context_chars(agent_doc)
        
        # Check if model supports prompt caching
        model_supports_caching = False
        cache_skipped_unsupported_model = False
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
                    f"Failed to check prompt caching support for model {normalized_model}",
                    "LiteLLM Prompt Caching"
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
            history_cache_enabled = (
                enable_prompt_caching and model_supports_caching and cache_conversation_history
            )
            messages.extend(
                _format_conversation_history(
                    context["conversation_history"],
                    provider_name,
                    history_cache_enabled,
                    cache_control_type,
                )
            )
        
        # Add user message with cache_control if conversation history caching is enabled
        cache_dynamic_content = cache_conversation_history
        if isinstance(cache_dynamic_content_override, bool):
            cache_dynamic_content = cache_dynamic_content_override

        user_content = _build_text_content(
            dynamic_suffix,
            provider_name,
            enable_prompt_caching and model_supports_caching and cache_dynamic_content,
            cache_control_type,
        )
        
        # Append images if any are passed in context (embedded as base64 data URIs)
        if context and context.get("files"):
            user_content = _append_context_images_to_user_content(user_content, context.get("files"))
        
        messages.append({"role": "user", "content": user_content})

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
        }
        total_cost = 0.0
        all_new_items = []

        MAX_ROUNDS = getattr(agent, "max_turns", 10) or 10

        # Tool-call loop guard for non-streaming path (same rationale as run_stream).
        last_tool_signature = None
        tool_loop_repeats = 0
        MAX_TOOL_LOOP_REPEATS = 1

        for round_num in range(MAX_ROUNDS):

            # Temperature / Top P
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

            if temperature is None:
                temperature = 0.7

            # Build completion params
            completion_kwargs = {
                "model": normalized_model,
                "temperature": temperature,
                "timeout": _DEFAULT_LITELLM_TIMEOUT,
            }

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

            if top_p:
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

            capability_cache_key = f"litellm_tool_json_conflict:{provider_name}"
            
            known_conflict = _L1_CAPABILITY_CACHE.get(capability_cache_key)
             
            if known_conflict is None:
                known_conflict = frappe.cache().get_value(capability_cache_key)
                if known_conflict:
                    _L1_CAPABILITY_CACHE[capability_cache_key] = 1
            
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

                    if is_config_conflict:
                        _L1_CAPABILITY_CACHE[capability_cache_key] = 1
                        frappe.cache().set_value(capability_cache_key, 1)

                        frappe.log_error(
                            f"Provider '{provider}' returned bad request. Retrying without tools and caching capability limitation. Error: {str(e)}", 
                            "LiteLLM Auto-Recovery"
                        )
                        completion_kwargs.pop("tools", None)
                        completion_kwargs.pop("tool_choice", None)
                        
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

            try:
                round_cost, _cost_source = calculate_cost(
                    model_name=model,
                    input_tokens=round_usage["input_tokens"],
                    output_tokens=round_usage["output_tokens"],
                    cached_tokens=round_usage["cache_read_tokens"],
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
            "timeout": _DEFAULT_LITELLM_TIMEOUT,
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
            "timeout": _DEFAULT_LITELLM_TIMEOUT,
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
        is_local_llm = bool(provider_doc.get("is_local_llm", 0))
        api_base = _resolve_api_base(provider_doc)

        # Check prompt caching configuration
        enable_prompt_caching = False
        cache_control_type = "ephemeral"
        cache_system_message = False
        cache_conversation_history = False
        prompt_cache_options = _get_prompt_cache_options(context)
        static_prefix = (prompt_cache_options.get("static_prefix") or "").strip()
        dynamic_suffix = prompt_cache_options.get("dynamic_suffix")
        openai_prompt_cache_retention = prompt_cache_options.get("openai_prompt_cache_retention")
        gemini_cached_content = prompt_cache_options.get("gemini_cached_content")
        cache_static_prefix = bool(prompt_cache_options.get("cache_static_prefix", True))
        cache_dynamic_content_override = prompt_cache_options.get("cache_dynamic_content")
        
        if agent_doc:
            enable_prompt_caching = bool(agent_doc.get("enable_prompt_caching", 0))
            cache_control_type = agent_doc.get("cache_control_type") or "ephemeral"
            cache_system_message = bool(agent_doc.get("cache_system_message", 0))
            cache_conversation_history = bool(agent_doc.get("cache_conversation_history", 0))

        if is_local_llm:
            # Local providers (Ollama/LM Studio) do not support prompt-caching cache_control blocks.
            enable_prompt_caching = False

        # Check if model supports prompt caching
        model_supports_caching = False
        cache_skipped_unsupported_model = False
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
            history_cache_enabled = (
                enable_prompt_caching and model_supports_caching and cache_conversation_history
            )
            messages.extend(
                _format_conversation_history(
                    context["conversation_history"],
                    provider_name,
                    history_cache_enabled,
                    cache_control_type,
                )
            )
        
        cache_dynamic_content = cache_conversation_history
        if isinstance(cache_dynamic_content_override, bool):
            cache_dynamic_content = cache_dynamic_content_override

        user_content = _build_text_content(
            dynamic_suffix,
            provider_name,
            enable_prompt_caching and model_supports_caching and cache_dynamic_content,
            cache_control_type,
        )
        
        # Append images if any are passed in context (embedded as base64 data URIs)
        if context and context.get("files"):
            user_content = _append_context_images_to_user_content(user_content, context.get("files"))
        
        messages.append({"role": "user", "content": user_content})

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

        if temperature is None:
            temperature = 0.7

        completion_kwargs = {
            "model": normalized_model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,  # Enable streaming
            "stream_options": {"include_usage": True}, # Request usage stats in stream
            "timeout": _DEFAULT_LITELLM_TIMEOUT,
        }
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

        if top_p:
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
        }
        stream_total_cost = 0.0

        for round_num in range(MAX_ROUNDS):
            try:
                # Use LiteLLM completion with stream=True
                # LiteLLM completion() supports streaming when stream=True
                stream = await _litellm_completion_with_retry(**completion_kwargs)

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
                                                            f"Failed to update tool call message for call_id={call_id}, tool_call_doc={tool_call_doc}",
                                                            "Tool Call Message Update"
                                                        )
                                                else:
                                                    frappe.log_error(
                                                        f"No Agent Message found for tool call call_id={call_id}, tool_call_doc={tool_call_doc}",
                                                        "Tool Call Message Update"
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

                try:
                    round_cost, _cost_source = calculate_cost(
                        model_name=model,
                        input_tokens=round_usage["input_tokens"],
                        output_tokens=round_usage["output_tokens"],
                        cached_tokens=round_usage["cache_read_tokens"],
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
