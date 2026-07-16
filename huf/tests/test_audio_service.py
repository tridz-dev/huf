# Copyright (c) 2026, Huf and Contributors
# See license.txt

"""
Unit tests for the canonical audio service (huf.ai.audio_service) and the
public audio API (huf.ai.audio_api).

These tests mock frappe (and LiteLLM) so the pure logic can be exercised
without a full Frappe bench and without hitting real providers:

    python -m unittest huf.tests.test_audio_service
"""

import base64
import sys
import tempfile
import types
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


class ThrowError(Exception):
    """Stand-in for frappe.throw so tests can assert on thrown messages."""


def _throw(msg, *args, **kwargs):
    raise ThrowError(str(msg))


# Mock frappe before importing the modules under test so pure logic can be
# exercised without a full Frappe bench.
frappe_mock = types.ModuleType("frappe")
frappe_mock._ = lambda x, *a, **k: x
frappe_mock.throw = MagicMock(side_effect=_throw)
frappe_mock.whitelist = MagicMock(return_value=lambda fn: fn)
frappe_mock.log_error = MagicMock()
frappe_mock.publish_realtime = MagicMock()
frappe_mock.get_doc = MagicMock()
frappe_mock.get_all = MagicMock()
frappe_mock.db = MagicMock()
frappe_mock.session = MagicMock()
frappe_mock.session.user = "Administrator"
frappe_mock.DoesNotExistError = type("DoesNotExistError", (Exception,), {})

frappe_utils = types.ModuleType("frappe.utils")
frappe_utils.cint = lambda v: 1 if v in (True, 1, "1", "true", "True", "yes") else 0
frappe_utils.now = MagicMock(return_value="2026-01-01 00:00:00")

frappe_file_manager = types.ModuleType("frappe.utils.file_manager")
frappe_file_manager.save_file = MagicMock()
frappe_utils.file_manager = frappe_file_manager
frappe_mock.utils = frappe_utils

sys.modules["frappe"] = frappe_mock
sys.modules["frappe.utils"] = frappe_utils
sys.modules["frappe.utils.file_manager"] = frappe_file_manager

# Mock litellm so no real provider is ever called.
litellm_mock = types.ModuleType("litellm")
litellm_mock.transcription = MagicMock()
litellm_mock.completion = MagicMock()
sys.modules["litellm"] = litellm_mock


def _normalize_model_name(model, provider):
    """Minimal stand-in for huf.ai.providers.litellm._normalize_model_name."""
    if "/" in model:
        return model
    prefix = (provider or "").lower()
    return f"{prefix}/{model}" if prefix else model


litellm_provider_stub = types.ModuleType("huf.ai.providers.litellm")
litellm_provider_stub._normalize_model_name = _normalize_model_name
sys.modules["huf.ai.providers.litellm"] = litellm_provider_stub

from huf.ai import audio_api, audio_service  # noqa: E402


def _b64(payload: bytes) -> str:
    return base64.b64encode(payload).decode("ascii")


def _provider_doc(name, api_key="sk-test"):
    doc = SimpleNamespace(name=name, provider_name=name)
    doc.get_password = lambda field: api_key
    return doc


def _agent_doc(name="Agent-1", provider="OpenAI", stt_model=None, model="gpt-4o"):
    return SimpleNamespace(
        name=name,
        provider=provider,
        stt_model=stt_model,
        model=model,
    )


def _install_docs(agent=None, providers=None, models=None, files=None):
    """Wire frappe.get_doc/get_all to serve the given fake documents."""
    agents = {d.name: d for d in ([agent] if agent else [])}
    providers = providers or {}
    models = models or {}
    files = files or {}

    def get_doc(doctype, name=None):
        if doctype == "Agent":
            return agents[name]
        if doctype == "AI Provider":
            return providers[name]
        if doctype == "AI Model":
            return models[name]
        if doctype == "File":
            if isinstance(name, dict):
                for f in files.values():
                    if all(getattr(f, k) == v for k, v in name.items()):
                        return f
                raise frappe_mock.DoesNotExistError("File not found")
            return files[name]
        raise ValueError(f"Unexpected get_doc: {doctype} {name}")

    frappe_mock.get_doc.side_effect = get_doc
    return agents


