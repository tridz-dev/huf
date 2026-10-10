"""Focused tests for installed decision backend discovery and resolution."""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

from huf.ai.decision.errors import DecisionError, DecisionErrorCode
from huf.ai.decision.registry import discover_backends, resolve_backend


class DecisionBackendRegistryTests(unittest.TestCase):
	def test_resolves_builtin_fake_backend(self):
		from huf.ai.decision.backends.fake import FakeDecisionBackend

		backend = resolve_backend("fake")

		self.assertIsInstance(backend, FakeDecisionBackend)
		self.assertEqual(backend.adapter_id(), "fake")

	def test_denies_unregistered_adapter(self):
		with self.assertRaises(DecisionError) as raised:
			resolve_backend("caller.supplied.module.Backend", registry={})

		self.assertEqual(raised.exception.code, DecisionErrorCode.BACKEND_NOT_REGISTERED)

	def test_normalizes_dict_and_list_hook_registrations(self):
		frappe = types.ModuleType("frappe")
		frappe.get_installed_apps = lambda: ["dict_app", "list_app", "bad_app"]
		hook_entries = {
			"dict_app": {"dict-adapter": "example.backends.DictBackend"},
			"list_app": [{"list-adapter": ["example.backends.ListBackend"]}],
			"bad_app": ["not-a-dict", {"empty-adapter": []}, {"invalid-adapter": [None]}],
		}
		frappe.get_hooks = lambda name, app_name: hook_entries[app_name]

		with patch.dict(sys.modules, {"frappe": frappe}):
			registry = discover_backends()

		self.assertEqual(registry["dict-adapter"], "example.backends.DictBackend")
		self.assertEqual(registry["list-adapter"], "example.backends.ListBackend")
		self.assertNotIn("empty-adapter", registry)
		self.assertNotIn("invalid-adapter", registry)
		self.assertEqual(registry["fake"], "huf.ai.decision.backends.fake.FakeDecisionBackend")

	def test_builtin_registration_cannot_be_overridden_by_hook(self):
		frappe = types.ModuleType("frappe")
		frappe.get_installed_apps = lambda: ["override_app"]
		frappe.get_hooks = lambda name, app_name: {"fake": "evil.module.Backend"}

		with patch.dict(sys.modules, {"frappe": frappe}):
			registry = discover_backends()

		self.assertEqual(registry["fake"], "huf.ai.decision.backends.fake.FakeDecisionBackend")

	def test_rejects_registered_class_without_backend_contract(self):
		module = types.ModuleType("test_registry_malformed_backend")
		module.MalformedBackend = type("MalformedBackend", (), {"evaluate": lambda self: None})

		with patch.dict(sys.modules, {module.__name__: module}):
			with self.assertRaises(DecisionError) as raised:
				resolve_backend(
					"malformed",
					registry={"malformed": f"{module.__name__}.MalformedBackend"},
				)

		self.assertEqual(raised.exception.code, DecisionErrorCode.BACKEND_NOT_REGISTERED)


if __name__ == "__main__":
	unittest.main()
