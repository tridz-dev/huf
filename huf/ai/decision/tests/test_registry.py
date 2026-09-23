"""Focused tests for installed decision backend discovery and resolution."""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from huf.ai.decision.errors import DecisionError, DecisionErrorCode
from huf.ai.decision.registry import discover_backends, resolve_backend
from huf.ai.decision.types import DeploymentSpec, DecisionIdentity, DecisionCapabilities, QuestionKind


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

	def test_resolve_backend_keeps_zero_arg_path_for_existing_callers(self):
		"""Verify backward compatibility: zero-arg constructor is still the default."""
		from huf.ai.decision.backends.fake import FakeDecisionBackend

		# Call without deployment/transport; should use zero-arg constructor
		backend = resolve_backend("fake", registry={"fake": "huf.ai.decision.backends.fake.FakeDecisionBackend"})

		self.assertIsInstance(backend, FakeDecisionBackend)
		self.assertEqual(backend.adapter_id(), "fake")

	def test_resolve_backend_calls_from_deployment_when_deployment_provided(self):
		"""Verify from_deployment is called when deployment is provided and class defines it."""
		module = types.ModuleType("test_registry_deployment_backend")

		# Create a mock backend class with from_deployment
		class MockDeploymentBackend:
			@classmethod
			def adapter_id(cls):
				return "mock_deployment"

			def capabilities(self):
				return MagicMock()

			def evaluate(self, request):
				return MagicMock()

			def healthcheck(self):
				return True

			@classmethod
			def from_deployment(cls, spec, transport):
				instance = cls()
				instance.spec = spec
				instance.transport = transport
				return instance

		module.MockDeploymentBackend = MockDeploymentBackend

		# Create a test deployment spec
		spec = DeploymentSpec(
			identity=DecisionIdentity(
				model_class="Test",
				model_family="TestFamily",
				canonical_model="TestModel",
				provider="TestProvider",
			),
			effective_capabilities=DecisionCapabilities(primitives=frozenset(QuestionKind)),
			wire_protocol="json",
		)
		mock_transport = MagicMock()

		with patch.dict(sys.modules, {module.__name__: module}):
			backend = resolve_backend(
				"mock_deployment",
				registry={"mock_deployment": f"{module.__name__}.MockDeploymentBackend"},
				deployment=spec,
				transport=mock_transport,
			)

		self.assertIsInstance(backend, MockDeploymentBackend)
		self.assertIs(backend.spec, spec)
		self.assertIs(backend.transport, mock_transport)

	def test_resolve_backend_falls_back_to_zero_arg_when_class_lacks_from_deployment(self):
		"""Verify fallback: if class doesn't define from_deployment, use zero-arg constructor."""
		from huf.ai.decision.backends.fake import FakeDecisionBackend

		# Call with deployment but backend doesn't have from_deployment
		spec = DeploymentSpec(
			identity=DecisionIdentity(model_class="Test"),
			effective_capabilities=DecisionCapabilities(primitives=frozenset(QuestionKind)),
			wire_protocol="json",
		)

		backend = resolve_backend(
			"fake",
			registry={"fake": "huf.ai.decision.backends.fake.FakeDecisionBackend"},
			deployment=spec,
			transport=MagicMock(),
		)

		self.assertIsInstance(backend, FakeDecisionBackend)
		self.assertEqual(backend.adapter_id(), "fake")

	def test_resolve_backend_ignores_transport_without_deployment(self):
		"""Verify transport is ignored if deployment is None."""
		from huf.ai.decision.backends.fake import FakeDecisionBackend

		# Call with transport but no deployment; should ignore transport
		backend = resolve_backend(
			"fake",
			registry={"fake": "huf.ai.decision.backends.fake.FakeDecisionBackend"},
			transport=MagicMock(),
		)

		self.assertIsInstance(backend, FakeDecisionBackend)
		self.assertEqual(backend.adapter_id(), "fake")


if __name__ == "__main__":
	unittest.main()
