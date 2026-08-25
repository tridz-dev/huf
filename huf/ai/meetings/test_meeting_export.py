# Copyright (c) 2026, Huf and Contributors
# For license information, please see license.txt

import unittest

import frappe

from huf.ai.meetings import meeting_api, meeting_export


class TestMeetingExport(unittest.TestCase):
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

    def test_download_transcript_requires_transcript(self):
        name = self._create(title="Standup")
        with self.assertRaises(frappe.ValidationError):
            meeting_export.download_transcript(name)

    def test_download_minutes_requires_summary(self):
        name = self._create(title="Standup")
        with self.assertRaises(frappe.ValidationError):
            meeting_export.download_minutes(name)

    def test_download_transcript_sets_response(self):
        name = self._create(title="Standup", participants="Alice, Bob")
        doc = frappe.get_doc("Meeting", name)
        doc.transcript = "Alice: hello there\nBob: hi"
        doc.save(ignore_permissions=True)

        frappe.response.clear()
        meeting_export.download_transcript(name)

        self.assertEqual(frappe.response["filename"], f"{name}-transcript.txt")
        self.assertEqual(frappe.response["type"], "download")
        content = frappe.response["filecontent"]
        self.assertTrue(content)
        text = content.decode("utf-8")
        self.assertIn("Standup", text)
        self.assertIn("Alice, Bob", text)
        self.assertIn("Alice: hello there", text)

    def test_download_minutes_sets_response_with_transcript(self):
        name = self._create(title="Planning Sync", participants="Carol")
        doc = frappe.get_doc("Meeting", name)
        doc.transcript = "Carol: let's plan the sprint"
        doc.summary = "## Headline\nSprint planning\n\n## Action Items\n- Carol to file tickets"
        doc.save(ignore_permissions=True)

        frappe.response.clear()
        meeting_export.download_minutes(name)

        self.assertEqual(frappe.response["filename"], f"{name}-minutes.md")
        self.assertEqual(frappe.response["type"], "download")
        content = frappe.response["filecontent"]
        self.assertTrue(content)
        text = content.decode("utf-8")
        self.assertIn("Planning Sync", text)
        self.assertIn("Sprint planning", text)
        self.assertIn("Carol to file tickets", text)
        self.assertIn("## Full Transcript", text)
        self.assertIn("Carol: let's plan the sprint", text)


if __name__ == "__main__":
    unittest.main()
