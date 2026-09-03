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


class TestHandleGenerateImagePrivatization(IntegrationTestCase):
	"""Test ST-R3.1: generated images are saved with is_private=True and URLs are /private/files/..."""

	def _get_agent_router(self, agent=None):
		"""Return a frappe.get_doc side_effect router for Agent/Provider lookups."""
		if agent is None:
			agent = _FakeAgent()

		def _get_doc(doctype, *args, **kwargs):
			if doctype == "Agent":
				return agent
			if doctype == "AI Provider":
				return _provider_doc()
			raise frappe.DoesNotExistError

		return _get_doc

	async def test_save_file_called_with_is_private_true_for_agent_message(self):
		"""When saving an image to an Agent Message, is_private=True is passed to save_file."""
		agent = _FakeAgent()

		mock_saved_file = MagicMock()
		mock_saved_file.file_url = "/private/files/test.png"
		mock_saved_file.name = "test-file-id"

		with patch("frappe.get_doc", side_effect=self._get_agent_router(agent)):
			with patch("frappe.get_doc") as mock_get_doc:
				mock_get_doc.side_effect = self._get_agent_router(agent)
				with patch("huf.ai.handlers.media.save_file", return_value=mock_saved_file) as mock_save:
					with patch("asyncio.to_thread") as mock_thread:
						# Mock the image generation response
						mock_response = MagicMock()
						mock_response.data = [MagicMock(url="http://example.com/image.png")]
						mock_thread.return_value = mock_response

						with patch("huf.ai.handlers.media._http_request") as mock_http:
							mock_http.return_value = MagicMock(content=b"fake image bytes")

							with patch("frappe.has_permission", return_value=True):
								with patch.object(MagicMock, "insert"):
									result = await media.handle_generate_image(
										prompt="test image",
										agent_name="Test Agent",
										conversation_id="test-conv"
									)

		# Verify save_file was called with is_private=True
		calls = mock_save.call_args_list
		self.assertTrue(len(calls) > 0)
		# Check at least one call has is_private=True
		private_call_found = any(call.kwargs.get("is_private") is True for call in calls)
		self.assertTrue(private_call_found, "save_file should be called with is_private=True")

	async def test_fallback_image_url_is_private_files(self):
		"""When save_file returns no file_url, the fallback URL should be /private/files/...."""
		agent = _FakeAgent()

		# Mock save_file returning no file_url
		mock_saved_file = MagicMock()
		mock_saved_file.file_url = None
		mock_saved_file.file_name = "test.png"
		mock_saved_file.name = "test-file-id"

		with patch("frappe.get_doc", side_effect=self._get_agent_router(agent)):
			with patch("huf.ai.handlers.media.save_file", return_value=mock_saved_file) as mock_save:
				with patch("asyncio.to_thread") as mock_thread:
					mock_response = MagicMock()
					mock_response.data = [MagicMock(url="http://example.com/image.png")]
					mock_thread.return_value = mock_response

					with patch("huf.ai.handlers.media._http_request") as mock_http:
						mock_http.return_value = MagicMock(content=b"fake image bytes")

						with patch("frappe.has_permission", return_value=True):
							msg_doc = MagicMock()
							msg_doc.name = "test-msg"
							with patch("frappe.get_doc", return_value=msg_doc):
								with patch.object(msg_doc, "db_set"):
									result = await media.handle_generate_image(
										prompt="test image",
										agent_name="Test Agent",
										conversation_id="test-conv"
									)

		# Verify the fallback URL is /private/files/...
		self.assertTrue(result["success"])
		self.assertTrue(len(result["images"]) > 0)
		image_url = result["images"][0]["url"]
		self.assertTrue(image_url.startswith("/private/files/"), f"Expected /private/files/ URL, got {image_url}")


