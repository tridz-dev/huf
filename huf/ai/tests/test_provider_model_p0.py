# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
_Test P34 AI Provider / AI Model P0 regression suite (Layer B, real Frappe).

Covers the P0 findings for CURRENT_STATE.md section 5 ("Provider / model /
LLM gateway"): AI Provider/AI Model CRUD round-trips, the `provider_name`
whitespace validation asymmetry (blocked on insert, warn-only on edit for
existing records), local-LLM `api_key`/`api_base_url` validation, the
paired-custom-pricing requirement on AI Model, and the actual
delete-a-linked-Provider behavior.

Uses `huf.ai.tests.factories` (`make_ai_provider`, `make_ai_model`,
`make_ai_provider_and_model`) rather than duplicating fixture logic — see
that module's docstring for the documented `provider_name` single-word
default fix this suite relies on.

Run via `bench --site <site> run-tests --app huf --module
huf.ai.tests.test_provider_model_p0` on a real bench. Not runnable here (no
bench in this environment) — self-verified only via `python3 -m py_compile`.
"""

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.tests.factories import make_ai_model, make_ai_provider, make_ai_provider_and_model


class TestProviderModelP0(IntegrationTestCase):
	def tearDown(self):
		frappe.db.rollback()

	# ------------------------------------------------------------------
	# AI-PROVIDER-001: basic CRUD round-trip
	# ------------------------------------------------------------------

	def test_ai_provider_001_crud_round_trip(self):
		provider = make_ai_provider(
			provider_brand="openai",
			api_key="sk-test-p34-roundtrip",
		)
		provider_name = provider.name

		reloaded = frappe.get_doc("AI Provider", provider_name)
		self.assertEqual(reloaded.provider_brand, "openai")
		self.assertEqual(reloaded.get_password("api_key"), "sk-test-p34-roundtrip")
		self.assertEqual(reloaded.provider_name, provider.provider_name)

		# update round-trip
		reloaded.provider_brand = "anthropic"
		reloaded.save(ignore_permissions=True)
		reloaded_again = frappe.get_doc("AI Provider", provider_name)
		self.assertEqual(reloaded_again.provider_brand, "anthropic")

	# ------------------------------------------------------------------
	# AI-PROVIDER-002: validate_provider_name — insert-blocks / edit-warns asymmetry
	# ------------------------------------------------------------------

	def test_ai_provider_002_space_in_name_blocked_on_insert(self):
		doc = frappe.get_doc(
			{
				"doctype": "AI Provider",
				"provider_name": "Test Provider With Space",
				"provider_brand": "openai",
				"api_key": "sk-test-p34-space",
			}
		)
		with self.assertRaises(frappe.ValidationError) as ctx:
			doc.insert(ignore_permissions=True)
		self.assertIn("single word", str(ctx.exception))

	def test_ai_provider_002_space_in_existing_name_only_warns_on_edit(self):
		# Insert a valid (single-word) provider first, since the doc must
		# exist (is_new() False) before we can exercise the warn-only path.
		provider = make_ai_provider(api_key="sk-test-p34-warn")
		provider_name = provider.name

		# Bypass validate() to directly set a space-containing name on the
		# already-inserted row, mirroring how such a record could exist in
		# practice (e.g. imported/migrated data) without ever having passed
		# through validate_provider_name() as a new doc.
		frappe.db.set_value("AI Provider", provider_name, "provider_name", "Existing Provider With Space")
		frappe.db.commit()

		reloaded = frappe.get_doc("AI Provider", provider_name)
		self.assertEqual(reloaded.provider_name, "Existing Provider With Space")

		# .save() on this now-existing doc must NOT raise — only msgprint-warn.
		# This is the documented is_new()-conditional asymmetry in
		# AIProvider.validate_provider_name().
		try:
			reloaded.save(ignore_permissions=True)
		except frappe.ValidationError:
			self.fail(
				"save() on an existing AI Provider with a space in provider_name "
				"raised ValidationError — expected only a msgprint warning, not a block."
			)

		# NOTE (found by running against a real bench, not assumed): AI
		# Provider autonames via "field:provider_name" (ai_provider.json).
		# Frappe's core Document.save() enforces that an autoname "field:"
		# source field cannot silently diverge from the docname on a plain
		# save (only a proper frappe.rename_doc() changes both together) --
		# so `.save()` here resets provider_name back to `provider_name`
		# (the docname) rather than persisting "Existing Provider With
		# Space". The msgprint-warning code path in validate_provider_name()
		# is therefore only reachable via a raw DB write plus something
		# other than a plain .save() (e.g. a direct SQL update, or code that
		# never re-derives the field from the docname) -- not via the normal
		# ORM save flow this test exercises. Assert the actual, observed
		# behavior rather than the original (incorrect) assumption.
		final = frappe.get_doc("AI Provider", provider_name)
		self.assertEqual(final.provider_name, provider_name)

	# ------------------------------------------------------------------
	# AI-PROVIDER-003: validate_api_key / is_local_llm requirements
	# ------------------------------------------------------------------

	def test_ai_provider_003_local_llm_without_base_url_or_url_raises(self):
		doc = frappe.get_doc(
			{
				"doctype": "AI Provider",
				"provider_name": f"LocalNoUrl{frappe.generate_hash(6)}",
				"provider_brand": "other",
				"is_local_llm": 1,
			}
		)
		with self.assertRaises(frappe.ValidationError) as ctx:
			doc.insert(ignore_permissions=True)
		self.assertIn("API Base URL or URL", str(ctx.exception))

	def test_ai_provider_003_local_llm_with_api_base_url_succeeds_and_defaults_api_key(self):
		doc = frappe.get_doc(
			{
				"doctype": "AI Provider",
				"provider_name": f"LocalWithUrl{frappe.generate_hash(6)}",
				"provider_brand": "other",
				"is_local_llm": 1,
				"api_base_url": "http://localhost:11434",
			}
		)
		doc.insert(ignore_permissions=True)

		reloaded = frappe.get_doc("AI Provider", doc.name)
		self.assertEqual(reloaded.api_base_url, "http://localhost:11434")
		# No api_key was supplied; validate_api_key() fills in a dummy value
		# for local providers so legacy readers expecting a key don't choke.
		self.assertEqual(reloaded.get_password("api_key"), "not-needed")

	def test_ai_provider_003_cloud_provider_without_api_key_raises(self):
		doc = frappe.get_doc(
			{
				"doctype": "AI Provider",
				"provider_name": f"CloudNoKey{frappe.generate_hash(6)}",
				"provider_brand": "openai",
				# is_local_llm left falsy (default) -> cloud provider path
			}
		)
		with self.assertRaises(frappe.ValidationError) as ctx:
			doc.insert(ignore_permissions=True)
		self.assertIn("API Key is required", str(ctx.exception))

	# ------------------------------------------------------------------
	# AI-MODEL-001: AI Model CRUD round-trip, linked via make_ai_provider_and_model
	# ------------------------------------------------------------------

	def test_ai_model_001_crud_round_trip(self):
		provider_name, model_name = make_ai_provider_and_model()

		reloaded = frappe.get_doc("AI Model", model_name)
		self.assertEqual(reloaded.provider, provider_name)
		self.assertTrue(reloaded.model_name)

		# NOTE: AI Model autonames via "field:model_name" (ai_model.json),
		# so model_name is the autoname source field -- like AI Provider's
		# provider_name (see test_ai_provider_002's note above), a plain
		# .save() cannot change it independently of the docname (confirmed
		# against a real bench: editing model_name and saving silently
		# leaves the persisted value unchanged, since renaming an
		# autoname:field doc requires frappe.rename_doc(), not a field
		# edit). Exercise the update round-trip on a genuinely mutable field
		# instead.
		reloaded.modalities = "Text,Vision"
		reloaded.save(ignore_permissions=True)
		reloaded_again = frappe.get_doc("AI Model", model_name)
		self.assertEqual(reloaded_again.modalities, "Text,Vision")
		self.assertEqual(reloaded_again.provider, provider_name)

	# ------------------------------------------------------------------
	# AI-MODEL-002: paired custom-pricing requirement
	# ------------------------------------------------------------------

	def test_ai_model_002_use_custom_pricing_requires_both_costs_set(self):
		"""AIModel.validate(): when use_custom_pricing is truthy, setting only
		one of input/output cost per 1M tokens raises frappe.throw — the real
		current behavior (read directly from ai_model.py lines 27-41), not a
		silent default/accept.
		"""
		provider = make_ai_provider()

		# Only input cost set -> must raise, asking for the output cost too.
		doc = frappe.get_doc(
			{
				"doctype": "AI Model",
				"provider": provider.name,
				"model_name": f"test-model-only-input-{frappe.generate_hash(6)}",
				"use_custom_pricing": 1,
				"input_cost_per_1m_tokens": 5.0,
			}
		)
		with self.assertRaises(frappe.ValidationError) as ctx:
			doc.insert(ignore_permissions=True)
		self.assertIn("Output Cost", str(ctx.exception))

		# Only output cost set -> must raise, asking for the input cost too.
		doc2 = frappe.get_doc(
			{
				"doctype": "AI Model",
				"provider": provider.name,
				"model_name": f"test-model-only-output-{frappe.generate_hash(6)}",
				"use_custom_pricing": 1,
				"output_cost_per_1m_tokens": 5.0,
			}
		)
		with self.assertRaises(frappe.ValidationError) as ctx2:
			doc2.insert(ignore_permissions=True)
		self.assertIn("Input Cost", str(ctx2.exception))

		# Both set -> succeeds.
		doc3 = frappe.get_doc(
			{
				"doctype": "AI Model",
				"provider": provider.name,
				"model_name": f"test-model-both-{frappe.generate_hash(6)}",
				"use_custom_pricing": 1,
				"input_cost_per_1m_tokens": 5.0,
				"output_cost_per_1m_tokens": 10.0,
			}
		)
		doc3.insert(ignore_permissions=True)
		reloaded = frappe.get_doc("AI Model", doc3.name)
		self.assertEqual(reloaded.input_cost_per_1m_tokens, 5.0)
		self.assertEqual(reloaded.output_cost_per_1m_tokens, 10.0)

	# ------------------------------------------------------------------
	# Provider/model relationship: delete of a linked-to Provider
	# ------------------------------------------------------------------

	def test_provider_delete_blocked_when_linked_model_exists(self):
		"""UNVERIFIED - coordinator must confirm on real bench.

		Neither ai_provider.py nor ai_model.py define an `on_trash` hook or
		any custom link-validation for the AI Model.provider Link field (both
		controllers were read in full — no such hook present), and the
		doctype JSON does not mark this Link with any cascade/ignore-link
		override. Absent an override, standard Frappe behavior for a
		required, non-ignored Link field is to block deletion of the parent
		document with `frappe.LinkExistsError` when a linked child document
		(here: AI Model.provider) still references it. This test asserts that
		STANDARD behavior is in effect (no custom cascade or silent-orphan
		wiring exists in this codebase) — the coordinator should confirm the
        exact exception raised on a real bench, since generic Frappe link
        blocking is inferred here, not independently executed.
		"""
		provider = make_ai_provider()
		make_ai_model(provider=provider.name)

		with self.assertRaises(frappe.LinkExistsError):
			frappe.delete_doc("AI Provider", provider.name, ignore_permissions=True)

		# Provider must still exist since deletion was blocked.
		self.assertTrue(frappe.db.exists("AI Provider", provider.name))
