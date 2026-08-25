"""Tests for huf.ai.knowledge.embedding.resolve_embedding_config.

These are isolated unit tests: the Knowledge Source and AI Provider
documents are faked with SimpleNamespace/MagicMock stand-ins so no live
Frappe site or database is required, following the mock-based convention
used in huf/ai/tests/test_conversation_title_autonaming.py.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from huf.ai.knowledge.embedding import resolve_embedding_config


def _make_provider(**overrides):
	defaults = {
		"api_key": None,
		"api_base_url": None,
		"is_local_llm": False,
		"url": None,
		"port": None,
		"provider_brand": None,
	}
	defaults.update(overrides)
	provider = SimpleNamespace(**defaults)
	provider.get_password = MagicMock(return_value=defaults.get("_password"))
	return provider


class TestResolveEmbeddingConfig(unittest.TestCase):
	def _run(self, source_overrides, provider=None, provider_brand=None):
		source_defaults = {
			"embedding_model": "text-embedding-3-small",
			"vector_dimension": 1536,
			"embedding_provider": "OpenAI Provider" if provider else None,
		}
		source_defaults.update(source_overrides)
		source = SimpleNamespace(**source_defaults)

		with patch("huf.ai.knowledge.embedding.frappe") as mock_frappe:
			mock_frappe.conf.get.return_value = None

			def get_doc(doctype, name=None):
				if doctype == "Knowledge Source":
					return source
				if doctype == "AI Provider":
					return provider
				raise AssertionError(f"unexpected get_doc({doctype!r})")

			mock_frappe.get_doc.side_effect = get_doc
			mock_frappe.db.get_value.return_value = provider_brand
			return resolve_embedding_config("Some Knowledge Source")

	def test_reads_api_base_url_from_provider(self):
		provider = _make_provider(api_key="secret", api_base_url="https://my-proxy.example.com/v1", _password="secret")
		config = self._run(
			{"embedding_provider": "Custom Provider"},
			provider=provider,
		)

		self.assertEqual(config["api_base"], "https://my-proxy.example.com/v1")
		self.assertEqual(config["api_key"], "secret")

	def test_prefixes_model_with_provider_brand_for_litellm(self):
		provider = _make_provider(api_key=None)
		config = self._run(
			{"embedding_model": "nomic-embed-text", "embedding_provider": "Ollama Provider"},
			provider=provider,
			provider_brand="ollama",
		)

		self.assertEqual(config["model"], "ollama/nomic-embed-text")

	def test_does_not_re_prefix_an_already_prefixed_model(self):
		provider = _make_provider(api_key=None)
		config = self._run(
			{"embedding_model": "openai/text-embedding-3-small", "embedding_provider": "OpenAI Provider"},
			provider=provider,
			provider_brand="openai",
		)

		self.assertEqual(config["model"], "openai/text-embedding-3-small")

	def test_local_llm_falls_back_to_url_and_port_when_no_api_base_url(self):
		provider = _make_provider(
			api_key=None,
			api_base_url="",
			is_local_llm=True,
			url="http://localhost",
			port=11434,
		)
		config = self._run(
			{"embedding_provider": "Local Ollama"},
			provider=provider,
		)

		self.assertEqual(config["api_base"], "http://localhost:11434")

	def test_local_llm_does_not_duplicate_port_already_in_url(self):
		provider = _make_provider(
			api_key=None,
			api_base_url="",
			is_local_llm=True,
			url="http://localhost:11434",
			port=11434,
		)
		config = self._run(
			{"embedding_provider": "Local Ollama"},
			provider=provider,
		)

		self.assertEqual(config["api_base"], "http://localhost:11434")

	def test_no_provider_returns_none_api_key_and_base(self):
		config = self._run({"embedding_provider": None}, provider=None)

		self.assertIsNone(config["api_key"])
		self.assertIsNone(config["api_base"])
		self.assertEqual(config["model"], "text-embedding-3-small")

	def test_falls_back_to_configured_dimension_default(self):
		config = self._run({"vector_dimension": None, "embedding_provider": None}, provider=None)

		self.assertEqual(config["dimension"], 1536)


if __name__ == "__main__":
	unittest.main()
