# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestAgentSettings(HufTestSuite):
	"""Agent Settings is a Single doctype with no custom controller logic —
	tests mutate and restore the single instance via self.change_settings."""

	def test_set_default_provider_and_model(self):
		with self.change_settings(
			"Agent Settings",
			default_provider=self.bootstrap.provider.name,
			default_model=self.bootstrap.model.name,
		):
			settings = frappe.get_single("Agent Settings")

			self.assertEqual(settings.default_provider, self.bootstrap.provider.name)
			self.assertEqual(settings.default_model, self.bootstrap.model.name)

	def test_change_settings_restores_previous_values(self):
		before = frappe.get_single("Agent Settings")
		original_provider = before.default_provider
		original_model = before.default_model

		with self.change_settings(
			"Agent Settings",
			default_provider=self.bootstrap.provider.name,
			default_model=self.bootstrap.model.name,
		):
			settings = frappe.get_single("Agent Settings")
			self.assertEqual(settings.default_provider, self.bootstrap.provider.name)

		after = frappe.get_single("Agent Settings")
		self.assertEqual(after.default_provider, original_provider)
		self.assertEqual(after.default_model, original_model)

	def test_default_provider_link_must_be_valid(self):
		with self.assertRaises(frappe.ValidationError):
			with self.change_settings("Agent Settings", default_provider="Nonexistent Provider"):
				pass
