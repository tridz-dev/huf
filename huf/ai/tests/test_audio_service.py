# Copyright (c) 2026, Huf and Contributors
# See license.txt

import asyncio
import base64
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils.file_manager import save_file

from huf.ai import audio_service
from huf.ai import audio_api


class TestAudioService(FrappeTestCase):
    """Tests for the canonical audio service."""

    def setUp(self):
        super().setUp()
        self.suffix = frappe.generate_hash(length=8)

        self.provider_name = f"Audio-Test-Provider-{self.suffix}"
        self.provider = frappe.get_doc({
            "doctype": "AI Provider",
            "provider_name": self.provider_name,
            "api_key": "test-api-key",
        }).insert(ignore_permissions=True)

        self.model_name = f"Audio-Test-Model-{self.suffix}"
        self.model = frappe.get_doc({
            "doctype": "AI Model",
            "model_name": self.model_name,
            "provider": self.provider.name,
        }).insert(ignore_permissions=True)

        self.stt_model_name = f"Audio-Test-STT-Model-{self.suffix}"
        self.stt_model = frappe.get_doc({
            "doctype": "AI Model",
            "model_name": self.stt_model_name,
            "provider": self.provider.name,
            "modalities": "Transcription",
        }).insert(ignore_permissions=True)

        self.agent_name = f"Audio-Test-Agent-{self.suffix}"
        self.agent = frappe.get_doc({
            "doctype": "Agent",
            "agent_name": self.agent_name,
            "provider": self.provider.name,
            "model": self.model.name,
            "instructions": "Test agent for audio service",
            "allow_audio_upload": 1,
        }).insert(ignore_permissions=True)

        self._created_files = []
        self._created_messages = []
        self._created_conversations = []

    def tearDown(self):
        for msg_name in self._created_messages:
            try:
                frappe.delete_doc("Agent Message", msg_name, force=True, ignore_permissions=True)
            except Exception:
                pass

        for conv_name in self._created_conversations:
            try:
                frappe.delete_doc("Agent Conversation", conv_name, force=True, ignore_permissions=True)
            except Exception:
                pass

        for file_name in self._created_files:
            try:
                frappe.delete_doc("File", file_name, delete_permanently=True, ignore_permissions=True)
            except Exception:
                pass

        try:
            frappe.delete_doc("Agent", self.agent.name, force=True, ignore_permissions=True)
        except Exception:
            pass
        try:
            frappe.delete_doc("AI Model", self.stt_model.name, force=True, ignore_permissions=True)
        except Exception:
            pass
        try:
            frappe.delete_doc("AI Model", self.model.name, force=True, ignore_permissions=True)
        except Exception:
            pass
        try:
            frappe.delete_doc("AI Provider", self.provider.name, force=True, ignore_permissions=True)
        except Exception:
            pass

        frappe.db.commit()
        super().tearDown()

    def _webm_bytes(self):
        return b"\x1aE\xdfa3" + b"\x00" * 64

    def _mp3_bytes(self):
        return b"ID3" + b"\x00" * 64

    def _save_audio_file(self, filename="test.webm", file_bytes=None, is_private=False):
        file_bytes = file_bytes or self._webm_bytes()
        saved = save_file(filename, file_bytes, "Agent", self.agent.name, is_private=is_private)
        self._created_files.append(saved.name)
        return saved

    def _make_conversation(self):
        conv = frappe.get_doc({
            "doctype": "Agent Conversation",
            "agent": self.agent.name,
            "model": self.model.name,
            "session_id": f"test-session-{self.suffix}-{len(self._created_conversations)}",
            "channel": "Chat",
        }).insert(ignore_permissions=True)
        self._created_conversations.append(conv.name)
        return conv

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def test_validate_audio_upload_empty(self):
        ok, error = audio_service.validate_audio_upload(b"", "test.webm")
        self.assertFalse(ok)
        self.assertIn("empty", error.lower())

    def test_validate_audio_upload_disabled_agent(self):
        self.agent.allow_audio_upload = 0
        ok, error = audio_service.validate_audio_upload(self._webm_bytes(), "test.webm", self.agent)
        self.assertFalse(ok)
        self.assertIn("disabled", error.lower())

    def test_validate_audio_upload_unsupported_extension(self):
        ok, error = audio_service.validate_audio_upload(self._webm_bytes(), "test.xyz")
        self.assertFalse(ok)
        self.assertIn("extension", error.lower())

    def test_validate_audio_upload_size_limit(self):
        big = b"\x1aE\xdfa3" + (26 * 1024 * 1024 + 1) * b"\x00"
        ok, error = audio_service.validate_audio_upload(big, "test.webm")
        self.assertFalse(ok)
        self.assertIn("exceeds", error.lower())

    def test_validate_audio_upload_valid_webm(self):
        ok, error = audio_service.validate_audio_upload(self._webm_bytes(), "test.webm")
        self.assertTrue(ok)
        self.assertIsNone(error)

    def test_validate_audio_upload_valid_mp3(self):
        ok, error = audio_service.validate_audio_upload(self._mp3_bytes(), "test.mp3")
        self.assertTrue(ok)
        self.assertIsNone(error)

    def test_sniff_audio_mime_magic_bytes(self):
        self.assertEqual(audio_service._sniff_audio_mime(self._webm_bytes(), "x.webm"), "audio/webm")
        self.assertEqual(audio_service._sniff_audio_mime(self._mp3_bytes(), "x.mp3"), "audio/mpeg")

    # ------------------------------------------------------------------
    # File handling
    # ------------------------------------------------------------------

    def test_save_audio_file_invalid_base64(self):
        result = audio_service.save_audio_file("test.webm", "not-valid-base64!!!")
        self.assertFalse(result["success"])
        self.assertIn("base64", result["error"].lower())

    def test_save_audio_file_success(self):
        b64 = base64.b64encode(self._webm_bytes()).decode("utf-8")
        result = audio_service.save_audio_file("test.webm", b64, agent_doc=self.agent)
        self.assertTrue(result["success"])
        self.assertTrue(result["file_id"])
        self.assertTrue(result["file_url"])
        self._created_files.append(result["file_id"])

    def test_save_audio_file_rejects_disabled_agent(self):
        self.agent.allow_audio_upload = 0
        b64 = base64.b64encode(self._webm_bytes()).decode("utf-8")
        result = audio_service.save_audio_file("test.webm", b64, agent_doc=self.agent)
        self.assertFalse(result["success"])
        self.assertIn("disabled", result["error"].lower())

    def test_get_audio_file_doc_by_id(self):
        saved = self._save_audio_file()
        doc = audio_service.get_audio_file_doc(file_id=saved.name)
        self.assertEqual(doc.name, saved.name)

    def test_get_audio_file_doc_by_url(self):
        saved = self._save_audio_file()
        doc = audio_service.get_audio_file_doc(file_url=saved.file_url)
        self.assertEqual(doc.name, saved.name)

    # ------------------------------------------------------------------
    # STT configuration
    # ------------------------------------------------------------------

    def test_resolve_stt_config_explicit_model(self):
        explicit_model = f"audio-explicit-{self.suffix}"
        config = audio_service.resolve_stt_config(self.agent, model=explicit_model)
        self.assertEqual(config["source"], "tool_param")
        self.assertEqual(config["provider_name"], self.provider_name.lower())
        self.assertEqual(config["api_key"], "test-api-key")

    def test_resolve_stt_config_agent_stt_model(self):
        self.agent.stt_model = self.stt_model.name
        self.agent.save(ignore_permissions=True)
        config = audio_service.resolve_stt_config(self.agent)
        self.assertEqual(config["source"], "agent_config")
        self.assertEqual(config["provider_name"], self.provider_name.lower())

    def test_resolve_stt_config_provider_default(self):
        self.provider.provider_name = "OpenAI"
        self.provider.save(ignore_permissions=True)
        agent = frappe.get_doc("Agent", self.agent.name)
        config = audio_service.resolve_stt_config(agent)
        self.assertEqual(config["source"], "provider_default")
        self.assertIn("whisper", config["stt_model"].lower())

    def test_get_default_stt_model(self):
        self.assertEqual(audio_service.get_default_stt_model("openai"), "whisper-1")
        self.assertIsNone(audio_service.get_default_stt_model("unknown-provider"))

    # ------------------------------------------------------------------
    # Transcription
    # ------------------------------------------------------------------

    def test_transcribe_audio_file_missing_args(self):
        result = asyncio.run(audio_service.transcribe_audio_file(agent_doc=self.agent))
        self.assertFalse(result["success"])
        self.assertIn("required", result["error"].lower())

    def test_transcribe_audio_file_file_not_found(self):
        result = asyncio.run(audio_service.transcribe_audio_file(file_id="NONEXISTENT", agent_doc=self.agent))
        self.assertFalse(result["success"])
        self.assertIn("not found", result["error"].lower())

    @patch("litellm.transcription")
    def test_transcribe_audio_file_litellm_success(self, mock_transcription):
        mock_response = MagicMock()
        mock_response.text = "hello world"
        mock_transcription.return_value = mock_response

        saved = self._save_audio_file()
        result = asyncio.run(audio_service.transcribe_audio_file(file_id=saved.name, agent_doc=self.agent))

        self.assertTrue(result["success"])
        self.assertEqual(result["transcript"], "hello world")
        self.assertEqual(result["text"], "hello world")
        self.assertEqual(result["file_id"], saved.name)
        self.assertIn("model", result)

    @patch("litellm.completion")
    def test_transcribe_audio_file_google_multimodal(self, mock_completion):
        # Use the real Google provider (if seeded) so _normalize_model_name maps
        # it to the Gemini prefix. Avoid creating a suffixed provider because the
        # normalizer keys on the exact provider_name.
        if not frappe.db.exists("AI Provider", "Google"):
            self.skipTest("Google AI Provider not available")

        self.agent.provider = "Google"
        self.agent.save(ignore_permissions=True)

        mock_message = MagicMock()
        mock_message.content = "transcribed via gemini"
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_completion.return_value = mock_response

        saved = self._save_audio_file()
        agent = frappe.get_doc("Agent", self.agent.name)
        result = asyncio.run(audio_service.transcribe_audio_file(file_id=saved.name, agent_doc=agent))

        self.assertTrue(result["success"])
        self.assertEqual(result["transcript"], "transcribed via gemini")
        mock_completion.assert_called_once()

    # ------------------------------------------------------------------
    # Message persistence
    # ------------------------------------------------------------------

    def test_create_audio_user_message_new(self):
        saved = self._save_audio_file()
        conv = self._make_conversation()
        msg = audio_service.create_audio_user_message(
            conv.name, saved.name, "hello", agent_name=self.agent.name, stt_model="whisper-1"
        )
        self._created_messages.append(msg.name)
        self.assertEqual(msg.role, "user")
        self.assertEqual(msg.content, "hello")
        self.assertEqual(msg.kind, "Audio")
        self.assertTrue(msg.voice_message)

    def test_create_audio_user_message_update(self):
        saved = self._save_audio_file()
        conv = self._make_conversation()
        placeholder = frappe.get_doc({
            "doctype": "Agent Message",
            "conversation": conv.name,
            "role": "user",
            "content": "(placeholder)",
            "kind": "Audio",
        }).insert(ignore_permissions=True)
        self._created_messages.append(placeholder.name)

        msg = audio_service.create_audio_user_message(
            conv.name, saved.name, "updated transcript", message_id=placeholder.name
        )
        self.assertEqual(msg.name, placeholder.name)
        self.assertEqual(msg.content, "updated transcript")


