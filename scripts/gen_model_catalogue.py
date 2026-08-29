#!/usr/bin/env python3
"""Generate huf/ai/model_catalogue.py from LiteLLM's model_cost table.

Usage:
    python scripts/gen_model_catalogue.py [--as-of YYYY-MM-DD] [--out PATH]

The output module exposes:
    MODELS      -- list[dict]: curated AI Model seed records
    DEPRECATED  -- tuple[str]: model_name values that should be deleted on
                   migrate (curated candidates that have since been
                   deprecated upstream per LiteLLM's deprecation_date).

Determinism: given the same installed litellm version and the same --as-of
date, this script produces a byte-identical output file. It never calls
datetime.now() to make a decision that affects output content -- "today" is
supplied explicitly.
"""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

try:
    import litellm
except ImportError:  # pragma: no cover
    print("litellm is required to run this generator", file=sys.stderr)
    raise

# --------------------------------------------------------------------------
# Allowed modality vocabulary (must match huf/huf/doctype/ai_model/ai_model.json
# field "modalities" -> options).
# --------------------------------------------------------------------------
TEXT = "Text"
VISION = "Vision"
IMAGE = "Image"
TTS = "Text-to-Speech"
STT = "Transcription"
EMB = "Embeddings"

ALLOWED_MODALITIES = {TEXT, VISION, IMAGE, TTS, STT, EMB, "OCR", "Speech-to-Speech", "Video"}

# --------------------------------------------------------------------------
# HUF provider display name -> LiteLLM litellm_provider value(s) this
# provider's models are looked up under, plus the LiteLLM model-key prefix
# (if any) to strip so the stored model_name matches HUF's existing
# convention (see huf/install.py::create_demo_ai_models -- e.g. OpenRouter
# entries are stored as "openai/gpt-5", not "openrouter/openai/gpt-5").
#
# Providers commented out in huf/install.py::create_demo_ai_providers() have
# no "AI Provider" record and are therefore skipped entirely (see
# SKIPPED_PROVIDERS below) -- an AI Model whose `provider` Link cannot
# resolve would fail validation.
# --------------------------------------------------------------------------
PROVIDER_LITELLM_KEYS = {
    "OpenAI": ("openai",),
    "Anthropic": ("anthropic",),
    "Google": ("gemini",),
    "OpenRouter": ("openrouter",),
    "DeepSeek": ("deepseek",),
    "Moonshot": ("moonshot",),
    "Groq": ("groq",),
    "Cohere": ("cohere", "cohere_chat"),
    "Perplexity": ("perplexity",),
    "ElevenLabs": ("elevenlabs",),
    "Huggingface": ("huggingface",),
    "AWS Bedrock": ("bedrock", "bedrock_converse"),
    "Vertex AI": ("vertex_ai",),
    "Mistral": ("mistral",),
    "xAI": ("xai",),
    "Alibaba": ("dashscope",),
}

# Prefix to strip from the LiteLLM model key when deriving the stored
# model_name, per provider. Groq has no unprefixed convention anywhere in
# HUF today, so its LiteLLM "groq/" prefix is kept as-is (it is also
# required for LiteLLM to route the call correctly).
STRIP_PREFIX = {
    "OpenAI": "",
    "Anthropic": "",
    "Google": "gemini/",
    "OpenRouter": "openrouter/",
    "DeepSeek": "deepseek/",
    "Moonshot": "moonshot/",
    "Groq": "",
    "Cohere": "cohere/",
    "Perplexity": "perplexity/",
    "ElevenLabs": "elevenlabs/",
    "Huggingface": "",
    # AWS Bedrock and Vertex AI have no entry in
    # huf/ai/providers/litellm.py::_normalize_model_name's
    # provider_prefix_map, so a bare (unprefixed) stored model_name would
    # be routed through LiteLLM as "<provider display name, lowercased>/model"
    # -- wrong. Instead, keep the routing prefix baked into the stored
    # model_name (see ADD_PREFIX below / candidate keys), which
    # _normalize_model_name passes through unchanged because it already
    # contains "/". Mirrors the existing Groq precedent.
    "AWS Bedrock": "",
    "Vertex AI": "",
    "Mistral": "mistral/",
    "xAI": "xai/",
    "Alibaba": "dashscope/",
}

# Prefix to prepend (opposite of STRIP_PREFIX) so the stored model_name still
# carries the routing prefix LiteLLM needs, for providers with no entry in
# _normalize_model_name's provider_prefix_map. See STRIP_PREFIX comment above.
ADD_PREFIX = {
    "AWS Bedrock": "bedrock/",
}

