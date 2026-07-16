# Copyright (c) 2026, Huf and Contributors
# For license information, please see license.txt

"""
Public API for audio transcription.

Clean, dedicated endpoint for API/SDK clients on top of the canonical
audio service (``huf.ai.audio_service``). Chat endpoints and the
``transcribe_audio`` agent tool wrap the same service.

Guest access is not allowed: the whitelisted method requires an
authenticated session by default.
"""

import frappe
from frappe import _
from frappe.utils import cint

from huf.ai import audio_service


@frappe.whitelist()
def transcribe(
    file_id: str = None,
    b64data: str = None,
    filename: str = None,
    agent: str = None,
    conversation: str = None,
    language: str = None,
    model: str = None,
    create_message: bool = False,
):
    """
    Transcribe an audio file via the canonical audio service.

    Provide either an existing Frappe File (``file_id``) or a base64
    upload (``b64data`` + ``filename``).

    Args:
        file_id: Existing Frappe File document ID (preferred).
        b64data: Base64 audio data, with or without a data-URL prefix.
        filename: Original file name (required with ``b64data``).
        agent: Agent whose STT configuration/provider is used (required).
        conversation: Agent Conversation to attach the result message to.
        language: Optional language code (ISO 639-1, e.g. "en", "es").
        model: Optional explicit STT model override.
        create_message: Create an Agent Message with the transcript
            (requires ``conversation``). Default: False.

    Returns:
        dict: {"success", "transcript", "file_id", "file_url",
               "message_id", "stt_model", "provider", "language"}
    """
    if not agent:
        frappe.throw(_("agent is required"))

    if file_id and (b64data or filename):
        frappe.throw(_("Provide either file_id or b64data with filename, not both"))

    if not file_id and not (b64data and filename):
        frappe.throw(_("Provide either file_id or b64data with filename"))

    if cint(create_message) and not conversation:
        frappe.throw(_("conversation is required when create_message is set"))

    file_url = None
    if not file_id:
        saved = audio_service.save_audio_upload(filename, b64data, is_private=1)
        file_id = saved["file_id"]
        file_url = saved["file_url"]

    result = audio_service.transcribe_audio_file(
        file_id=file_id,
        agent_name=agent,
        language=language,
        model=model,
    )

    if not result.get("success"):
        return result

    transcript = result["text"]

    message_id = None
    if cint(create_message):
        try:
            message_doc = audio_service.create_audio_user_message(
                conversation,
                file_id,
                transcript,
                metadata={"agent_name": agent},
            )
            message_id = message_doc.name if message_doc else None
        except Exception as e:
            frappe.log_error(
                title="Audio Transcription Message Creation",
                message=f"Error creating Agent Message for transcription: {e!s}",
            )

    return {
        "success": True,
        "transcript": transcript,
        "file_id": file_id,
        "file_url": result.get("file_url") or file_url,
        "message_id": message_id,
        "stt_model": result.get("stt_model"),
        "provider": result.get("provider"),
        "language": result.get("language"),
        "duration_ms": None,
    }
