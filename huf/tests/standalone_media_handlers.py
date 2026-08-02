# Copyright (c) 2026, Huf and Contributors
# See license.txt

"""
Unit tests for media tools and handlers (huf/ai/handlers/media.py).

Tests handle_generate_image (including SSRF URL blocking and network failure),
handle_ocr_document, handle_generate_audio, and handle_transcribe_audio.
"""

import asyncio
import os
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

# Re-use standalone audio service mocks setup
path = os.path.abspath(os.path.join(os.path.dirname(__file__), "standalone_audio_service.py"))
import importlib.util
spec = importlib.util.spec_from_file_location("standalone_audio_service", path)
_audio_mocks = importlib.util.module_from_spec(spec)
sys.modules["standalone_audio_service"] = _audio_mocks
spec.loader.exec_module(_audio_mocks)

frappe_mock = _audio_mocks.frappe_mock
frappe_mock.whitelist = lambda *a, **k: (lambda f: f)
frappe_mock.has_permission = MagicMock(return_value=True)
frappe_mock.ValidationError = type("ValidationError", (Exception,), {})
frappe_mock.DoesNotExistError = type("DoesNotExistError", (Exception,), {})
frappe_mock.local = SimpleNamespace(site="site1.local", flags=SimpleNamespace())

# Mock litellm module
litellm_mock = sys.modules.get("litellm") or types.ModuleType("litellm")
sys.modules["litellm"] = litellm_mock

# Mock huf.ai.ocr_engine
ocr_engine_stub = types.ModuleType("huf.ai.ocr_engine")
extract_document_mock = AsyncMock()
ocr_engine_stub.extract_document = extract_document_mock
sys.modules["huf.ai.ocr_engine"] = ocr_engine_stub

# Mock huf.ai.http_handler
http_handler_stub = types.ModuleType("huf.ai.http_handler")
http_request_mock = MagicMock()
http_handler_stub._http_request = http_request_mock
sys.modules["huf.ai.http_handler"] = http_handler_stub

# Import handler after mocking
from huf.ai.handlers import media  # noqa: E402
from huf.ai import audio_service  # noqa: E402

RequestException = media.RequestException


def _agent_doc(provider="OpenAI"):
    doc = SimpleNamespace(
        name="Agent-1",
        provider=provider,
        model="gpt-4o",
        image_generation_model=None,
        tts_model=None,
        tts_voice=None,
    )
    return doc


def _provider_doc():
    doc = SimpleNamespace(provider_name="OpenAI")
    doc.get_password = MagicMock(return_value="sk-test-key")
    return doc


def _install_docs():
    def get_doc(doctype, name=None):
        if isinstance(doctype, dict):
            m = SimpleNamespace(name="MSG-0001", content="", conversation_index=1, insert=MagicMock(), db_set=MagicMock())
            return m
        if doctype == "Agent":
            return _agent_doc()
        if doctype == "AI Provider":
            return _provider_doc()
        raise ValueError(f"Unexpected get_doc: {doctype} {name}")

    frappe_mock.get_doc.side_effect = get_doc


class TestMediaHandlersImageSSRF(unittest.TestCase):
    def setUp(self):
        frappe_mock.get_doc.reset_mock()
        frappe_mock.get_doc.side_effect = None
        frappe_mock.db.reset_mock()
        frappe_mock.db.sql.return_value = [SimpleNamespace(last_index=0)]
        http_request_mock.reset_mock()
        litellm_mock.image_generation = MagicMock()

    def test_generate_image_ssrf_url_blocked_handled_gracefully(self):
        _install_docs()
        litellm_mock.image_generation.return_value = SimpleNamespace(
            data=[SimpleNamespace(url="http://169.254.169.254/latest/meta-data")]
        )
        http_request_mock.side_effect = ValueError("Requests to private/internal addresses are not allowed")

        res = asyncio.run(media.handle_generate_image(
            prompt="test image",
            agent_name="Agent-1",
            conversation_id="CONV-1"
        ))

        self.assertFalse(res["success"])
        self.assertIn("no images were returned", res["error"])
        http_request_mock.assert_called_once_with("GET", "http://169.254.169.254/latest/meta-data", timeout=30)

    def test_generate_image_network_exception_handled_gracefully(self):
        _install_docs()
        litellm_mock.image_generation.return_value = SimpleNamespace(
            data=[SimpleNamespace(url="https://cdn.example.com/generated.png")]
        )
        http_request_mock.side_effect = RequestException("Connection reset")

        res = asyncio.run(media.handle_generate_image(
            prompt="test image",
            agent_name="Agent-1",
            conversation_id="CONV-1"
        ))

        self.assertFalse(res["success"])
        self.assertIn("no images were returned", res["error"])
        http_request_mock.assert_called_once_with("GET", "https://cdn.example.com/generated.png", timeout=30)

    def test_generate_image_b64_success(self):
        _install_docs()
        # Mock base64 image return
        litellm_mock.image_generation.return_value = SimpleNamespace(
            data=[SimpleNamespace(b64_json=_audio_mocks._b64(b"fake-png-bytes"), url=None)]
        )
        _audio_mocks.frappe_file_manager.save_file.return_value = SimpleNamespace(
            name="FILE-IMG-1", file_url="/files/generated_image_1.png", file_name="generated_image_1.png"
        )

        res = asyncio.run(media.handle_generate_image(
            prompt="a cute cat",
            agent_name="Agent-1",
            conversation_id="CONV-1"
        ))

        self.assertTrue(res["success"])
        self.assertEqual(len(res["images"]), 1)
        self.assertEqual(res["images"][0]["file_id"], "FILE-IMG-1")


class TestMediaHandlersOCRAndAudio(unittest.TestCase):
    def setUp(self):
        frappe_mock.get_doc.reset_mock()
        frappe_mock.get_doc.side_effect = None

    def test_handle_ocr_document_delegates_to_extract_document(self):
        _install_docs()
        extract_document_mock.return_value = SimpleNamespace(
            as_dict=lambda: {"success": True, "text": "Extracted OCR text"}
        )

        res = asyncio.run(media.handle_ocr_document(
            file_id="FILE-DOC-1",
            agent_name="Agent-1",
            conversation_id="CONV-1"
        ))

        self.assertTrue(res["success"])
        self.assertEqual(res["text"], "Extracted OCR text")
        extract_document_mock.assert_called_once()

    def test_handle_transcribe_audio_delegates_to_audio_service(self):
        with patch.object(audio_service, "transcribe_audio_file") as transcribe:
            transcribe.return_value = {
                "success": True,
                "text": "Transcribed transcript",
                "file_id": "FILE-AUD-1",
                "file_url": "/files/audio.mp3",
                "local_path": None,
                "language": "en",
                "stt_model": "whisper-1",
                "provider": "openai",
            }

            res = asyncio.run(media.handle_transcribe_audio(
                file_id="FILE-AUD-1",
                agent_name="Agent-1",
            ))

            self.assertTrue(res["success"])
            self.assertEqual(res["text"], "Transcribed transcript")
            transcribe.assert_called_once_with(
                file_id="FILE-AUD-1",
                file_url=None,
                local_path=None,
                agent_name="Agent-1",
                language=None,
                model=None
            )


if __name__ == "__main__":
    unittest.main()
