# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""
MM-F: image generation and TTS must use the *model's own* AI Provider
(API key + LiteLLM name normalisation), not the agent's chat provider.

No network: litellm is mocked.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.tests.test_media_model_provider
"""

import asyncio
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase


class _LazyModule:
	def __init__(self, module_path):
		self._module_path = module_path

	def __getattr__(self, name):
		import importlib

		return getattr(importlib.import_module(self._module_path), name)


media = _LazyModule("huf.ai.handlers.media")


class _Doc:
	def __init__(self, **kw):
		self.__dict__.update(kw)

	def get(self, field, default=None):
		return self.__dict__.get(field, default)


def _provider(name, key):
	doc = MagicMock()
	doc.provider_name = name
	doc.get_password.return_value = key
	return doc


def _router(agent, models=None, providers=None):
	models = models or {}
	providers = providers or {}

	def _get_doc(doctype, name=None, *a, **k):
		if doctype == "Agent":
			return agent
		if doctype == "AI Model":
			return models[name]
		if doctype == "AI Provider":
			return providers[name]
		return MagicMock()

	return _get_doc


def _agent(**kw):
	base = dict(
		name="WA Agent",
		agent_name="WA Agent",
		provider="Anthropic",
		image_generation_model=None,
		tts_model=None,
		tts_voice=None,
	)
	base.update(kw)
	return _Doc(**base)


PROVIDERS = {
	"Anthropic": _provider("Anthropic", "key-anthropic"),
	"Google": _provider("Google", "key-google"),
	"OpenAI": _provider("OpenAI", "key-openai"),
}


class TestImageModelProvider(IntegrationTestCase):
	def _call(self, agent, models, providers=None):
		fake = MagicMock()
		with (
			patch("frappe.get_doc", side_effect=_router(agent, models, providers or PROVIDERS)),
			patch("huf.ai.agent.access.assert_agent_access"),
			patch("litellm.image_generation", return_value=MagicMock(data=[])) as image_generation,
		):
			fake.image_generation = image_generation
			result = asyncio.run(media.handle_generate_image(prompt="a cat", agent_name="WA Agent"))
		return fake, result

	def test_cross_provider_image_model_uses_its_provider_key(self):
		agent = _agent(image_generation_model="gemini-img")
		models = {"gemini-img": _Doc(model_name="gemini-2.5-flash-image", provider="Google")}
		fake, _ = self._call(agent, models)
		kwargs = fake.image_generation.call_args.kwargs
		self.assertEqual(kwargs["api_key"], "key-google")
		self.assertTrue(kwargs["model"].startswith("gemini/"), kwargs["model"])

	def test_fallback_to_agent_provider_when_unset(self):
		agent = _agent(provider="OpenAI")
		fake, _ = self._call(agent, {})
		kwargs = fake.image_generation.call_args.kwargs
		self.assertEqual(kwargs["api_key"], "key-openai")

	def test_missing_key_on_image_model_provider_names_provider(self):
		providers = dict(PROVIDERS, Google=_provider("Google", None))
		agent = _agent(image_generation_model="gemini-img")
		models = {"gemini-img": _Doc(model_name="gemini-2.5-flash-image", provider="Google")}
		fake, result = self._call(agent, models, providers)
		self.assertFalse(result["success"])
		self.assertIn("Google", result["error"])
		self.assertIn("API key", result["error"])
		fake.image_generation.assert_not_called()


class TestTtsModelProvider(IntegrationTestCase):
	def _resolve(self, agent, models, providers=None):
		with patch("frappe.get_doc", side_effect=_router(agent, models, providers or PROVIDERS)):
			return media._resolve_tts_config(agent)

	def test_cross_provider_tts_model_uses_its_provider_key(self):
		agent = _agent(tts_model="oa-tts")
		models = {"oa-tts": _Doc(model_name="tts-1", provider="OpenAI")}
		cfg = self._resolve(agent, models)
		self.assertEqual(cfg["api_key"], "key-openai")
		self.assertEqual(cfg["provider_name"], "openai")
		self.assertEqual(cfg["source"], "agent_config")

	def test_fallback_to_agent_provider_when_unset(self):
		agent = _agent(provider="OpenAI")
		cfg = self._resolve(agent, {})
		self.assertEqual(cfg["api_key"], "key-openai")
		self.assertEqual(cfg["source"], "provider_default")

	def test_missing_key_on_tts_provider_names_provider(self):
		providers = dict(PROVIDERS, OpenAI=_provider("OpenAI", None))
		agent = _agent(tts_model="oa-tts")
		models = {"oa-tts": _Doc(model_name="tts-1", provider="OpenAI")}
		with self.assertRaises(ValueError) as cm:
			self._resolve(agent, models, providers)
		self.assertIn("OpenAI", str(cm.exception))


def _fake_speech_response():
	resp = MagicMock()
	resp.content = b"RIFFxxxxWAVEdata"
	return resp


def _fake_completion_audio():
	import base64

	msg = MagicMock()
	msg.audio.data = base64.b64encode(b"\x01\x00" * 100).decode()
	choice = MagicMock()
	choice.message = msg
	return MagicMock(choices=[choice])


class TestGenerateAudioHandlerProvider(IntegrationTestCase):
	"""handle_generate_audio must send the TTS model's own provider key to LiteLLM."""

	def _run(self, agent, models, providers=None, **kw):
		saved = MagicMock(file_url="/private/files/a.wav", name="FILE-1")
		with (
			patch("frappe.get_doc", side_effect=_router(agent, models, providers or PROVIDERS)),
			patch("huf.ai.agent.access.assert_agent_access"),
			patch("litellm.speech", return_value=_fake_speech_response()) as speech,
			patch("litellm.completion", return_value=_fake_completion_audio()) as completion,
			patch("huf.ai.handlers.media.save_file", return_value=saved) as save,
		):
			result = asyncio.run(media.handle_generate_audio(input="Hello", agent_name="WA Agent", **kw))
		return result, speech, completion, save

	def test_google_tts_on_anthropic_agent_uses_google_key(self):
		agent = _agent(tts_model="gem-tts")
		models = {"gem-tts": _Doc(model_name="gemini-3.1-flash-tts-preview", provider="Google")}
		result, speech, completion, save = self._run(agent, models)
		self.assertTrue(result.get("success"), result)
		# gemini TTS goes through completion(modalities=audio) so api_key is honoured
		speech.assert_not_called()
		self.assertEqual(completion.call_count, 1)
		kwargs = completion.call_args.kwargs
		self.assertEqual(kwargs["api_key"], "key-google")
		self.assertTrue(kwargs["model"].startswith("gemini/"), kwargs["model"])
		self.assertEqual(kwargs["modalities"], ["audio"])
		fname, data = save.call_args.args[0], save.call_args.args[1]
		self.assertTrue(fname.endswith(".wav"), fname)
		self.assertTrue(data.startswith(b"RIFF"))
		self.assertEqual(result["audio"]["format"], "wav")

	def test_tool_param_model_uses_that_models_provider_key(self):
		agent = _agent()
		models = {"gem-tts": _Doc(model_name="gemini-3.1-flash-tts-preview", provider="Google")}
		result, _speech, completion, _ = self._run(agent, models, model="gem-tts")
		self.assertTrue(result.get("success"), result)
		self.assertEqual(completion.call_args.kwargs["api_key"], "key-google")

	def test_openai_tts_on_anthropic_agent_uses_openai_key_via_speech(self):
		agent = _agent(tts_model="oa-tts")
		models = {"oa-tts": _Doc(model_name="tts-1", provider="OpenAI")}
		result, speech, completion, _ = self._run(agent, models)
		self.assertTrue(result.get("success"), result)
		completion.assert_not_called()
		self.assertEqual(speech.call_args.kwargs["api_key"], "key-openai")

	def test_tool_param_missing_key_names_model_provider(self):
		providers = dict(PROVIDERS, Google=_provider("Google", None))
		models = {"gem-tts": _Doc(model_name="gemini-3.1-flash-tts-preview", provider="Google")}
		result, speech, completion, _ = self._run(_agent(), models, providers, model="gem-tts")
		self.assertFalse(result["success"])
		self.assertIn("Google", result["error"])
		speech.assert_not_called()
		completion.assert_not_called()

	def test_tool_param_cross_provider_resolve(self):
		models = {"gem-tts": _Doc(model_name="gemini-3.1-flash-tts-preview", provider="Google")}
		with patch("frappe.get_doc", side_effect=_router(_agent(), models, PROVIDERS)):
			cfg = media._resolve_tts_config(_agent(), tool_model="gem-tts")
		self.assertEqual(cfg["api_key"], "key-google")
		self.assertEqual(cfg["provider_name"], "google")
		self.assertEqual(cfg["tts_model"], "gemini/gemini-3.1-flash-tts-preview")

	def test_tool_param_unknown_model_falls_back_to_agent_provider(self):
		agent = _agent(provider="OpenAI")
		with patch("frappe.get_doc", side_effect=_router(agent, {}, PROVIDERS)):
			cfg = media._resolve_tts_config(agent, tool_model="tts-1")
		self.assertEqual(cfg["api_key"], "key-openai")
		self.assertEqual(cfg["source"], "tool_param")


