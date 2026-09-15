# Copyright (c) 2026, Huf and Contributors
# See license.txt

"""
Unit tests for server-side (local filesystem) audio imports in
huf.ai.audio_service and huf.ai.audio_api: ``resolve_local_audio_path``,
``transcribe_audio_file(local_path=...)``, ``import_local_audio``, and the
``file_path`` branch of the public transcribe API.

These tests reuse the frappe mock installed by huf.tests.standalone_audio_service
so all suites share a single mocked frappe module (and a single binding of
huf.ai.audio_service) regardless of test ordering:

    python -m unittest huf.tests.standalone_local_audio_path
"""

import importlib.util
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# NOTE: deliberately NOT named test_*.py — see standalone_audio_service.py.
# This module stubs sys.modules and would corrupt bench test discovery.
# Run explicitly:  python -m unittest huf.tests.standalone_local_audio_path

# Importing the audio service test module installs its frappe/frappe.utils/
# litellm stubs into sys.modules and imports huf.ai.audio_service against
# them. Reusing that mock keeps audio_service.frappe bound to one shared
# mock no matter which suite is imported first. It may already be loaded
# under a different name depending on how unittest discovered it.
_audio_mocks = sys.modules.get("huf.tests.standalone_audio_service") or sys.modules.get(
    "standalone_audio_service"
)
if _audio_mocks is None:
    path = os.path.abspath(os.path.join(os.path.dirname(__file__), "standalone_audio_service.py"))
    spec = importlib.util.spec_from_file_location("standalone_audio_service", path)
    _audio_mocks = importlib.util.module_from_spec(spec)
    sys.modules["standalone_audio_service"] = _audio_mocks
    spec.loader.exec_module(_audio_mocks)

frappe_mock = _audio_mocks.frappe_mock
frappe_file_manager = sys.modules["frappe.utils.file_manager"]
litellm_mock = sys.modules["litellm"]
ThrowError = _audio_mocks.ThrowError

# audio_service now touches site-path/config and role APIs the base audio
# mock does not provide.
if not hasattr(frappe_mock, "get_site_path"):
    frappe_mock.get_site_path = MagicMock()
if not hasattr(frappe_mock, "get_site_config"):
    frappe_mock.get_site_config = MagicMock(return_value={})
if not hasattr(frappe_mock, "only_for"):
    frappe_mock.only_for = MagicMock()

from huf.ai import audio_api, audio_service  # noqa: E402


class LocalAudioTestCase(unittest.TestCase):
    """Base case: real temp dir acting as the site's allowed import root."""

    def setUp(self):
        self.site_dir = tempfile.mkdtemp(prefix="huf-site-")
        self.allowed_root = os.path.join(self.site_dir, "private", "audio_imports")
        os.makedirs(self.allowed_root, exist_ok=True)

        frappe_mock.get_site_path.reset_mock()
        frappe_mock.get_site_path.side_effect = lambda *parts: os.path.join(self.site_dir, *parts)
        frappe_mock.get_site_config.reset_mock()
        frappe_mock.get_site_config.side_effect = None
        frappe_mock.get_site_config.return_value = {}
        frappe_mock.only_for.reset_mock()
        frappe_mock.only_for.side_effect = None

    def tearDown(self):
        frappe_mock.get_site_path.reset_mock()
        frappe_mock.get_site_path.side_effect = None
        frappe_mock.get_site_config.reset_mock()
        frappe_mock.get_site_config.side_effect = None
        frappe_mock.only_for.reset_mock()
        frappe_mock.only_for.side_effect = None

    def _write_audio(self, name="clip.webm", payload=b"fake audio bytes", root=None):
        path = os.path.join(root or self.allowed_root, name)
        with open(path, "wb") as f:
            f.write(payload)
        return path