class TestSaveAudioUpload(unittest.TestCase):
    def setUp(self):
        frappe_file_manager.save_file.reset_mock()
        frappe_file_manager.save_file.side_effect = None
        frappe_file_manager.save_file.return_value = SimpleNamespace(
            name="FILE-0001",
            file_name="clip.webm",
            file_url="/private/files/clip.webm",
        )

    def test_rejects_unsupported_extension(self):
        with self.assertRaises(ThrowError) as ctx:
            audio_service.save_audio_upload("notes.txt", _b64(b"audio"))
        self.assertIn("Unsupported audio file type", str(ctx.exception))
        frappe_file_manager.save_file.assert_not_called()

    def test_rejects_oversized_file(self):
        payload = b"x" * (audio_service.MAX_AUDIO_FILE_SIZE + 1)
        with self.assertRaises(ThrowError) as ctx:
            audio_service.save_audio_upload("big.webm", _b64(payload))
        self.assertIn("maximum allowed size", str(ctx.exception))
        frappe_file_manager.save_file.assert_not_called()

    def test_rejects_invalid_base64(self):
        with self.assertRaises(ThrowError) as ctx:
            audio_service.save_audio_upload("clip.webm", "!!!not-base64!!!")
        self.assertIn("Invalid base64 audio data", str(ctx.exception))
        frappe_file_manager.save_file.assert_not_called()

    def test_rejects_empty_audio(self):
        with self.assertRaises(ThrowError) as ctx:
            audio_service.save_audio_upload("clip.webm", "data:audio/webm;base64,")
        self.assertIn("empty", str(ctx.exception))
        frappe_file_manager.save_file.assert_not_called()

    def test_rejects_missing_filename_or_data(self):
        with self.assertRaises(ThrowError) as ctx:
            audio_service.save_audio_upload("", _b64(b"audio"))
        self.assertIn("Filename and audio data are required", str(ctx.exception))
        with self.assertRaises(ThrowError):
            audio_service.save_audio_upload("clip.webm", "")

    def test_saves_valid_upload(self):
        result = audio_service.save_audio_upload(
            "clip.webm",
            _b64(b"audio-bytes"),
            attached_to_doctype="Agent Message",
            attached_to_name="MSG-1",
        )
        self.assertEqual(result["file_id"], "FILE-0001")
        self.assertEqual(result["file_url"], "/private/files/clip.webm")
        self.assertEqual(result["file_name"], "clip.webm")
        args, kwargs = frappe_file_manager.save_file.call_args
        self.assertEqual(args[0], "clip.webm")
        self.assertEqual(args[1], b"audio-bytes")
        self.assertEqual(args[2], "Agent Message")
        self.assertEqual(args[3], "MSG-1")
        self.assertEqual(kwargs["is_private"], 1)

    def test_strips_data_url_prefix(self):
        result = audio_service.save_audio_upload(
            "clip.webm", "data:audio/webm;base64," + _b64(b"audio-bytes")
        )
        self.assertEqual(result["file_id"], "FILE-0001")
        args, _ = frappe_file_manager.save_file.call_args
        self.assertEqual(args[1], b"audio-bytes")

    def test_accepts_allowed_audio_extensions(self):
        for ext in ("webm", "wav", "mp3", "m4a", "ogg", "flac", "mp4", "aac"):
            with self.subTest(ext=ext):
                result = audio_service.save_audio_upload(f"clip.{ext}", _b64(b"audio"))
                self.assertEqual(result["file_id"], "FILE-0001")


