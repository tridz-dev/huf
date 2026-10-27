# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-T6: test_gateway_send reports success; preview_gateway_readiness provider hook."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
import litellm
from frappe.tests import IntegrationTestCase

from huf.ai import gateway_service
from huf.ai.gateway_adapters import provider_hooks
from huf.ai.gateway_adapters.types import OutboundDelivery

CORE_IDS = [cid for cid, _ in gateway_service.GATEWAY_READINESS_CHECKS]


class TestGatewayTestSend(IntegrationTestCase):
	def _run(self, provider, adapter):
		gw = SimpleNamespace(is_enabled=1, provider=provider, integration_settings="IS-1")
		with (
			patch("huf.ai.gateway_service.frappe") as mock_frappe,
			patch("huf.ai.gateway_webhook.get_gateway_adapter", return_value=adapter),
		):
			mock_frappe.has_permission.return_value = True
			mock_frappe.get_doc.return_value = gw
			return gateway_service.test_gateway_send("GW", "recipient-1")

	def test_success_reported_for_two_providers_with_real_outbound_delivery(self):
		for provider, receipt in (("Telegram", "tg-42"), ("Microsoft Teams", "19:abc")):
			adapter = MagicMock()
			adapter.send_reply.return_value = OutboundDelivery(provider_message_id=receipt)
			result = self._run(provider, adapter)
			self.assertTrue(result["success"], (provider, result))
			self.assertEqual(json.loads(result["provider_response"]), {"provider_message_id": receipt})
			self.assertEqual(adapter.send_reply.call_args.args[0].conversation_id, "recipient-1")

	def test_adapter_error_is_surfaced_and_redacted(self):
		adapter = MagicMock()
		adapter.send_reply.side_effect = RuntimeError("boom ?key=abcSECRET123")
		result = self._run("Telegram", adapter)
		self.assertFalse(result["success"])
		self.assertIn("boom", result["message"])
		self.assertNotIn("abcSECRET123", result["message"] + str(result["provider_response"]))

	def test_missing_delivery_field_is_not_silently_swallowed_as_success(self):
		adapter = MagicMock()
		adapter.send_reply.return_value = SimpleNamespace(delivery_id="legacy")  # wrong shape
		result = self._run("Telegram", adapter)
		self.assertFalse(result["success"])


class TestReadinessProviderHook(IntegrationTestCase):
	PROVIDER = "Slack"

	def setUp(self):
		frappe.set_user("Administrator")
		self._saved = dict(provider_hooks._HOOKS)
		doc = frappe.get_doc(
			{
				"doctype": "Gateway",
				"gateway_name": frappe.generate_hash(length=10),
				"provider": self.PROVIDER,
				"is_enabled": 0,
				"direct_policy": "Pairing",
			}
		).insert(ignore_permissions=True)
		self.gw = doc.name

	def tearDown(self):
		provider_hooks._HOOKS.clear()
		provider_hooks._HOOKS.update(self._saved)
		frappe.delete_doc("Gateway", self.gw, force=True, ignore_permissions=True)
		frappe.db.commit()

	def _hook(self, fn):
		provider_hooks.register(self.PROVIDER, "readiness_checks", fn)

	def test_no_hook_output_is_core_only(self):
		result = gateway_service.preview_gateway_readiness(self.gw)
		self.assertEqual([c["id"] for c in result["checks"]], CORE_IDS)

	def test_empty_hook_output_is_identical_to_no_hook(self):
		before = gateway_service.preview_gateway_readiness(self.gw)
		self._hook(lambda gateway, adapter: [])
		self.assertEqual(json.dumps(gateway_service.preview_gateway_readiness(self.gw)), json.dumps(before))

	def test_extra_checks_appended_and_counted(self):
		base = gateway_service.preview_gateway_readiness(self.gw)
		seen = {}

		def hook(gateway, adapter):
			seen["provider"] = gateway.provider
			return [
				{"id": "x-ok", "label": "X ok", "done": True, "hint": "ignored"},
				{"id": "x-bad", "label": "X bad", "done": False, "hint": "Fix X"},
			]

		self._hook(hook)
		result = gateway_service.preview_gateway_readiness(self.gw)
		self.assertEqual(seen["provider"], self.PROVIDER)
		self.assertEqual([c["id"] for c in result["checks"]], CORE_IDS + ["x-ok", "x-bad"])
		self.assertEqual(result["checks"][-2], {"id": "x-ok", "label": "X ok", "done": True, "hint": None})
		self.assertEqual(result["checks"][-1]["hint"], "Fix X")
		self.assertEqual(result["blocking_count"], base["blocking_count"] + 1)
		self.assertFalse(result["ready"])

	def test_hook_receives_adapter_when_buildable_else_none(self):
		got = []
		self._hook(lambda gateway, adapter: got.append(adapter) or [])
		sentinel = object()
		with patch("huf.ai.gateway_webhook.get_gateway_adapter", return_value=sentinel):
			gateway_service.preview_gateway_readiness(self.gw)
		with patch("huf.ai.gateway_webhook.get_gateway_adapter", side_effect=ValueError("no creds")):
			gateway_service.preview_gateway_readiness(self.gw)
		self.assertEqual(got, [sentinel, None])

	def test_hook_failure_becomes_failing_check_without_breaking_core(self):
		def boom(gateway, adapter):
			raise RuntimeError("bad https://x.test/a ?key=abcSECRET123")

		self._hook(boom)
		result = gateway_service.preview_gateway_readiness(self.gw)
		self.assertEqual([c["id"] for c in result["checks"]][: len(CORE_IDS)], CORE_IDS)
		last = result["checks"][-1]
		self.assertEqual((last["id"], last["done"]), ("provider-checks", False))
		self.assertNotIn("abcSECRET123", last["hint"])
