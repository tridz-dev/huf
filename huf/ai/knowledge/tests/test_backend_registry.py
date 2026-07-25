# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

"""Tests for the hook-based knowledge backend registry."""

import unittest
from unittest.mock import patch

import frappe

from huf.ai.knowledge.backends import (
	_BUILTIN_BACKENDS,
	KnowledgeBackend,
	_discover_backends,
	get_backend,
)


class _FakeBackend(KnowledgeBackend):
	"""A valid KnowledgeBackend subclass used for hook-validation tests."""

	def initialize(self, knowledge_source, config):
		pass

	def add_chunks(self, chunks):
		return len(chunks)

	def delete_chunks(self, input_id):
		return 0

	def search(self, query, top_k=5, filters=None):
		return []

	def clear(self):
		pass

	def get_stats(self):
		return {}


class _NotABackend:
	"""A class that does not subclass KnowledgeBackend."""

	def initialize(self, knowledge_source, config):
		pass


class TestBackendRegistry(unittest.TestCase):
	"""Unit tests for _discover_backends and get_backend hook handling."""

	def _clear_registry_cache(self):
		"""Remove per-request registry cache so tests see fresh discoveries."""
		if hasattr(frappe.local, "huf_backend_registry"):
			del frappe.local.huf_backend_registry

	def setUp(self):
		self._clear_registry_cache()

	def tearDown(self):
		self._clear_registry_cache()

	@patch("huf.ai.knowledge.backends.frappe.get_installed_apps")
	@patch("huf.ai.knowledge.backends.frappe.get_hooks")
	def test_discover_backends_includes_built_ins_when_no_hooks(
		self, mock_get_hooks, mock_get_installed_apps
	):
		mock_get_installed_apps.return_value = ["huf"]
		mock_get_hooks.return_value = []

		registry = _discover_backends()

		self.assertEqual(set(registry.keys()), set(_BUILTIN_BACKENDS.keys()))
		for key in _BUILTIN_BACKENDS:
			self.assertIn(key, registry)

	@patch("huf.ai.knowledge.backends.frappe.get_installed_apps")
	@patch("huf.ai.knowledge.backends.frappe.get_hooks")
	def test_discover_backends_merges_hooked_backends(self, mock_get_hooks, mock_get_installed_apps):
		mock_get_installed_apps.return_value = ["huf", "my_app"]

		def fake_hooks(hook_name, app_name=None):
			if hook_name == "huf_knowledge_backends" and app_name == "my_app":
				# Real Frappe shape: merged dict of lists, first declaration wins.
				return {"qdrant": ["my_app.knowledge.qdrant.QdrantBackend"]}
			return []

		mock_get_hooks.side_effect = fake_hooks

		registry = _discover_backends()

		self.assertIn("qdrant", registry)
		self.assertEqual(registry["qdrant"], "my_app.knowledge.qdrant.QdrantBackend")
		for key in _BUILTIN_BACKENDS:
			self.assertIn(key, registry)

	@patch("huf.ai.knowledge.backends.frappe.get_installed_apps")
	@patch("huf.ai.knowledge.backends.frappe.get_hooks")
	def test_discover_backends_skips_built_in_collisions(self, mock_get_hooks, mock_get_installed_apps):
		mock_get_installed_apps.return_value = ["huf", "evil_app"]

		def fake_hooks(hook_name, app_name=None):
			if hook_name == "huf_knowledge_backends" and app_name == "evil_app":
				return {"pgvector": ["evil_app.pgvector.OverrideBackend"]}
			return []

		mock_get_hooks.side_effect = fake_hooks

		with patch("huf.ai.knowledge.backends.frappe.logger") as mock_logger:
			registry = _discover_backends()

		self.assertEqual(registry["pgvector"], _BUILTIN_BACKENDS["pgvector"])
		mock_logger.return_value.warning.assert_called_once()
		warning_message = mock_logger.return_value.warning.call_args[0][0]
		self.assertIn("pgvector", warning_message)
		self.assertIn("built-in", warning_message)

	@patch("huf.ai.knowledge.backends.frappe.get_installed_apps")
	@patch("huf.ai.knowledge.backends.frappe.get_hooks")
	def test_discover_backends_skips_duplicate_hook_keys(self, mock_get_hooks, mock_get_installed_apps):
		mock_get_installed_apps.return_value = ["huf", "app_a", "app_b"]

		def fake_hooks(hook_name, app_name=None):
			if hook_name != "huf_knowledge_backends":
				return []
			if app_name == "app_a":
				return {"weaviate": ["app_a.weaviate.WeaviateBackend"]}
			if app_name == "app_b":
				return {"weaviate": ["app_b.weaviate.OtherBackend"]}
			return []

		mock_get_hooks.side_effect = fake_hooks

		with patch("huf.ai.knowledge.backends.frappe.logger") as mock_logger:
			registry = _discover_backends()

		self.assertEqual(registry["weaviate"], "app_a.weaviate.WeaviateBackend")
		mock_logger.return_value.warning.assert_called_once()
		warning_message = mock_logger.return_value.warning.call_args[0][0]
		self.assertIn("weaviate", warning_message)
		self.assertIn("duplicate", warning_message)

	@patch("huf.ai.knowledge.backends.frappe.get_installed_apps")
	@patch("huf.ai.knowledge.backends.frappe.get_hooks")
	def test_discover_backends_first_declaration_wins_within_app(
		self, mock_get_hooks, mock_get_installed_apps
	):
		"""Frappe merges repeated dict declarations into a list; the first wins."""
		mock_get_installed_apps.return_value = ["huf", "my_app"]

		def fake_hooks(hook_name, app_name=None):
			if hook_name == "huf_knowledge_backends" and app_name == "my_app":
				return {"weaviate": ["my_app.weaviate.FirstBackend", "my_app.weaviate.SecondBackend"]}
			return []

		mock_get_hooks.side_effect = fake_hooks

		registry = _discover_backends()

		self.assertEqual(registry["weaviate"], "my_app.weaviate.FirstBackend")

	@patch("huf.ai.knowledge.backends.frappe.get_installed_apps")
	@patch("huf.ai.knowledge.backends.frappe.get_hooks")
	def test_discover_backends_skips_malformed_entries(self, mock_get_hooks, mock_get_installed_apps):
		mock_get_installed_apps.return_value = ["huf", "bad_app"]

		def fake_hooks(hook_name, app_name=None):
			if hook_name == "huf_knowledge_backends" and app_name == "bad_app":
				return ["not_a_dict"]
			return []

		mock_get_hooks.side_effect = fake_hooks

		with patch("huf.ai.knowledge.backends.frappe.logger") as mock_logger:
			registry = _discover_backends()

		mock_logger.return_value.warning.assert_called_once()
		for key in _BUILTIN_BACKENDS:
			self.assertIn(key, registry)

	@patch("huf.ai.knowledge.backends._get_backend_registry")
	@patch("huf.ai.knowledge.backends.frappe.get_attr")
	def test_get_backend_validates_subclass(self, mock_get_attr, mock_get_registry):
		mock_get_registry.return_value = {"fake": "huf.ai.knowledge.tests.test_backend_registry._FakeBackend"}
		mock_get_attr.return_value = _FakeBackend

		backend_class = get_backend("fake")
		self.assertIs(backend_class, _FakeBackend)

	@patch("huf.ai.knowledge.backends._get_backend_registry")
	@patch("huf.ai.knowledge.backends.frappe.get_attr")
	def test_get_backend_rejects_non_subclass(self, mock_get_attr, mock_get_registry):
		mock_get_registry.return_value = {
			"not_a_backend": "huf.ai.knowledge.tests.test_backend_registry._NotABackend"
		}
		mock_get_attr.return_value = _NotABackend

		with self.assertRaises(frappe.ValidationError):
			get_backend("not_a_backend")

	@patch("huf.ai.knowledge.backends._get_backend_registry")
	def test_get_backend_unknown_type_throws(self, mock_get_registry):
		mock_get_registry.return_value = dict(_BUILTIN_BACKENDS)

		with self.assertRaises(frappe.ValidationError):
			get_backend("does_not_exist")


if __name__ == "__main__":
	unittest.main()
