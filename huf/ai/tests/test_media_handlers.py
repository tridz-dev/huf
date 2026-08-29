# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""
Tests for huf.ai.handlers.media — media generation/transcription handlers.

Covers:
- handle_generate_video: fails closed (returns success=False with a clear
  error) when no Video-modality AI Model is configured. This tool's actual
  provider generation call is intentionally unimplemented (see the
  NotImplementedError + docstring in huf/ai/handlers/media.py and
  docs/hub-orchestrator-unified-builder-plan.md Phase 10), so no test here
  asserts a successful video generation — that would be testing a lie.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.tests.test_media_handlers
"""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase


class _LazyModule:
	"""Defer heavy app imports until first use (see test_builder_tools.py)."""

	def __init__(self, module_path):
		self._module_path = module_path

	def __getattr__(self, name):
		import importlib

		return getattr(importlib.import_module(self._module_path), name)


media = _LazyModule("huf.ai.handlers.media")


class _FakeAgent:
	"""Minimal stand-in for an Agent document."""

	def __init__(self, **kwargs):
		self.agent_name = kwargs.pop("agent_name", "Test Agent")
		self.name = self.agent_name
		self.provider = kwargs.pop("provider", "Test Provider")
		self.model = kwargs.pop("model", "test-model")

	def get(self, field, default=None):
		return self.__dict__.get(field, default)


class _FakeAiModel:
	"""Minimal stand-in for an AI Model document."""

	def __init__(self, model_name="veo-test", modalities=""):
		self.model_name = model_name
		self._modalities = modalities

	def get(self, field, default=None):
		if field == "modalities":
			return self._modalities
		return getattr(self, field, default)


def _provider_doc(api_key="sk-test"):
	doc = MagicMock()
	doc.get_password.return_value = api_key
	doc.provider_name = "openai"
	return doc


class TestHandleGenerateVideo(IntegrationTestCase):
	"""handle_generate_video must fail closed until a provider is wired up."""

	def _get_doc_router(self, agent, ai_model=None):
		def _get_doc(first, *args, **kwargs):
			if first == "Agent":
				return agent
			if first == "AI Provider":
				return _provider_doc()
			if first == "AI Model":
				if ai_model is None:
					raise frappe.DoesNotExistError
				return ai_model
			return MagicMock()

		return _get_doc

	async def test_no_agent_name_returns_error(self):
		result = await media.handle_generate_video(prompt="a cat playing piano")
		self.assertFalse(result["success"])
		self.assertIn("Agent name", result["error"])

	async def test_no_video_model_configured_returns_clear_error(self):
		agent = _FakeAgent()

		with patch("frappe.get_doc", side_effect=self._get_doc_router(agent, ai_model=None)):
			result = await media.handle_generate_video(
				prompt="a cat playing piano",
				agent_name="Test Agent",
			)

		self.assertFalse(result["success"])
		self.assertIn("Video generation requires a configured AI Model", result["error"])

	async def test_video_model_without_video_modality_is_rejected(self):
		agent = _FakeAgent()
		non_video_model = _FakeAiModel(model_name="dall-e-3", modalities="Image")

		with patch(
			"frappe.get_doc",
			side_effect=self._get_doc_router(agent, ai_model=non_video_model),
		):
			result = await media.handle_generate_video(
				prompt="a cat playing piano",
				agent_name="Test Agent",
				model="dall-e-3",
			)

		self.assertFalse(result["success"])
		self.assertIn("Video generation requires a configured AI Model", result["error"])

	async def test_video_modality_model_resolves_but_generation_is_unimplemented(self):
		"""Even with a valid Video-modality AI Model configured, the actual
		provider call is intentionally unimplemented (see NotImplementedError
		in handle_generate_video). This asserts the honest failure mode, NOT
		a successful generation.
		"""
		agent = _FakeAgent()
		video_model = _FakeAiModel(model_name="veo-3", modalities="Video")

		with patch(
			"frappe.get_doc",
			side_effect=self._get_doc_router(agent, ai_model=video_model),
		):
			result = await media.handle_generate_video(
				prompt="a cat playing piano",
				agent_name="Test Agent",
				model="veo-3",
			)

		self.assertFalse(result["success"])
		self.assertIn("not yet", result["error"])