class TestResolveSttConfig(unittest.TestCase):
    def setUp(self):
        frappe_mock.get_all.reset_mock()
        frappe_mock.get_all.side_effect = None
        frappe_mock.get_all.return_value = []

    def test_explicit_model_wins(self):
        _install_docs(
            agent=_agent_doc(),
            providers={"OpenAI": _provider_doc("OpenAI"), "Groq": _provider_doc("Groq")},
        )
        frappe_mock.get_all.side_effect = lambda doctype, **kw: (
            [SimpleNamespace(provider="Groq")] if doctype == "AI Model" else []
        )

        config = audio_service.resolve_stt_config("Agent-1", model="whisper-large-v3")

        self.assertEqual(config["source"], "tool_param")
        self.assertEqual(config["provider_name"], "groq")
        self.assertEqual(config["stt_model"], "groq/whisper-large-v3")
        self.assertEqual(config["api_key"], "sk-test")

    def test_agent_stt_model_second_priority(self):
        _install_docs(
            agent=_agent_doc(stt_model="Whisper Large"),
            providers={"OpenAI": _provider_doc("OpenAI"), "Groq": _provider_doc("Groq")},
            models={
                "Whisper Large": SimpleNamespace(
                    name="Whisper Large", model_name="whisper-large-v3", provider="Groq"
                )
            },
        )

        config = audio_service.resolve_stt_config("Agent-1")

        self.assertEqual(config["source"], "agent_config")
        self.assertEqual(config["provider_name"], "groq")
        self.assertEqual(config["stt_model"], "groq/whisper-large-v3")

    def test_provider_default_prefers_transcription_modality(self):
        _install_docs(
            agent=_agent_doc(),
            providers={"OpenAI": _provider_doc("OpenAI")},
        )

        def get_all(doctype, filters=None, **kw):
            if doctype == "AI Model" and filters and "modalities" in filters:
                return [SimpleNamespace(model_name="whisper-1")]
            return []

        frappe_mock.get_all.side_effect = get_all

        config = audio_service.resolve_stt_config("Agent-1")

        self.assertEqual(config["source"], "provider_default")
        self.assertEqual(config["provider_name"], "openai")
        self.assertEqual(config["stt_model"], "openai/whisper-1")

    def test_provider_default_falls_back_to_map(self):
        _install_docs(
            agent=_agent_doc(provider="Groq"),
            providers={"Groq": _provider_doc("Groq")},
        )
        frappe_mock.get_all.return_value = []

        config = audio_service.resolve_stt_config("Agent-1")

        self.assertEqual(config["source"], "provider_default")
        self.assertEqual(config["provider_name"], "groq")
        self.assertEqual(config["stt_model"], "groq/whisper-large-v3")

    def test_missing_api_key_raises(self):
        _install_docs(
            agent=_agent_doc(),
            providers={"OpenAI": _provider_doc("OpenAI", api_key="")},
        )

        with self.assertRaises(ValueError) as ctx:
            audio_service.resolve_stt_config("Agent-1")
        self.assertIn("API key is not configured", str(ctx.exception))


class TestTranscribeAudioFile(unittest.TestCase):
    def setUp(self):
        litellm_mock.transcription.reset_mock()
        litellm_mock.completion.reset_mock()
        litellm_mock.transcription.return_value = SimpleNamespace(text="hello world")
        frappe_mock.publish_realtime.reset_mock()
        frappe_mock.get_all.reset_mock()
        frappe_mock.get_all.side_effect = None
        frappe_mock.get_all.return_value = []

        self.tmp = tempfile.NamedTemporaryFile(suffix=".webm", delete=False)
        self.tmp.write(b"fake audio bytes")
        self.tmp.close()

        self.file_doc = SimpleNamespace(
            name="FILE-0001",
            file_name="clip.webm",
            file_url="/private/files/clip.webm",
            attached_to_name=None,
            get_full_path=lambda: self.tmp.name,
        )
        _install_docs(
            agent=_agent_doc(),
            providers={"OpenAI": _provider_doc("OpenAI")},
            files={"FILE-0001": self.file_doc},
        )

    def test_success_returns_transcript_without_side_effects(self):
        result = audio_service.transcribe_audio_file(
            file_id="FILE-0001", agent_name="Agent-1"
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["transcript"], "hello world")
        self.assertEqual(result["text"], "hello world")
        self.assertEqual(result["file_id"], "FILE-0001")
        self.assertEqual(result["file_url"], "/private/files/clip.webm")
        self.assertEqual(result["stt_model"], "openai/whisper-1")
        self.assertEqual(result["provider"], "openai")
        self.assertEqual(result["language"], "auto-detected")

        # Pure transcription: no Agent Message creation, no socket events.
        frappe_mock.publish_realtime.assert_not_called()
        for call in frappe_mock.get_doc.call_args_list:
            self.assertNotEqual(call.args[0], "Agent Message")

    def test_language_is_forwarded(self):
        result = audio_service.transcribe_audio_file(
            file_id="FILE-0001", agent_name="Agent-1", language="en"
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["language"], "en")
        _, kwargs = litellm_mock.transcription.call_args
        self.assertEqual(kwargs["language"], "en")

    def test_requires_agent_name(self):
        result = audio_service.transcribe_audio_file(file_id="FILE-0001")
        self.assertFalse(result["success"])
        self.assertIn("Agent name", result["error"])

    def test_requires_file(self):
        result = audio_service.transcribe_audio_file(agent_name="Agent-1")
        self.assertFalse(result["success"])
        self.assertIn("Either file_id or file_url is required", result["error"])

    def test_missing_file_returns_error(self):
        result = audio_service.transcribe_audio_file(
            file_id="NOPE", agent_name="Agent-1"
        )
        self.assertFalse(result["success"])
        self.assertIn("File not found", result["error"])

    def test_provider_failure_returns_error(self):
        litellm_mock.transcription.side_effect = Exception("boom")
        result = audio_service.transcribe_audio_file(
            file_id="FILE-0001", agent_name="Agent-1"
        )
        self.assertFalse(result["success"])
        self.assertIn("Transcription failed", result["error"])
        litellm_mock.transcription.side_effect = None


