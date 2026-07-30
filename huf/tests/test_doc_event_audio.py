# Copyright (c) 2026, Huf and Contributors
# See license.txt

"""
Unit tests for doc-event trigger audio routing in huf.ai.agent_hooks.

Attachments configured on Agent Trigger ``file_attachments`` are classified
per file: audio goes to the canonical audio service
(``audio_service.transcribe_audio_file``), other documents keep going to OCR
(``handle_ocr_document``), and images go to neither.

These tests reuse the frappe mock installed by huf.tests.test_audio_service
so both suites share a single mocked frappe module (and a single binding of
huf.ai.audio_service) regardless of test ordering:

    python -m unittest huf.tests.test_doc_event_audio huf.tests.test_audio_service
"""

import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

# Standalone-only — see the matching note in test_audio_service.py. This module
# additionally replaces "frappe.utils.safe_exec", "huf.ai.agent_integration"
# and "huf.ai.sdk_tools", which corrupts a bench test run.
if getattr(sys.modules.get("frappe"), "__file__", None):
    raise unittest.SkipTest(
        "huf.tests.test_doc_event_audio is a standalone unit-test module; "
        "it stubs sys.modules and is skipped under a real Frappe bench"
    )

# Importing the audio service test module installs its frappe/frappe.utils/
# litellm stubs into sys.modules and imports huf.ai.audio_service against
# them. Reusing that mock keeps audio_service.frappe bound to one shared
# mock no matter which suite is imported first.
#
# The module may already be loaded under a different name: unittest
# discovery (``python -m unittest discover -s huf/tests``) imports it as the
# top-level module "test_audio_service", while dotted runs
# (``python -m unittest huf.tests.test_doc_event_audio``) import it as
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
frappe_utils = sys.modules["frappe.utils"]

# agent_hooks touches frappe APIs the base audio mock does not provide.
frappe_mock.get_traceback = MagicMock(return_value="traceback")
frappe_mock.set_user = MagicMock()
frappe_utils.now_datetime = MagicMock(
    return_value=SimpleNamespace(isoformat=lambda: "2026-01-01T00:00:00")
)

background_jobs_stub = types.ModuleType("frappe.utils.background_jobs")
background_jobs_stub.enqueue = MagicMock()
sys.modules["frappe.utils.background_jobs"] = background_jobs_stub

safe_exec_stub = types.ModuleType("frappe.utils.safe_exec")
safe_exec_stub.get_safe_globals = MagicMock(return_value={})
safe_exec_stub.safe_eval = MagicMock(return_value=True)
sys.modules["frappe.utils.safe_exec"] = safe_exec_stub

# Stub the heavy modules agent_hooks pulls in: run_agent_sync is a
# module-level import; handle_ocr_document is a lazy import inside
# run_agent_for_doc (async, hence AsyncMock for run_until_complete).
run_agent_sync_mock = MagicMock()
agent_integration_stub = types.ModuleType("huf.ai.agent_integration")
agent_integration_stub.run_agent_sync = run_agent_sync_mock
sys.modules["huf.ai.agent_integration"] = agent_integration_stub

handle_ocr_document_mock = AsyncMock(
    return_value={"success": True, "text": "ocr text", "file_hash": "abc123"}
)
sdk_tools_stub = types.ModuleType("huf.ai.sdk_tools")
sdk_tools_stub.handle_ocr_document = handle_ocr_document_mock
sys.modules["huf.ai.sdk_tools"] = sdk_tools_stub

from huf.ai import agent_hooks, audio_service  # noqa: E402


def _doc_event_inputs(filename, field="attachment"):
    doc = {
        "doctype": "ToDo",
        "name": "TODO-0001",
        "owner": "Administrator",
        field: f"/files/{filename}",
    }
    attachments = [
        {"source_type": "DocField", "field_name": field, "child_table": None}
    ]
    return doc, attachments


class TestIsAudioFile(unittest.TestCase):
    """The routing classifier reuses the audio service allowlists."""

    def test_audio_extensions_are_audio(self):
        for name in ("clip.mp3", "clip.webm", "voice.WAV", "note.m4a", "rec.ogg"):
            with self.subTest(name=name):
                self.assertTrue(audio_service.is_audio_file(name))

    def test_browser_audio_container_is_audio(self):
        # Browsers record audio into mp4/webm containers; the allowlist
        # intentionally treats those extensions as audio.
        self.assertTrue(audio_service.is_audio_file("recording.mp4"))

    def test_audio_mime_type_is_audio(self):
        self.assertTrue(audio_service.is_audio_file("attachment.bin", "audio/mpeg"))

    def test_non_audio_files_are_not_audio(self):
        for name in ("report.pdf", "photo.png", "notes.txt", "data.csv"):
            with self.subTest(name=name):
                self.assertFalse(audio_service.is_audio_file(name))

    def test_extensionless_file_is_not_audio(self):
        self.assertFalse(audio_service.is_audio_file("README"))