class TestAudioAPI(FrappeTestCase):
    """Tests for the public audio transcription API."""

    def setUp(self):
        super().setUp()
        self.suffix = frappe.generate_hash(length=8)

        self.provider = frappe.get_doc({
            "doctype": "AI Provider",
            "provider_name": f"Audio-API-Provider-{self.suffix}",
            "api_key": "test-api-key",
        }).insert(ignore_permissions=True)

        self.model = frappe.get_doc({
            "doctype": "AI Model",
            "model_name": f"Audio-API-Model-{self.suffix}",
            "provider": self.provider.name,
        }).insert(ignore_permissions=True)

        self.agent = frappe.get_doc({
            "doctype": "Agent",
            "agent_name": f"Audio-API-Agent-{self.suffix}",
            "provider": self.provider.name,
            "model": self.model.name,
            "instructions": "Test agent for audio API",
            "allow_audio_upload": 1,
        }).insert(ignore_permissions=True)

        self._created_files = []
        self._created_messages = []
        self._created_conversations = []

    def tearDown(self):
        for msg_name in self._created_messages:
            try:
                frappe.delete_doc("Agent Message", msg_name, force=True, ignore_permissions=True)
            except Exception:
                pass

        for conv_name in self._created_conversations:
            try:
                frappe.delete_doc("Agent Conversation", conv_name, force=True, ignore_permissions=True)
            except Exception:
                pass

        for file_name in self._created_files:
            try:
                frappe.delete_doc("File", file_name, delete_permanently=True, ignore_permissions=True)
            except Exception:
                pass

        try:
            frappe.delete_doc("Agent", self.agent.name, force=True, ignore_permissions=True)
        except Exception:
            pass
        try:
            frappe.delete_doc("AI Model", self.model.name, force=True, ignore_permissions=True)
        except Exception:
            pass
        try:
            frappe.delete_doc("AI Provider", self.provider.name, force=True, ignore_permissions=True)
        except Exception:
            pass

        frappe.db.commit()
        super().tearDown()

    def _save_audio_file(self):
        file_bytes = b"\x1aE\xdfa3" + b"\x00" * 64
        saved = save_file("test.webm", file_bytes, "Agent", self.agent.name, is_private=False)
        self._created_files.append(saved.name)
        return saved

    def test_transcribe_requires_agent(self):
        with self.assertRaises(Exception):
            audio_api.transcribe(filename="test.webm", b64data="abc")

    @patch("huf.ai.audio_api.audio_service.transcribe_audio_file")
    def test_transcribe_by_file_id(self, mock_transcribe):
        saved = self._save_audio_file()
        mock_transcribe.return_value = {
            "success": True,
            "transcript": "hello api",
            "text": "hello api",
            "file_id": saved.name,
            "file_url": saved.file_url,
            "model": "whisper-1",
            "provider": self.provider.provider_name,
            "language": "auto-detected",
        }

        result = audio_api.transcribe(file_id=saved.name, agent=self.agent.name)

        self.assertTrue(result["success"])
        self.assertEqual(result["transcript"], "hello api")
        self.assertEqual(result["text"], "hello api")
        self.assertIsNone(result["message_id"])

    @patch("huf.ai.audio_api.audio_service.transcribe_audio_file")
    def test_transcribe_upload_and_create_message(self, mock_transcribe):
        file_bytes = b"\x1aE\xdfa3" + b"\x00" * 64
        b64data = base64.b64encode(file_bytes).decode("utf-8")

        mock_transcribe.return_value = {
            "success": True,
            "transcript": "hello message",
            "text": "hello message",
            "file_id": "FILE-ID",
            "file_url": "/files/test.webm",
            "model": "whisper-1",
            "provider": self.provider.provider_name,
            "language": "en",
        }

        result = audio_api.transcribe(
            filename="test.webm",
            b64data=b64data,
            agent=self.agent.name,
            create_message=True,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["transcript"], "hello message")
        self.assertTrue(result["message_id"])
        self._created_messages.append(result["message_id"])
        # conversation should have been created
        self.assertTrue(result.get("conversation_id"))
        self._created_conversations.append(result["conversation_id"])


if __name__ == "__main__":
    unittest.main()