# Providers named in the task brief that do not have a corresponding
# "AI Provider" record seeded by huf/install.py::create_demo_ai_providers()
# (they are present there only as commented-out entries). An AI Model's
# `provider` field is a required Link to "AI Provider", so seeding a model
# against one of these would violate the doctype -- they are skipped.
SKIPPED_PROVIDERS_NO_RECORD = {
    "TII Falcon": "no 'AI Provider' record, and no litellm_provider group for Falcon exists in "
                  "litellm.model_cost -- confirmed by scanning every key in litellm.model_cost "
                  "for a 'falcon' litellm_provider value (none) and for 'falcon' anywhere in the "
                  "model key itself (zero matches). Not invented; not enabled.",
}

# --------------------------------------------------------------------------
# Curated candidate model keys per provider, as they appear (verbatim) as
# keys in litellm.model_cost. This is the judgement pass: flagship/
# widely-used models, long-context variants kept distinct, dated snapshots
# and region-prefixed duplicates excluded, fine-tune scaffolds (ft:...)
# excluded, moderation/rerank entries excluded (no matching modality rule).
#
# Candidates that turn out to be past their deprecation_date as of --as-of
# are automatically moved to DEPRECATED instead of MODELS -- see build().
# --------------------------------------------------------------------------
CANDIDATES: dict[str, list[str]] = {
    "OpenAI": [
        # Chat / reasoning flagships
        "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna",
        "gpt-5.5", "gpt-5.5-pro",
        "gpt-5.4", "gpt-5.4-pro", "gpt-5.4-mini", "gpt-5.4-nano",
        "gpt-5.3-codex",
        "gpt-5.2", "gpt-5.2-pro",
        "gpt-5.1",
        "gpt-5", "gpt-5-mini", "gpt-5-nano",
        "chat-latest",
        "gpt-5.3-chat-latest", "gpt-5.2-chat-latest",
        "gpt-4.1", "gpt-4.1-mini",
        "gpt-4o", "gpt-4o-mini",
        "o3", "o4-mini",
        # Text-to-Speech
        "gpt-4o-mini-tts", "tts-1", "tts-1-hd",
        # Transcription
        "whisper-1", "gpt-4o-transcribe", "gpt-4o-mini-transcribe",
        "gpt-transcribe", "gpt-live-transcribe", "gpt-realtime-whisper",
        # Image
        "gpt-image-2", "gpt-image-1", "gpt-image-1-mini", "chatgpt-image-latest",
        # Embeddings
        "text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002",
        "gpt-5.6",
        "gpt-5.6-cyber",
        "daybreak-blue-latest",
        "daybreak-red-latest",
    ],
    "Anthropic": [
        "claude-opus-5",
        "claude-mythos-5",
        "claude-fable-5",
        "claude-opus-4-8",
        "claude-opus-4-7",
        "claude-opus-4-6",
        "claude-opus-4-5",
        "claude-sonnet-4-6",
        "claude-sonnet-4-5",
        "claude-haiku-4-5",
        "claude-sonnet-5",
        "claude-mythos-preview",
    ],
    "Google": [
        "gemini/gemini-3.6-flash",
        "gemini/gemini-3.5-flash",
        "gemini/gemini-3.5-flash-lite",
        "gemini/gemini-3.1-flash-lite",
        "gemini/gemini-3.1-pro-preview",
        "gemini/gemini-3-flash-preview",
        "gemini/gemini-3.7-flash",
        "gemini/gemini-2.5-pro",
        "gemini/gemini-2.5-flash",
        "gemini/gemini-2.5-flash-lite",
        "gemini/gemma-3-27b-it",
        "gemini-pro-latest",
        "gemini-flash-latest",
        "gemini-flash-lite-latest",
        # Image
        "gemini/gemini-3-pro-image",
        "gemini/gemini-3.1-flash-image",
        "gemini/gemini-3.1-flash-lite-image",
        "gemini/gemini-2.5-flash-image",
        # Text-to-Speech
        "gemini/gemini-3.1-flash-tts-preview",
        "gemini/gemini-2.5-flash-preview-tts",
        # Transcription
        "gemini/gemini-3.5-transcribe",
        # Embeddings
        "gemini/gemini-embedding-001",
        "gemini/gemini-embedding-2",
    ],
    "OpenRouter": [
        "openrouter/anthropic/claude-opus-5",
        "openrouter/anthropic/claude-opus-4.6",
        "openrouter/anthropic/claude-sonnet-4.6",
        "openrouter/anthropic/claude-sonnet-4.5",
        "openrouter/anthropic/claude-haiku-4.5",
        "openrouter/google/gemini-3-pro-preview",
        "openrouter/google/gemini-3-flash-preview",
        "openrouter/google/gemini-3.1-pro-preview",
        "openrouter/google/gemini-3.1-flash-lite",
        "openrouter/openai/gpt-5.2",
        "openrouter/openai/gpt-5.2-pro",
        "openrouter/openai/gpt-5.1-codex-max",
        "openrouter/openai/gpt-oss-120b",
        "openrouter/openai/gpt-oss-20b",
        "openrouter/deepseek/deepseek-v4-pro",
        "openrouter/deepseek/deepseek-v3.2",
        "openrouter/deepseek/deepseek-chat-v3.1",
        "openrouter/moonshotai/kimi-k2.5",
        "openrouter/minimax/minimax-m2.5",
        "openrouter/minimax/minimax-m2.1",
        "openrouter/z-ai/glm-5.1",
        "openrouter/z-ai/glm-4.7",
        "openrouter/mistralai/mistral-large-2512",
        "openrouter/mistralai/devstral-2512",
        "openrouter/qwen/qwen3.6-plus",
        "openrouter/qwen/qwen3.5-flash-02-23",
        "openrouter/qwen/qwen3-coder-plus",
        "openrouter/qwen/qwen3-coder",
        "openrouter/xiaomi/mimo-v2.5",
        "openrouter/openrouter/auto",
        "openrouter/openrouter/free",
        "openrouter/google/gemini-2.5-pro",
        "openrouter/google/gemini-2.5-flash",
        "openrouter/openai/gpt-5",
        "openrouter/openai/gpt-5-mini",
        "openrouter/openai/gpt-5-nano",
        "openrouter/openai/gpt-5-codex",
        "openrouter/openai/gpt-4.1",
        "openrouter/openai/gpt-4.1-mini",
        "openrouter/openai/gpt-4.1-nano",
        "openrouter/anthropic/claude-opus-4.7",
        "openrouter/anthropic/claude-opus-4.5",
        "openrouter/x-ai/grok-4",
        "openrouter/z-ai/glm-5",
        "openrouter/xiaomi/mimo-v2.5-pro",
    ],
    "DeepSeek": [
        "deepseek-chat",
        "deepseek-reasoner",
        "deepseek/deepseek-r1",
        "deepseek/deepseek-v3.2",
        "deepseek-v4-flash",
        "deepseek-v4-flash-vision-exp",
        "deepseek-v4-pro",
    ],
    "Moonshot": [
        "moonshot/kimi-k3",
        "moonshot/kimi-k2.6",
        "moonshot/kimi-k2.5",
        "moonshot/kimi-k2-thinking",
        "moonshot/kimi-k2-thinking-turbo",
        "moonshot/kimi-latest",
        "moonshot/kimi-latest-128k",
        "moonshot/moonshot-v1-128k",
        "moonshot/moonshot-v1-128k-vision-preview",
        "moonshot/moonshot-v1-32k",
        "moonshot/moonshot-v1-8k",
        "moonshot/moonshot-v1-auto",
        "moonshot/moonshot-v1-32k-vision-preview",
        "moonshot/moonshot-v1-8k-vision-preview",
    ],
    "Groq": [
        "groq/llama-3.3-70b-versatile",
        "groq/llama-3.1-8b-instant",
        "groq/meta-llama/llama-4-maverick-17b-128e-instruct",
        "groq/meta-llama/llama-4-scout-17b-16e-instruct",
        "groq/openai/gpt-oss-120b",
        "groq/openai/gpt-oss-20b",
        "groq/qwen/qwen3.6-27b",
        "groq/qwen/qwen3-32b",
        "groq/whisper-large-v3",
        "groq/whisper-large-v3-turbo",
        "groq/playai-tts",
    ],
    "Cohere": [
        "command-a-03-2025",
        "command-r-08-2024",
        "command-r-plus-08-2024",
        "command-r7b-12-2024",
        "cohere/embed-v4.0",
        "embed-english-v3.0",
        "embed-multilingual-v3.0",
        "embed-english-light-v3.0",
        "embed-multilingual-light-v3.0",
    ],
    "Perplexity": [
        "perplexity/sonar",
        "perplexity/sonar-pro",
        "perplexity/sonar-reasoning",
        "perplexity/sonar-reasoning-pro",
        "perplexity/sonar-deep-research",
    ],
    "ElevenLabs": [
        "elevenlabs/eleven_multilingual_v2",
        "elevenlabs/eleven_v3",
        "elevenlabs/scribe_v1",
        "elevenlabs/scribe_v1_experimental",
    ],
    "Huggingface": [
        # litellm.model_cost carries zero "huggingface" litellm_provider
        # entries in this litellm version -- nothing to curate. See report.
    ],
    # AWS Bedrock: keys as they appear (unprefixed) under litellm_provider
    # "bedrock"/"bedrock_converse". Canonical (non-region-prefixed,
    # non-commitment) keys only -- litellm.model_cost carries dozens of
    # region-duplicated ("ap-northeast-1/...", "eu...", "apac...") and
    # reserved-capacity ("1-month-commitment/...") duplicates of the same
    # models, which are excluded here. STRIP_PREFIX is "" and ADD_PREFIX
    # bakes "bedrock/" back onto the stored model_name (see STRIP_PREFIX
    # comment above) so LiteLLM routing is unaffected by the missing
    # provider_prefix_map entry.
    "AWS Bedrock": [
        "anthropic.claude-opus-5",
        "anthropic.claude-sonnet-5",
        "anthropic.claude-fable-5",
        "anthropic.claude-opus-4-8",
        "anthropic.claude-sonnet-4-6",
        "anthropic.claude-haiku-4-5-20251001-v1:0",
        "deepseek.v3.2",
        "amazon.nova-2-pro-preview-20251202-v1:0",
        "amazon.nova-2-lite-v1:0",
        "amazon.nova-pro-v1:0",
        "amazon.nova-lite-v1:0",
        "amazon.nova-micro-v1:0",
        "amazon.titan-embed-text-v2:0",
        "amazon.titan-image-generator-v2:0",
    ],
    # Vertex AI (Google): candidates are drawn only from litellm_provider
    # "vertex_ai" keys that already carry the "vertex_ai/" prefix baked into
    # the litellm.model_cost key itself (as opposed to the parallel
    # "vertex_ai-language-models" group, whose keys are bare and would need
    # a second, inconsistent prefixing rule) -- keeps STRIP_PREFIX/ADD_PREFIX
    # simple and the stored model_name identical to the litellm key.
    # Audio (chirp), OCR, vector-store, and xai-via-vertex duplicate entries
    # are excluded (no clean modality mapping / already covered by xAI direct).
    "Vertex AI": [
        "vertex_ai/gemini-3-pro-preview",
        "vertex_ai/gemini-3-flash-preview",
        "vertex_ai/gemini-3.1-pro-preview",
        "vertex_ai/gemini-3.5-flash",
        "vertex_ai/gemini-3.6-flash",
        "vertex_ai/gemini-3.7-flash",
        "vertex_ai/gemini-embedding-2",
        "vertex_ai/xai/grok-4.1-fast-reasoning",
        "vertex_ai/xai/grok-4.1-fast-non-reasoning",
        "vertex_ai/xai/grok-4.20-reasoning",
        "vertex_ai/xai/grok-4.20-non-reasoning",
    ],
    "Mistral": [
        "mistral/mistral-large-latest",
        "mistral/mistral-medium-latest",
        "mistral/mistral-small-latest",
        "mistral/ministral-8b-latest",
        "mistral/ministral-3b-latest",
        "mistral/codestral-latest",
        "mistral/devstral-latest",
        "mistral/magistral-medium-latest",
        "mistral/mistral-embed",
        "mistral/mistral-large-3",
        "mistral/mistral-medium-3",
        "mistral/mistral-medium-3-5",
        "mistral/devstral-small-latest",
        "mistral/devstral-medium-latest",
        "mistral/pixtral-large-latest",
        "mistral/magistral-small-latest",
        "mistral/ministral-14b-latest",
        "mistral/codestral-mamba-latest",
        "mistral/zai-glm-5-2",
    ],
    "xAI": [
        "xai/grok-4.6",
        "xai/grok-4.5",
        "xai/grok-4.3",
        "xai/grok-4-1-fast",
        "xai/grok-3-mini-latest",
        "xai/grok-3-fast-latest",
        "xai/grok-4.3-latest",
        "xai/grok-4.5-latest",
        "xai/grok-4.20-0309-reasoning",
        "xai/grok-4.20-0309-non-reasoning",
        "xai/grok-build-0.1",
        "xai/grok-3-mini-fast-latest",
    ],
    # Alibaba: HUF has a single "Alibaba" AI Provider (provider_brand
    # "dashscope") covering Qwen/DashScope -- litellm.model_cost has no
    # separate "alibaba" litellm_provider group, only "dashscope".
    "Alibaba": [
        "dashscope/qwen3-max",
        "dashscope/qwen3.7-max",
        "dashscope/qwen3.8-max",
        "dashscope/qwen-plus-latest",
        "dashscope/qwen-turbo-latest",
        "dashscope/qwen3-coder-plus",
        "dashscope/qwen3-vl-plus",
        "dashscope/qwen-image-3.0",
        "dashscope/qwen-image-3.0-pro",
        "dashscope/qwen-max",
        "dashscope/qwen-flash",
        "dashscope/qwen-coder",
        "dashscope/qwen3.5-plus",
        "dashscope/qwen3.7-plus",
        "dashscope/qwen3-coder-flash",
        "dashscope/qwen3-vl-235b-a22b-instruct",
        "dashscope/qwen3-vl-235b-a22b-thinking",
        "dashscope/qwen3-vl-32b-instruct",
        "dashscope/qwen3-next-80b-a3b-instruct",
        "dashscope/qwen3-next-80b-a3b-thinking",
        "dashscope/glm-5.1",
        "dashscope/glm-5.2",
        "dashscope/qwq-plus",
    ],
}