class TestDocEventAudioRouting(unittest.TestCase):
    def setUp(self):
        frappe_mock.get_doc.reset_mock()
        frappe_mock.get_doc.side_effect = None
        frappe_mock.get_doc.return_value = SimpleNamespace(persist_user_history=False)
        frappe_mock.db.get_value.reset_mock()
        frappe_mock.db.get_value.return_value = "FILE-0001"
        frappe_mock.log_error.reset_mock()
        run_agent_sync_mock.reset_mock()
        handle_ocr_document_mock.reset_mock()
        handle_ocr_document_mock.return_value = {
            "success": True,
            "text": "ocr text",
            "file_hash": "abc123",
        }
        transcribe_patcher = patch.object(audio_service, "transcribe_audio_file")
        self.transcribe_mock = transcribe_patcher.start()
        self.addCleanup(transcribe_patcher.stop)
        self.transcribe_mock.return_value = {
            "success": True,
            "transcript": "hello audio",
            "text": "hello audio",
            "file_id": "FILE-0001",
            "file_url": "/files/clip.mp3",
            "stt_model": "openai/whisper-1",
            "provider": "openai",
            "language": "auto-detected",
        }

    def _run_agent_for_doc(self, filename):
        doc, attachments = _doc_event_inputs(filename)
        agent_hooks.run_agent_for_doc(
            doc,
            "Agent-1",
            "Summarize the attachment.",
            "after_insert",
            "OpenAI",
            "gpt-4o",
            initiating_user=None,
            channel_id="doc_event",
            file_attachments=attachments,
        )

    def _sent_prompt(self):
        run_agent_sync_mock.assert_called_once()
        return run_agent_sync_mock.call_args.args[1]

    def _audio_error_log_titles(self):
        return [
            c.kwargs.get("title") or (c.args[1] if len(c.args) > 1 else None)
            for c in frappe_mock.log_error.call_args_list
        ]

    def test_audio_file_is_transcribed_not_ocrd(self):
        self._run_agent_for_doc("clip.mp3")

        self.transcribe_mock.assert_called_once_with(
            file_id="FILE-0001", file_url="/files/clip.mp3", agent_name="Agent-1"
        )
        handle_ocr_document_mock.assert_not_called()

        prompt = self._sent_prompt()
        self.assertIn("Attached Audio Transcript(s):", prompt)
        self.assertIn("--- File: clip.mp3 ---", prompt)
        self.assertIn("hello audio", prompt)
        self.assertNotIn("OCR Extracted", prompt)

    def test_pdf_is_ocrd_not_transcribed(self):
        self._run_agent_for_doc("report.pdf")

        handle_ocr_document_mock.assert_called_once_with(
            file_id="FILE-0001", file_url="/files/report.pdf", agent_name="Agent-1"
        )
        self.transcribe_mock.assert_not_called()

        prompt = self._sent_prompt()
        self.assertIn("Attached File Content (OCR Extracted):", prompt)
        self.assertIn("--- File: report.pdf (hash: abc123) ---", prompt)
        self.assertIn("ocr text", prompt)
        self.assertNotIn("Attached Audio Transcript(s):", prompt)

    def test_image_is_neither_transcribed_nor_ocrd(self):
        self._run_agent_for_doc("photo.png")

        self.transcribe_mock.assert_not_called()
        handle_ocr_document_mock.assert_not_called()

        prompt = self._sent_prompt()
        self.assertNotIn("Attached Audio Transcript(s):", prompt)
        self.assertNotIn("OCR Extracted", prompt)

    def test_transcription_error_does_not_abort_run(self):
        self.transcribe_mock.return_value = {"success": False, "error": "boom"}
        self._run_agent_for_doc("clip.mp3")

        prompt = self._sent_prompt()  # run still executed with the agent
        self.assertNotIn("Attached Audio Transcript(s):", prompt)
        self.assertIn("Agent Hooks Audio", self._audio_error_log_titles())

    def test_transcription_exception_does_not_abort_run(self):
        self.transcribe_mock.side_effect = Exception("kaboom")
        self._run_agent_for_doc("clip.mp3")

        prompt = self._sent_prompt()
        self.assertNotIn("Attached Audio Transcript(s):", prompt)
        self.assertIn("Agent Hooks Audio", self._audio_error_log_titles())


if __name__ == "__main__":
    unittest.main()
