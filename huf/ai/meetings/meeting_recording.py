# Copyright (c) 2026, Huf and Contributors
# For license information, please see license.txt

"""
Chunk-upload ingest for Meeting recordings.

Generalizes ``huf.ai.audio_service.save_audio_upload``'s validation
(extension/MIME allowlist, base64 decode, size cap) to a meeting/chunk
context instead of the conversation/message context that
``huf.ai.audio_api`` uses. Does not modify ``audio_service`` - only reuses
its constants and file-saving helper.
"""

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, now_datetime

from huf.ai import audio_service
from huf.ai.meetings.meeting_api import RUNNING_STATUSES, _get_meeting

# How long a chunk may sit in "Uploaded" status without being transcribed before
# the recovery sweep re-enqueues its job (e.g. if the initial enqueue call failed
# or the process died mid-request). 10 minutes is a safe threshold for legitimate
# processing time without being too lenient for stuck jobs.
STUCK_CHUNK_THRESHOLD_MINUTES = 10

# How long a Meeting may sit in "Recording"/"Paused" with no new chunk
# activity before the stale-recording sweep auto-stops it (K-table row 1:
# "auto-stop after N hours of no new chunk"). 6 hours comfortably covers any
# legitimate single-session meeting (including a long, heavily paused one)
# while still reclaiming abandoned tab/device-sleep sessions within the day.
STALE_RECORDING_THRESHOLD_HOURS = 6


@frappe.whitelist()
def upload_chunk(
    meeting: str,
    sequence,
    client_started_at: str = None,
    duration_seconds=None,
    audio_b64: str = None,
    file: str = None,
):
    """
    Upload one recorded audio chunk for a Meeting.

    Provide exactly one audio source: ``audio_b64`` (base64 data, optionally
    with a data-URL prefix and a ``filename``-free extension guess of
    ``webm``) or ``file`` (an existing Frappe File ID already uploaded via
    the standard file uploader).

    Args:
        meeting: Meeting this chunk belongs to.
        sequence: Chunk order within the meeting (0-based).
        client_started_at: Meeting-relative timestamp the chunk started at.
        duration_seconds: Chunk duration in seconds.
        audio_b64: Base64 audio data, with or without a data-URL prefix.
        file: Existing Frappe File ID holding the chunk audio.

    Returns:
        dict: {"chunk_name": str, "sequence": int, "upload_status": str,
               "chunk_count": int}
    """
    meeting_doc = _get_meeting(meeting, "write")

    # Allow Recording, Paused, and Stopped (late chunk uploads after auto-stop or user stop).
    if meeting_doc.status not in ("Recording", "Paused", "Stopped"):
        frappe.throw(_("Meeting is not currently recording"))

    if sequence is None:
        frappe.throw(_("sequence is required"))
    sequence = cint(sequence)

    sources = sum(1 for source in (audio_b64, file) if source)
    if sources != 1:
        frappe.throw(_("Provide exactly one of audio_b64 or file"))

    if file:
        file_doc = frappe.get_doc("File", file)
        audio_service.validate_audio_filename(file_doc.file_name)
        audio_file = file_doc.name
    else:
        # No attached_to_doctype/attached_to_name here: the chunk doc that
        # this file will belong to doesn't exist yet (it's created below),
        # and File.validate_attachment_references() throws "Attached To
        # Name must be a string or an integer" if attached_to_doctype is
        # set while attached_to_name is empty. The file is linked to its
        # chunk via the attached_to_doctype/attached_to_name db_set below,
        # once the chunk has a name.
        saved = audio_service.save_audio_upload(
            f"chunk-{meeting}-{sequence}.webm",
            audio_b64,
            is_private=1,
        )
        audio_file = saved["file_id"]

    chunk = frappe.get_doc({
        "doctype": "Meeting Recording Chunk",
        "meeting": meeting,
        "sequence": sequence,
        "audio_file": audio_file,
        "upload_status": "Uploaded",
        "client_started_at": client_started_at,
        "duration_seconds": duration_seconds,
        # See meeting_api.create_meeting: is_system_owned defaults to 1 to
        # protect system/fixture-seeded records; user-uploaded chunks belong
        # to the user and must be deletable via Meeting's cascade delete.
        "is_system_owned": 0,
    })
    chunk.insert()

    if audio_file:
        frappe.db.set_value(
            "File",
            audio_file,
            {
                "attached_to_doctype": "Meeting Recording Chunk",
                "attached_to_name": chunk.name,
            },
        )

    meeting_doc.db_set("chunk_count", cint(meeting_doc.chunk_count) + 1)

    # The transcription job itself (huf.ai.meetings.meeting_transcription.
    # transcribe_meeting_chunk) is built in Phase 4; the dotted path is
    # referenced here so Phase 4's job name/signature is already pinned.
    try:
        frappe.enqueue(
            "huf.ai.meetings.meeting_transcription.transcribe_meeting_chunk",
            queue="default",
            chunk_name=chunk.name,
        )
    except Exception as exc:  # noqa: BLE001
        # If enqueue fails (Redis down, serialization error, etc.), mark the chunk
        # as Failed so it surfaces through the retry UI instead of silently vanishing.
        chunk.upload_status = "Failed"
        chunk.transcription_error = f"Failed to queue transcription job: {exc!s}"
        chunk.save()
        frappe.db.commit()
        # Re-raise so the caller knows the enqueue failed
        frappe.throw(
            _("Failed to queue transcription job. Chunk marked as failed for manual retry."),
            exc=exc
        )

    # For late uploads to Stopped meetings, trigger finalize_meeting so the meeting
    # doesn't stay stuck in Stopped status if it had already reached a terminal check.
    if meeting_doc.status == "Stopped":
        frappe.enqueue(
            "huf.ai.meetings.meeting_transcription._maybe_finalize_meeting",
            queue="default",
            meeting_name=meeting_doc.name,
        )

    return {
        "chunk_name": chunk.name,
        "sequence": chunk.sequence,
        "upload_status": chunk.upload_status,
        "chunk_count": meeting_doc.chunk_count,
    }


