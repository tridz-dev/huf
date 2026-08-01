"""Tests for Hub's short-lived secret request boundary."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase


class _LazyModule:
	def __init__(self, module_path):
		self._module_path = module_path

	def __getattr__(self, name):
		import importlib

		return getattr(importlib.import_module(self._module_path), name)


hub_secret = _LazyModule("huf.ai.hub_secret")


class TestHubSecret(IntegrationTestCase):
	def test_create_request_stores_no_secret(self):
		cache = MagicMock()
		service = SimpleNamespace(
			required_credentials=json.dumps([{"key": "token", "required": True}])
		)
		settings = SimpleNamespace(service="telegram")
		with (
			patch("frappe.get_roles", return_value=["System Manager"]),
			patch("frappe.db.exists", return_value=True),
			patch("frappe.get_doc", side_effect=[settings, service]),
			patch("frappe.cache", return_value=cache),
			patch.dict(frappe.session, {"user": "test@example.com"}),
		):
			result = hub_secret.create_secret_request(
				{
					"type": "integration_credential",
					"integration_settings": "telegram-0001",
					"credential_key": "token",
				},
				conversation_id="conv-1",
			)

		stored = cache.set_value.call_args.args[1]
		self.assertNotIn("secret", stored)
		self.assertEqual(result["target"]["credential_key"], "token")
		self.assertNotIn("secret", json.dumps(result))

	def test_submit_provider_secret_consumes_request_and_returns_redacted_result(self):
		cache = MagicMock()
		cache.get_value.return_value = {
			"user": "test@example.com",
			"conversation_id": "conv-1",
			"target": {"type": "provider_api_key", "provider_name": "OpenAI"},
		}
		provider = SimpleNamespace(name="OpenAI", api_key=None)
		provider.save = MagicMock()
		with (
			patch("frappe.get_roles", return_value=["System Manager"]),
			patch("frappe.has_permission", return_value=True),
			patch("frappe.get_doc", return_value=provider),
			patch("frappe.cache", return_value=cache),
			patch.dict(frappe.session, {"user": "test@example.com"}),
		):
			result = hub_secret.submit_hub_secret("opaque-request", "provider-secret", "conv-1")

		self.assertEqual(provider.api_key, "provider-secret")
		provider.save.assert_called_once_with()
		cache.delete_value.assert_called_once()
		self.assertNotIn("provider-secret", json.dumps(result))

	def test_unknown_target_is_rejected(self):
		with patch("frappe.get_roles", return_value=["System Manager"]):
			self.assertRaises(
				frappe.ValidationError,
				hub_secret.create_secret_request,
				{"type": "arbitrary_password_field", "field": "api_key"},
			)