class TestAudioApiValidation(unittest.TestCase):
    def test_agent_required(self):
        with self.assertRaises(ThrowError) as ctx:
            audio_api.transcribe(file_id="FILE-0001")
        self.assertIn("agent is required", str(ctx.exception))

    def test_both_inputs_rejected(self):
        with self.assertRaises(ThrowError) as ctx:
            audio_api.transcribe(
                file_id="FILE-0001",
                b64data=_b64(b"audio"),
                filename="clip.webm",
                agent="Agent-1",
            )
        self.assertIn("not both", str(ctx.exception))

    def test_no_input_rejected(self):
        with self.assertRaises(ThrowError) as ctx:
            audio_api.transcribe(agent="Agent-1")
        self.assertIn("Provide either file_id or b64data", str(ctx.exception))

    def test_create_message_requires_conversation(self):
        with self.assertRaises(ThrowError) as ctx:
            audio_api.transcribe(
                file_id="FILE-0001", agent="Agent-1", create_message=True
            )
        self.assertIn("conversation is required", str(ctx.exception))

    def test_upload_success_shape(self):
        with patch.object(
            audio_service,
            "save_audio_upload",
            return_value={
                "file_id": "FILE-0001",
                "file_url": "/private/files/clip.webm",
                "file_name": "clip.webm",
            },
        ) as save_mock, patch.object(
            audio_service,
            "transcribe_audio_file",
            return_value={
                "success": True,
                "transcript": "hello",
                "text": "hello",
                "file_id": "FILE-0001",
                "file_url": "/private/files/clip.webm",
                "stt_model": "openai/whisper-1",
                "provider": "openai",
                "language": "auto-detected",
                "stt_source": "provider_default",
            },
        ) as transcribe_mock, patch.object(
            audio_service, "create_audio_user_message"
        ) as message_mock:
            result = audio_api.transcribe(
                b64data=_b64(b"audio"),
                filename="clip.webm",
                agent="Agent-1",
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["transcript"], "hello")
        self.assertEqual(result["file_id"], "FILE-0001")
        self.assertEqual(result["file_url"], "/private/files/clip.webm")
        self.assertIsNone(result["message_id"])
        self.assertEqual(result["stt_model"], "openai/whisper-1")
        self.assertEqual(result["provider"], "openai")
        self.assertEqual(result["language"], "auto-detected")
        save_mock.assert_called_once()
        transcribe_mock.assert_called_once()
        message_mock.assert_not_called()

    def test_create_message_uses_service(self):
        with patch.object(
            audio_service,
            "transcribe_audio_file",
            return_value={
                "success": True,
                "transcript": "hello",
                "text": "hello",
                "file_id": "FILE-0001",
                "file_url": "/private/files/clip.webm",
                "stt_model": "openai/whisper-1",
                "provider": "openai",
                "language": "auto-detected",
                "stt_source": "provider_default",
            },
        ), patch.object(
            audio_service,
            "create_audio_user_message",
            return_value=SimpleNamespace(name="MSG-0001"),
        ) as message_mock:
            result = audio_api.transcribe(
                file_id="FILE-0001",
                agent="Agent-1",
                conversation="CONV-0001",
                create_message=True,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["message_id"], "MSG-0001")
        message_mock.assert_called_once()
        args, kwargs = message_mock.call_args
        self.assertEqual(args[0], "CONV-0001")
        self.assertEqual(args[1], "FILE-0001")
        self.assertEqual(args[2], "hello")


if __name__ == "__main__":
    unittest.main()
