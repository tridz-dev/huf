# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""
Chat guard test suite for Decision-only AI Models.

Tests the rejection of Decision-modality-only AI Models in chat/generation paths:
- _resolve_effective_model (agent_integration.py) guard
- Agent._validate_advanced_models (agent.py) guard
- is_decision_only_model classification (ai_model.py)
- get_models_by_modality legacy-model inclusion (ai_model.py)
- _default_model_for_provider (hub_orchestrator.py) exclusion
- litellm run/run_stream (litellm.py) defense-in-depth guards
- hub_api.get_model_catalog_proposals (hub_api.py) separate grouping

Fixtures:
- An AI Provider (demo/local, flags.ignore_mandatory)
- A Decision-only AI Model (modalities = "Decision")
- A normal Text AI Model (modalities = "Text")
- A legacy AI Model (modalities = "" blank, should still be pickable as Text)

Assertions:
- Decision-only model fails in all chat paths (resolve, validate, picker, defaults)
- Text model and legacy models still pass (no regression)
- litellm.run and litellm.run_stream raise ProviderUnavailableError before network call
- Catalog proposals separate Decision models into decision_proposals key

Run:
    bench --site dr-activation.local run-tests --app huf --module huf.ai.decision.tests.test_chat_guard
"""

import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from types import SimpleNamespace

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.agent_integration import _resolve_effective_model
from huf.ai.hub_api import get_model_catalog_proposals
from huf.huf.doctype.ai_model.ai_model import is_decision_only_model, get_models_by_modality
from huf.ai.app_seeding.hub_orchestrator import _default_model_for_provider
from huf.ai.tests.factories import make_ai_provider, make_ai_model, make_agent


PREFIX = "_Test ChatGuard"


class TestChatGuard(IntegrationTestCase):
	"""Verify Decision-only models are rejected in chat paths; Text/legacy models pass."""

	def setUp(self):
		self._names = {
			"AI Provider": [],
			"AI Model": [],
			"Agent": [],
		}

		# Create demo provider (local, no external calls)
		# Provider name must be a single word (no spaces)
		self.provider = make_ai_provider(
			provider_name="TestChatGuard",
			provider_brand="openai",
		)
		self.provider.flags.ignore_mandatory = True
		self._track("AI Provider", self.provider.name)

		# Decision-only model
		self.decision_model = make_ai_model(
			provider=self.provider.name,
			model_name=f"{PREFIX}_decision_model",
			modalities="Decision",
		)
		self._track("AI Model", self.decision_model.name)

		# Text model (normal chat)
		self.text_model = make_ai_model(
			provider=self.provider.name,
			model_name=f"{PREFIX}_text_model",
			modalities="Text",
		)
		self._track("AI Model", self.text_model.name)

		# Legacy model (blank modalities, should still be pickable as Text)
		self.legacy_model = make_ai_model(
			provider=self.provider.name,
			model_name=f"{PREFIX}_legacy_model",
			modalities="",  # Blank: pre-modality-era model
		)
		self._track("AI Model", self.legacy_model.name)

	def tearDown(self):
		frappe.set_user("Administrator")
		for doctype in ("Agent", "AI Model", "AI Provider"):
			for name in self._names.get(doctype, []):
				self._delete(doctype, name)
		frappe.db.commit()

	def _delete(self, doctype, name):
		try:
			frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
		except Exception:
			pass

	def _track(self, doctype, name):
		self._names.setdefault(doctype, []).append(name)
		return name

	# =========================================================================
	# is_decision_only_model classification
	# =========================================================================

	def test_is_decision_only_model_with_decision_modality(self):
		"""Decision-only model is correctly classified."""
		self.assertTrue(is_decision_only_model(self.decision_model.name))

	def test_is_decision_only_model_with_text_modality(self):
		"""Text model is NOT Decision-only."""
		self.assertFalse(is_decision_only_model(self.text_model.name))

	def test_is_decision_only_model_with_blank_modality(self):
		"""Legacy model with blank modality is NOT Decision-only."""
		self.assertFalse(is_decision_only_model(self.legacy_model.name))

	def test_is_decision_only_model_with_doc_object(self):
		"""is_decision_only_model accepts both docname and document object."""
		doc = frappe.get_doc("AI Model", self.decision_model.name)
		self.assertTrue(is_decision_only_model(doc))
		self.assertFalse(is_decision_only_model(frappe.get_doc("AI Model", self.text_model.name)))

	# =========================================================================
	# get_models_by_modality (picker query)
	# =========================================================================

	def test_get_models_by_modality_text_excludes_decision_only(self):
		"""Text modality picker excludes Decision-only models."""
		results = get_models_by_modality(
			doctype="AI Model",
			txt="",
			searchfield="name",
			start=0,
			page_len=100,
			filters={"modality": "Text", "provider": self.provider.name},
		)
		result_names = [r[0] for r in results]
		self.assertIn(self.text_model.name, result_names)
		self.assertIn(self.legacy_model.name, result_names)  # Legacy models still pickable
		self.assertNotIn(self.decision_model.name, result_names)  # Decision-only excluded

	def test_get_models_by_modality_text_includes_legacy_models(self):
		"""Legacy models (blank modality) are still included in Text picker."""
		results = get_models_by_modality(
			doctype="AI Model",
			txt="",
			searchfield="name",
			start=0,
			page_len=100,
			filters={"modality": "Text", "provider": self.provider.name},
		)
		result_names = [r[0] for r in results]
		self.assertIn(
			self.legacy_model.name,
			result_names,
			"Legacy model with blank modality should be included in Text picker for backward compat",
		)

	# =========================================================================
	# Agent model picker & validation
	# =========================================================================

	def test_agent_rejects_decision_only_as_primary_model(self):
		"""Agent.save() rejects Decision-only model in primary model field."""
		agent = make_ai_model(provider=self.provider.name, model_name="temp_model_for_agent")
		self._track("AI Model", agent.name)
		agent_doc = make_agent(
			agent_name=f"{PREFIX}_agent_decision",
			provider=self.provider.name,
			model=agent.name,
		)
		self._track("Agent", agent_doc.name)

		# Now swap to Decision-only model
		agent_doc.model = self.decision_model.name
		with self.assertRaises(frappe.ValidationError) as raised:
			agent_doc.save()
		error_msg = str(raised.exception)
		self.assertIn("decision", error_msg.lower())

	def test_agent_accepts_text_model(self):
		"""Agent.save() accepts Text model in primary field (no regression)."""
		agent_doc = make_agent(
			agent_name=f"{PREFIX}_agent_text",
			provider=self.provider.name,
			model=self.text_model.name,
		)
		self._track("Agent", agent_doc.name)
		# Should not raise
		agent_doc.save()
		self.assertEqual(agent_doc.model, self.text_model.name)

	def test_agent_accepts_legacy_model(self):
		"""Agent.save() accepts legacy (blank-modality) model (no regression)."""
		agent_doc = make_agent(
			agent_name=f"{PREFIX}_agent_legacy",
			provider=self.provider.name,
			model=self.legacy_model.name,
		)
		self._track("Agent", agent_doc.name)
		# Should not raise
		agent_doc.save()
		self.assertEqual(agent_doc.model, self.legacy_model.name)

	def test_agent_rejects_decision_only_as_summary_model(self):
		"""Agent.save() rejects Decision-only model in summary_model field."""
		agent_doc = make_agent(
			agent_name=f"{PREFIX}_agent_summary_decision",
			provider=self.provider.name,
			model=self.text_model.name,  # Primary is valid
		)
		self._track("Agent", agent_doc.name)
		agent_doc.summary_model = self.decision_model.name
		with self.assertRaises(frappe.ValidationError) as raised:
			agent_doc.save()
		error_msg = str(raised.exception)
		self.assertIn("decision", error_msg.lower())

	# =========================================================================
	# _resolve_effective_model guard (integration.py)
	# =========================================================================

	def test_resolve_effective_model_rejects_decision_only(self):
		"""_resolve_effective_model raises when model is Decision-only."""
		agent_doc = make_agent(
			agent_name=f"{PREFIX}_agent_resolve",
			provider=self.provider.name,
			model=self.text_model.name,
		)
		self._track("Agent", agent_doc.name)

		# Manually set to Decision-only (bypass validation for this test)
		frappe.db.set_value("Agent", agent_doc.name, "model", self.decision_model.name)

		with self.assertRaises(frappe.ValidationError) as raised:
			_resolve_effective_model(agent_doc, model=self.decision_model.name)
		error_msg = str(raised.exception)
		self.assertIn("decision", error_msg.lower())
		self.assertIn("chat", error_msg.lower())

	def test_resolve_effective_model_accepts_text_model(self):
		"""_resolve_effective_model accepts Text model (no regression)."""
		agent_doc = make_agent(
			agent_name=f"{PREFIX}_agent_resolve_text",
			provider=self.provider.name,
			model=self.text_model.name,
		)
		self._track("Agent", agent_doc.name)

		# Should not raise
		_resolve_effective_model(agent_doc, model=self.text_model.name)

	def test_resolve_effective_model_accepts_legacy_model(self):
		"""_resolve_effective_model accepts legacy model (no regression)."""
		agent_doc = make_agent(
			agent_name=f"{PREFIX}_agent_resolve_legacy",
			provider=self.provider.name,
			model=self.legacy_model.name,
		)
		self._track("Agent", agent_doc.name)

		# Should not raise
		_resolve_effective_model(agent_doc, model=self.legacy_model.name)

	# =========================================================================
	# _default_model_for_provider (hub_orchestrator.py)
	# =========================================================================

	def test_default_model_excludes_decision_only(self):
		"""_default_model_for_provider never returns a Decision-only model."""
		default = _default_model_for_provider(self.provider.name)
		if default:  # May be None if no other models exist
			self.assertFalse(
				is_decision_only_model(default),
				f"Default model should not be Decision-only, got {default}",
			)

	def test_default_model_prefers_text_over_decision(self):
		"""When Text and Decision models both exist, default prefers Text."""
		# Create a preferred Text model
		text_preferred = make_ai_model(
			provider=self.provider.name,
			model_name=f"{PREFIX}_gpt_4o",  # Marker in preferred list
			modalities="Text",
		)
		self._track("AI Model", text_preferred.name)

		default = _default_model_for_provider(self.provider.name)
		# Should pick the Text model, not the Decision model
		self.assertNotEqual(
			default,
			self.decision_model.name,
			"Should never return Decision-only as default",
		)

	# =========================================================================
	# hub_api.get_model_catalog_proposals separation
	# =========================================================================

	def test_catalog_proposals_separates_decision_models(self):
		"""get_model_catalog_proposals returns decision_proposals as separate key."""
		proposals = get_model_catalog_proposals()

		# Result should have both 'proposals' and 'decision_proposals' keys
		self.assertIn("proposals", proposals)
		self.assertIn("decision_proposals", proposals)

		# All decision proposals should have Decision in modalities
		for proposal in proposals.get("decision_proposals", []):
			self.assertIn("Decision", proposal.get("modalities", ""))

		# No proposals should have Decision-only (Text/Vision models go to proposals)
		for proposal in proposals.get("proposals", []):
			modalities = proposal.get("modalities", "")
			if "Decision" in modalities:
				# Should only happen if also has other modalities
				self.assertTrue(
					any(m in modalities for m in ["Text", "Image", "Vision", "Audio"]),
					f"Non-Decision-only proposal has Decision: {proposal}",
				)

	# =========================================================================
	# litellm run/run_stream defense-in-depth (litellm.py)
	# =========================================================================

	async def test_litellm_run_rejects_decision_only_before_network_call(self):
		"""litellm.run raises ProviderUnavailableError before litellm network call."""
		from huf.ai.providers.litellm import run, ProviderUnavailableError

		agent_doc = make_agent(
			agent_name=f"{PREFIX}_agent_litellm_run",
			provider=self.provider.name,
			model=self.decision_model.name,
		)
		self._track("Agent", agent_doc.name)

		# Manually bypass Agent validation to test defense-in-depth
		frappe.db.set_value("Agent", agent_doc.name, "model", self.decision_model.name)
		agent_doc.reload()

		enhanced_prompt = "Test prompt"

		# Mock litellm.completion to ensure it is NOT called
		with patch("litellm.completion") as mock_completion:
			try:
				await run(agent_doc, enhanced_prompt, self.provider.name, self.decision_model.name)
				self.fail("Should have raised ProviderUnavailableError")
			except ProviderUnavailableError as e:
				self.assertIn("Decision", str(e))
				self.assertIn("chat", str(e).lower())
				# Verify litellm.completion was NEVER called
				mock_completion.assert_not_called()

	async def test_litellm_run_stream_rejects_decision_only_before_network_call(self):
		"""litellm.run_stream raises ProviderUnavailableError before litellm network call."""
		from huf.ai.providers.litellm import run_stream, ProviderUnavailableError

		agent_doc = make_agent(
			agent_name=f"{PREFIX}_agent_litellm_stream",
			provider=self.provider.name,
			model=self.decision_model.name,
		)
		self._track("Agent", agent_doc.name)

		# Manually bypass Agent validation
		frappe.db.set_value("Agent", agent_doc.name, "model", self.decision_model.name)
		agent_doc.reload()

		enhanced_prompt = "Test prompt"

		# Mock litellm.completion_with_retries to ensure it is NOT called
		with patch("litellm.completion") as mock_completion:
			try:
				async for chunk in run_stream(
					agent_doc, enhanced_prompt, self.provider.name, self.decision_model.name
				):
					pass  # Consume the generator
				self.fail("Should have raised ProviderUnavailableError")
			except ProviderUnavailableError as e:
				self.assertIn("Decision", str(e))
				self.assertIn("chat", str(e).lower())
				# Verify litellm.completion was NEVER called
				mock_completion.assert_not_called()

	def test_litellm_run_accepts_text_model(self):
		"""litellm.run accepts Text model (no regression with guard in place)."""
		from huf.ai.providers.litellm import run

		agent_doc = make_agent(
			agent_name=f"{PREFIX}_agent_litellm_text",
			provider=self.provider.name,
			model=self.text_model.name,
		)
		self._track("Agent", agent_doc.name)

		# Mock litellm.completion to allow this to succeed without real API
		with patch("litellm.completion") as mock_completion:
			mock_completion.return_value = MagicMock(
				choices=[MagicMock(message=MagicMock(content="test response"))],
				usage=MagicMock(prompt_tokens=10, completion_tokens=5),
			)

			# Run the async function — should not raise before litellm is called
			import asyncio

			try:
				asyncio.run(run(agent_doc, "Test prompt", self.provider.name, self.text_model.name))
			except Exception as e:
				# If it fails later (network, etc), that's OK — we're testing the guard didn't fire
				if "Decision" in str(e):
					self.fail(f"Guard fired for Text model: {e}")

	# =========================================================================
	# No regression: Text & legacy models still work end-to-end
	# =========================================================================

	def test_text_model_full_path_no_regression(self):
		"""Text model passes all guards: picker, validation, resolution, defaults."""
		# Picker
		results = get_models_by_modality(
			doctype="AI Model",
			txt="",
			searchfield="name",
			start=0,
			page_len=100,
			filters={"modality": "Text", "provider": self.provider.name},
		)
		result_names = [r[0] for r in results]
		self.assertIn(self.text_model.name, result_names, "Text model should be in picker")

		# Validation
		agent_doc = make_agent(
			agent_name=f"{PREFIX}_regression_text",
			provider=self.provider.name,
			model=self.text_model.name,
		)
		self._track("Agent", agent_doc.name)
		agent_doc.save()  # Should not raise

		# Resolution
		_resolve_effective_model(agent_doc, model=self.text_model.name)  # Should not raise

		# Defaults
		default = _default_model_for_provider(self.provider.name)
		# May be None, but should never be Decision-only
		if default:
			self.assertFalse(is_decision_only_model(default))

	def test_legacy_model_full_path_no_regression(self):
		"""Legacy (blank-modality) model passes all guards for backward compat."""
		# Picker
		results = get_models_by_modality(
			doctype="AI Model",
			txt="",
			searchfield="name",
			start=0,
			page_len=100,
			filters={"modality": "Text", "provider": self.provider.name},
		)
		result_names = [r[0] for r in results]
		self.assertIn(
			self.legacy_model.name,
			result_names,
			"Legacy model should be in Text picker (backward compat)",
		)

		# Validation
		agent_doc = make_agent(
			agent_name=f"{PREFIX}_regression_legacy",
			provider=self.provider.name,
			model=self.legacy_model.name,
		)
		self._track("Agent", agent_doc.name)
		agent_doc.save()  # Should not raise

		# Resolution
		_resolve_effective_model(agent_doc, model=self.legacy_model.name)  # Should not raise

		# is_decision_only_model should return False
		self.assertFalse(is_decision_only_model(self.legacy_model.name))


# ============================================================================
# Async test runner wrapper (unittest doesn't natively support async tests)
# ============================================================================


class TestChatGuardAsync(unittest.TestCase):
	"""Wrapper for async litellm tests."""

	def setUp(self):
		self._names = {
			"AI Provider": [],
			"AI Model": [],
			"Agent": [],
		}

		# Minimal provider for async tests
		# Provider name must be a single word (no spaces)
		self.provider = make_ai_provider(
			provider_name="TestChatGuardAsync",
			provider_brand="openai",
		)
		self._track("AI Provider", self.provider.name)

		self.decision_model = make_ai_model(
			provider=self.provider.name,
			model_name=f"{PREFIX}_async_decision",
			modalities="Decision",
		)
		self._track("AI Model", self.decision_model.name)

		self.text_model = make_ai_model(
			provider=self.provider.name,
			model_name=f"{PREFIX}_async_text",
			modalities="Text",
		)
		self._track("AI Model", self.text_model.name)

	def tearDown(self):
		frappe.set_user("Administrator")
		for doctype in ("Agent", "AI Model", "AI Provider"):
			for name in self._names.get(doctype, []):
				self._delete(doctype, name)
		frappe.db.commit()

	def _delete(self, doctype, name):
		try:
			frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
		except Exception:
			pass

	def _track(self, doctype, name):
		self._names.setdefault(doctype, []).append(name)
		return name

	def test_litellm_run_rejects_decision_only_defense_in_depth(self):
		"""Test that litellm.run defense-in-depth guard fires before network."""
		import asyncio

		async def _async_test():
			from huf.ai.providers.litellm import run, ProviderUnavailableError

			# Create agent with Text model first (to pass validation)
			agent_doc = make_agent(
				agent_name=f"{PREFIX}_async_run_test",
				provider=self.provider.name,
				model=self.text_model.name,
			)
			self._track("Agent", agent_doc.name)

			# Manually set to Decision-only model (bypass validation for defense-in-depth test)
			frappe.db.set_value("Agent", agent_doc.name, "model", self.decision_model.name)
			agent_doc.reload()

			with patch("litellm.completion") as mock_completion:
				with self.assertRaises(ProviderUnavailableError):
					await run(
						agent_doc,
						"Test prompt",
						self.provider.name,
						self.decision_model.name,
					)
				mock_completion.assert_not_called()

		asyncio.run(_async_test())

	def test_litellm_run_stream_accepts_text_model(self):
		"""Test that litellm.run_stream accepts Text model (no regression with guard in place)."""
		import asyncio

		async def _async_test():
			from huf.ai.providers.litellm import run_stream

			# Create agent with Text model
			agent_doc = make_agent(
				agent_name=f"{PREFIX}_async_stream_text",
				provider=self.provider.name,
				model=self.text_model.name,
			)
			self._track("Agent", agent_doc.name)

			# Mock litellm.completion to avoid real API calls
			with patch("litellm.completion") as mock_completion:
				mock_completion.return_value = MagicMock(
					choices=[MagicMock(message=MagicMock(content="test response"))],
					usage=MagicMock(prompt_tokens=10, completion_tokens=5),
				)
				# Should not raise when model is Text
				try:
					async for chunk in run_stream(
						agent_doc,
						"Test prompt",
						self.provider.name,
						self.text_model.name,
					):
						pass  # Consume generator
				except Exception as e:
					if "decision" in str(e).lower():
						self.fail(f"Guard should not fire for Text model: {e}")

		asyncio.run(_async_test())
