"""Admission-policy regression tests for the legacy Telegram webhook handler.

Covers the Gateway lookup in `process_telegram_update`: a disabled Gateway must
never fall back to the ungoverned legacy execution path -- only the true
"no Gateway configured at all" case may do so.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.tools.telegram_webhook import process_telegram_update

UPDATE = {
	"message": {
		"message_id": 10,
		"chat": {"id": 999},
		"from": {"username": "janedoe"},
		"text": "hello bot",
	}
}


class TestTelegramWebhookGatewayAdmission(IntegrationTestCase):
	"""process_telegram_update must not let a disabled Gateway widen access."""

	def _settings_doc(self):
		return frappe.get_doc(
			{
				"name": "bot-settings",
				"doctype": "Integration Settings",
				"service": "telegram",
				"is_active": 1,
				"telegram_agent": "test-agent",
			}
		)

	def _patch_common(self, settings_doc):
		"""Patch the shared lookups so we only exercise the Gateway branch."""
		return [
			patch("frappe.db.exists", side_effect=lambda doctype, *a, **k: True),
			patch("frappe.get_doc", return_value=settings_doc),
		]

	def test_enabled_gateway_hands_off_to_gateway_path(self):
		settings_doc = self._settings_doc()
		with patch("frappe.db.exists", return_value=True), patch(
			"frappe.get_doc", return_value=settings_doc
		), patch(
			"frappe.db.get_value", return_value="GATEWAY-001"
		), patch(
			"huf.ai.gateway_service.ingest_gateway_event"
		) as mock_ingest, patch(
			"huf.ai.agent_integration.run_agent_sync"
		) as mock_run_sync:
			process_telegram_update("bot-settings", UPDATE)

		mock_ingest.assert_called_once()
		self.assertEqual(mock_ingest.call_args.args[0], "GATEWAY-001")
		mock_run_sync.assert_not_called()

	def test_disabled_gateway_does_not_run_agent(self):
		settings_doc = self._settings_doc()

		def fake_exists(doctype, *args, **kwargs):
			if doctype == "Gateway":
				return True
			return True

		with patch("frappe.db.exists", side_effect=fake_exists), patch(
			"frappe.get_doc", return_value=settings_doc
		), patch(
			"frappe.db.get_value", return_value=None
		), patch(
			"huf.ai.agent_integration.run_agent_sync"
		) as mock_run_sync, patch(
			"huf.ai.tools.telegram_webhook._send_telegram_message"
		) as mock_send:
			process_telegram_update("bot-settings", UPDATE)

		mock_run_sync.assert_not_called()
		mock_send.assert_called_once()

	def test_no_gateway_falls_back_to_legacy_agent_run(self):
		settings_doc = self._settings_doc()

		def fake_exists(doctype, *args, **kwargs):
			if doctype == "Gateway":
				return False
			return True

		with patch("frappe.db.exists", side_effect=fake_exists), patch(
			"frappe.get_doc", return_value=settings_doc
		), patch(
			"frappe.db.get_value", return_value=None
		), patch(
			"huf.ai.agent_integration.run_agent_sync",
			return_value={"response": "hi there"},
		) as mock_run_sync, patch(
			"huf.ai.tools.telegram_webhook._send_telegram_message"
		) as mock_send:
			process_telegram_update("bot-settings", UPDATE)

		mock_run_sync.assert_called_once()
		mock_send.assert_called_once()