def modalities_for(entry: dict) -> list[str]:
    mode = entry.get("mode")
    mods: list[str] = []
    if mode == "chat":
        mods.append(TEXT)
        if entry.get("supports_vision"):
            mods.append(VISION)
    elif mode == "image_generation":
        mods.append(IMAGE)
    elif mode == "audio_transcription":
        mods.append(STT)
    elif mode == "audio_speech":
        mods.append(TTS)
    elif mode == "embedding":
        mods.append(EMB)
    return mods


def parse_date(value) -> datetime.date | None:
    if not value:
        return None
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError:
        return None


def strip_prefix(provider: str, key: str) -> str:
    prefix = STRIP_PREFIX.get(provider, "")
    if prefix and key.startswith(prefix):
        return key[len(prefix):]
    return key


def _positive_int(value) -> int | None:
    """Coerce a LiteLLM token limit to a positive int, or None if unusable.

    LiteLLM is not consistent about the numeric type it stores: most entries use
    int, but some (e.g. xai/grok-4-1-fast) carry a float like 2000000.0. An
    isinstance(value, int) test silently drops those, so the model ends up with
    no context_window at all. bool is excluded because bool is a subclass of int.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value != value or value in (float("inf"), float("-inf")):  # NaN / inf
        return None
    ivalue = int(value)
    return ivalue if ivalue > 0 else None


def build(as_of: datetime.date, model_cost: dict) -> tuple[list[dict], list[str], dict]:
    """Returns (models, deprecated_names, stats).

    stats: {"per_provider": {provider: count}, "excluded_deprecated": int,
            "missing_keys": {provider: [keys not found in model_cost]}}
    """
    models: dict[str, dict] = {}  # model_name -> entry (dedupe)
    deprecated: set[str] = set()
    per_provider_count: dict[str, int] = {}
    missing_keys: dict[str, list[str]] = {}
    excluded_deprecated = 0

    for provider, keys in CANDIDATES.items():
        per_provider_count.setdefault(provider, 0)
        for key in keys:
            entry = model_cost.get(key)
            if entry is None:
                missing_keys.setdefault(provider, []).append(key)
                continue

            model_name = strip_prefix(provider, key)
            model_name = ADD_PREFIX.get(provider, "") + model_name
            dep_date = parse_date(entry.get("deprecation_date"))

            if dep_date is not None and dep_date < as_of:
                deprecated.add(model_name)
                excluded_deprecated += 1
                continue

            mods = modalities_for(entry)
            mods = [m for m in mods if m in ALLOWED_MODALITIES]

            record: dict = {
                "model_name": model_name,
                "provider": provider,
            }
            if mods:
                record["modalities"] = ",".join(mods)

            ctx = entry.get("max_input_tokens") or entry.get("max_tokens")
            if _positive_int(ctx) is not None:
                record["context_window"] = _positive_int(ctx)

            max_out = _positive_int(entry.get("max_output_tokens"))
            if max_out is not None:
                record["max_output_tokens"] = max_out

            if entry.get("supports_reasoning") is True:
                record["supports_reasoning"] = True

            if model_name in models and models[model_name] != record:
                # Two candidate keys collapsed to the same stored
                # model_name (e.g. an aliased/unprefixed litellm entry
                # duplicating a prefixed one). Keep the first, deterministic
                # by candidate list order.
                continue

            models[model_name] = record
            per_provider_count[provider] += 1

    # A name cannot be both current and deprecated.
    deprecated -= set(models.keys())

    sorted_models = sorted(models.values(), key=lambda m: (m["provider"], m["model_name"]))
    sorted_deprecated = sorted(deprecated)

    stats = {
        "per_provider": per_provider_count,
        "excluded_deprecated": excluded_deprecated,
        "missing_keys": missing_keys,
    }
    return sorted_models, sorted_deprecated, stats


def render(models: list[dict], deprecated: list[str], as_of: datetime.date, litellm_version: str) -> str:
    lines = []
    lines.append('"""Auto-generated AI Model catalogue. DO NOT EDIT BY HAND.')
    lines.append("")
    lines.append(f"Generated by: scripts/gen_model_catalogue.py")
    lines.append(f"litellm version: {litellm_version}")
    lines.append(f"--as-of date: {as_of.isoformat()}")
    lines.append(f"Entry count: {len(models)} models, {len(deprecated)} deprecated")
    lines.append("")
    lines.append("Regenerate with:")
    lines.append("    python scripts/gen_model_catalogue.py --as-of " + as_of.isoformat())
    lines.append('"""')
    lines.append("")
    lines.append("MODELS = [")
    for m in models:
        parts = [f'"model_name": {m["model_name"]!r}', f'"provider": {m["provider"]!r}']
        if "modalities" in m:
            parts.append(f'"modalities": {m["modalities"]!r}')
        if "context_window" in m:
            parts.append(f'"context_window": {m["context_window"]!r}')
        if "max_output_tokens" in m:
            parts.append(f'"max_output_tokens": {m["max_output_tokens"]!r}')
        if "supports_reasoning" in m:
            parts.append(f'"supports_reasoning": {m["supports_reasoning"]!r}')
        lines.append("    {" + ", ".join(parts) + "},")
    lines.append("]")
    lines.append("")
    lines.append("DEPRECATED = (")
    for name in deprecated:
        lines.append(f"    {name!r},")
    lines.append(")")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--as-of",
        default=datetime.date.today().isoformat(),
        help="ISO date (YYYY-MM-DD) to evaluate deprecation_date against. "
             "Passed explicitly so output is reproducible; the generator "
             "itself never calls datetime.now() to decide content.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output path for the generated module (default: huf/ai/model_catalogue.py "
             "relative to the repo root inferred from this script's location).",
    )
    args = parser.parse_args()

    as_of = datetime.date.fromisoformat(args.as_of)

    litellm_version = "unknown"
    try:
        from importlib.metadata import version as _pkg_version
        litellm_version = _pkg_version("litellm")
    except Exception:
        pass

    model_cost = litellm.model_cost

    models, deprecated, stats = build(as_of, model_cost)

    out_path = Path(args.out) if args.out else (
        Path(__file__).resolve().parent.parent / "huf" / "ai" / "model_catalogue.py"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(models, deprecated, as_of, litellm_version))

    print(f"Wrote {out_path} ({len(models)} models, {len(deprecated)} deprecated)")
    print(f"litellm version: {litellm_version}")
    print(f"as-of: {as_of.isoformat()}")
    print("Per-provider counts:")
    for provider in CANDIDATES:
        print(f"  {provider}: {stats['per_provider'].get(provider, 0)}")
    print(f"Excluded as deprecated (candidate had a past deprecation_date): {stats['excluded_deprecated']}")
    if stats["missing_keys"]:
        print("Candidate keys not found in litellm.model_cost (skipped):")
        for provider, keys in stats["missing_keys"].items():
            for k in keys:
                print(f"  {provider}: {k}")
    print("Providers skipped entirely (no AI Provider record / no litellm coverage):")
    for provider, reason in SKIPPED_PROVIDERS_NO_RECORD.items():
        print(f"  {provider}: {reason}")
    print("  Huggingface: candidate list processed but litellm.model_cost has zero 'huggingface' entries in this version")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