def cleanup_stale_recordings():
    """
    Scheduled sweep (see ``huf/hooks.py`` ``scheduler_events["hourly"]``):
    auto-stops any Meeting left in ``Recording``/``Paused`` whose
    ``modified`` timestamp is older than ``STALE_RECORDING_THRESHOLD_HOURS``.

    Covers the "recording interrupted" recovery case from PLAN.md K row 1
    (tab crash, device sleep, abandoned session) — without this sweep, a
    Meeting with no explicit Stop would sit in a running status forever.
    ``modified`` is used as the staleness signal rather than a dedicated
    "last chunk received" field because every chunk upload (``upload_chunk``
    above) and every explicit pause/resume both touch the Meeting doc
    (``meeting_doc.db_set``/``meeting.save()``), so ``modified`` already
    tracks "last activity" without a schema change.

    Mirrors ``huf.ai.meetings.meeting_api.stop_recording``'s transition
    (status -> "Stopped", ``stopped_at`` stamped) so a stale meeting is
    picked up by the normal finalize/transcription pipeline exactly as if
    the user had pressed Stop themselves.
    """
    cutoff = add_to_date(now_datetime(), hours=-STALE_RECORDING_THRESHOLD_HOURS)

    stale_meetings = frappe.get_all(
        "Meeting",
        filters={"status": ["in", RUNNING_STATUSES], "modified": ["<", cutoff]},
        pluck="name",
    )

    for meeting_name in stale_meetings:
        try:
            meeting = frappe.get_doc("Meeting", meeting_name)
            meeting.status = "Stopped"
            meeting.stopped_at = now_datetime()
            meeting.save(ignore_permissions=True)

            frappe.enqueue(
                "huf.ai.meetings.meeting_transcription.finalize_meeting",
                queue="default",
                meeting_name=meeting.name,
            )
        except Exception:  # noqa: BLE001
            frappe.log_error(
                title="Stale meeting cleanup failed",
                message=frappe.get_traceback(),
            )

    if stale_meetings:
        frappe.db.commit()


def recover_stuck_uploaded_chunks():
    """
    Scheduled sweep (see ``huf/hooks.py`` ``scheduler_events["hourly"]``):
    find and re-enqueue transcription jobs for chunks stuck in ``Uploaded``
    status for longer than ``STUCK_CHUNK_THRESHOLD_MINUTES``.

    Covers the edge case where the initial ``frappe.enqueue()`` call never ran
    (e.g. process died mid-request) or where a chunk got into Uploaded state
    through some other path. Re-enqueuing ensures the transcription job is
    eventually attempted, allowing the meeting to proceed to finalization
    instead of staying stuck forever.
    """
    cutoff = add_to_date(now_datetime(), minutes=-STUCK_CHUNK_THRESHOLD_MINUTES)

    stuck_chunks = frappe.get_all(
        "Meeting Recording Chunk",
        filters={
            "upload_status": "Uploaded",
            "modified": ["<", cutoff],
        },
        fields=["name", "meeting"],
    )

    for chunk_row in stuck_chunks:
        try:
            chunk = frappe.get_doc("Meeting Recording Chunk", chunk_row["name"])
            frappe.enqueue(
                "huf.ai.meetings.meeting_transcription.transcribe_meeting_chunk",
                queue="default",
                chunk_name=chunk.name,
            )
        except Exception:  # noqa: BLE001
            frappe.log_error(
                title="Stuck chunk recovery failed",
                message=frappe.get_traceback(),
            )

    if stuck_chunks:
        frappe.db.commit()
