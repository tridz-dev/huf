"""Unit tests for the decision model catalog."""

from __future__ import annotations

import unittest

from huf.ai.decision.catalog import CatalogEntry, brand_default_base_url, get_entries, get_entry


class TestCatalogEntry(unittest.TestCase):
	"""CatalogEntry immutability and field structure."""

	def test_catalog_entry_is_frozen(self):
		"""CatalogEntry instances are immutable."""
		entry = CatalogEntry(
			provider_brand="test-brand",
			model_name="test-model",
			canonical_model="Test 1.0",
			model_family="Test",
			model_class="TestClass",
			wire_protocol="test_wire",
			endpoint_path="/test/endpoint",
			base_url="https://test.example.com",
		)
		with self.assertRaises(AttributeError):
			entry.canonical_model = "Modified"

	def test_catalog_entry_fields(self):
		"""CatalogEntry has all required fields."""
		entry = CatalogEntry(
			provider_brand="opencode-zen",
			model_name="jev-1.13-free",
			canonical_model="Jev 1.13",
			model_family="Jev",
			model_class="System One",
			wire_protocol="systemone",
			endpoint_path="/v1/systemone",
			base_url="https://opencode.ai/zen",
		)
		self.assertEqual(entry.provider_brand, "opencode-zen")
		self.assertEqual(entry.model_name, "jev-1.13-free")
		self.assertEqual(entry.canonical_model, "Jev 1.13")
		self.assertEqual(entry.model_family, "Jev")
		self.assertEqual(entry.model_class, "System One")
		self.assertEqual(entry.wire_protocol, "systemone")
		self.assertEqual(entry.endpoint_path, "/v1/systemone")
		self.assertEqual(entry.base_url, "https://opencode.ai/zen")


class TestCatalogLookups(unittest.TestCase):
	"""Catalog query functions."""

	def test_get_entry_opencode_zen_free(self):
		"""Look up OpenCode Zen free tier model."""
		entry = get_entry("opencode-zen", "jev-1.13-free")
		self.assertIsNotNone(entry)
		self.assertEqual(entry.canonical_model, "Jev 1.13")
		self.assertEqual(entry.model_family, "Jev")
		self.assertEqual(entry.wire_protocol, "systemone")
		self.assertEqual(entry.endpoint_path, "/v1/systemone")
		self.assertEqual(entry.base_url, "https://opencode.ai/zen")

	def test_get_entry_opencode_zen_paid(self):
		"""Look up OpenCode Zen paid tier model."""
		entry = get_entry("opencode-zen", "jev-1.13")
		self.assertIsNotNone(entry)
		self.assertEqual(entry.canonical_model, "Jev 1.13")
		self.assertEqual(entry.model_family, "Jev")
		self.assertEqual(entry.wire_protocol, "systemone")
		self.assertEqual(entry.endpoint_path, "/v1/systemone")
		self.assertEqual(entry.base_url, "https://opencode.ai/zen")

	def test_get_entry_openrouter(self):
		"""Look up OpenRouter Jev model."""
		entry = get_entry("openrouter", "typesafe/jev-1.13")
		self.assertIsNotNone(entry)
		self.assertEqual(entry.canonical_model, "Jev 1.13")
		self.assertEqual(entry.model_family, "Jev")
		self.assertEqual(entry.wire_protocol, "systemone")
		self.assertEqual(entry.endpoint_path, "/api/v1/systemone")
		self.assertEqual(entry.base_url, "https://openrouter.ai")

	def test_get_entry_not_found(self):
		"""Look up non-existent model."""
		entry = get_entry("unknown-brand", "unknown-model")
		self.assertIsNone(entry)

	def test_get_entries_opencode_zen(self):
		"""Get all OpenCode Zen entries."""
		entries = get_entries("opencode-zen")
		self.assertEqual(len(entries), 2)
		model_names = {e.model_name for e in entries}
		self.assertEqual(model_names, {"jev-1.13-free", "jev-1.13"})
		# All share the same base URL
		for entry in entries:
			self.assertEqual(entry.base_url, "https://opencode.ai/zen")

	def test_get_entries_openrouter(self):
		"""Get all OpenRouter entries."""
		entries = get_entries("openrouter")
		self.assertEqual(len(entries), 1)
		self.assertEqual(entries[0].model_name, "typesafe/jev-1.13")

	def test_get_entries_unknown_brand(self):
		"""Get entries for unknown brand returns empty tuple."""
		entries = get_entries("unknown-brand")
		self.assertEqual(entries, ())

	def test_brand_default_base_url_opencode_zen(self):
		"""Get OpenCode Zen default base URL."""
		url = brand_default_base_url("opencode-zen")
		self.assertEqual(url, "https://opencode.ai/zen")

	def test_brand_default_base_url_openrouter(self):
		"""OpenRouter's catalog default base URL."""
		url = brand_default_base_url("openrouter")
		self.assertEqual(url, "https://openrouter.ai")

	def test_brand_default_base_url_unknown(self):
		"""Unknown brand returns None."""
		url = brand_default_base_url("unknown-brand")
		self.assertIsNone(url)


class TestCatalogConsistency(unittest.TestCase):
	"""Cross-entry invariants."""

	def test_all_jev_entries_share_canonical_model(self):
		"""All Jev entries across all brands map to the same canonical model."""
		opencode_free = get_entry("opencode-zen", "jev-1.13-free")
		opencode_paid = get_entry("opencode-zen", "jev-1.13")
		openrouter = get_entry("openrouter", "typesafe/jev-1.13")

		self.assertEqual(opencode_free.canonical_model, "Jev 1.13")
		self.assertEqual(opencode_paid.canonical_model, "Jev 1.13")
		self.assertEqual(openrouter.canonical_model, "Jev 1.13")

	def test_all_jev_entries_use_systemone_wire(self):
		"""All Jev entries use System One wire protocol."""
		for entry in [
			get_entry("opencode-zen", "jev-1.13-free"),
			get_entry("opencode-zen", "jev-1.13"),
			get_entry("openrouter", "typesafe/jev-1.13"),
		]:
			self.assertEqual(entry.wire_protocol, "systemone")

	def test_endpoint_paths_vary_by_provider(self):
		"""Endpoint paths differ between OpenCode Zen and OpenRouter."""
		opencode = get_entry("opencode-zen", "jev-1.13-free")
		openrouter = get_entry("openrouter", "typesafe/jev-1.13")

		self.assertEqual(opencode.endpoint_path, "/v1/systemone")
		self.assertEqual(openrouter.endpoint_path, "/api/v1/systemone")
		self.assertNotEqual(opencode.endpoint_path, openrouter.endpoint_path)


class TestCatalogDataStructure(unittest.TestCase):
	"""Catalog structure and immutability."""

	def test_all_entries_are_immutable(self):
		"""Every entry in the catalog is immutable."""
		for (brand, model_name), entry in [(k, v) for k, v in locals().items() if isinstance(v, CatalogEntry)]:
			with self.subTest(entry=f"{brand}/{model_name}"):
				with self.assertRaises(AttributeError):
					entry.canonical_model = "Modified"

	def test_catalog_query_returns_tuples(self):
		"""get_entries returns a tuple, not a list."""
		result = get_entries("opencode-zen")
		self.assertIsInstance(result, tuple)
		self.assertEqual(len(result), 2)


if __name__ == "__main__":
	unittest.main()
