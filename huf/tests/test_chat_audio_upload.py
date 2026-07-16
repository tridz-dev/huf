# Copyright (c) 2026, Huf and Contributors
# See license.txt

"""
Unit tests for audio routing in the chat attachment pipeline
(huf.ai.agent_chat).

Audio attachments must bypass the OCR/Vision modality gate: an audio upload
is allowed whenever STT is resolvable for the agent
(``audio_service.resolve_stt_config``), and processing routes to
``audio_service.transcribe_audio_file`` instead of OCR. Non-audio files keep
the existing OCR/Vision behavior.

These tests reuse the frappe mock installed by huf.tests.test_audio_service
so all suites share a single mocked frappe module (and a single binding of
huf.ai.audio_service) regardless of test ordering:

    python -m unittest huf.tests.test_chat_audio_upload
"""

import asyncio
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

# Importing the audio service test module installs its frappe/frappe.utils/
# litellm stubs into sys.modules and imports huf.ai.audio_service against
# them. Reusing that mock keeps audio_service.frappe bound to one shared
# mock no matter which suite is imported first.
#
# The module may already be loaded under a different name: unittest
# discovery (``python -m unittest discover -s huf/tests``) imports it as the
# top-level module "test_audio_service", while dotted runs
# (``python -m unittest huf.tests.test_chat_audio_upload``) import it as
# "huf.tests.test_audio_service". Reuse whichever copy is already loaded so
# its module-level mock setup executes exactly once; importing it a second
# time under the other name would rebind sys.modules["litellm"] and break
# the first copy's mock assertions.
_audio_mocks = sys.modules.get("huf.tests.test_audio_service") or sys.modules.get(
    "test_audio_service"
)
if _audio_mocks is None:
    from huf.tests import test_audio_service as _audio_mocks

frappe_mock = _audio_mocks.frappe_mock
frappe_file_manager = sys.modules["frappe.utils.file_manager"]

# agent_chat touches frappe APIs the base audio mock does not provide.
frappe_mock.PermissionError = type("PermissionError", (Exception,), {})
frappe_mock.ValidationError = type("ValidationError", (Exception,), {})
frappe_mock.get_meta = MagicMock()

# Stub the heavy modules agent_chat pulls in. handle_ocr_document is async,
# hence AsyncMock; _run_async_safely runs the coroutine it is given.
#
# Stubs are reused (and only extended with missing attributes) when another
# suite already installed them: huf.ai.agent_hooks lazily re-imports
# huf.ai.sdk_tools at call time, so replacing an existing stub module object
# would steal that lazy binding from whichever suite installed it first.
def _get_or_create_stub(module_name, **attrs):
    stub = sys.modules.get(module_name)
    if stub is None:
        stub = types.ModuleType(module_name)
        sys.modules[module_name] = stub
    for attr_name, value in attrs.items():
        if not hasattr(stub, attr_name):
            setattr(stub, attr_name, value)
    return stub


sdk_tools_stub = _get_or_create_stub(
    "huf.ai.sdk_tools",
    handle_ocr_document=AsyncMock(
        return_value={"success": True, "text": "ocr text", "file_hash": "abc123"}
    ),
)
handle_ocr_document_mock = sdk_tools_stub.handle_ocr_document


def _run_async_safely(coro):
    if asyncio.iscoroutine(coro):
        return asyncio.run(coro)
    return coro


_get_or_create_stub(
    "huf.ai.agent_integration",
    _run_async_safely=_run_async_safely,
    run_agent_sync=MagicMock(),
)
conversation_manager_stub = _get_or_create_stub(
    "huf.ai.conversation_manager", ConversationManager=MagicMock()
)
_get_or_create_stub("huf.ai.transcription_handler")

from huf.ai import agent_chat, audio_service  # noqa: E402


def _agent_dict(**overrides):
    agent = {
        "allow_file_upload": 1,
        "max_upload_size_mb": 25,
        "model": "gpt-4o",
        "enable_ocr": 0,
        "provider": "OpenAI",
    }
    agent.update(overrides)
    return agent


