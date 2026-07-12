# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestAIModel(HufTestSuite):
	def _make_model(self, **overrides):
		doc = {
			"doctype": "AI Model",
			"provider": self.bootstrap.provider.name,
			"model_name": "_Test Model Extra",
		}
		doc.update(overrides)
		return frappe.get_doc(doc).insert(ignore_permissions=True)

	def test_create_model_with_required_fields(self):
		model = self._make_model()

		# autoname is "field:model_name"
		self.assertEqual(model.name, "_Test Model Extra")
		self.assertEqual(model.provider, self.bootstrap.provider.name)

	def test_missing_provider_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "AI Model",
				"model_name": "_Test Model No Provider",
			}).insert(ignore_permissions=True)

	def test_invalid_provider_link_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_model(
				model_name="_Test Model Bad Provider",
				provider="_Nonexistent Provider",
			)

	def test_custom_pricing_requires_both_input_and_output(self):
		# AIModel.validate(): if use_custom_pricing and only one price is set, throw.
		with self.assertRaises(frappe.ValidationError):
			self._make_model(
				model_name="_Test Model Half Pricing",
				use_custom_pricing=1,
				input_cost_per_1m_tokens=1.5,
			)

	def test_custom_pricing_with_both_prices_succeeds(self):
		model = self._make_model(
			model_name="_Test Model Full Pricing",
			use_custom_pricing=1,
			input_cost_per_1m_tokens=1.5,
			output_cost_per_1m_tokens=3.0,
		)

		self.assertEqual(model.input_cost_per_1m_tokens, 1.5)
		self.assertEqual(model.output_cost_per_1m_tokens, 3.0)

	def test_pricing_not_required_when_custom_pricing_disabled(self):
		model = self._make_model(model_name="_Test Model Default Pricing")

		self.assertFalse(model.get("use_custom_pricing"))