class TestHandleGenerateAudioPrivatization(IntegrationTestCase):
	"""Test ST-R3.1: generated audio is saved with is_private=True and URLs are /private/files/..."""

	def _get_agent_router(self, agent=None):
		"""Return a frappe.get_doc side_effect router for Agent/Provider lookups."""
		if agent is None:
			agent = _FakeAgent()

		def _get_doc(doctype, *args, **kwargs):
			if doctype == "Agent":
				return agent
			if doctype == "AI Provider":
				return _provider_doc()
			raise frappe.DoesNotExistError

		return _get_doc

	async def test_save_file_called_with_is_private_true_for_agent_message(self):
		"""When saving audio to an Agent Message, is_private=True is passed to save_file."""
		agent = _FakeAgent()

		mock_saved_file = MagicMock()
		mock_saved_file.file_url = "/private/files/test.mp3"
		mock_saved_file.name = "test-file-id"

		with patch("frappe.get_doc", side_effect=self._get_agent_router(agent)):
			with patch("huf.ai.handlers.media.save_file", return_value=mock_saved_file) as mock_save:
				with patch("asyncio.to_thread") as mock_thread:
					mock_response = MagicMock()
					mock_response.content = b"fake audio bytes"
					mock_thread.return_value = mock_response

					with patch("frappe.has_permission", return_value=True):
						with patch.object(MagicMock, "insert"):
							result = await media.handle_generate_audio(
								input="test audio",
								agent_name="Test Agent",
								conversation_id="test-conv"
							)

		# Verify save_file was called with is_private=True
		calls = mock_save.call_args_list
		self.assertTrue(len(calls) > 0)
		# Check at least one call has is_private=True
		private_call_found = any(call.kwargs.get("is_private") is True for call in calls)
		self.assertTrue(private_call_found, "save_file should be called with is_private=True")

	async def test_fallback_audio_url_is_private_files(self):
		"""When save_file returns no file_url, the fallback URL should be /private/files/...."""
		agent = _FakeAgent()

		# Mock save_file returning no file_url
		mock_saved_file = MagicMock()
		mock_saved_file.file_url = None
		mock_saved_file.file_name = "test.mp3"
		mock_saved_file.name = "test-file-id"

		with patch("frappe.get_doc", side_effect=self._get_agent_router(agent)):
			with patch("huf.ai.handlers.media.save_file", return_value=mock_saved_file) as mock_save:
				with patch("asyncio.to_thread") as mock_thread:
					mock_response = MagicMock()
					mock_response.content = b"fake audio bytes"
					mock_thread.return_value = mock_response

					with patch("frappe.has_permission", return_value=True):
						msg_doc = MagicMock()
						msg_doc.name = "test-msg"
						with patch("frappe.get_doc", return_value=msg_doc):
							with patch.object(msg_doc, "db_set"):
								result = await media.handle_generate_audio(
									input="test audio",
									agent_name="Test Agent",
									conversation_id="test-conv"
								)

		# Verify the fallback URL is /private/files/...
		self.assertTrue(result["success"])
		audio_url = result["audio"]["url"]
		self.assertTrue(audio_url.startswith("/private/files/"), f"Expected /private/files/ URL, got {audio_url}")


class TestPrivatizeGeneratedMediaFilesPatch(IntegrationTestCase):
	"""Test ST-R3.1b: privatize_generated_media_files patch flips is_private and rewrites URLs."""

	def test_patch_flips_is_private_and_rewrites_urls(self):
		"""The patch should flip is_private=1 on Files and rewrite /files/ to /private/files/ in Agent Messages."""
		from huf.patches.v1.privatize_generated_media_files import execute as run_patch

		# Create a mock File and Agent Message representing the old state
		mock_file = MagicMock()
		mock_file["name"] = "test-file"
		mock_file["file_name"] = "generated_image_1.png"
		mock_file["attached_to_name"] = "test-msg"
		mock_file["attached_to_field"] = "generated_image"

		mock_message = MagicMock()
		mock_message.generated_image = "/files/generated_image_1.png"

		with patch("frappe.db.get_list", return_value=[mock_file]):
			with patch("frappe.db.set_value") as mock_set_value:
				with patch("frappe.get_doc", return_value=mock_message):
					run_patch()

		# Verify set_value was called to flip is_private
		calls = mock_set_value.call_args_list
		is_private_set = any(
			call[0] == ("File", "test-file", "is_private", 1)
			for call in calls
		)
		self.assertTrue(is_private_set, "Patch should set is_private=1 on File")

		# Verify set_value was called to rewrite the URL
		url_set = any(
			call[0] == ("Agent Message", "test-msg", "generated_image", "/private/files/generated_image_1.png")
			for call in calls
		)
		self.assertTrue(url_set, "Patch should rewrite /files/ to /private/files/ in Agent Message")

	def test_patch_handles_generated_audio_urls(self):
		"""The patch should also handle generated_audio field URLs."""
		from huf.patches.v1.privatize_generated_media_files import execute as run_patch

		mock_file = MagicMock()
		mock_file["name"] = "test-audio-file"
		mock_file["file_name"] = "generated_audio_1.mp3"
		mock_file["attached_to_name"] = "test-msg-audio"
		mock_file["attached_to_field"] = "generated_audio"

		mock_message = MagicMock()
		mock_message.generated_audio = "/files/generated_audio_1.mp3"

		with patch("frappe.db.get_list", return_value=[mock_file]):
			with patch("frappe.db.set_value") as mock_set_value:
				with patch("frappe.get_doc", return_value=mock_message):
					run_patch()

		# Verify set_value was called to rewrite the audio URL
		calls = mock_set_value.call_args_list
		url_set = any(
			call[0] == ("Agent Message", "test-msg-audio", "generated_audio", "/private/files/generated_audio_1.mp3")
			for call in calls
		)
		self.assertTrue(url_set, "Patch should rewrite generated_audio URLs from /files/ to /private/files/")
