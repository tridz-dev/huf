# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""Curated provider brand catalog for AI Provider logos and UI grouping."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

SLUG_ALIASES = {
	"bedrock": "amazon-bedrock",
	"gemini": "google",
	"grok": "xai",
	"dashscope": "alibaba",
	"hugging_face": "huggingface",
}

CHEF_TO_BRAND = {
	"OpenAI": "openai",
	"Anthropic": "anthropic",
	"Google": "google",
	"OpenRouter": "openrouter",
	"xAI": "xai",
	"Groq": "groq",
	"Mistral": "mistral",
	"DeepSeek": "deepseek",
	"Perplexity": "perplexity",
	"Cohere": "cohere",
	"HuggingFace": "huggingface",
	"Hugging Face": "huggingface",
	"ElevenLabs": "elevenlabs",
	"Amazon": "amazon-bedrock",
	"Microsoft": "azure",
	"Alibaba": "alibaba",
	"TogetherAI": "togetherai",
	"Together AI": "togetherai",
	"Meta": "meta",
	"Ollama": "ollama",
}


@lru_cache(maxsize=1)
def _load_brands() -> list[dict]:
	path = Path(__file__).with_name("provider_brands.json")
	with path.open(encoding="utf-8") as handle:
		return json.load(handle)


@lru_cache(maxsize=1)
def _brand_ids() -> frozenset[str]:
	return frozenset(brand["id"] for brand in _load_brands())


def get_brand_options() -> list[dict]:
	return _load_brands()


def get_brand_label(brand_id: str | None) -> str:
	if not brand_id:
		return "Other"
	for brand in _load_brands():
		if brand["id"] == brand_id:
			return brand["label"]
	return brand_id.replace("-", " ").title()


def is_known_brand(brand_id: str | None) -> bool:
	return bool(brand_id and brand_id in _brand_ids() and brand_id != "other")


def normalize_slug_to_brand(slug: str | None) -> str | None:
	if not slug:
		return None
	normalized = slug.strip().lower().replace("_", "-")
	return SLUG_ALIASES.get(normalized, normalized)


def resolve_brand_from_chef(chef: str | None) -> str | None:
	if not chef:
		return None
	return CHEF_TO_BRAND.get(chef.strip())


def resolve_brand_from_provider_name(provider_name: str | None) -> str | None:
	if not provider_name:
		return None
	import frappe

	scrubbed = frappe.scrub(provider_name).replace("_", "-")
	return normalize_slug_to_brand(scrubbed)


def resolve_brand_from_litellm_prefix(prefix: str | None) -> str | None:
	return normalize_slug_to_brand(prefix)


def migrate_legacy_provider_brand(
	slug: str | None,
	chef: str | None,
	provider_name: str | None,
) -> str:
	brand = None
	if slug:
		brand = normalize_slug_to_brand(slug)
	elif chef:
		brand = resolve_brand_from_chef(chef)
	else:
		brand = resolve_brand_from_provider_name(provider_name)

	if brand and brand in _brand_ids():
		return brand
	return "other"


def get_select_field_options() -> str:
	"""Newline-separated options for Frappe Select field."""
	return "\n".join(brand["id"] for brand in _load_brands())
