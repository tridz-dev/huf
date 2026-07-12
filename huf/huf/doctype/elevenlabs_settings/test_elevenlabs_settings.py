# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestElevenlabsSettings(HufTestSuite):
	"""ElevenLabs Settings is a Single doctype with no custom controller
	logic — just confirm the field set round-trips and the AI Provider link
	validates, since that's the only real behavior Frappe enforces here."""

	def test_settings_fields_round_trip(self):
		with self.change_settings(
			"Elevenlabs Settings",
			agent_id="_test-agent-id",
			provider=self.bootstrap.provider.name,
			webhook_secret="test-webhook-secret",
		):
			settings = frappe.get_single("Elevenlabs Settings")

			self.assertEqual(settings.agent_id, "_test-agent-id")
			self.assertEqual(settings.provider, self.bootstrap.provider.name)
			self.assertEqual(settings.get_password("webhook_secret"), "test-webhook-secret")

	def test_invalid_provider_link_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			with self.change_settings("Elevenlabs Settings", provider="_Nonexistent Provider"):
				pass
