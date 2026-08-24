# Copyright (c) 2026, Huf and Contributors
# For license information, please see license.txt

"""
Summary generation for Meetings.

``run_meeting_summary`` is enqueued once ``huf.ai.meetings.meeting_transcription.
finalize_meeting`` has assembled ``Meeting.transcript`` and set
``Meeting.status = "Summarizing"``. It runs the seeded "Meeting Summary Agent"
(see ``huf.install.create_meeting_summary_agent``) against the transcript and
writes the resulting Markdown summary back onto the Meeting.

``retry_summary_job`` is enqueued by ``huf.ai.meetings.meeting_api.retry_summary``
after it resets a failed Meeting back to "Summarizing".
"""

import frappe

from huf.ai.agent_integration import run_agent_sync
from huf.ai.meetings.meeting_transcription import _emit_processing_status

SUMMARY_AGENT = "Meeting Summary Agent"


def _build_summary_prompt(meeting) -> str:
    parts = ["Meeting transcript:", meeting.transcript]

    if meeting.title:
        parts.append(f"Meeting title: {meeting.title}")
    if meeting.description:
        parts.append(f"Meeting description: {meeting.description}")
    if meeting.participants:
        parts.append(f"Participants: {meeting.participants}")

    return "\n\n".join(parts)


def run_meeting_summary(meeting_name: str):
    meeting = frappe.get_doc("Meeting", meeting_name)
    prompt = _build_summary_prompt(meeting)

    try:
        result = run_agent_sync(
            agent_name=SUMMARY_AGENT,
            prompt=prompt,
            channel_id="meeting-summary",
            external_id=meeting_name,
            now=True,
        )
    except Exception:
        frappe.log_error(title="Meeting Summary failed", message=frappe.get_traceback())
        result = {}

    if result.get("success") and result.get("status") == "Success":
        meeting.summary = result.get("response")
        meeting.summary_agent_run = result.get("agent_run_id")
        meeting.status = "Completed"
    else:
        meeting.status = "Failed"

    meeting.save(ignore_permissions=True)
    frappe.db.commit()
    _emit_processing_status(meeting_name, meeting.status)


def retry_summary_job(meeting_name: str):
    run_meeting_summary(meeting_name)
