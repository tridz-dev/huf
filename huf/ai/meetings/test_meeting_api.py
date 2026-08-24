# Copyright (c) 2026, Huf and Contributors
# For license information, please see license.txt

import unittest
from unittest.mock import patch

import frappe

from huf.ai.meetings import meeting_api


class TestMeetingApi(unittest.TestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._meetings = []

    def tearDown(self):
        frappe.set_user("Administrator")
        for name in self._meetings:
            try:
                frappe.delete_doc("Meeting", name, ignore_permissions=True, force=True)
            except Exception:
                pass
        frappe.db.commit()

    def _create(self, **kwargs):
        result = meeting_api.create_meeting(**kwargs)
        self._meetings.append(result["meeting_name"])
        return result["meeting_name"]

    def test_create_meeting_defaults_to_draft(self):
        name = self._create()
        doc = frappe.get_doc("Meeting", name)
        self.assertEqual(doc.status, "Draft")

    def test_create_meeting_with_context(self):
        name = self._create(title="Standup", description="Daily sync", participants="Alice, Bob")
        doc = frappe.get_doc("Meeting", name)
        self.assertEqual(doc.title, "Standup")
        self.assertEqual(doc.description, "Daily sync")
        self.assertEqual(doc.participants, "Alice, Bob")

    def test_start_pause_resume_stop_transitions(self):
        name = self._create()

        started = meeting_api.start_recording(name)
        self.assertEqual(started["status"], "Recording")
        self.assertIsNotNone(started["started_at"])

        paused = meeting_api.pause_recording(name)
        self.assertEqual(paused["status"], "Paused")

        resumed = meeting_api.resume_recording(name)
        self.assertEqual(resumed["status"], "Recording")

        stopped = meeting_api.stop_recording(name)
        self.assertEqual(stopped["status"], "Stopped")
        self.assertIsNotNone(stopped["stopped_at"])

    def test_pause_requires_recording_status(self):
        name = self._create()
        with self.assertRaises(frappe.ValidationError):
            meeting_api.pause_recording(name)

    def test_resume_requires_paused_status(self):
        name = self._create()
        meeting_api.start_recording(name)
        with self.assertRaises(frappe.ValidationError):
            meeting_api.resume_recording(name)

    def test_stop_requires_running_status(self):
        name = self._create()
        with self.assertRaises(frappe.ValidationError):
            meeting_api.stop_recording(name)

    def test_update_meeting_context_marks_completed(self):
        name = self._create()
        result = meeting_api.update_meeting_context(name, title="Renamed", participants="Carol")
        self.assertEqual(result["title"], "Renamed")
        self.assertEqual(result["participants"], "Carol")
        self.assertEqual(result["context_completed"], 1)

    def test_get_meeting_returns_ordered_chunks(self):
        name = self._create()
        for sequence in (1, 0, 2):
            frappe.get_doc({
                "doctype": "Meeting Recording Chunk",
                "meeting": name,
                "sequence": sequence,
                "upload_status": "Uploaded",
            }).insert(ignore_permissions=True)

        result = meeting_api.get_meeting(name)
        self.assertEqual(result["meeting"]["name"], name)
        self.assertEqual([c["sequence"] for c in result["chunks"]], [0, 1, 2])

    def test_list_meetings_pagination_shape(self):
        for _ in range(3):
            self._create()

        result = meeting_api.list_meetings(start=0, limit=2)
        self.assertIn("meetings", result)
        self.assertIn("has_more", result)
        self.assertLessEqual(len(result["meetings"]), 2)

    def test_list_meetings_filters_by_status(self):
        draft = self._create()
        recording = self._create()
        meeting_api.start_recording(recording)

        result = meeting_api.list_meetings(status="Recording", limit=50)
        names = [m["name"] for m in result["meetings"]]
        self.assertIn(recording, names)
        self.assertNotIn(draft, names)

    def test_retry_summary_resets_status_and_returns(self):
        # meeting_summary.retry_summary_job (Phase 5) does not exist yet;
        # frappe.enqueue is mocked so the test only exercises Phase 2's
        # status-reset behavior, not the not-yet-built job import.
        name = self._create()
        meeting_api.start_recording(name)
        meeting_api.stop_recording(name)

        with patch("frappe.enqueue") as mock_enqueue:
            result = meeting_api.retry_summary(name)

        mock_enqueue.assert_called_once()
        self.assertEqual(result["status"], "Summarizing")


if __name__ == "__main__":
    unittest.main()
