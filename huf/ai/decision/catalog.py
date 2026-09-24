"""Decision model catalog: provider-hosted canonical models and their deployment metadata.

Entries are immutable and keyed by (provider_brand, model_name).
Metadata includes canonical model/family, default wire_protocol, endpoint_path, and base URL defaults.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class CatalogEntry:
	"""Immutable decision model catalog entry."""

	provider_brand: str
	model_name: str
	canonical_model: str
	model_family: str
	model_class: str
	wire_protocol: str
	endpoint_path: str
	base_url: str | None = None


# Catalog keyed by (provider_brand, model_name).
# Entries are immutable.
_CATALOG = {
	# OpenCode Zen — Jev System One
	("opencode-zen", "jev-1.13-free"): CatalogEntry(
		provider_brand="opencode-zen",
		model_name="jev-1.13-free",
		canonical_model="Jev 1.13",
		model_family="Jev",
		model_class="System One",
		wire_protocol="systemone",
		endpoint_path="/v1/systemone",
		base_url="https://opencode.ai/zen",
	),
	("opencode-zen", "jev-1.13"): CatalogEntry(
		provider_brand="opencode-zen",
		model_name="jev-1.13",
		canonical_model="Jev 1.13",
		model_family="Jev",
		model_class="System One",
		wire_protocol="systemone",
		endpoint_path="/v1/systemone",
		base_url="https://opencode.ai/zen",
	),
	# OpenRouter — Jev System One
	("openrouter", "typesafe/jev-1.13"): CatalogEntry(
		provider_brand="openrouter",
		model_name="typesafe/jev-1.13",
		canonical_model="Jev 1.13",
		model_family="Jev",
		model_class="System One",
		wire_protocol="systemone",
		endpoint_path="/api/v1/systemone",
		base_url="https://openrouter.ai",
	),
}


def get_entries(brand: str) -> tuple[CatalogEntry, ...]:
	"""Return all catalog entries for a provider brand.

	Args:
		brand: provider_brand (e.g. "opencode-zen", "openrouter")

	Returns:
		Tuple of immutable CatalogEntry objects, empty if brand not found.
	"""
	return tuple(entry for entry in _CATALOG.values() if entry.provider_brand == brand)


def brand_default_base_url(brand: str) -> str | None:
	"""Return the canonical base URL default for a provider brand, if any.

	Args:
		brand: provider_brand

	Returns:
		Base URL string, or None if the brand uses its provider's standard base.
	"""
	entries = get_entries(brand)
	if not entries:
		return None
	# All entries for a brand share the same base_url (by design).
	return entries[0].base_url


def get_entry(provider_brand: str, model_name: str) -> CatalogEntry | None:
	"""Look up a catalog entry by provider brand and model name.

	Args:
		provider_brand: The provider's brand (e.g. "opencode-zen")
		model_name: The model identifier (e.g. "jev-1.13-free")

	Returns:
		CatalogEntry if found, None otherwise.
	"""
	return _CATALOG.get((provider_brand, model_name))
