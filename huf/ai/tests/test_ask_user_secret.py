"""ask_user ``secret`` kind: masked form questions whose values never enter chat."""

import importlib

import frappe
from frappe.tests import IntegrationTestCase


class _LazyModule:
	"""Defer the app import until first use (see test_builder_tools for why)."""

	def __init__(self, module_path):
		self._module_path = module_path

	def __getattr__(self, name):
		return getattr(importlib.import_module(self._module_path), name)


ask_user_mod = _LazyModule("huf.ai.tools.ask_user")


def _secret_question(**overrides):
	question = {
		"id": "meta_creds",
		"text": "Enter your Meta app credentials",
		"kind": "secret",
		"purpose": "Connect the WhatsApp gateway",
		"fields": [
			{"id": "access_token", "label": "Access token"},
			{"id": "app_secret", "label": "App secret"},
		],
	}
	question.update(overrides)
	return question


class TestAskUserSecret(IntegrationTestCase):
	def _run(self, **kwargs):
		return ask_user_mod.ask_user(**kwargs)

	def _block(self, result):
		import json

		raw = result["block"].split("```ask-user\n", 1)[1].rsplit("\n```", 1)[0]
		return json.loads(raw)

	def test_secret_is_a_known_kind(self):
		self.assertIn("secret", ask_user_mod.ASK_USER_KINDS)

	def test_form_schema_accepts_secret_kind_and_fields(self):
		props = ask_user_mod.ASK_USER_PARAMS_SCHEMA["properties"]["questions"]["items"]["properties"]
		self.assertIn("secret", props["kind"]["enum"])
		self.assertIn("fields", props)

	def test_secret_question_emits_masked_fields_and_purpose(self):
		result = self._run(questions=[_secret_question()])
		question = result["ask_user"]["questions"][0]
		self.assertEqual(question["kind"], "secret")
		self.assertEqual(
			question["fields"],
			[
				{"id": "access_token", "label": "Access token", "secret": True},
				{"id": "app_secret", "label": "App secret", "secret": True},
			],
		)
		self.assertEqual(question["purpose"], "Connect the WhatsApp gateway")
		self.assertFalse(question["allow_free_text"])
		self.assertEqual(question["options"], [])

		block = self._block(result)
		self.assertEqual(block["kind"], "secret")
		self.assertEqual(block["purpose"], "Connect the WhatsApp gateway")
		self.assertEqual(len(block["fields"]), 2)
		self.assertTrue(all(field["secret"] is True for field in block["fields"]))

	def test_purpose_defaults_to_question_text(self):
		question = _secret_question()
		del question["purpose"]
		result = self._run(questions=[question])
		self.assertEqual(result["ask_user"]["questions"][0]["purpose"], "Enter your Meta app credentials")

	def test_secret_question_requires_at_least_one_field(self):
		with self.assertRaises(frappe.ValidationError):
			self._run(questions=[_secret_question(fields=[])])
		with self.assertRaises(frappe.ValidationError):
			self._run(questions=[_secret_question(fields=None)])

	def test_secret_field_ids_must_be_unique(self):
		fields = [{"id": "token", "label": "A"}, {"id": "token", "label": "B"}]
		with self.assertRaises(frappe.ValidationError):
			self._run(questions=[_secret_question(fields=fields)])

	def test_secret_field_label_is_required(self):
		fields = [{"id": "token", "label": "   "}]
		with self.assertRaises(frappe.ValidationError):
			self._run(questions=[_secret_question(fields=fields)])

	def test_secret_field_id_is_required(self):
		fields = [{"id": "", "label": "Token"}]
		with self.assertRaises(frappe.ValidationError):
			self._run(questions=[_secret_question(fields=fields)])

	def test_secret_field_must_be_an_object(self):
		with self.assertRaises(frappe.ValidationError):
			self._run(questions=[_secret_question(fields=["token"])])

	def test_secret_field_label_is_capped(self):
		fields = [{"id": "token", "label": "x" * 5000}]
		result = self._run(questions=[_secret_question(fields=fields)])
		label = result["ask_user"]["questions"][0]["fields"][0]["label"]
		self.assertEqual(len(label), ask_user_mod.MAX_TEXT_LENGTH)

	def test_secret_field_count_is_capped(self):
		fields = [{"id": f"f{i}", "label": f"Field {i}"} for i in range(ask_user_mod.MAX_SECRET_FIELDS + 1)]
		with self.assertRaises(frappe.ValidationError):
			self._run(questions=[_secret_question(fields=fields)])

	def test_secret_questions_can_mix_with_other_kinds(self):
		result = self._run(
			questions=[
				{"id": "region", "text": "Which region?", "options": ["EU", "US"]},
				_secret_question(),
			]
		)
		kinds = [q["kind"] for q in result["ask_user"]["questions"]]
		self.assertEqual(kinds, ["single_choice", "secret"])

	def test_legacy_single_question_rejects_secret_kind(self):
		with self.assertRaises(frappe.ValidationError):
			self._run(question="Token?", kind="secret")

	def test_secret_block_carries_no_values(self):
		# The tool never receives values; the block must only describe the form.
		result = self._run(questions=[_secret_question()])
		self.assertNotIn("value", result["block"].lower())
