# Copyright (c) 2026, Huf and Contributors
# For license information, please see license.txt

"""
A tiny, minimal chat surface over a finalized Meeting — the "get info out,
revise the summary by prompt" alternative to a full Firefly-style meeting
copilot. ``ask_meeting`` answers questions grounded in the transcript and
summary; ``revise_summary`` regenerates ``Meeting.summary`` from a natural
language instruction. Every turn (including failures) is persisted as a
``Meeting Chat Message`` so the exchange is visible as a log, matching the
retry/failure-visibility pattern used by huf.ai.meetings.meeting_transcription
and huf.ai.meetings.meeting_summary.
"""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from huf.ai.agent_integration import run_agent_sync
from huf.ai.meetings.meeting_api import _get_meeting
from huf.ai.meetings.meeting_summary import SUMMARY_AGENT

CHAT_HISTORY_LIMIT = 10
MAX_TRANSCRIPT_CHARS = 24_000


def _truncate_transcript(transcript: str) -> str:
    """Cap the transcript text sent to the model to protect against a
    pathologically long, multi-hour meeting blowing the context window (or
    being needlessly expensive) on every chat turn. Keeps the LAST
    ``MAX_TRANSCRIPT_CHARS`` characters — the most recent portion of a
    meeting is usually more relevant for Q&A/revision than the opening — and
    prepends a marker line so it's clear (in the prompt and when debugging
    via error_log/chat history) that content was cut, not silently missing.
    This only affects what's sent to the model; the stored/displayed
    transcript is untouched."""
    if len(transcript) <= MAX_TRANSCRIPT_CHARS:
        return transcript
    return (
        "[transcript truncated — showing the most recent portion]\n"
        + transcript[-MAX_TRANSCRIPT_CHARS:]
    )


def _recent_history(meeting_name: str) -> list:
    rows = frappe.get_all(
        "Meeting Chat Message",
        filters={"meeting": meeting_name},
        fields=["role", "content"],
        order_by="creation desc",
        limit_page_length=CHAT_HISTORY_LIMIT,
    )
    return list(reversed(rows))


def _format_history(rows: list) -> str:
    lines = []
    for row in rows:
        speaker = "User" if row.role == "user" else "Assistant"
        if row.content:
            lines.append(f"{speaker}: {row.content}")
    return "\n".join(lines)


def _insert_message(meeting_name: str, role: str, content: str, error: str = None, applied_to_summary: bool = False):
    doc = frappe.get_doc({
        "doctype": "Meeting Chat Message",
        "meeting": meeting_name,
        "role": role,
        "content": content or "",
        "error": error,
        "applied_to_summary": 1 if applied_to_summary else 0,
    })
    doc.insert(ignore_permissions=True)
    return doc


@frappe.whitelist()
@rate_limit(limit=20, seconds=60)
def ask_meeting(meeting_name: str, message: str):
    """
    Answer a question about a meeting, grounded in its transcript, summary,
    and recent chat history. Never raises on model failure — the failure is
    recorded as an assistant message with ``error`` set so it stays visible
    in the chat log, and a dict with an ``error`` key is returned so the
    caller can render an inline error instead of a toast.
    """
    if not message or not message.strip():
        frappe.throw(_("message is required"))

    meeting = _get_meeting(meeting_name, "read")
    if not meeting.transcript:
        frappe.throw(_("This meeting has no transcript yet to chat about."))

    _insert_message(meeting_name, "user", message)

    history = _format_history(_recent_history(meeting_name))
    prompt_parts = [
        "You are answering questions about a specific meeting, using only the "
        "transcript, summary, and chat history below. Be concise.",
        f"Meeting transcript:\n{_truncate_transcript(meeting.transcript)}",
    ]
    if meeting.summary:
        prompt_parts.append(f"Current summary:\n{meeting.summary}")
    if history:
        prompt_parts.append(f"Recent chat:\n{history}")
    prompt_parts.append(f"User: {message}")
    prompt = "\n\n".join(prompt_parts)

    try:
        result = run_agent_sync(
            agent_name=SUMMARY_AGENT,
            prompt=prompt,
            channel_id="meeting-chat",
            external_id=meeting_name,
            now=True,
        )
    except Exception:
        frappe.log_error(title="Meeting chat failed", message=frappe.get_traceback())
        result = {}

    if result.get("success") and result.get("status") == "Success":
        reply = result.get("response")
        reply_doc = _insert_message(meeting_name, "assistant", reply)
        return {"reply": reply, "message_name": reply_doc.name}

    error_message = result.get("error") or "I couldn't process that."
    reply_doc = _insert_message(meeting_name, "assistant", "", error=error_message[:500])
    return {"error": error_message, "message_name": reply_doc.name}


@frappe.whitelist()
@rate_limit(limit=10, seconds=60)
def revise_summary(meeting_name: str, instruction: str):
    """
    Regenerate ``Meeting.summary`` from a natural-language revision
    instruction. On failure, ``meeting.summary`` is left untouched and the
    failure is recorded as a visible chat-log entry (see ``ask_meeting``).
    """
    if not instruction or not instruction.strip():
        frappe.throw(_("instruction is required"))

    meeting = _get_meeting(meeting_name, "write")
    if not meeting.summary:
        frappe.throw(_("This meeting has no summary yet to revise."))

    _insert_message(meeting_name, "user", f"Revise summary: {instruction}")

    prompt = "\n\n".join([
        "Revise the meeting summary below per the instruction. Output the "
        "complete revised summary again in the same four-section Markdown "
        "format (Headline, Key Points, Decisions, Action Items) — never a "
        "partial diff or just the changed section.",
        f"Meeting transcript:\n{_truncate_transcript(meeting.transcript)}",
        f"Current summary:\n{meeting.summary}",
        f"Revision instruction: {instruction}",
    ])

    try:
        result = run_agent_sync(
            agent_name=SUMMARY_AGENT,
            prompt=prompt,
            channel_id="meeting-chat",
            external_id=meeting_name,
            now=True,
        )
    except Exception:
        frappe.log_error(title="Meeting summary revision failed", message=frappe.get_traceback())
        result = {}

    if result.get("success") and result.get("status") == "Success":
        new_summary = result.get("response")
        meeting.summary = new_summary
        meeting.summary_agent_run = result.get("agent_run_id")
        meeting.save(ignore_permissions=True)
        frappe.db.commit()
        _insert_message(meeting_name, "assistant", new_summary, applied_to_summary=True)
        return {"summary": new_summary}

    error_message = result.get("error") or "Summary revision failed"
    _insert_message(meeting_name, "assistant", "", error=error_message[:500])
    return {"error": error_message}


@frappe.whitelist()
def get_chat_history(meeting_name: str):
    """Full chat log for a meeting, oldest first."""
    _get_meeting(meeting_name, "read")
    return frappe.get_all(
        "Meeting Chat Message",
        filters={"meeting": meeting_name},
        fields=["name", "role", "content", "applied_to_summary", "error", "creation"],
        order_by="creation asc",
    )