def _transcript_result(text="hello world"):
    return {
        "success": True,
        "transcript": text,
        "text": text,
        "file_id": "FILE-0001",
        "file_url": "/private/files/clip.mp3",
        "stt_model": "openai/whisper-1",
        "provider": "openai",
        "language": "auto-detected",
        "stt_source": "provider_default",
    }


def _staged_file(name="FILE-0001", filename="clip.mp3"):
    return SimpleNamespace(
        name=name,
        file_name=filename,
        file_url=f"/private/files/{filename}",
        owner="Administrator",
        attached_to_doctype="Agent",
        attached_to_name="Agent-1",
    )


def _conversation(name="CONV-1"):
    return SimpleNamespace(name=name, owner="Administrator")


def _install(agents=None, conversations=None, files=None):
    """Wire frappe.get_doc to serve the given fake documents."""
    agents = agents or {}
    conversations = conversations or {}
    files = files or {}

    def get_doc(doctype, name=None):
        if isinstance(doctype, dict):
            # frappe.get_doc({...}) creates a new Agent Message
            return SimpleNamespace(name="MSG-0001", insert=MagicMock())
        if doctype == "Agent":
            return agents[name]
        if doctype == "Agent Conversation":
            return conversations[name]
        if doctype == "File":
            return files[name]
        raise ValueError(f"Unexpected get_doc: {doctype} {name}")

    frappe_mock.get_doc.side_effect = get_doc


def _reset_mocks():
    frappe_mock.get_doc.reset_mock()
    frappe_mock.get_doc.side_effect = None
    frappe_mock.db.reset_mock()
    frappe_mock.db.get_value.return_value = ""
    frappe_mock.get_meta.reset_mock()
    frappe_mock.get_meta.return_value.get_field.return_value = object()
    frappe_file_manager.save_file.reset_mock()
    frappe_file_manager.save_file.side_effect = None
    handle_ocr_document_mock.reset_mock()
    handle_ocr_document_mock.return_value = {
        "success": True,
        "text": "ocr text",
        "file_hash": "abc123",
    }


class TestWebUploadAudioValidation(unittest.TestCase):
    """_validate_web_file_upload: audio bypasses the OCR/Vision gate."""

    def setUp(self):
        _reset_mocks()

    def test_audio_allowed_when_stt_resolvable(self):
        agent = _agent_dict(enable_ocr=0)
        _install(agents={"Agent-1": agent})

        with patch.object(
            audio_service,
            "resolve_stt_config",
            return_value={"stt_model": "openai/whisper-1"},
        ) as stt:
            agent_doc, error = agent_chat._validate_web_file_upload(
                "Agent-1", "clip.mp3", b"audio-bytes"
            )

        self.assertIsNone(error)
        self.assertIs(agent_doc, agent)
        stt.assert_called_once_with("Agent-1")
        # The OCR/Vision modality lookup must not run for audio files.
        frappe_mock.db.get_value.assert_not_called()

    def test_audio_rejected_when_stt_unresolvable(self):
        _install(agents={"Agent-1": _agent_dict()})

        with patch.object(
            audio_service,
            "resolve_stt_config",
            side_effect=ValueError(
                "No transcription model available for provider 'OpenAI'."
            ),
        ):
            agent_doc, error = agent_chat._validate_web_file_upload(
                "Agent-1", "clip.mp3", b"audio-bytes"
            )

        self.assertIsNone(agent_doc)
        self.assertFalse(error["success"])
        self.assertIn(
            "no transcription model configured for audio files", error["error"]
        )

    def test_non_audio_rejected_without_ocr_or_vision(self):
        _install(agents={"Agent-1": _agent_dict(enable_ocr=0)})
        frappe_mock.db.get_value.return_value = ""

        with patch.object(audio_service, "resolve_stt_config") as stt:
            agent_doc, error = agent_chat._validate_web_file_upload(
                "Agent-1", "report.pdf", b"pdf-bytes"
            )

        self.assertIsNone(agent_doc)
        self.assertFalse(error["success"])
        self.assertIn("does not support file analysis", error["error"])
        stt.assert_not_called()

    def test_non_audio_allowed_with_ocr(self):
        agent = _agent_dict(enable_ocr=1)
        _install(agents={"Agent-1": agent})
        frappe_mock.db.get_value.return_value = "OCR"

        with patch.object(audio_service, "resolve_stt_config") as stt:
            agent_doc, error = agent_chat._validate_web_file_upload(
                "Agent-1", "report.pdf", b"pdf-bytes"
            )

        self.assertIsNone(error)
        self.assertIs(agent_doc, agent)
        stt.assert_not_called()

    def test_non_audio_allowed_with_vision(self):
        agent = _agent_dict(enable_ocr=0)
        _install(agents={"Agent-1": agent})
        frappe_mock.db.get_value.return_value = "Vision"

        with patch.object(audio_service, "resolve_stt_config") as stt:
            agent_doc, error = agent_chat._validate_web_file_upload(
                "Agent-1", "photo.png", b"png-bytes"
            )

        self.assertIsNone(error)
        self.assertIs(agent_doc, agent)
        stt.assert_not_called()


