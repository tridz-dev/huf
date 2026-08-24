# Copyright (c) 2026, Huf and Contributors
# For license information, please see license.txt

"""
Transcription pipeline for Meeting recordings.

``transcribe_meeting_chunk`` is enqueued once per uploaded chunk (see
``huf.ai.meetings.meeting_recording.upload_chunk`` and
``huf.ai.meetings.meeting_api.retry_chunk_transcription``); it resolves the
Meeting Summary Agent's STT configuration through the existing
``huf.ai.audio_service`` reuse surface and writes the chunk's transcript.
Once a Meeting is Stopped and every chunk has reached a terminal state,
``finalize_meeting`` assembles ``Meeting.transcript`` and hands off to the
summary step (``huf.ai.meetings.meeting_summary.run_meeting_summary``,
built in Phase 5).
"""

import time

import frappe
from frappe.utils import cint, flt, get_datetime, time_diff_in_seconds

from huf.ai import audio_service

TRANSCRIPTION_AGENT = "Meeting Summary Agent"
MAX_RETRY_COUNT = 3
RETRY_BACKOFF_SECONDS = 5
FINALIZE_POLL_SECONDS = 5
TERMINAL_UPLOAD_STATUSES = ("Transcribed", "Failed")


def transcribe_meeting_chunk(chunk_name: str):
    chunk = frappe.get_doc("Meeting Recording Chunk", chunk_name)
    chunk.upload_status = "Transcribing"
    chunk.save(ignore_permissions=True)
    frappe.db.commit()
    _emit_processing_status(chunk.meeting, "Transcribing")

    result = audio_service.transcribe_audio_file(
        file_id=chunk.audio_file,
        agent_name=TRANSCRIPTION_AGENT,
    )

    if not result.get("success"):
        _handle_transcription_failure(chunk, result.get("error") or "Transcription failed")
        return

    chunk.transcript_text = result.get("transcript")
    chunk.upload_status = "Transcribed"
    chunk.transcription_error = None
    chunk.save(ignore_permissions=True)
    frappe.db.commit()
    _emit_processing_status(chunk.meeting, "Transcribing")

    _maybe_finalize_meeting(chunk.meeting)


def _handle_transcription_failure(chunk, error_message: str):
    chunk.retry_count = cint(chunk.retry_count) + 1
    chunk.transcription_error = error_message

    if chunk.retry_count < MAX_RETRY_COUNT:
        chunk.upload_status = "Uploaded"
        chunk.save(ignore_permissions=True)
        frappe.db.commit()

        time.sleep(RETRY_BACKOFF_SECONDS * chunk.retry_count)
        frappe.enqueue(
            "huf.ai.meetings.meeting_transcription.transcribe_meeting_chunk",
            queue="default",
            chunk_name=chunk.name,
        )
        return

    chunk.upload_status = "Failed"
    chunk.save(ignore_permissions=True)
    frappe.db.commit()
    _emit_processing_status(chunk.meeting, "Transcribing")

    _maybe_finalize_meeting(chunk.meeting)


def _maybe_finalize_meeting(meeting_name: str):
    meeting_status = frappe.db.get_value("Meeting", meeting_name, "status")
    if meeting_status != "Stopped":
        return

    if not _all_chunks_terminal(meeting_name):
        return

    frappe.enqueue(
        "huf.ai.meetings.meeting_transcription.finalize_meeting",
        queue="default",
        meeting_name=meeting_name,
    )


def _all_chunks_terminal(meeting_name: str) -> bool:
    statuses = frappe.get_all(
        "Meeting Recording Chunk",
        filters={"meeting": meeting_name},
        pluck="upload_status",
    )
    if not statuses:
        return False

    return all(status in TERMINAL_UPLOAD_STATUSES for status in statuses)


def _chunk_progress(meeting_name: str) -> tuple:
    """Return (chunks_transcribed, chunks_total) for the meeting's chunks."""
    statuses = frappe.get_all(
        "Meeting Recording Chunk",
        filters={"meeting": meeting_name},
        pluck="upload_status",
    )
    chunks_transcribed = sum(1 for status in statuses if status == "Transcribed")
    return chunks_transcribed, len(statuses)


def _emit_processing_status(meeting_name: str, status: str):
    """Publish a ``meeting_processing_status`` realtime event to the meeting owner.

    Mirrors ``huf.ai.agent_integration._emit_conversation_title_updated``: the
    job runs off the request/session context, so the target user is resolved
    from the record's owner rather than ``frappe.session.user``, and any
    publish failure is swallowed as a non-critical UI notification.
    """
    try:
        owner = frappe.db.get_value("Meeting", meeting_name, "owner")
        if not owner:
            return

        chunks_transcribed, chunks_total = _chunk_progress(meeting_name)
        frappe.publish_realtime(
            event=f"meeting:{meeting_name}",
            message={
                "type": "meeting_processing_status",
                "meeting": meeting_name,
                "status": status,
                "chunks_transcribed": chunks_transcribed,
                "chunks_total": chunks_total,
            },
            user=owner,
        )
    except (RuntimeError, TypeError, ValueError, KeyError, AttributeError,
            frappe.DoesNotExistError, frappe.ValidationError, frappe.PermissionError) as exc:
        frappe.logger("huf").debug(f"Meeting processing status publish failed: {exc!s}")


def finalize_meeting(meeting_name: str):
    meeting = frappe.get_doc("Meeting", meeting_name)

    if meeting.status != "Stopped" or not _all_chunks_terminal(meeting_name):
        time.sleep(FINALIZE_POLL_SECONDS)
        frappe.enqueue(
            "huf.ai.meetings.meeting_transcription.finalize_meeting",
            queue="default",
            meeting_name=meeting_name,
        )
        return

    chunks = frappe.get_all(
        "Meeting Recording Chunk",
        filters={"meeting": meeting_name},
        fields=["name", "sequence", "upload_status", "transcript_text", "client_started_at", "duration_seconds"],
        order_by="sequence asc",
    )

    transcript, duration_seconds = _assemble_transcript(meeting, chunks)

    meeting.transcript = transcript
    meeting.duration_seconds = duration_seconds
    meeting.status = "Summarizing"
    meeting.save(ignore_permissions=True)
    frappe.db.commit()
    _emit_processing_status(meeting_name, "Summarizing")

    frappe.enqueue(
        "huf.ai.meetings.meeting_summary.run_meeting_summary",
        queue="default",
        meeting_name=meeting_name,
    )


def _assemble_transcript(meeting, chunks: list) -> tuple:
    started_at = meeting.started_at and get_datetime(meeting.started_at)

    lines = []
    duration_seconds = flt(meeting.duration_seconds)

    for chunk in chunks:
        timestamp = _format_timestamp(started_at, chunk.get("client_started_at"))

        if chunk.get("upload_status") == "Transcribed":
            lines.append(f"[{timestamp}] {chunk.get('transcript_text') or ''}".rstrip())
        else:
            lines.append(f"[{timestamp}] [this part could not be transcribed]")

        chunk_end = flt(chunk.get("duration_seconds"))
        if chunk.get("client_started_at") and started_at:
            offset = time_diff_in_seconds(get_datetime(chunk["client_started_at"]), started_at)
            duration_seconds = max(duration_seconds, offset + chunk_end)

    return "\n".join(lines), duration_seconds


def _format_timestamp(started_at, client_started_at) -> str:
    if not started_at or not client_started_at:
        return "00:00:00"

    offset_seconds = int(max(0, time_diff_in_seconds(get_datetime(client_started_at), started_at)))
    hours, remainder = divmod(offset_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