class TestVideoModelProvider(IntegrationTestCase):
	def _call(self, models, providers=None):
		agent = _agent()
		with (
			patch("frappe.get_doc", side_effect=_router(agent, models, providers or PROVIDERS)),
			patch("huf.ai.agent.access.assert_agent_access"),
			patch("frappe.log_error"),
		):
			return asyncio.run(media.handle_generate_video(prompt="x", agent_name="WA Agent", model="veo"))

	def test_missing_key_names_video_model_provider_not_agent_provider(self):
		providers = dict(PROVIDERS, Google=_provider("Google", None))
		models = {"veo": _Doc(model_name="veo-3", provider="Google", modalities="Video")}
		result = self._call(models, providers)
		self.assertFalse(result["success"])
		self.assertIn("Google", result["error"])
		self.assertNotIn("Anthropic", result["error"])

	def test_agent_provider_key_missing_does_not_block_other_provider_video_model(self):
		providers = dict(PROVIDERS, Anthropic=_provider("Anthropic", None))
		models = {"veo": _Doc(model_name="veo-3", provider="Google", modalities="Video")}
		result = self._call(models, providers)
		self.assertFalse(result["success"])
		self.assertNotIn("API key", result["error"])
		self.assertIn("not yet implemented", result["error"])


class TestOcrModelProvider(IntegrationTestCase):
	def _run(self, agent, models, providers=None, model=None):
		import os
		import tempfile

		from huf.ai import ocr_engine

		with tempfile.TemporaryDirectory() as tmp:
			path = os.path.join(tmp, "a.png")
			with open(path, "wb") as fh:
				fh.write(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
			file_doc = MagicMock()
			file_doc.name = "F1"
			file_doc.file_name = "a.png"
			file_doc.file_type = "PNG"
			file_doc.is_private = 0
			file_doc.get_full_path.return_value = path
			file_doc.has_permission.return_value = True
			seen = {}

			async def _vision(file_path, model_name, api_key, mime, name):
				seen.update(model=model_name, api_key=api_key)
				return ocr_engine.ExtractionResult(success=True, text="ok", strategy="vision", model=model_name)

			with (
				patch("frappe.get_doc", side_effect=_router(agent, models, providers or PROVIDERS)),
				patch("frappe.utils.get_files_path", return_value=tmp),
				patch.object(ocr_engine, "_resolve_file_doc", return_value=file_doc),
				patch.object(ocr_engine, "_process_with_vision_model", side_effect=_vision),
			):
				result = asyncio.run(
					ocr_engine.extract_document(agent, file_id="F1", model=model, create_message=False)
				)
		return result, seen

	def test_cross_provider_ocr_model_uses_its_provider_key(self):
		models = {"gem-vision": _Doc(model_name="gemini-2.5-flash", provider="Google")}
		result, seen = self._run(_agent(), models, model="gem-vision")
		self.assertTrue(result.success, getattr(result, "error", None))
		self.assertEqual(seen["api_key"], "key-google")
		self.assertTrue(seen["model"].startswith("gemini/"), seen["model"])

	def test_fallback_to_agent_provider_when_no_model(self):
		result, seen = self._run(_agent(provider="OpenAI"), {})
		self.assertTrue(result.success, getattr(result, "error", None))
		self.assertEqual(seen["api_key"], "key-openai")

	def test_missing_key_names_ocr_model_provider(self):
		providers = dict(PROVIDERS, Google=_provider("Google", None))
		models = {"gem-vision": _Doc(model_name="gemini-2.5-flash", provider="Google")}
		result, seen = self._run(_agent(), models, providers, model="gem-vision")
		self.assertFalse(result.success)
		self.assertIn("Google", result.error)
		self.assertEqual(seen, {})


class TestGeminiVoice(IntegrationTestCase):
	def test_openai_style_voice_maps_to_valid_gemini_voice(self):
		self.assertEqual(media._gemini_voice("alloy"), "Kore")
		self.assertEqual(media._gemini_voice(None), "Kore")
		self.assertEqual(media._gemini_voice("puck"), "Puck")

	def test_completion_requests_pcm16_and_honours_key(self):
		with patch("litellm.completion", return_value=_fake_completion_audio()) as completion:
			wav = media._gemini_tts_completion("gemini/x-tts", "hi", "alloy", "k")
		kw = completion.call_args.kwargs
		self.assertEqual(kw["audio"], {"voice": "Kore", "format": "pcm16"})
		self.assertEqual(kw["api_key"], "k")
		self.assertTrue(wav.startswith(b"RIFF"))