class TestPrepareMessageWithFileWebAudio(unittest.TestCase):
    """prepare_message_with_file_web: audio routes to transcription."""

    def setUp(self):
        _reset_mocks()

    def test_audio_staged_file_routed_to_transcription(self):
        _install(
            files={"FILE-0001": _staged_file()},
            conversations={"CONV-1": _conversation()},
        )

        with patch.object(
            audio_service,
            "transcribe_audio_file",
            return_value=_transcript_result("hello world"),
        ) as transcribe:
            result = agent_chat.prepare_message_with_file_web(
                agent="Agent-1",
                conversation="CONV-1",
                message="what did I say?",
                file_id="FILE-0001",
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["conversation_id"], "CONV-1")
        self.assertEqual(result["message_id"], "MSG-0001")
        self.assertIsNone(result["files"])

        prompt = result["agent_prompt"]
        self.assertIn("what did I say?", prompt)
        self.assertIn("Attached Audio Transcript:", prompt)
        self.assertIn("--- File: clip.mp3 ---", prompt)
        self.assertIn("hello world", prompt)

        transcribe.assert_called_once_with(file_id="FILE-0001", agent_name="Agent-1")
        handle_ocr_document_mock.assert_not_called()

        # Audio metadata stamped on the Agent Message (kind stays "Message").
        frappe_mock.db.set_value.assert_any_call(
            "Agent Message",
            "MSG-0001",
            {
                "voice_message": "/private/files/clip.mp3",
                "stt_model": "openai/whisper-1",
            },
            update_modified=False,
        )

    def test_audio_transcription_failure_returns_error(self):
        _install(
            files={"FILE-0001": _staged_file()},
            conversations={"CONV-1": _conversation()},
        )

        with patch.object(
            audio_service,
            "transcribe_audio_file",
            return_value={"success": False, "error": "boom"},
        ):
            result = agent_chat.prepare_message_with_file_web(
                agent="Agent-1", conversation="CONV-1", message="", file_id="FILE-0001"
            )

        self.assertEqual(result, {"success": False, "error": "boom"})
        handle_ocr_document_mock.assert_not_called()

    def test_audio_b64_upload_validated_and_transcribed(self):
        agent = _agent_dict(enable_ocr=0)
        _install(agents={"Agent-1": agent})
        frappe_file_manager.save_file.return_value = SimpleNamespace(
            name="FILE-9", file_name="note.wav", file_url="/private/files/note.wav"
        )
        conversation_manager_stub.ConversationManager.return_value.create_new_conversation.return_value = SimpleNamespace(
            name="CONV-NEW"
        )

        with patch.object(
            audio_service,
            "resolve_stt_config",
            return_value={"stt_model": "openai/whisper-1"},
        ) as stt, patch.object(
            audio_service,
            "transcribe_audio_file",
            return_value=_transcript_result("transcribed words"),
        ) as transcribe:
            result = agent_chat.prepare_message_with_file_web(
                agent="Agent-1",
                message="",
                filename="note.wav",
                b64data=_audio_mocks._b64(b"audio-bytes"),
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["conversation_id"], "CONV-NEW")
        stt.assert_called_once_with("Agent-1")
        transcribe.assert_called_once_with(file_id="FILE-9", agent_name="Agent-1")
        handle_ocr_document_mock.assert_not_called()
        self.assertIn("transcribed words", result["agent_prompt"])
        self.assertIn("--- File: note.wav ---", result["agent_prompt"])

    def test_non_audio_staged_file_uses_ocr(self):
        _install(
            files={"FILE-0002": _staged_file(name="FILE-0002", filename="report.pdf")},
            conversations={"CONV-1": _conversation()},
        )

        with patch.object(audio_service, "transcribe_audio_file") as transcribe:
            result = agent_chat.prepare_message_with_file_web(
                agent="Agent-1",
                conversation="CONV-1",
                message="summarize",
                file_id="FILE-0002",
            )

        self.assertTrue(result["success"])
        self.assertIn("Attached File Content (OCR Extracted):", result["agent_prompt"])
        self.assertIn("ocr text", result["agent_prompt"])
        transcribe.assert_not_called()
        handle_ocr_document_mock.assert_called_once()
        _, kwargs = handle_ocr_document_mock.call_args
        self.assertEqual(kwargs["file_id"], "FILE-0002")
        self.assertFalse(kwargs["create_message"])