class TestResolveLocalAudioPath(LocalAudioTestCase):
    def test_rejects_relative_path(self):
        with self.assertRaises(ThrowError) as ctx:
            audio_service.resolve_local_audio_path("relative/clip.webm")
        self.assertIn("absolute file path", str(ctx.exception))

    def test_rejects_empty_path(self):
        with self.assertRaises(ThrowError):
            audio_service.resolve_local_audio_path("")
        with self.assertRaises(ThrowError):
            audio_service.resolve_local_audio_path(None)

    def test_rejects_traversal_attempt(self):
        # "/allowed/../etc/passwd" resolves outside the allowed root.
        traversal = os.path.join(self.allowed_root, "..", "etc", "passwd")
        with self.assertRaises(ThrowError) as ctx:
            audio_service.resolve_local_audio_path(traversal)
        self.assertIn("outside the allowed audio import directories", str(ctx.exception))

    def test_rejects_symlink_escape(self):
        # A symlink inside the allowed root whose real path escapes it.
        target = self._write_audio()
        real_realpath = os.path.realpath

        def fake_realpath(path):
            if path == target:
                return os.path.join(self.site_dir, "escape.webm")
            return real_realpath(path)

        with patch.object(os.path, "realpath", side_effect=fake_realpath):
            with self.assertRaises(ThrowError) as ctx:
                audio_service.resolve_local_audio_path(target)
        self.assertIn("outside the allowed audio import directories", str(ctx.exception))

    def test_rejects_non_allowlisted_dir(self):
        outside_dir = tempfile.mkdtemp(prefix="huf-outside-")
        outside_file = self._write_audio(root=outside_dir)
        with self.assertRaises(ThrowError) as ctx:
            audio_service.resolve_local_audio_path(outside_file)
        self.assertIn("outside the allowed audio import directories", str(ctx.exception))

    def test_rejects_missing_file(self):
        missing = os.path.join(self.allowed_root, "nope.webm")
        with self.assertRaises(ThrowError) as ctx:
            audio_service.resolve_local_audio_path(missing)
        self.assertIn("Audio file not found", str(ctx.exception))

    def test_rejects_directory(self):
        with self.assertRaises(ThrowError) as ctx:
            audio_service.resolve_local_audio_path(os.path.realpath(self.allowed_root))
        self.assertIn("Audio file not found", str(ctx.exception))

    def test_rejects_disallowed_extension(self):
        notes = self._write_audio(name="notes.txt")
        with self.assertRaises(ThrowError) as ctx:
            audio_service.resolve_local_audio_path(notes)
        self.assertIn("Unsupported audio file type", str(ctx.exception))

    def test_rejects_oversized_file(self):
        big = self._write_audio(name="big.webm")
        with patch.object(
            os.path, "getsize", return_value=audio_service.MAX_AUDIO_FILE_SIZE + 1
        ):
            with self.assertRaises(ThrowError) as ctx:
                audio_service.resolve_local_audio_path(big)
        self.assertIn("maximum allowed size", str(ctx.exception))

    def test_extra_dirs_from_site_config(self):
        extra_dir = tempfile.mkdtemp(prefix="huf-extra-")
        dropped = self._write_audio(root=extra_dir)
        frappe_mock.get_site_config.return_value = {"audio_import_dirs": [extra_dir]}

        resolved = audio_service.resolve_local_audio_path(dropped)
        self.assertEqual(resolved, os.path.realpath(dropped))

    def test_happy_path_returns_realpath(self):
        target = self._write_audio()
        resolved = audio_service.resolve_local_audio_path(target)
        self.assertEqual(resolved, os.path.realpath(target))


class TestTranscribeLocalPath(LocalAudioTestCase):
    def setUp(self):
        super().setUp()
        litellm_mock.transcription.reset_mock()
        litellm_mock.transcription.side_effect = None
        litellm_mock.transcription.return_value = SimpleNamespace(text="hello world")
        frappe_mock.get_all.reset_mock()
        frappe_mock.get_all.side_effect = None
        frappe_mock.get_all.return_value = []

        self.audio_path = self._write_audio()
        _audio_mocks._install_docs(
            agent=_audio_mocks._agent_doc(),
            providers={"OpenAI": _audio_mocks._provider_doc("OpenAI")},
        )

    def test_transcribes_in_place_without_file_record(self):
        result = audio_service.transcribe_audio_file(
            local_path=self.audio_path, agent_name="Agent-1"
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["transcript"], "hello world")
        self.assertEqual(result["text"], "hello world")
        self.assertIsNone(result["file_id"])
        self.assertIsNone(result["file_url"])
        self.assertEqual(result["local_path"], os.path.realpath(self.audio_path))
        self.assertEqual(result["stt_model"], "openai/whisper-1")
        self.assertEqual(result["provider"], "openai")
        litellm_mock.transcription.assert_called_once()

    def test_local_path_mutually_exclusive_with_file_id(self):
        result = audio_service.transcribe_audio_file(
            file_id="FILE-0001", local_path=self.audio_path, agent_name="Agent-1"
        )
        self.assertFalse(result["success"])
        self.assertIn("mutually exclusive", result["error"])
        litellm_mock.transcription.assert_not_called()

    def test_outside_path_returns_error_dict(self):
        outside_dir = tempfile.mkdtemp(prefix="huf-outside-")
        outside_file = self._write_audio(root=outside_dir)
        result = audio_service.transcribe_audio_file(
            local_path=outside_file, agent_name="Agent-1"
        )
        self.assertFalse(result["success"])
        self.assertIn("outside the allowed audio import directories", result["error"])
        litellm_mock.transcription.assert_not_called()


