# Copyright (c) 2026, Huf and Contributors
# For license information, please see license.txt

import base64
import unittest
from unittest.mock import patch

import frappe

from huf.ai.meetings import meeting_api, meeting_recording

# 1x1 transparent-ish tiny payload used as a stand-in for audio bytes; the
# validation under test cares about extension/size, not real audio content.
TINY_AUDIO_B64 = base64.b64encode(b"fake-audio-bytes").decode("ascii")


class TestMeetingRecording(unittest.TestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._meetings = []
        self.meeting = meeting_api.create_meeting()
        self._meetings.append(self.meeting["meeting_name"])
        meeting_api.start_recording(self.meeting["meeting_name"])

    def tearDown(self):
        frappe.set_user("Administrator")
        for name in self._meetings:
            try:
                frappe.delete_doc("Meeting", name, ignore_permissions=True, force=True)
            except Exception:
                pass
        frappe.db.commit()

    def _upload(self, **kwargs):
        with patch("frappe.enqueue"):
            return meeting_recording.upload_chunk(
                meeting=self.meeting["meeting_name"],
                sequence=kwargs.pop("sequence", 0),
                client_started_at=kwargs.pop("client_started_at", None),
                duration_seconds=kwargs.pop("duration_seconds", 30),
                audio_b64=kwargs.pop("audio_b64", TINY_AUDIO_B64),
                **kwargs,
            )

    def test_upload_chunk_creates_row_and_increments_count(self):
        result = self._upload(sequence=0)

        self.assertEqual(result["upload_status"], "Uploaded")
        self.assertEqual(result["chunk_count"], 1)

        chunk = frappe.get_doc("Meeting Recording Chunk", result["chunk_name"])
        self.assertEqual(chunk.meeting, self.meeting["meeting_name"])
        self.assertEqual(chunk.sequence, 0)
        self.assertEqual(chunk.upload_status, "Uploaded")

        meeting_doc = frappe.get_doc("Meeting", self.meeting["meeting_name"])
        self.assertEqual(meeting_doc.chunk_count, 1)

    def test_upload_chunk_count_increments_across_multiple_chunks(self):
        self._upload(sequence=0)
        self._upload(sequence=1)
        result = self._upload(sequence=2)

        self.assertEqual(result["chunk_count"], 3)

    def test_upload_chunk_requires_exactly_one_source(self):
        with self.assertRaises(frappe.ValidationError):
            self._upload(audio_b64=None, file=None)

    def test_upload_chunk_rejects_when_both_sources_given(self):
        with self.assertRaises(frappe.ValidationError):
            self._upload(audio_b64=TINY_AUDIO_B64, file="some-file")

    def test_upload_chunk_requires_sequence(self):
        with self.assertRaises(frappe.ValidationError):
            self._upload(sequence=None)

    def test_upload_chunk_requires_running_meeting(self):
        meeting_api.stop_recording(self.meeting["meeting_name"])
        with self.assertRaises(frappe.ValidationError):
            self._upload(sequence=0)

    def test_upload_chunk_rejects_oversized_payload(self):
        from huf.ai import audio_service

        oversized = base64.b64encode(b"0" * (audio_service.MAX_AUDIO_FILE_SIZE + 1)).decode("ascii")
        with self.assertRaises(frappe.ValidationError):
            self._upload(sequence=0, audio_b64=oversized)


if __name__ == "__main__":
    unittest.main()
