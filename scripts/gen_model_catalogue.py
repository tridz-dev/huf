#!/usr/bin/env python3
"""Generate huf/ai/model_catalogue.py from LiteLLM's model_cost table.

Usage:
    python scripts/gen_model_catalogue.py [--as-of YYYY-MM-DD] [--out PATH]

The output module exposes:
    MODELS   -- list[dict]: curated AI Model seed records (LiteLLM-backed
                candidates + EXTRA_MODELS), aliases flagged is_latest_alias.
    RETIRED  -- dict[str, str | None]: model_name -> replacement for models
                removed from existing sites (hand-verified RETIRED table plus
                candidates past their LiteLLM deprecation_date).

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
except ImportError:  # pragma: no cover -- only needed without --model-cost-json
    litellm = None

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
    # Sources (retrieved 2026-10-22): developers.openai.com/api/docs/models,
    # /models/all, /deprecations. Deprecated names live in RETIRED below.
    "OpenAI": [
        # Chat / reasoning
        "gpt-6.1-sol", "gpt-6-sol", "gpt-6-astra", "gpt-6-luna",
        "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.6-cyber",
        "gpt-5.5", "gpt-5.5-pro",
        "gpt-5.4", "gpt-5.4-pro", "gpt-5.4-mini", "gpt-5.4-nano",
        "gpt-5.3-codex",
        "gpt-5.2", "gpt-5.2-pro",
        "gpt-5.1",
        "gpt-5", "gpt-5-mini", "gpt-5-nano",
        # Latest-tracking alias ("not recommended for API use" per OpenAI,
        # but it is the one moving chat alias OpenAI still serves).
        "chat-latest",
        # Text-to-Speech
        "gpt-4o-mini-tts",
        # Transcription
        # gpt-live-transcribe / gpt-realtime-whisper are Realtime-API only and
        # cannot serve litellm.transcription, so they are not seeded.
        "gpt-transcribe",
        "gpt-4o-mini-transcribe",
        # Image
        "gpt-image-2.5-sunburst", "gpt-image-2.5-flare", "gpt-image-2",
        # Embeddings
        "text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002",
    ],
    # Sources: platform.claude.com/docs/en/about-claude/models/overview and
    # /model-deprecations. Anthropic publishes NO "-latest" aliases; undated
    # IDs from 4.6 onward are fixed snapshots.
    "Anthropic": [
        "claude-fable-5-1",
        "claude-opus-5-5",
        "claude-sonnet-5-5",
        "claude-haiku-5-5",
        "claude-mythos-5-1",
        "claude-mythos-5",
        "claude-fable-5",
        "claude-opus-5",
        "claude-sonnet-5",
        "claude-opus-4-8",
        "claude-opus-4-7",
        "claude-opus-4-6",
        "claude-opus-4-5",
        "claude-sonnet-4-6",
        "claude-haiku-4-5",
    ],
    # Sources: ai.google.dev/gemini-api/docs/models, /deprecations (updated
    # 2026-10-20), /changelog. Gemini 2.5 is closed to new users since
    # 2026-09-18 -> removed (see RETIRED).
    "Google": [
        # Latest-tracking aliases (preferred defaults)
        "gemini-flash-latest",
        "gemini-pro-latest",
        "gemini-flash-lite-latest",
        # Pinned chat models
        "gemini/gemini-4-argon",
        "gemini/gemini-3.8-flash",
        "gemini/gemini-3.6-flash",
        "gemini/gemini-3.5-flash-lite",
        "gemini/gemini-3.1-pro-preview",
        "gemini/gemini-3-flash-preview",
        "gemini/gemma-3-27b-it",
        # Image
        "gemini/gemini-nano-banana-2.1",
        "gemini/gemini-3-pro-image",
        "gemini/gemini-3.1-flash-image",
        "gemini/gemini-3.1-flash-lite-image",
        # Text-to-Speech
        "gemini/gemini-3.8-flash-tts",
        "gemini/gemini-3.8-flash-lite-tts",
        # Embeddings
        "gemini/gemini-embedding-2",
        # Transcription: HUF transcribes Gemini audio through a multimodal
        # completion (audio_service.MULTIMODAL_STT_PROVIDERS), so the
        # Transcription-capable Google model is the gemini-flash-latest alias
        # (see MODALITY_OVERRIDES). gemini-3.5-transcribe is a real model but
        # is not served through generateContent, which is why it returned an
        # empty transcript on the bench -- it is intentionally not seeded.
    ],
    # OpenRouter is curated from the live https://openrouter.ai/api/v1/models
    # list in EXTRA_MODELS below (LiteLLM's table lags OpenRouter badly).
    "OpenRouter": [],
    # Sources: api-docs.deepseek.com/quick_start/pricing, /news/news261017.
    # deepseek-chat / deepseek-reasoner were deprecated 2026-07-24;
    # deepseek-flash is the moving Flash name (V4.1-Flash-1017 today).
    "DeepSeek": [
        "deepseek-flash",
        "deepseek-v4-pro",
    ],
    # Source: platform.kimi.ai/docs/pricing/chat (IDs cross-checked against
    # LiteLLM). kimi-latest, kimi-k2-thinking*, kimi-k2.5 and moonshot-v1-*
    # are discontinued.
    "Moonshot": [
        "moonshot/kimi-k3",
        "moonshot/kimi-k2.7-code",
        "moonshot/kimi-k2.6",
    ],
    # Sources: console.groq.com/docs/models, /docs/deprecations.
    "Groq": [
        "groq/openai/gpt-oss-120b",
        "groq/openai/gpt-oss-20b",
        "groq/qwen/qwen3.8-27b",
        "groq/whisper-large-v3",
        "groq/whisper-large-v3-turbo",
        "groq/canopylabs/orpheus-v1-english",
        "groq/canopylabs/orpheus-arabic-saudi",
    ],
    # Sources: docs.cohere.com/docs/models, /docs/deprecations.
    "Cohere": [
        "command-a-plus-05-2026",
        "command-a-03-2025",
        "command-r-08-2024",
        "command-r-plus-08-2024",
        "command-r7b-12-2024",
        "cohere/embed-v5.0-pro",
        "cohere/embed-v5.0-fast",
        "cohere/embed-v4.0",
        "embed-english-v3.0",
        "embed-multilingual-v3.0",
        "embed-english-light-v3.0",
        "embed-multilingual-light-v3.0",
    ],
    # Source: docs.perplexity.ai/getting-started/models -- only `sonar` is
    # still listed; the sonar-pro / sonar-reasoning* / sonar-deep-research
    # Chat Completions models are gone (see RETIRED).
    "Perplexity": [
        "perplexity/sonar",
    ],
    # Source: elevenlabs.io/docs/models. eleven_turbo_v2_5 and scribe_v1 are
    # deprecated (see RETIRED); eleven_flash_v2_5 lives in EXTRA_MODELS
    # because LiteLLM has no entry for it.
    "ElevenLabs": [
        "elevenlabs/eleven_v3",
        "elevenlabs/eleven_multilingual_v2",
        "elevenlabs/scribe_v2",
    ],
    "Huggingface": [],
    # Source: docs.aws.amazon.com/bedrock/latest/userguide/model-lifecycle-legacy.html
    "AWS Bedrock": [
        "anthropic.claude-opus-5-5",
        "anthropic.claude-sonnet-5-5",
        "anthropic.claude-haiku-5-5",
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
    ],
    # Vertex model-versions page could not be fully read (see notes); IDs are
    # the Gemini API equivalents that LiteLLM lists under vertex_ai/.
    "Vertex AI": [
        "vertex_ai/gemini-4-argon",
        "vertex_ai/gemini-3.8-flash",
        "vertex_ai/gemini-3.1-pro-preview",
        "vertex_ai/gemini-3-flash-preview",
        "vertex_ai/gemini-3.8-flash-tts",
        "vertex_ai/gemini-3.8-flash-lite-tts",
        "vertex_ai/gemini-embedding-2",
        "vertex_ai/xai/grok-4.7",
        "vertex_ai/xai/grok-4.6",
        "vertex_ai/xai/grok-4.3",
        "vertex_ai/xai/grok-4.20-reasoning",
        "vertex_ai/xai/grok-4.20-non-reasoning",
    ],
    # Source: docs.mistral.ai/getting-started/models/models_overview/ (current
    # families) + LiteLLM for the API IDs. Mistral's "-latest" aliases are the
    # recommended entry points.
    "Mistral": [
        "mistral/mistral-large-latest",
        "mistral/mistral-medium-latest",
        "mistral/mistral-small-latest",
        "mistral/ministral-14b-latest",
        "mistral/ministral-8b-latest",
        "mistral/ministral-3b-latest",
        "mistral/codestral-latest",
        "mistral/voxtral-mini-latest",
        "mistral/voxtral-mini-tts-latest",
        "mistral/mistral-large-4",
        "mistral/mistral-large-3",
        "mistral/mistral-medium-3-5",
        "mistral/zai-glm-5-3",
        "mistral/mistral-embed",
        "mistral/codestral-embed",
    ],
    # Sources: docs.x.ai/docs/models, /docs/migration/may-15-retirement.
    "xAI": [
        "xai/grok-4.7",
        "xai/grok-4.6",
        "xai/grok-4.5",
        "xai/grok-4.5-latest",
        "xai/grok-4.3",
        "xai/grok-4.3-latest",
        "xai/grok-4.20-0309-reasoning",
        "xai/grok-4.20-0309-non-reasoning",
        "xai/grok-build-0.1",
        "xai/grok-build-latest",
        "xai/grok-imagine-image-2.0",
    ],
    # Source: alibabacloud.com/help/en/model-studio/models (+ /model-depreciation).
    "Alibaba": [
        "dashscope/qwen3.8-max",
        "dashscope/qwen3.8-flash",
        "dashscope/qwen3.8-omni-flash",
        "dashscope/qwen3.7-max",
        "dashscope/qwen3.7-plus",
        "dashscope/qwen3.5-plus",
        "dashscope/qwen-plus-latest",
        "dashscope/qwen-flash",
        "dashscope/qwen-coder",
        "dashscope/qwen3-coder-plus",
        "dashscope/qwen3-coder-flash",
        "dashscope/qwen3-vl-plus",
        "dashscope/qwen3-vl-235b-a22b-instruct",
        "dashscope/qwen3-vl-235b-a22b-thinking",
        "dashscope/qwen3-vl-32b-instruct",
        "dashscope/qwen3-next-80b-a3b-instruct",
        "dashscope/qwen3-next-80b-a3b-thinking",
        "dashscope/qwen-image-3.0",
        "dashscope/qwen-image-3.0-pro",
        "dashscope/glm-5.1",
        "dashscope/glm-5.2",
        "dashscope/qwq-plus",
    ],
}

# --------------------------------------------------------------------------
# Stored model_names that track the provider's newest model rather than a
# pinned snapshot. Emitted as is_latest_alias=1 on the AI Model record.
# --------------------------------------------------------------------------
ALIASES: set[str] = {
    # OpenAI
    "chat-latest",
    # Google
    "gemini-flash-latest", "gemini-pro-latest", "gemini-flash-lite-latest",
    # DeepSeek: the un-versioned Flash name is re-pointed on every release.
    "deepseek-flash",
    # Mistral
    "mistral-large-latest", "mistral-medium-latest", "mistral-small-latest",
    "ministral-14b-latest", "ministral-8b-latest", "ministral-3b-latest",
    "codestral-latest", "voxtral-mini-latest", "voxtral-mini-tts-latest",
    # xAI
    "grok-4.5-latest", "grok-4.3-latest", "grok-build-latest",
    # Alibaba
    "qwen-plus-latest",
    # OpenRouter (live list, "~" prefix = latest-tracking router alias)
    "~google/gemini-flash-latest", "~google/gemini-pro-latest",
    "~anthropic/claude-opus-latest", "~anthropic/claude-sonnet-latest",
    "~anthropic/claude-haiku-latest", "~anthropic/claude-fable-latest",
    "~openai/gpt-sol-latest", "~openai/gpt-luna-latest", "~openai/gpt-terra-latest",
    "~openai/gpt-astra-latest", "~openai/gpt-mini-latest", "openai/gpt-chat-latest",
    "~x-ai/grok-latest", "~moonshotai/kimi-latest", "~z-ai/glm-latest",
    "~deepseek/deepseek-flash-latest", "~deepseek/deepseek-pro-latest",
    "openrouter/auto",
}

# Modalities LiteLLM's "mode" cannot express. Gemini chat models accept audio
# and HUF's Google STT path is a multimodal completion, so the Flash alias is
# the provider's Transcription model.
MODALITY_OVERRIDES: dict[str, str] = {
    "gemini-flash-latest": "Text,Vision,Transcription",
}

# --------------------------------------------------------------------------
# Models LiteLLM has no (or no usable) entry for, written out in full. This
# replaces the hand list that used to live in huf/install.py so that this
# generator is the single source of truth for the seeded catalogue.
# OpenRouter slugs and context lengths are taken from the live
# https://openrouter.ai/api/v1/models list (retrieved 2026-10-22).
# --------------------------------------------------------------------------
def _e(model_name, provider, modalities, context_window=None, max_output_tokens=None, reasoning=False):
    entry = {"model_name": model_name, "provider": provider, "modalities": modalities}
    if context_window:
        entry["context_window"] = context_window
    if max_output_tokens:
        entry["max_output_tokens"] = max_output_tokens
    if reasoning:
        entry["supports_reasoning"] = True
    return entry


_TV = "Text,Vision"
EXTRA_MODELS: list[dict] = [
    _e("gpt-oss-20b", "OpenAI", "Text", 131072),
    _e("gpt-oss-120b", "OpenAI", "Text", 131072),
    _e("eleven_flash_v2_5", "ElevenLabs", "Text-to-Speech"),
    _e("huggingface/meta-llama/Llama-3.2-3B-Instruct", "Huggingface", "Text"),
    # OpenRouter -- latest-tracking aliases
    _e("~google/gemini-flash-latest", "OpenRouter", _TV, 1048576),
    _e("~google/gemini-pro-latest", "OpenRouter", _TV, 1048576),
    _e("~anthropic/claude-opus-latest", "OpenRouter", _TV, 1000000),
    _e("~anthropic/claude-sonnet-latest", "OpenRouter", _TV, 1000000),
    _e("~anthropic/claude-haiku-latest", "OpenRouter", _TV, 1000000),
    _e("~anthropic/claude-fable-latest", "OpenRouter", _TV, 1000000),
    _e("~openai/gpt-sol-latest", "OpenRouter", _TV, 1050000),
    _e("~openai/gpt-luna-latest", "OpenRouter", _TV, 1050000),
    _e("~openai/gpt-terra-latest", "OpenRouter", _TV, 1050000),
    _e("~openai/gpt-astra-latest", "OpenRouter", _TV, 1050000),
    _e("~openai/gpt-mini-latest", "OpenRouter", _TV, 400000),
    _e("openai/gpt-chat-latest", "OpenRouter", _TV, 400000),
    _e("~x-ai/grok-latest", "OpenRouter", _TV, 500000),
    _e("~moonshotai/kimi-latest", "OpenRouter", _TV, 1048576),
    _e("~z-ai/glm-latest", "OpenRouter", "Text", 1048576),
    _e("~deepseek/deepseek-flash-latest", "OpenRouter", "Text", 1048576),
    _e("~deepseek/deepseek-pro-latest", "OpenRouter", "Text", 1048576),
    _e("openrouter/auto", "OpenRouter", _TV, 2000000),
    _e("openrouter/free", "OpenRouter", _TV, 200000),
    # OpenRouter -- pinned
    _e("anthropic/claude-opus-5.5", "OpenRouter", _TV, 1000000),
    _e("anthropic/claude-sonnet-5.5", "OpenRouter", _TV, 1000000),
    _e("anthropic/claude-haiku-5.5", "OpenRouter", _TV, 1000000),
    _e("anthropic/claude-opus-5", "OpenRouter", _TV, 1000000),
    _e("anthropic/claude-sonnet-5", "OpenRouter", _TV, 1000000),
    _e("anthropic/claude-opus-4.8", "OpenRouter", _TV, 1000000),
    _e("anthropic/claude-sonnet-4.6", "OpenRouter", _TV, 1000000),
    _e("anthropic/claude-haiku-4.5", "OpenRouter", _TV, 200000),
    _e("google/gemini-4-argon", "OpenRouter", _TV, 1048576),
    _e("google/gemini-3.8-flash", "OpenRouter", _TV, 1048576),
    _e("google/gemini-3.6-flash", "OpenRouter", _TV, 1048576),
    _e("google/gemini-3.5-flash-lite", "OpenRouter", _TV, 1048576),
    _e("google/gemini-3.1-pro-preview", "OpenRouter", _TV, 1048576),
    _e("google/gemini-3-flash-preview", "OpenRouter", _TV, 1048576),
    _e("google/gemini-3.1-flash-image", "OpenRouter", "Image"),
    _e("google/gemini-3-pro-image", "OpenRouter", "Image"),
    _e("google/gemma-4-31b-it", "OpenRouter", _TV, 262144),
    _e("google/gemma-4-26b-a4b-it", "OpenRouter", _TV, 262144),
    _e("google/gemma-4-31b-it:free", "OpenRouter", _TV, 262144),
    _e("google/gemma-4-26b-a4b-it:free", "OpenRouter", _TV, 262144),
    _e("google/gemma-3-27b-it", "OpenRouter", _TV, 131072),
    _e("openai/gpt-6.1-sol", "OpenRouter", _TV, 1050000),
    _e("openai/gpt-6-astra", "OpenRouter", _TV, 1050000),
    _e("openai/gpt-6-luna", "OpenRouter", _TV, 1050000),
    _e("openai/gpt-5.6-sol", "OpenRouter", _TV, 1050000),
    _e("openai/gpt-5.6-terra", "OpenRouter", _TV, 1050000),
    _e("openai/gpt-5.6-luna", "OpenRouter", _TV, 1050000),
    _e("openai/gpt-5.5", "OpenRouter", _TV, 1050000),
    _e("openai/gpt-5.5-pro", "OpenRouter", _TV, 1050000),
    _e("openai/gpt-5.4", "OpenRouter", _TV, 1050000),
    _e("openai/gpt-5.4-pro", "OpenRouter", _TV, 1050000),
    _e("openai/gpt-5.4-mini", "OpenRouter", _TV, 400000),
    _e("openai/gpt-5.4-nano", "OpenRouter", _TV, 400000),
    _e("openai/gpt-5.3-codex", "OpenRouter", _TV, 400000),
    _e("openai/gpt-5", "OpenRouter", _TV, 400000),
    _e("openai/gpt-5-mini", "OpenRouter", _TV, 400000),
    _e("openai/gpt-5-nano", "OpenRouter", _TV, 400000),
    _e("openai/gpt-oss-120b", "OpenRouter", "Text", 131072),
    _e("openai/gpt-oss-20b", "OpenRouter", "Text", 131072),
    _e("deepseek/deepseek-v4-pro", "OpenRouter", "Text", 1048576),
    _e("moonshotai/kimi-k3", "OpenRouter", _TV, 1048576),
    _e("moonshotai/kimi-k2.6", "OpenRouter", _TV, 262144),
    _e("minimax/minimax-m3", "OpenRouter", _TV, 1048576),
    _e("minimax/minimax-m2.7", "OpenRouter", "Text", 204800),
    _e("z-ai/glm-5.3", "OpenRouter", "Text", 1048576),
    _e("z-ai/glm-5.2", "OpenRouter", "Text", 1048576),
    _e("x-ai/grok-4.7", "OpenRouter", _TV, 500000),
    _e("qwen/qwen3.7-max", "OpenRouter", "Text", 1000000),
    _e("qwen/qwen3.6-plus", "OpenRouter", _TV, 1000000),
    _e("qwen/qwen3-coder", "OpenRouter", "Text", 262144),
    _e("qwen/qwen3-vl-235b-a22b-instruct", "OpenRouter", _TV, 262144),
    _e("mistralai/mistral-large-2512", "OpenRouter", _TV, 262144),
    _e("xiaomi/mimo-v2.5", "OpenRouter", _TV, 1050000),
    _e("xiaomi/mimo-v2.5-pro", "OpenRouter", "Text", 1050000),
    _e("microsoft/phi-4", "OpenRouter", "Text", 16384),
    _e("nvidia/nemotron-3-super-120b-a12b:free", "OpenRouter", "Text", 262144),
    _e("nvidia/nemotron-3-ultra-550b-a55b:free", "OpenRouter", "Text", 1000000),
    _e("nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", "OpenRouter", _TV, 256000),
    _e("cohere/north-mini-code:free", "OpenRouter", "Text", 256000),
    _e("poolside/laguna-xs-2.1:free", "OpenRouter", "Text", 262144),
    _e("poolside/laguna-s-2.1:free", "OpenRouter", "Text", 262144),
]

# --------------------------------------------------------------------------
# Retired / deprecated / no-longer-usable model_names -> closest current
# replacement (None = no sensible replacement; the row is only deleted when
# nothing references it). Every name here is removed from existing sites by
# huf.patches.v1.refresh_model_catalogue, which first repoints Agents and
# other configuration rows to the replacement. Candidates whose LiteLLM
# deprecation_date has passed are added automatically (replacement None
# unless listed here). Sources: the provider deprecation pages cited per group.
# --------------------------------------------------------------------------
RETIRED: dict[str, str | None] = {
    # OpenAI (developers.openai.com/api/docs/deprecations)
    "gpt-5.2-chat-latest": "chat-latest",
    "gpt-5.3-chat-latest": "chat-latest",
    "gpt-4.1": "gpt-6-luna",
    "gpt-4.1-mini": "gpt-6-luna",
    "gpt-4o": "gpt-6-luna",
    "o3": "gpt-5.6-sol",
    "o4-mini": "gpt-5.6-terra",
    "tts-1": "gpt-4o-mini-tts",
    "tts-1-hd": "gpt-4o-mini-tts",
    "whisper-1": "gpt-transcribe",
    "gpt-4o-transcribe": "gpt-transcribe",
    "gpt-image-1": "gpt-image-2",
    "chatgpt-image-latest": "gpt-image-2",
    "dall-e-2": "gpt-image-2",
    "dall-e-3": "gpt-image-2",
    # Anthropic (platform.claude.com/docs/en/about-claude/model-deprecations)
    "claude-sonnet-4-5": "claude-sonnet-5-5",
    "claude-mythos-preview": "claude-mythos-5-1",
    # Invalid dotted IDs from the old hand list (Anthropic IDs use dashes).
    "claude-opus-4.8": "claude-opus-4-8",
    "claude-haiku-4.5": "claude-haiku-4-5",
    # Google (ai.google.dev/gemini-api/docs/deprecations)
    "gemini-2.5-pro": "gemini-pro-latest",
    "gemini-2.5-flash": "gemini-flash-latest",
    "gemini-2.5-flash-lite": "gemini-flash-lite-latest",
    "gemini-3.7-flash": "gemini-flash-latest",
    "gemini-3.5-flash": "gemini-flash-latest",
    "gemini-3.1-flash-lite": "gemini-flash-lite-latest",
    "gemini-2.5-flash-image": "gemini-3.1-flash-image",
    "gemini-2.5-flash-preview-tts": "gemini-3.8-flash-tts",
    "gemini-3.1-flash-tts-preview": "gemini-3.8-flash-tts",
    "gemini-2.5-flash-tts-preview": "gemini-3.8-flash-tts",
    "gemini-2.5-pro-tts-preview": "gemini-3.8-flash-tts",
    "gemini-3.5-transcribe": "gemini-flash-latest",
    "gemini-embedding-001": "gemini-embedding-2",
    "text-embedding-004": "gemini-embedding-2",
    "computer-use-preview": "gemini-flash-latest",
    "nano-banana-pro": "gemini-3-pro-image",
    "gemma-3-9b-it": "gemma-3-27b-it",
    "gemini-deep-research-preview": "gemini-pro-latest",
    "gemini-deep-research-max-preview": "gemini-pro-latest",
    # Vertex AI (mirrors the Gemini API lifecycle; xAI retirements below)
    "vertex_ai/gemini-3-pro-preview": "vertex_ai/gemini-3.1-pro-preview",
    "vertex_ai/gemini-3.5-flash": "vertex_ai/gemini-3.8-flash",
    "vertex_ai/gemini-3.7-flash": "vertex_ai/gemini-3.8-flash",
    "vertex_ai/xai/grok-4.1-fast-reasoning": "vertex_ai/xai/grok-4.3",
    "vertex_ai/xai/grok-4.1-fast-non-reasoning": "vertex_ai/xai/grok-4.3",
    # Groq (console.groq.com/docs/deprecations)
    "groq/llama-3.3-70b-versatile": "groq/openai/gpt-oss-120b",
    "groq/llama-3.1-8b-instant": "groq/openai/gpt-oss-20b",
    "groq/meta-llama/llama-4-maverick-17b-128e-instruct": "groq/openai/gpt-oss-120b",
    "groq/meta-llama/llama-4-scout-17b-16e-instruct": "groq/openai/gpt-oss-120b",
    "groq/qwen/qwen3-32b": "groq/openai/gpt-oss-120b",
    "groq/qwen/qwen3.6-27b": "groq/qwen/qwen3.8-27b",
    "groq/playai-tts": "groq/canopylabs/orpheus-v1-english",
    # Mistral (docs.mistral.ai models overview, retired table)
    "codestral-mamba-latest": "codestral-latest",
    "pixtral-large-latest": "mistral-medium-latest",
    "magistral-medium-latest": "mistral-medium-latest",
    "magistral-small-latest": "mistral-small-latest",
    "devstral-latest": "mistral-medium-latest",
    "devstral-medium-latest": "mistral-medium-latest",
    "devstral-small-latest": "mistral-small-latest",
    "mistral-medium-3": "mistral-medium-latest",
    "zai-glm-5-2": "zai-glm-5-3",
    # DeepSeek (api-docs.deepseek.com news)
    "deepseek-chat": "deepseek-flash",
    "deepseek-reasoner": "deepseek-flash",
    "deepseek-v4-flash": "deepseek-flash",
    "deepseek-v4-flash-vision-exp": "deepseek-flash",
    "deepseek-r1": "deepseek-v4-pro",
    "deepseek-v3.2": "deepseek-v4-pro",
    "deepseek-chat-v3.1": "deepseek-flash",
    "deepseek-chat-v3-0324": "deepseek-flash",
    # xAI (docs.x.ai/docs/migration/may-15-retirement)
    "grok-4-1-fast": "grok-4.3",
    "grok-3-fast-latest": "grok-4.3",
    "grok-3-mini-latest": "grok-4.3",
    "grok-3-mini-fast-latest": "grok-4.3",
    # Moonshot (platform.kimi.ai; secondary sources, see notes)
    "kimi-latest": "kimi-k3",
    "kimi-latest-128k": "kimi-k3",
    "kimi-k2-thinking": "kimi-k3",
    "kimi-k2-thinking-turbo": "kimi-k3",
    "kimi-k2.5": "kimi-k3",
    "kimi-k2.7": "kimi-k2.7-code",
    "moonshot-v1-8k": "kimi-k3",
    "moonshot-v1-32k": "kimi-k3",
    "moonshot-v1-128k": "kimi-k3",
    "moonshot-v1-auto": "kimi-k3",
    "moonshot-v1-8k-vision-preview": "kimi-k3",
    "moonshot-v1-32k-vision-preview": "kimi-k3",
    "moonshot-v1-128k-vision-preview": "kimi-k3",
    # Perplexity (docs.perplexity.ai models page)
    "sonar-pro": "sonar",
    "sonar-reasoning": "sonar",
    "sonar-reasoning-pro": "sonar",
    "sonar-deep-research": "sonar",
    # ElevenLabs (elevenlabs.io/docs/models)
    "eleven_turbo_v2_5": "eleven_flash_v2_5",
    "scribe_v1": "scribe_v2",
    "scribe_v1_experimental": "scribe_v2",
    # Alibaba (model-studio/model-depreciation)
    "qwen3-max": "qwen3.8-max",
    "qwen-turbo-latest": "qwen3.8-flash",
    # AWS Bedrock
    "bedrock/amazon.titan-image-generator-v2:0": None,
    # OpenRouter -- slugs absent from the live /api/v1/models list
    "google/gemini-2.5-flash-lite-preview-06-17": "~google/gemini-flash-latest",
    "google/gemini-2.5-pro": "~google/gemini-pro-latest",
    "google/gemini-2.5-flash": "~google/gemini-flash-latest",
    "google/gemini-3-pro-preview": "google/gemini-3.1-pro-preview",
    "google/gemini-3.5-flash": "~google/gemini-flash-latest",
    "openai/chat-latest": "openai/gpt-chat-latest",
    "openai/gpt-5.3-chat-latest": "openai/gpt-chat-latest",
    "openai/gpt-5.2-chat-latest": "openai/gpt-chat-latest",
    "openai/gpt-4o-mini": "~openai/gpt-mini-latest",
    "openai/gpt-4o-mini-tts": None,
    "openai/gpt-4o-transcribe": None,
    "openai/gpt-4o-mini-transcribe": None,
    "openai/gpt-transcribe": None,
    "openai/gpt-live-transcribe": None,
    "openai/gpt-realtime-whisper": None,
    "openai/gpt-image-2": None,
    "openai/gpt-image-1": None,
    "openai/gpt-image-1-mini": None,
    "openai/chatgpt-image-latest": None,
    "openai/gpt-5-codex": "openai/gpt-5.3-codex",
    "openai/gpt-oss-20b:free": "openai/gpt-oss-20b",
    "x-ai/grok-4": "~x-ai/grok-latest",
    "moonshotai/kimi-k2.7": "~moonshotai/kimi-latest",
    "qwen/qwen3-coder-plus": "qwen/qwen3-coder",
    "nvidia/nemotron-3-nano-30b-a3b:free": "nvidia/nemotron-3-super-120b-a12b:free",
    "nvidia/nemotron-nano-12b-v2-vl:free": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "nvidia/nemotron-nano-9b-v2:free": "nvidia/nemotron-3-super-120b-a12b:free",
    "poolside/laguna-m.1:free": "poolside/laguna-s-2.1:free",
    "inclusionai/ling-3.0-flash:free": "openrouter/free",
    "tencent/hy3:free": "openrouter/free",
    "deepseek/deepseek-v4-flash": "~deepseek/deepseek-flash-latest",
    "deepseek/deepseek-chat-v3-0324": "~deepseek/deepseek-flash-latest",
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


def build(as_of: datetime.date, model_cost: dict) -> tuple[list[dict], dict[str, str | None], dict]:
    """Returns (models, retired, stats).

    retired maps model_name -> replacement model_name (or None). It is the
    union of the hand-verified RETIRED table and any candidate whose LiteLLM
    deprecation_date is before ``as_of``.

    stats: {"per_provider": {provider: count}, "excluded_deprecated": int,
            "missing_keys": {provider: [keys not found in model_cost]}}
    """
    models: dict[str, dict] = {}  # model_name -> entry (dedupe)
    retired: dict[str, str | None] = dict(RETIRED)
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
                retired.setdefault(model_name, None)
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

            if model_name in models:
                # Two candidate keys collapsed to the same stored model_name.
                # Keep the first, deterministic by candidate list order.
                continue

            models[model_name] = record
            per_provider_count[provider] += 1

    for extra in EXTRA_MODELS:
        if extra["model_name"] in models:
            raise SystemExit(f"EXTRA_MODELS entry duplicates a LiteLLM candidate: {extra['model_name']}")
        models[extra["model_name"]] = dict(extra)
        per_provider_count[extra["provider"]] = per_provider_count.get(extra["provider"], 0) + 1

    for name, mods in MODALITY_OVERRIDES.items():
        if name in models:
            models[name]["modalities"] = mods

    for name in ALIASES:
        if name not in models:
            raise SystemExit(f"ALIASES names a model that is not seeded: {name}")
        models[name]["is_latest_alias"] = True

    clash = set(models) & set(retired)
    if clash:
        raise SystemExit(f"model_name(s) both seeded and retired: {sorted(clash)}")
    for name, replacement in retired.items():
        if replacement is not None and replacement not in models:
            raise SystemExit(f"RETIRED[{name!r}] -> {replacement!r} is not a seeded model")

    sorted_models = sorted(models.values(), key=lambda m: (m["provider"], m["model_name"]))

    stats = {
        "per_provider": per_provider_count,
        "excluded_deprecated": excluded_deprecated,
        "missing_keys": missing_keys,
    }
    return sorted_models, dict(sorted(retired.items())), stats


_FIELD_ORDER = ("modalities", "context_window", "max_output_tokens", "supports_reasoning", "is_latest_alias")


def render(models: list[dict], retired: dict[str, str | None], as_of: datetime.date, litellm_version: str) -> str:
    lines = []
    lines.append('"""Auto-generated AI Model catalogue. DO NOT EDIT BY HAND.')
    lines.append("")
    lines.append("Single source of truth for the seeded AI Model catalogue: consumed by")
    lines.append("huf/install.py::create_demo_ai_models and the")
    lines.append("huf.patches.v1.refresh_model_catalogue patch.")
    lines.append("")
    lines.append("Generated by: scripts/gen_model_catalogue.py")
    lines.append(f"litellm model table: {litellm_version}")
    lines.append(f"--as-of date: {as_of.isoformat()}")
    lines.append(f"Entry count: {len(models)} models, {len(retired)} retired")
    lines.append("")
    lines.append("Regenerate with:")
    lines.append("    python scripts/gen_model_catalogue.py --as-of " + as_of.isoformat()
                 + " [--model-cost-json model_prices_and_context_window.json]")
    lines.append('"""')
    lines.append("")
    lines.append("MODELS = [")
    for m in models:
        parts = [f'"model_name": {m["model_name"]!r}', f'"provider": {m["provider"]!r}']
        for field in _FIELD_ORDER:
            if field in m:
                parts.append(f'"{field}": {m[field]!r}')
        lines.append("    {" + ", ".join(parts) + "},")
    lines.append("]")
    lines.append("")
    lines.append("# Retired / deprecated model_name -> closest current replacement (None = none).")
    lines.append("RETIRED = {")
    for name, replacement in retired.items():
        lines.append(f"    {name!r}: {replacement!r},")
    lines.append("}")
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
    parser.add_argument(
        "--model-cost-json",
        default=None,
        help="Path to LiteLLM's model_prices_and_context_window.json to use instead of "
             "the installed litellm package's bundled table (lets the catalogue track "
             "upstream without upgrading litellm).",
    )
    args = parser.parse_args()

    as_of = datetime.date.fromisoformat(args.as_of)

    litellm_version = "unknown"
    try:
        from importlib.metadata import version as _pkg_version
        litellm_version = _pkg_version("litellm")
    except Exception:
        pass

    if args.model_cost_json:
        import json

        model_cost = json.loads(Path(args.model_cost_json).read_text())
        model_cost.pop("sample_spec", None)
        litellm_version = f"{Path(args.model_cost_json).name} (BerriAI/litellm main)"
    else:
        model_cost = litellm.model_cost

    models, retired, stats = build(as_of, model_cost)

    out_path = Path(args.out) if args.out else (
        Path(__file__).resolve().parent.parent / "huf" / "ai" / "model_catalogue.py"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(models, retired, as_of, litellm_version))

    print(f"Wrote {out_path} ({len(models)} models, {len(retired)} retired)")
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
