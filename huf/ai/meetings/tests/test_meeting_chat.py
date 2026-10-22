# Copyright (c) 2026, Huf and Contributors
# For license information, please see license.txt

import unittest
from unittest.mock import patch

import frappe

from huf.ai.meetings import meeting_api, meeting_chat


class TestTruncateTranscript(unittest.TestCase):
    def test_under_limit_returned_unchanged(self):
        transcript = "Alice: hello.\nBob: hi." * 10
        self.assertLess(len(transcript), meeting_chat.MAX_TRANSCRIPT_CHARS)
        self.assertEqual(meeting_chat._truncate_transcript(transcript), transcript)

    def test_over_limit_truncated_to_tail_with_marker(self):
        transcript = "x" * (meeting_chat.MAX_TRANSCRIPT_CHARS + 500)
        # Make the tail distinguishable from the truncated-away head.
        transcript = transcript[:-10] + "END-MARKER"

        result = meeting_chat._truncate_transcript(transcript)

        self.assertTrue(result.startswith("[transcript truncated — showing the most recent portion]\n"))
        self.assertTrue(result.endswith("END-MARKER"))
        self.assertEqual(len(result) - len("[transcript truncated — showing the most recent portion]\n"), meeting_chat.MAX_TRANSCRIPT_CHARS)


class TestMeetingChat(unittest.TestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._meetings = []
        self.meeting_name = meeting_api.create_meeting()["meeting_name"]
        self._meetings.append(self.meeting_name)
        meeting = frappe.get_doc("Meeting", self.meeting_name)
        meeting.transcript = "Alice: Let's ship the feature.\nBob: Agreed."
        meeting.summary = "## Headline\nShipping the feature.\n\n## Key Points\n- Ship it\n\n## Decisions\n- Ship now\n\n## Action Items\n- None identified."
        meeting.status = "Completed"
        meeting.save(ignore_permissions=True)

    def tearDown(self):
        frappe.set_user("Administrator")
        for name in self._meetings:
            try:
                frappe.delete_doc("Meeting", name, ignore_permissions=True, force=True)
            except Exception:
                pass
        frappe.db.commit()

    def _make_agent_run(self):
        """
        Meeting.summary_agent_run is a Link to Agent Run, so a fake string
        id fails Frappe's link validation on save — create a real row so
        tests exercise the same save() path production code does.
        """
        doc = frappe.get_doc({"doctype": "Agent Run"}).insert(ignore_permissions=True)
        self.addCleanup(lambda: frappe.delete_doc("Agent Run", doc.name, ignore_permissions=True, force=True))
        return doc.name

    def test_ask_meeting_success_inserts_two_messages(self):
        with patch(
            "huf.ai.meetings.meeting_chat.run_agent_sync",
            return_value={"success": True, "status": "Success", "response": "They agreed to ship it."},
        ):
            result = meeting_chat.ask_meeting(self.meeting_name, "What was decided?")

        self.assertEqual(result["reply"], "They agreed to ship it.")
        messages = meeting_chat.get_chat_history(self.meeting_name)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].role, "user")
        self.assertEqual(messages[0].content, "What was decided?")
        self.assertEqual(messages[1].role, "assistant")
        self.assertEqual(messages[1].content, "They agreed to ship it.")

    def test_ask_meeting_failure_records_error_and_does_not_raise(self):
        with (
            patch(
                "huf.ai.meetings.meeting_chat.run_agent_sync",
                return_value={"success": False, "status": "Failed", "error": "provider down"},
            ),
        ):
            result = meeting_chat.ask_meeting(self.meeting_name, "What was decided?")

        self.assertEqual(result["error"], "provider down")
        messages = meeting_chat.get_chat_history(self.meeting_name)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[1].role, "assistant")
        self.assertEqual(messages[1].error, "provider down")

    def test_ask_meeting_requires_transcript(self):
        meeting = frappe.get_doc("Meeting", self.meeting_name)
        meeting.transcript = None
        meeting.save(ignore_permissions=True)

        with self.assertRaises(frappe.ValidationError):
            meeting_chat.ask_meeting(self.meeting_name, "hi")

    def test_revise_summary_success_updates_meeting(self):
        new_summary = "## Headline\nRevised.\n\n## Key Points\n- Ship it\n\n## Decisions\n- Ship now\n\n## Action Items\n- None identified."
        agent_run_name = self._make_agent_run()
        with patch(
            "huf.ai.meetings.meeting_chat.run_agent_sync",
            return_value={"success": True, "status": "Success", "response": new_summary, "agent_run_id": agent_run_name},
        ):
            result = meeting_chat.revise_summary(self.meeting_name, "Make it shorter")

        self.assertEqual(result["summary"], new_summary)
        meeting = frappe.get_doc("Meeting", self.meeting_name)
        self.assertEqual(meeting.summary, new_summary)
        self.assertEqual(meeting.summary_agent_run, agent_run_name)

        messages = meeting_chat.get_chat_history(self.meeting_name)
        self.assertEqual(messages[-1].role, "assistant")
        self.assertTrue(messages[-1].applied_to_summary)

    def test_revise_summary_failure_leaves_summary_untouched(self):
        original_summary = frappe.get_doc("Meeting", self.meeting_name).summary

        with patch(
            "huf.ai.meetings.meeting_chat.run_agent_sync",
            return_value={"success": False, "status": "Failed", "error": "provider down"},
        ):
            result = meeting_chat.revise_summary(self.meeting_name, "Make it shorter")

        self.assertEqual(result["error"], "provider down")
        meeting = frappe.get_doc("Meeting", self.meeting_name)
        self.assertEqual(meeting.summary, original_summary)

    def test_revise_summary_requires_existing_summary(self):
        meeting = frappe.get_doc("Meeting", self.meeting_name)
        meeting.summary = None
        meeting.save(ignore_permissions=True)

        with self.assertRaises(frappe.ValidationError):
            meeting_chat.revise_summary(self.meeting_name, "Make it shorter")

    def test_get_chat_history_ordered_oldest_first(self):
        with patch(
            "huf.ai.meetings.meeting_chat.run_agent_sync",
            return_value={"success": True, "status": "Success", "response": "First reply."},
        ):
            meeting_chat.ask_meeting(self.meeting_name, "First question")
        with patch(
            "huf.ai.meetings.meeting_chat.run_agent_sync",
            return_value={"success": True, "status": "Success", "response": "Second reply."},
        ):
            meeting_chat.ask_meeting(self.meeting_name, "Second question")

        messages = meeting_chat.get_chat_history(self.meeting_name)
        self.assertEqual([m.content for m in messages], [
            "First question", "First reply.", "Second question", "Second reply.",
        ])


if __name__ == "__main__":
    unittest.main()