class TestImportLocalAudio(LocalAudioTestCase):
    def setUp(self):
        super().setUp()
        frappe_file_manager.save_file.reset_mock()
        frappe_file_manager.save_file.side_effect = None
        frappe_file_manager.save_file.return_value = SimpleNamespace(
            name="FILE-0009",
            file_name="clip.webm",
            file_url="/private/files/clip.webm",
        )

    def test_imports_as_frappe_file(self):
        payload = b"fake audio bytes"
        target = self._write_audio(payload=payload)

        result = audio_service.import_local_audio(
            target,
            attach_to_doctype="Agent Message",
            attach_to_name="MSG-1",
        )

        self.assertEqual(result["file_id"], "FILE-0009")
        self.assertEqual(result["file_url"], "/private/files/clip.webm")
        self.assertEqual(result["file_name"], "clip.webm")
        args, kwargs = frappe_file_manager.save_file.call_args
        self.assertEqual(args[0], "clip.webm")
        self.assertEqual(args[1], payload)
        self.assertEqual(args[2], "Agent Message")
        self.assertEqual(args[3], "MSG-1")
        self.assertEqual(kwargs["is_private"], 1)

    def test_rejects_outside_path_without_saving(self):
        outside_dir = tempfile.mkdtemp(prefix="huf-outside-")
        outside_file = self._write_audio(root=outside_dir)
        with self.assertRaises(ThrowError) as ctx:
            audio_service.import_local_audio(outside_file)
        self.assertIn("outside the allowed audio import directories", str(ctx.exception))
        frappe_file_manager.save_file.assert_not_called()


class TestTranscribeApiFilePath(LocalAudioTestCase):
    def test_file_path_and_file_id_rejected(self):
        with self.assertRaises(ThrowError) as ctx:
            audio_api.transcribe(
                file_id="FILE-0001",
                file_path=os.path.join(self.allowed_root, "clip.webm"),
                agent="Agent-1",
            )
        self.assertIn("exactly one", str(ctx.exception))

    def test_file_path_and_b64data_rejected(self):
        with self.assertRaises(ThrowError) as ctx:
            audio_api.transcribe(
                file_path=os.path.join(self.allowed_root, "clip.webm"),
                b64data="YXVkaW8=",
                filename="clip.webm",
                agent="Agent-1",
            )
        self.assertIn("exactly one", str(ctx.exception))

    def test_file_path_requires_system_manager(self):
        frappe_mock.only_for.side_effect = PermissionError("no")
        with self.assertRaises(PermissionError):
            audio_api.transcribe(
                file_path=os.path.join(self.allowed_root, "clip.webm"),
                agent="Agent-1",
            )
        frappe_mock.only_for.assert_called_once_with("System Manager")

    def test_in_place_transcribe_passes_local_path(self):
        local = self._write_audio()
        with patch.object(
            audio_service,
            "transcribe_audio_file",
            return_value={
                "success": True,
                "transcript": "hello",
                "text": "hello",
                "file_id": None,
                "file_url": None,
                "local_path": os.path.realpath(local),
                "stt_model": "openai/whisper-1",
                "provider": "openai",
                "language": "auto-detected",
                "stt_source": "provider_default",
            },
        ) as transcribe_mock, patch.object(
            audio_service, "import_local_audio"
        ) as import_mock, patch.object(
            audio_service, "create_audio_user_message"
        ) as message_mock:
            result = audio_api.transcribe(file_path=local, agent="Agent-1")

        self.assertTrue(result["success"])
        self.assertEqual(result["transcript"], "hello")
        self.assertIsNone(result["file_id"])
        self.assertEqual(result["local_path"], os.path.realpath(local))
        frappe_mock.only_for.assert_called_once_with("System Manager")
        _, kwargs = transcribe_mock.call_args
        self.assertIsNone(kwargs["file_id"])
        self.assertEqual(kwargs["local_path"], local)
        import_mock.assert_not_called()
        message_mock.assert_not_called()

    def test_create_message_imports_then_proceeds_as_file_id(self):
        local = self._write_audio()
        with patch.object(
            audio_service,
            "import_local_audio",
            return_value={
                "file_id": "FILE-IMP",
                "file_url": "/private/files/clip.webm",
                "file_name": "clip.webm",
            },
        ) as import_mock, patch.object(
            audio_service,
            "transcribe_audio_file",
            return_value={
                "success": True,
                "transcript": "hello",
                "text": "hello",
                "file_id": "FILE-IMP",
                "file_url": "/private/files/clip.webm",
                "local_path": None,
                "stt_model": "openai/whisper-1",
                "provider": "openai",
                "language": "auto-detected",
                "stt_source": "provider_default",
            },
        ) as transcribe_mock, patch.object(
            audio_service,
            "create_audio_user_message",
            return_value=SimpleNamespace(name="MSG-0001"),
        ) as message_mock:
            result = audio_api.transcribe(
                file_path=local,
                agent="Agent-1",
                conversation="CONV-0001",
                create_message=True,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["message_id"], "MSG-0001")
        self.assertEqual(result["file_id"], "FILE-IMP")
        import_mock.assert_called_once_with(local, is_private=1)
        _, kwargs = transcribe_mock.call_args
        self.assertEqual(kwargs["file_id"], "FILE-IMP")
        self.assertIsNone(kwargs["local_path"])
        args, _ = message_mock.call_args
        self.assertEqual(args[0], "CONV-0001")
        self.assertEqual(args[1], "FILE-IMP")
        self.assertEqual(args[2], "hello")


if __name__ == "__main__":
    unittest.main()
