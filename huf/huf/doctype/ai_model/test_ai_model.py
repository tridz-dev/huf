# Copyright (c) 2025, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from huf.huf.doctype.ai_model.ai_model import MODEL_MODALITY_OPTIONS, get_models_by_modality


class TestAIModel(IntegrationTestCase):
	def setUp(self):
		"""Set up test fixtures."""
		# Ensure test provider exists
		self.provider_name = "test-provider-decision-t1-03"
		if not frappe.db.exists("AI Provider", self.provider_name):
			provider = frappe.get_doc({
				"doctype": "AI Provider",
				"provider_name": self.provider_name,
				"provider_brand": "opencode-zen",
				"api_key": "test-key-12345",
			})
			provider.insert(ignore_if_duplicate=True)

	def test_decision_modality_in_options(self):
		"""Test that 'Decision' is in MODEL_MODALITY_OPTIONS."""
		self.assertIn("Decision", MODEL_MODALITY_OPTIONS)

	def test_decision_modality_options_in_doctype_meta(self):
		"""Test that 'Decision' is in the modalities field options from DocType meta."""
		meta = frappe.get_meta("AI Model")
		modalities_field = meta.get_field("modalities")
		self.assertIsNotNone(modalities_field)
		
		options_text = modalities_field.options
		self.assertIn("Decision", options_text)

	def test_get_models_by_modality_with_decision(self):
		"""Test that get_models_by_modality returns Decision models when filtered by Decision modality."""
		# Create a Decision-only model
		decision_model_id = "decision-model-test-t103"
		if frappe.db.exists("AI Model", decision_model_id):
			frappe.delete_doc("AI Model", decision_model_id)
		
		decision_model = frappe.get_doc({
			"doctype": "AI Model",
			"name": decision_model_id,
			"model_name": decision_model_id,
			"provider": self.provider_name,
			"modalities": "Decision",
		})
		decision_model.insert(ignore_if_duplicate=True)

		# Create a Text model for comparison
		text_model_id = "text-model-test-t103"
		if frappe.db.exists("AI Model", text_model_id):
			frappe.delete_doc("AI Model", text_model_id)
		
		text_model = frappe.get_doc({
			"doctype": "AI Model",
			"name": text_model_id,
			"model_name": text_model_id,
			"provider": self.provider_name,
			"modalities": "Text",
		})
		text_model.insert(ignore_if_duplicate=True)

		# Query Decision models
		decision_filters = {"modality": "Decision"}
		results = get_models_by_modality(
			doctype="AI Model",
			txt="",
			searchfield="name",
			start=0,
			page_len=20,
			filters=decision_filters,
		)
		
		# Verify Decision model is in results, Text model is not
		# get_models_by_modality returns tuples of (name, model_name)
		model_names = [r[0] for r in results]
		model_model_names = [r[1] for r in results]
		
		self.assertIn(decision_model_id, model_names)
		self.assertNotIn(text_model_id, model_names)

	def test_get_models_by_modality_with_text(self):
		"""Test that get_models_by_modality still works correctly with Text modality."""
		# Create a Text model
		text_model_id = "text-model-test-t103-2"
		if frappe.db.exists("AI Model", text_model_id):
			frappe.delete_doc("AI Model", text_model_id)
		
		text_model = frappe.get_doc({
			"doctype": "AI Model",
			"name": text_model_id,
			"model_name": text_model_id,
			"provider": self.provider_name,
			"modalities": "Text",
		})
		text_model.insert(ignore_if_duplicate=True)

		# Query Text models
		text_filters = {"modality": "Text"}
		results = get_models_by_modality(
			doctype="AI Model",
			txt="",
			searchfield="name",
			start=0,
			page_len=20,
			filters=text_filters,
		)
		
		# Verify Text model is in results
		model_names = [r[0] for r in results]
		self.assertIn(text_model_id, model_names)

	def test_get_models_by_modality_with_provider_filter(self):
		"""Test that get_models_by_modality respects provider filter."""
		# Create a different provider
		other_provider_name = "test-provider-other-t103"
		if not frappe.db.exists("AI Provider", other_provider_name):
			frappe.get_doc({
				"doctype": "AI Provider",
				"provider_name": other_provider_name,
				"provider_brand": "anthropic",
				"api_key": "test-key-other-12345",
			}).insert(ignore_if_duplicate=True)

		# Create Decision models on different providers
		model1_id = "decision-model-p1-t103"
		if frappe.db.exists("AI Model", model1_id):
			frappe.delete_doc("AI Model", model1_id)
		
		model1 = frappe.get_doc({
			"doctype": "AI Model",
			"name": model1_id,
			"model_name": model1_id,
			"provider": self.provider_name,
			"modalities": "Decision",
		})
		model1.insert(ignore_if_duplicate=True)

		model2_id = "decision-model-p2-t103"
		if frappe.db.exists("AI Model", model2_id):
			frappe.delete_doc("AI Model", model2_id)
		
		model2 = frappe.get_doc({
			"doctype": "AI Model",
			"name": model2_id,
			"model_name": model2_id,
			"provider": other_provider_name,
			"modalities": "Decision",
		})
		model2.insert(ignore_if_duplicate=True)

		# Query Decision models for self.provider_name
		decision_filters = {"modality": "Decision", "provider": self.provider_name}
		results = get_models_by_modality(
			doctype="AI Model",
			txt="",
			searchfield="name",
			start=0,
			page_len=20,
			filters=decision_filters,
		)
		
		# Verify only model from self.provider_name is in results
		model_names = [r[0] for r in results]
		self.assertIn(model1_id, model_names)
		self.assertNotIn(model2_id, model_names)

	def test_modalities_validation_rejects_invalid_modality(self):
		"""Test that validation rejects invalid modality values."""
		try:
			frappe.get_doc({
				"doctype": "AI Model",
				"name": "test-invalid-modality-t103",
				"model_name": "invalid-model",
				"provider": self.provider_name,
				"modalities": "InvalidModality",
			}).insert(ignore_if_duplicate=True)
			self.fail("Expected validation error for invalid modality")
		except frappe.ValidationError:
			pass  # Expected
