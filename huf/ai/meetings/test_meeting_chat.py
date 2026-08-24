# Copyright (c) 2026, Huf and Contributors
# For license information, please see license.txt

import unittest
from unittest.mock import patch

import frappe

from huf.ai.meetings import meeting_api, meeting_chat


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
        with patch(
            "huf.ai.meetings.meeting_chat.run_agent_sync",
            return_value={"success": True, "status": "Success", "response": new_summary, "agent_run_id": "Agent Run 2"},
        ):
            result = meeting_chat.revise_summary(self.meeting_name, "Make it shorter")

        self.assertEqual(result["summary"], new_summary)
        meeting = frappe.get_doc("Meeting", self.meeting_name)
        self.assertEqual(meeting.summary, new_summary)
        self.assertEqual(meeting.summary_agent_run, "Agent Run 2")

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
