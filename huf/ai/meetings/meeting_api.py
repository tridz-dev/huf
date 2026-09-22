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

from huf.ai.meetings import meeting_summary, meeting_transcription
from huf.ai.meetings.meeting_transcription import MODEL_NOT_CONFIGURED_MESSAGE, _agent_is_configured

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
        # Meetings created through this user-facing endpoint are owned by the
        # user, not the system — is_system_owned defaults to 1 to protect
        # system/fixture-seeded meetings from deletion; explicitly clear it
        # here so a user can delete their own recordings (see delete_meeting).
        "is_system_owned": 0,
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

    Supports two grouped pseudo-statuses:
    - ``status="Processing"``: maps to ``status in [Stopped, Transcribing, Summarizing]``
    - ``status="Recording"``: maps to ``status in [Recording, Paused]``

    For any other status value, uses exact-match filtering.

    Returns:
        dict: {"meetings": list, "has_more": bool}
    """
    start = cint(start)
    limit = cint(limit) or 20

    filters = {}
    if status:
        if status == "Processing":
            filters["status"] = ["in", ["Stopped", "Transcribing", "Summarizing"]]
        elif status == "Recording":
            filters["status"] = ["in", ["Recording", "Paused"]]
        else:
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
            "failed_step",
            "last_error",
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
def get_meeting_status_counts():
    """
    Return a permission-aware grouped count of Meetings by status.

    Zero-fills all statuses from the Meeting doctype's status field so the
    frontend doesn't need defensive fallback logic for missing statuses.

    Returns:
        dict: {"counts": {"Recording": n, "Paused": n, ..., zero-filled for all statuses}}
    """
    # Get all status options from the Meeting doctype's status field
    status_field = frappe.get_meta("Meeting").get_field("status")
    status_options = [opt.strip() for opt in status_field.options.split("\n") if opt.strip()]

    # Seed counts dict with all statuses defaulting to 0
    counts = {status: 0 for status in status_options}

    # Query grouped counts by status, respecting implicit permission filtering
    # (Frappe applies the permission WHERE clause automatically)
    grouped_counts = frappe.get_list(
        "Meeting",
        fields=["status", {"COUNT": "*", "as": "cnt"}],
        group_by="status",
        order_by="status asc",
        as_list=False,
    )

    # Overlay query results on top of zero-seeded dict
    for row in grouped_counts:
        status = row.get("status")
        if status in counts:
            counts[status] = row.get("cnt", 0)

    return {"counts": counts}


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

    # Fetch the chunk's parent meeting name without loading the full doc.
    # This prevents an info disclosure vulnerability: we check permission
    # on the parent meeting BEFORE loading the chunk, so "chunk doesn't exist"
    # and "chunk exists but no access" fail indistinguishably.
    meeting_name = frappe.db.get_value("Meeting Recording Chunk", chunk_name, "meeting")
    if not meeting_name:
        # Chunk doesn't exist, or the lookup failed. Fail with generic error.
        frappe.throw(_("Not permitted to access this Meeting"), frappe.PermissionError)

    meeting = _get_meeting(meeting_name, "write")
    chunk = frappe.get_doc("Meeting Recording Chunk", chunk_name)

    if not _agent_is_configured(meeting_transcription.TRANSCRIPTION_AGENT):
        frappe.throw(_(MODEL_NOT_CONFIGURED_MESSAGE))

    chunk.upload_status = "Uploaded"
    chunk.transcription_error = None
    chunk.retry_count = cint(chunk.retry_count) + 1
    chunk.save()

    meeting.failed_step = None
    meeting.last_error = None
    meeting.save()

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

    if not _agent_is_configured(meeting_summary.SUMMARY_AGENT):
        frappe.throw(_(MODEL_NOT_CONFIGURED_MESSAGE))

    meeting.status = "Summarizing"
    meeting.failed_step = None
    meeting.last_error = None
    meeting.save()

    frappe.enqueue(
        "huf.ai.meetings.meeting_summary.retry_summary_job",
        queue="default",
        meeting_name=meeting.name,
    )

    return {"meeting_name": meeting.name, "status": meeting.status}


@frappe.whitelist()
def delete_meeting(meeting_name: str):
    """
    Delete a Meeting and cascade-delete all related Meeting Chat Message
    and Meeting Recording Chunk records.

    Honors the on_trash guards on all three doctypes (Meeting, Meeting Chat Message,
    Meeting Recording Chunk) — system-owned meetings and their related records
    cannot be deleted.

    The cascade order is critical: delete messages and chunks FIRST
    (which are linked to the meeting via Link fields), then delete the Meeting itself.
    Reversing this order causes Frappe to throw LinkExistsError.

    Attached audio files (Attach fields on chunks) are automatically cleaned up
    by Frappe's delete_doc since they have attached_to_doctype/attached_to_name set.

    Returns:
        dict: {"success": True}
    """
    meeting = _get_meeting(meeting_name, "delete")

    # Check the on_trash guard: system-owned meetings cannot be deleted.
    if meeting.is_system_owned:
        frappe.throw(
            _("System-owned meetings cannot be deleted."),
            title=_("Meeting Protected"),
        )

    try:
        # Delete all Chat Messages for this meeting.
        chat_messages = frappe.get_all(
            "Meeting Chat Message",
            filters={"meeting": meeting_name},
            fields=["name"],
        )
        for msg in chat_messages:
            # Ownership was already enforced above via _get_meeting(meeting_name, "delete");
            # these child records don't grant delete rights to Huf User in DocPerm, so we
            # bypass that check here rather than widen DocPerm for all users.
            frappe.delete_doc("Meeting Chat Message", msg.name, ignore_permissions=True)

        # Delete all Recording Chunks for this meeting.
        chunks = frappe.get_all(
            "Meeting Recording Chunk",
            filters={"meeting": meeting_name},
            fields=["name"],
        )
        for chunk in chunks:
            frappe.delete_doc("Meeting Recording Chunk", chunk.name, ignore_permissions=True)

        # Finally, delete the Meeting itself.
        frappe.delete_doc("Meeting", meeting_name)

        # Commit transaction to finalize all deletes.
        frappe.db.commit()

    except Exception as exc:  # noqa: BLE001
        # Rollback on any error to ensure we don't leave a partially deleted meeting.
        frappe.db.rollback()
        frappe.log_error(f"Failed to delete meeting {meeting_name}: {exc}")
        frappe.throw(
            _("Failed to delete meeting. Please try again."),
            exc=exc,
        )

    return {"success": True}
