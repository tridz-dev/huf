# Copyright (c) 2026, Huf and Contributors
# For license information, please see license.txt

"""
Download endpoints for a completed Meeting's transcript and Minutes of
Meeting (MoM) export.

Both methods reuse ``meeting_api._get_meeting`` for permission checks (the
same ``frappe.get_doc`` + ``has_permission`` pattern used across
``huf.ai.meetings``) and use the standard Frappe file-download response
(``frappe.response["filename"]`` / ``["filecontent"]`` / ``["type"]``) to
trigger a browser download from a whitelisted method, matching
``huf.ai.skills.exporter.download_skill_huf``.
"""

import frappe
from frappe import _

from huf.ai.meetings.meeting_api import _get_meeting


def _meeting_metadata_lines(meeting) -> list[str]:
    lines = [f"Title: {meeting.title or meeting.name}"]
    if meeting.started_at:
        lines.append(f"Date: {meeting.started_at}")
    if meeting.duration_seconds:
        lines.append(f"Duration (seconds): {meeting.duration_seconds}")
    if meeting.participants:
        lines.append(f"Participants: {meeting.participants}")
    return lines


@frappe.whitelist()
def download_transcript(meeting_name: str):
    """Download a Meeting's raw transcript as a plain-text file."""
    meeting = _get_meeting(meeting_name, "read")

    if not meeting.transcript:
        frappe.throw(_("This Meeting does not have a transcript yet"))

    header = "\n".join(_meeting_metadata_lines(meeting))
    content = f"{header}\n\n{meeting.transcript}"

    frappe.response["filename"] = f"{meeting.name}-transcript.txt"
    frappe.response["filecontent"] = content.encode("utf-8")
    frappe.response["type"] = "download"


@frappe.whitelist()
def download_minutes(meeting_name: str):
    """Download a Meeting's Minutes of Meeting (MoM) as a Markdown file.

    Includes the summary verbatim (it already carries its own ## sections)
    and, when available, appends the full transcript so a single file can
    capture both the MoM and the full transcript.
    """
    meeting = _get_meeting(meeting_name, "read")

    if not meeting.summary:
        frappe.throw(_("This Meeting does not have a summary yet"))

    title = meeting.title or "Meeting"
    metadata = "\n".join(_meeting_metadata_lines(meeting)[1:])

    parts = [f"# {title} — Minutes of Meeting"]
    if metadata:
        parts.append(metadata)
    parts.append(meeting.summary)

    if meeting.transcript:
        parts.append("## Full Transcript")
        parts.append(meeting.transcript)

    content = "\n\n".join(parts)

    frappe.response["filename"] = f"{meeting.name}-minutes.md"
    frappe.response["filecontent"] = content.encode("utf-8")
    frappe.response["type"] = "download"
