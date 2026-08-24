# Copyright (c) 2026, Huf and Contributors
# For license information, please see license.txt

"""
Public API for Meeting lifecycle: create, start/pause/resume/stop, context
updates, detail/list reads, and manual retry actions.

All methods operate on a specific ``Meeting`` document and go through
standard Frappe doc permissions (``frappe.get_doc`` + ``has_permission``),
matching the pattern used by ``huf.ai.audio_api``/``huf.ai.apps_api``.
Guest access is not allowed.
"""

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

RUNNING_STATUSES = ("Recording", "Paused")


def _get_meeting(meeting_name: str, ptype: str = "read"):
    if not meeting_name:
        frappe.throw(_("meeting_name is required"))

    meeting = frappe.get_doc("Meeting", meeting_name)
    if not frappe.has_permission(doc=meeting, ptype=ptype):
        frappe.throw(_("Not permitted to access this Meeting"), frappe.PermissionError)

    return meeting


@frappe.whitelist()
def create_meeting(title: str = None, description: str = None, participants: str = None):
    """
    Create a new Meeting in Draft status.

    Returns:
        dict: {"meeting_name": str}
    """
    if not frappe.has_permission("Meeting", "create"):
        frappe.throw(_("Not permitted to create a Meeting"), frappe.PermissionError)

    meeting = frappe.get_doc({
        "doctype": "Meeting",
        "title": title,
        "description": description,
        "participants": participants,
        "status": "Draft",
    })
    meeting.insert()

    return {"meeting_name": meeting.name}


@frappe.whitelist()
def start_recording(meeting_name: str):
    """Transition a Meeting to Recording and stamp started_at."""
    meeting = _get_meeting(meeting_name, "write")

    meeting.status = "Recording"
    meeting.started_at = now_datetime()
    meeting.save()

    return {"meeting_name": meeting.name, "status": meeting.status, "started_at": meeting.started_at}


@frappe.whitelist()
def pause_recording(meeting_name: str):
    """Toggle a Recording Meeting to Paused."""
    meeting = _get_meeting(meeting_name, "write")

    if meeting.status != "Recording":
        frappe.throw(_("Meeting is not currently recording"))

    meeting.status = "Paused"
    meeting.save()

    return {"meeting_name": meeting.name, "status": meeting.status}


@frappe.whitelist()
def resume_recording(meeting_name: str):
    """Toggle a Paused Meeting back to Recording."""
    meeting = _get_meeting(meeting_name, "write")

    if meeting.status != "Paused":
        frappe.throw(_("Meeting is not currently paused"))

    meeting.status = "Recording"
    meeting.save()

    return {"meeting_name": meeting.name, "status": meeting.status}


@frappe.whitelist()
def stop_recording(meeting_name: str):
    """Transition a Meeting to Stopped and stamp stopped_at."""
    meeting = _get_meeting(meeting_name, "write")

    if meeting.status not in RUNNING_STATUSES:
        frappe.throw(_("Meeting is not currently recording or paused"))

    meeting.status = "Stopped"
    meeting.stopped_at = now_datetime()
    meeting.save()

    return {"meeting_name": meeting.name, "status": meeting.status, "stopped_at": meeting.stopped_at}


@frappe.whitelist()
def update_meeting_context(
    meeting_name: str,
    title: str = None,
    description: str = None,
    participants: str = None,
):
    """Update the post-meeting context fields (title/description/participants)."""
    meeting = _get_meeting(meeting_name, "write")

    if title is not None:
        meeting.title = title
    if description is not None:
        meeting.description = description
    if participants is not None:
        meeting.participants = participants
    meeting.context_completed = 1

    meeting.save()

    return {
        "meeting_name": meeting.name,
        "title": meeting.title,
        "description": meeting.description,
        "participants": meeting.participants,
        "context_completed": meeting.context_completed,
    }


@frappe.whitelist()
def get_meeting(meeting_name: str):
    """Return a Meeting document plus its ordered Meeting Recording Chunk rows."""
    meeting = _get_meeting(meeting_name, "read")

    chunks = frappe.get_all(
        "Meeting Recording Chunk",
        filters={"meeting": meeting_name},
        fields=[
            "name",
            "sequence",
            "audio_file",
            "upload_status",
            "client_started_at",
            "duration_seconds",
            "transcript_text",
            "transcription_error",
            "retry_count",
        ],
        order_by="sequence asc",
    )

    return {"meeting": meeting.as_dict(), "chunks": chunks}


@frappe.whitelist()
def list_meetings(start: int = 0, limit: int = 20, status: str = None, search: str = None):
    """
    Return a paginated, permission-aware list of Meetings.

    Uses the ``limit+1`` pattern: fetches one extra row to compute
    ``has_more`` without a separate count query.

    Returns:
        dict: {"meetings": list, "has_more": bool}
    """
    start = cint(start)
    limit = cint(limit) or 20

    filters = {}
    if status:
        filters["status"] = status

    or_filters = None
    if search:
        or_filters = [
            ["title", "like", f"%{search}%"],
            ["description", "like", f"%{search}%"],
            ["transcript", "like", f"%{search}%"],
        ]

    meetings = frappe.get_list(
        "Meeting",
        filters=filters,
        or_filters=or_filters,
        fields=[
            "name",
            "title",
            "description",
            "status",
            "started_at",
            "stopped_at",
            "duration_seconds",
            "chunk_count",
            "summary",
            "modified",
        ],
        order_by="modified desc",
        start=start,
        page_length=limit + 1,
    )

    has_more = len(meetings) > limit
    meetings = meetings[:limit]

    return {"meetings": meetings, "has_more": has_more}


@frappe.whitelist()
def retry_chunk_transcription(chunk_name: str):
    """
    Reset a failed chunk back to Uploaded and re-enqueue transcription.

    The transcription job itself (``huf.ai.meetings.meeting_transcription.
    transcribe_meeting_chunk``) is built in Phase 4; the dotted path is
    referenced here so Phase 2's enqueue call already matches the job name
    and signature Phase 4 will implement.
    """
    if not chunk_name:
        frappe.throw(_("chunk_name is required"))

    chunk = frappe.get_doc("Meeting Recording Chunk", chunk_name)
    _get_meeting(chunk.meeting, "write")

    chunk.upload_status = "Uploaded"
    chunk.transcription_error = None
    chunk.retry_count = cint(chunk.retry_count) + 1
    chunk.save()

    frappe.enqueue(
        "huf.ai.meetings.meeting_transcription.transcribe_meeting_chunk",
        queue="default",
        chunk_name=chunk.name,
    )

    return {"chunk_name": chunk.name, "upload_status": chunk.upload_status}


@frappe.whitelist()
def retry_summary(meeting_name: str):
    """
    Re-invoke summary generation for a meeting whose summary step failed.

    The summary job itself (``huf.ai.meetings.meeting_summary.
    retry_summary_job``) is built in Phase 5; the dotted path is referenced
    here so Phase 2's enqueue call already matches the job name Phase 5
    will implement.
    """
    meeting = _get_meeting(meeting_name, "write")

    meeting.status = "Summarizing"
    meeting.save()

    frappe.enqueue(
        "huf.ai.meetings.meeting_summary.retry_summary_job",
        queue="default",
        meeting_name=meeting.name,
    )

    return {"meeting_name": meeting.name, "status": meeting.status}
