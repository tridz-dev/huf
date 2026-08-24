# Copyright (c) 2026, Huf and Contributors
# For license information, please see license.txt

import unittest
from unittest.mock import patch

import frappe

from huf.ai.meetings import meeting_api, meeting_summary


class TestMeetingSummary(unittest.TestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._meetings = []
        self.meeting_name = meeting_api.create_meeting()["meeting_name"]
        self._meetings.append(self.meeting_name)
        meeting = frappe.get_doc("Meeting", self.meeting_name)
        meeting.transcript = "Alice: Let's ship the feature.\nBob: Agreed."
        meeting.status = "Summarizing"
        meeting.save(ignore_permissions=True)

    def tearDown(self):
        frappe.set_user("Administrator")
        for name in self._meetings:
            try:
                frappe.delete_doc("Meeting", name, ignore_permissions=True, force=True)
            except Exception:
                pass
        frappe.db.commit()

    def test_prompt_includes_full_context(self):
        meeting = frappe.get_doc("Meeting", self.meeting_name)
        meeting.title = "Launch sync"
        meeting.description = "Weekly launch review"
        meeting.participants = "Alice, Bob"
        meeting.save(ignore_permissions=True)

        prompt = meeting_summary._build_summary_prompt(meeting)

        self.assertIn(meeting.transcript, prompt)
        self.assertIn("Launch sync", prompt)
        self.assertIn("Weekly launch review", prompt)
        self.assertIn("Alice, Bob", prompt)

    def test_prompt_omits_missing_context(self):
        meeting = frappe.get_doc("Meeting", self.meeting_name)

        prompt = meeting_summary._build_summary_prompt(meeting)

        self.assertIn(meeting.transcript, prompt)
        self.assertNotIn("Meeting title", prompt)
        self.assertNotIn("Meeting description", prompt)
        self.assertNotIn("Participants", prompt)

    def test_success_sets_summary_and_completes(self):
        with patch(
            "huf.ai.meetings.meeting_summary.run_agent_sync",
            return_value={
                "success": True,
                "status": "Success",
                "response": "## Headline\nShipping the feature.",
                "agent_run_id": "Agent Run 1",
            },
        ):
            meeting_summary.run_meeting_summary(self.meeting_name)

        meeting = frappe.get_doc("Meeting", self.meeting_name)
        self.assertEqual(meeting.summary, "## Headline\nShipping the feature.")
        self.assertEqual(meeting.summary_agent_run, "Agent Run 1")
        self.assertEqual(meeting.status, "Completed")

    def test_failure_sets_failed_and_preserves_transcript(self):
        transcript_before = frappe.get_doc("Meeting", self.meeting_name).transcript

        with patch(
            "huf.ai.meetings.meeting_summary.run_agent_sync",
            return_value={"success": False, "status": "Failed", "error": "provider down"},
        ):
            meeting_summary.run_meeting_summary(self.meeting_name)

        meeting = frappe.get_doc("Meeting", self.meeting_name)
        self.assertEqual(meeting.status, "Failed")
        self.assertEqual(meeting.transcript, transcript_before)
        self.assertFalse(meeting.summary)

    def test_exception_sets_failed_and_preserves_transcript(self):
        transcript_before = frappe.get_doc("Meeting", self.meeting_name).transcript

        with patch(
            "huf.ai.meetings.meeting_summary.run_agent_sync",
            side_effect=RuntimeError("boom"),
        ), patch("frappe.log_error"):
            meeting_summary.run_meeting_summary(self.meeting_name)

        meeting = frappe.get_doc("Meeting", self.meeting_name)
        self.assertEqual(meeting.status, "Failed")
        self.assertEqual(meeting.transcript, transcript_before)

    def test_retry_summary_job_reinvokes_run_meeting_summary(self):
        with patch(
            "huf.ai.meetings.meeting_summary.run_agent_sync",
            return_value={
                "success": True,
                "status": "Success",
                "response": "## Headline\nRetried summary.",
                "agent_run_id": "Agent Run 2",
            },
        ) as mock_run:
            meeting_summary.retry_summary_job(self.meeting_name)

        mock_run.assert_called_once()
        meeting = frappe.get_doc("Meeting", self.meeting_name)
        self.assertEqual(meeting.status, "Completed")
        self.assertEqual(meeting.summary, "## Headline\nRetried summary.")
