# Copyright (c) 2026, Huf and Contributors
# For license information, please see license.txt

import unittest
from unittest.mock import patch

import frappe

from huf.ai.meetings import meeting_api, meeting_transcription


class TestMeetingTranscription(unittest.TestCase):
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

    def _make_chunk(self, **kwargs):
        chunk = frappe.get_doc({
            "doctype": "Meeting Recording Chunk",
            "meeting": self.meeting["meeting_name"],
            "sequence": kwargs.pop("sequence", 0),
            "audio_file": kwargs.pop("audio_file", None),
            "upload_status": kwargs.pop("upload_status", "Uploaded"),
            "client_started_at": kwargs.pop("client_started_at", None),
            "duration_seconds": kwargs.pop("duration_seconds", 30),
            **kwargs,
        })
        chunk.insert(ignore_permissions=True)
        return chunk

    def test_successful_transcription_updates_chunk(self):
        chunk = self._make_chunk()

        with patch(
            "huf.ai.audio_service.transcribe_audio_file",
            return_value={"success": True, "transcript": "hello world"},
        ):
            meeting_transcription.transcribe_meeting_chunk(chunk.name)

        chunk.reload()
        self.assertEqual(chunk.upload_status, "Transcribed")
        self.assertEqual(chunk.transcript_text, "hello world")
        self.assertFalse(chunk.transcription_error)

    def test_failure_increments_retry_and_reaches_failed_after_max_retries(self):
        chunk = self._make_chunk()

        with (
            patch(
                "huf.ai.audio_service.transcribe_audio_file",
                return_value={"success": False, "error": "provider down"},
            ),
            patch("time.sleep"),
            patch("frappe.enqueue") as mock_enqueue,
        ):
            for _ in range(meeting_transcription.MAX_RETRY_COUNT):
                meeting_transcription.transcribe_meeting_chunk(chunk.name)
                chunk.reload()

        self.assertEqual(chunk.retry_count, meeting_transcription.MAX_RETRY_COUNT)
        self.assertEqual(chunk.upload_status, "Failed")
        self.assertEqual(chunk.transcription_error, "provider down")
        self.assertEqual(mock_enqueue.call_count, meeting_transcription.MAX_RETRY_COUNT - 1)

    def test_finalize_meeting_reenqueues_when_chunks_not_terminal(self):
        self._make_chunk(upload_status="Transcribing")
        meeting_api.stop_recording(self.meeting["meeting_name"])

        with patch("time.sleep") as mock_sleep, patch("frappe.enqueue") as mock_enqueue:
            meeting_transcription.finalize_meeting(self.meeting["meeting_name"])

        mock_sleep.assert_called_once()
        mock_enqueue.assert_called_once_with(
            "huf.ai.meetings.meeting_transcription.finalize_meeting",
            queue="default",
            meeting_name=self.meeting["meeting_name"],
        )

        meeting_doc = frappe.get_doc("Meeting", self.meeting["meeting_name"])
        self.assertEqual(meeting_doc.status, "Stopped")

    def test_finalize_meeting_assembles_transcript_with_gap_markers_and_timestamps(self):
        meeting_doc = frappe.get_doc("Meeting", self.meeting["meeting_name"])
        started_at = meeting_doc.started_at

        self._make_chunk(
            sequence=0,
            upload_status="Transcribed",
            transcript_text="first segment",
            client_started_at=started_at,
            duration_seconds=30,
        )
        self._make_chunk(
            sequence=1,
            upload_status="Failed",
            client_started_at=frappe.utils.add_to_date(started_at, seconds=30),
            duration_seconds=30,
        )
        self._make_chunk(
            sequence=2,
            upload_status="Transcribed",
            transcript_text="third segment",
            client_started_at=frappe.utils.add_to_date(started_at, seconds=90),
            duration_seconds=30,
        )

        meeting_api.stop_recording(self.meeting["meeting_name"])

        with patch("frappe.enqueue") as mock_enqueue:
            meeting_transcription.finalize_meeting(self.meeting["meeting_name"])

        meeting_doc.reload()
        self.assertEqual(meeting_doc.status, "Summarizing")
        self.assertIn("[00:00:00] first segment", meeting_doc.transcript)
        self.assertIn("[00:00:30] [this part could not be transcribed]", meeting_doc.transcript)
        self.assertIn("[00:01:30] third segment", meeting_doc.transcript)
        self.assertGreaterEqual(meeting_doc.duration_seconds, 120)

        mock_enqueue.assert_called_once_with(
            "huf.ai.meetings.meeting_summary.run_meeting_summary",
            queue="default",
            meeting_name=self.meeting["meeting_name"],
        )


if __name__ == "__main__":
    unittest.main()
