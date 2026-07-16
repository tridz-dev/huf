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
    file_path: str = None,
    agent: str = None,
    conversation: str = None,
    language: str = None,
    model: str = None,
    create_message: bool = False,
):
    """
    Transcribe an audio file via the canonical audio service.

    Provide exactly one source: an existing Frappe File (``file_id``), a
    base64 upload (``b64data`` + ``filename``), or a server-side
    filesystem path (``file_path``, e.g. an scp/wget drop inside an
    allowed audio import directory).

    Args:
        file_id: Existing Frappe File document ID (preferred).
        b64data: Base64 audio data, with or without a data-URL prefix.
        filename: Original file name (required with ``b64data``).
        file_path: Absolute server path inside an allowed audio import
            directory. Requires the System Manager role. With
            ``create_message`` the file is first imported as a Frappe
            File (so the message has a playable attachment); otherwise
            it is transcribed in place with no File record.
        agent: Agent whose STT configuration/provider is used (required).
        conversation: Agent Conversation to attach the result message to.
        language: Optional language code (ISO 639-1, e.g. "en", "es").
        model: Optional explicit STT model override.
        create_message: Create an Agent Message with the transcript
            (requires ``conversation``). Default: False.

    Returns:
        dict: {"success", "transcript", "file_id", "file_url",
               "local_path", "message_id", "stt_model", "provider",
               "language"}
    """
    if not agent:
        frappe.throw(_("agent is required"))

    sources = sum(1 for source in (file_id, file_path, b64data or filename) if source)
    if sources > 1:
        frappe.throw(_("Provide exactly one of file_id, b64data with filename, or file_path"))
    if sources == 0:
        frappe.throw(_("Provide one of file_id, b64data with filename, or file_path"))

    if file_path:
        # Server filesystem paths must not be probeable by ordinary users.
        frappe.only_for("System Manager")

    if cint(create_message) and not conversation:
        frappe.throw(_("conversation is required when create_message is set"))

    file_url = None
    if file_path and cint(create_message):
        # Import the server-drop as a Frappe File so the resulting message
        # has a playable attachment, then proceed as the file_id path.
        saved = audio_service.import_local_audio(file_path, is_private=1)
        file_id = saved["file_id"]
        file_url = saved["file_url"]
        file_path = None
    elif not file_id and not file_path:
        saved = audio_service.save_audio_upload(filename, b64data, is_private=1)
        file_id = saved["file_id"]
        file_url = saved["file_url"]

    result = audio_service.transcribe_audio_file(
        file_id=file_id,
        local_path=file_path,
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
        "local_path": result.get("local_path"),
        "message_id": message_id,
        "stt_model": result.get("stt_model"),
        "provider": result.get("provider"),
        "language": result.get("language"),
        "duration_ms": None,
    }