class TestUploadFileAndProcessWebAudio(unittest.TestCase):
    """upload_file_and_process_web: audio gate + STT routing."""

    def setUp(self):
        _reset_mocks()

    def test_audio_upload_processed_via_transcription(self):
        agent = _agent_dict(enable_ocr=0)
        _install(
            agents={"Agent-1": agent},
            conversations={"CONV-1": _conversation()},
        )
        frappe_mock.db.get_value.return_value = ""  # no OCR/Vision modalities
        frappe_file_manager.save_file.return_value = SimpleNamespace(
            name="FILE-0001", file_name="clip.mp3", file_url="/private/files/clip.mp3"
        )

        with patch.object(
            audio_service,
            "resolve_stt_config",
            return_value={"stt_model": "openai/whisper-1"},
        ), patch.object(
            audio_service,
            "transcribe_audio_file",
            return_value=_transcript_result("hello world"),
        ) as transcribe:
            result = agent_chat.upload_file_and_process_web(
                filename="clip.mp3",
                b64data=_audio_mocks._b64(b"audio-bytes"),
                agent="Agent-1",
                conversation="CONV-1",
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["conversation_id"], "CONV-1")
        self.assertEqual(result["message_id"], "MSG-0001")
        self.assertEqual(result["transcript"], "hello world")
        transcribe.assert_called_once_with(file_id="FILE-0001", agent_name="Agent-1")
        handle_ocr_document_mock.assert_not_called()

    def test_audio_upload_rejected_when_stt_unresolvable(self):
        _install(agents={"Agent-1": _agent_dict(enable_ocr=0)})
        frappe_mock.db.get_value.return_value = ""

        with patch.object(
            audio_service,
            "resolve_stt_config",
            side_effect=ValueError(
                "No transcription model available for provider 'OpenAI'."
            ),
        ):
            result = agent_chat.upload_file_and_process_web(
                filename="clip.mp3",
                b64data=_audio_mocks._b64(b"audio-bytes"),
                agent="Agent-1",
            )

        self.assertFalse(result["success"])
        self.assertIn(
            "no transcription model configured for audio files", result["error"]
        )
        frappe_file_manager.save_file.assert_not_called()
        handle_ocr_document_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
