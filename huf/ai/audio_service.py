# Copyright (c) 2026, Huf and Contributors
# For license information, please see license.txt

"""
Canonical backend audio service for Huf.

Single home for audio upload guardrails, STT configuration resolution,
audio transcription, and audio user-message creation. Chat endpoints
(``huf.ai.agent_chat``), the ``transcribe_audio`` agent tool
(``huf.ai.sdk_tools.handle_transcribe_audio``), and the public audio API
(``huf.ai.audio_api``) are thin wrappers around these functions.

Separation of concerns:
- ``save_audio_upload``        -> validate + store base64 audio as a Frappe File
- ``resolve_local_audio_path`` -> validate a server-side path (scp/wget drops)
- ``import_local_audio``       -> turn a server-drop file into a Frappe File
- ``resolve_stt_config``       -> pick STT model/provider/credentials
- ``transcribe_audio_file``    -> pure transcription (no messages, no sockets)
- ``create_audio_user_message``-> persist an Agent Message for a transcript
"""

import base64
import binascii
import mimetypes
import os

import frappe
from frappe import _
from frappe.utils.file_manager import save_file

# Maximum accepted size for a decoded audio upload (25 MB).
MAX_AUDIO_FILE_SIZE = 25 * 1024 * 1024

# Extensions accepted for audio upload/transcription. webm/mp4 are
# included because browsers record audio into those containers.
ALLOWED_AUDIO_EXTENSIONS = {
    "webm",
    "wav",
    "mp3",
    "m4a",
    "ogg",
    "oga",
    "flac",
    "mp4",
    "aac",
}

# MIME types accepted for uploaded audio. ``video/webm`` and ``video/mp4``
# are accepted because MediaRecorder audio commonly uses those containers.
ALLOWED_AUDIO_MIME_TYPES = {
    "audio/webm",
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/x-m4a",
    "audio/ogg",
    "application/ogg",
    "audio/flac",
    "audio/x-flac",
    "audio/aac",
    "audio/x-aac",
    "audio/mp4a-latm",
    "audio/x-hx-aac-adts",
    "video/webm",
    "video/mp4",
}

# Providers that have no LiteLLM transcription endpoint and are handled
# through the multimodal completion adapter instead.
MULTIMODAL_STT_PROVIDERS = ("google", "gemini", "vertex_ai")


def _get_file_extension(filename: str) -> str:
    """Return the lowercase file extension without the dot."""
    return (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""


def is_audio_file(filename: str, mime_type: str = None) -> bool:
    """
    Return True when a file should be routed to audio transcription.

    Reuses the same allowlists as upload validation
    (``ALLOWED_AUDIO_EXTENSIONS`` / ``ALLOWED_AUDIO_MIME_TYPES``), so any
    file that would be accepted as an audio upload is classified as audio
    here. Unlike ``validate_audio_filename`` this never throws - it is a
    passive classifier for routing decisions (e.g. doc-event triggers).

    Args:
        filename: File name used for the extension check.
        mime_type: Optional known MIME type (e.g. guessed from the file
            name). When omitted, it is guessed from the filename.
    """
    if mime_type and mime_type.lower() in ALLOWED_AUDIO_MIME_TYPES:
        return True

    if _get_file_extension(filename) in ALLOWED_AUDIO_EXTENSIONS:
        return True

    if not mime_type:
        guessed = mimetypes.guess_type(filename)[0]
        if guessed and guessed.lower() in ALLOWED_AUDIO_MIME_TYPES:
            return True

    return False


def validate_audio_filename(filename: str) -> None:
    """Guardrail: only allow known audio extensions/MIME types."""
    ext = _get_file_extension(filename)
    if ext not in ALLOWED_AUDIO_EXTENSIONS:
        frappe.throw(
            _("Unsupported audio file type: '{0}'. Allowed types: {1}.").format(
                ext or _("none"), ", ".join(sorted(ALLOWED_AUDIO_EXTENSIONS))
            )
        )

    mime_type = mimetypes.guess_type(filename)[0]
    if mime_type and mime_type not in ALLOWED_AUDIO_MIME_TYPES:
        frappe.throw(
            _("Unsupported audio MIME type: '{0}'.").format(mime_type)
        )


def decode_audio_base64(b64data: str) -> bytes:
    """Guardrail: strip any data-URL prefix and strictly decode base64 audio."""
    if "," in b64data:
        b64data = b64data.split(",", 1)[1]

    try:
        audio_bytes = base64.b64decode(b64data.strip(), validate=True)
    except (binascii.Error, ValueError):
        frappe.throw(_("Invalid base64 audio data"))

    if len(audio_bytes) == 0:
        frappe.throw(_("Audio recording was empty (0 bytes)."))

    if len(audio_bytes) > MAX_AUDIO_FILE_SIZE:
        frappe.throw(
            _("Audio file exceeds the maximum allowed size of {0} MB.").format(
                MAX_AUDIO_FILE_SIZE // (1024 * 1024)
            )
        )

    return audio_bytes


def save_audio_upload(
    filename: str,
    b64data: str,
    *,
    attached_to_doctype: str = None,
    attached_to_name: str = None,
    is_private: int = 1,
) -> dict:
    """
    Validate and store a base64 audio upload as a Frappe File.

    Enforces guardrails: filename/extension allowlist, strict base64
    validation, non-empty payload, and a maximum file size of 25 MB.

    Args:
        filename: Original file name (used for extension/MIME validation).
        b64data: Base64 audio data, with or without a data-URL prefix.
        attached_to_doctype: Optional DocType the file is attached to.
        attached_to_name: Optional document name the file is attached to.
        is_private: Whether the stored file is private (default: 1).

    Returns:
        dict: {"file_id": str, "file_url": str, "file_name": str}
    """
    if not filename or not b64data:
        frappe.throw(_("Filename and audio data are required"))

    validate_audio_filename(filename)
    audio_bytes = decode_audio_base64(b64data)

    try:
        saved_file = save_file(
            filename,
            audio_bytes,
            attached_to_doctype,
            attached_to_name,
            is_private=is_private,
        )
    except Exception as e:
        frappe.log_error(message=f"Save File Failed: {e}", title="Save File Failed")
        frappe.throw(_("Could not save audio file to database."))

    file_id = None
    file_url = None
    file_name = filename
    if hasattr(saved_file, "name"):
        file_id = saved_file.name
        file_url = saved_file.file_url
        file_name = getattr(saved_file, "file_name", None) or filename
    elif isinstance(saved_file, dict):
        file_id = saved_file.get("name")
        file_url = saved_file.get("file_url")
        file_name = saved_file.get("file_name") or filename

    if not file_id:
        frappe.throw(_("File was saved but ID could not be retrieved."))

    return {"file_id": file_id, "file_url": file_url, "file_name": file_name}


def _get_allowed_audio_import_dirs() -> list:
    """
    Return the realpath'd root directories from which server-side audio
    imports (scp/wget/cron drops) are allowed.

    Always includes the site's ``private/audio_imports`` directory; extra
    roots can be added via the ``audio_import_dirs`` list in site config.
    This only defines the security boundary - no directory is created.
    """
    roots = [frappe.get_site_path("private", "audio_imports")]
    extra_dirs = frappe.get_site_config().get("audio_import_dirs") or []
    roots.extend(extra_dirs)
    return [os.path.realpath(root) for root in roots]


def resolve_local_audio_path(file_path: str) -> str:
    """
    Resolve and validate a server-side audio file path for transcription.

    Guardrails against path traversal and symlink escapes:
    - The path must be absolute.
    - Symlinks are resolved (``os.path.realpath``) and the real path must
      live inside one of the allowed import roots
      (``_get_allowed_audio_import_dirs``).
    - The target must exist and be a regular file, pass the audio
      filename allowlist (``validate_audio_filename``), and respect the
      maximum size cap (``MAX_AUDIO_FILE_SIZE``).

    Args:
        file_path: Absolute path to an audio file on the server.

    Returns:
        str: The resolved real path.
    """
    if not file_path or not isinstance(file_path, str) or not os.path.isabs(file_path):
        frappe.throw(_("An absolute file path is required."))

    real_path = os.path.realpath(file_path)

    allowed_roots = _get_allowed_audio_import_dirs()
    if not any(real_path == root or real_path.startswith(root + os.sep) for root in allowed_roots):
        frappe.throw(_("Path is outside the allowed audio import directories."))

    if not os.path.exists(real_path) or not os.path.isfile(real_path):
        frappe.throw(_("Audio file not found: {0}").format(file_path))

    validate_audio_filename(os.path.basename(real_path))

    if os.path.getsize(real_path) > MAX_AUDIO_FILE_SIZE:
        frappe.throw(
            _("Audio file exceeds the maximum allowed size of {0} MB.").format(
                MAX_AUDIO_FILE_SIZE // (1024 * 1024)
            )
        )

    return real_path


def import_local_audio(
    file_path: str,
    *,
    attach_to_doctype: str = None,
    attach_to_name: str = None,
    is_private: int = 1,
) -> dict:
    """
    Import a server-side audio file (scp/wget/cron drop) as a Frappe File.

    Validates the path via ``resolve_local_audio_path`` (the same security
    boundary used for in-place local transcription), reads the bytes, and
    stores them through ``save_audio_upload`` so all upload guardrails
    (extension/MIME allowlist, size cap) apply. Useful when a server-drop
    should become a normal File for message/chat integration.

    Args:
        file_path: Absolute path to an audio file on the server.
        attach_to_doctype: Optional DocType the file is attached to.
        attach_to_name: Optional document name the file is attached to.
        is_private: Whether the stored file is private (default: 1).

    Returns:
        dict: {"file_id": str, "file_url": str, "file_name": str}
    """
    real_path = resolve_local_audio_path(file_path)

    with open(real_path, "rb") as audio_file:
        audio_bytes = audio_file.read()

    b64data = base64.b64encode(audio_bytes).decode("ascii")
    return save_audio_upload(
        os.path.basename(real_path),
        b64data,
        attached_to_doctype=attach_to_doctype,
        attached_to_name=attach_to_name,
        is_private=is_private,
    )


def _get_default_stt_model(provider_name: str) -> str:
    """
    Get default STT model for a provider.
    """
    defaults = {
        "openai": "whisper-1",
        "azure": "whisper-1",
        "groq": "groq/whisper-large-v3",
        "deepgram": "deepgram/nova-2",
        # Multimodal providers transcribe via completion with audio input
        "google": "gemini/gemini-2.5-flash",
        "gemini": "gemini/gemini-2.5-flash",
        "vertex_ai": "gemini/gemini-2.5-flash",
    }
    return defaults.get(provider_name.lower())


def _find_transcription_model(provider: str) -> str:
    """
    Prefer an AI Model record flagged with the ``Transcription`` modality
    for the given provider over the hardcoded provider default map.
    """
    try:
        models = frappe.get_all(
            "AI Model",
            filters={"provider": provider, "modalities": ["like", "%Transcription%"]},
            fields=["model_name"],
            order_by="modified desc",
            limit=1,
        )
    except Exception:
        return None

    return models[0].model_name if models else None


def resolve_stt_config(agent_name: str = None, model: str = None) -> dict:
    """
    Resolve the STT model, API key, and provider for audio transcription.

    Priority (highest -> lowest):
    1. Explicit ``model`` parameter (tool call / API override)
    2. Agent-level STT configuration (``Agent.stt_model``)
    3. Provider default, preferring AI Model records whose ``modalities``
       contain ``Transcription`` over the hardcoded provider default map

    Returns:
        dict: {"stt_model", "api_key", "provider_name", "provider_doc", "source"}
    """
    from huf.ai.providers.litellm import _normalize_model_name

    agent_doc = frappe.get_doc("Agent", agent_name) if agent_name else None

    if model:
        stt_provider_name = None
        search_model = model
        if "/" in search_model:
            search_model = search_model.split("/")[-1]

        model_doc = frappe.get_all("AI Model", filters={"name": search_model}, fields=["provider"])
        if model_doc:
            stt_provider_name = model_doc[0].provider
        elif "/" in model:
            provider_slug = model.split("/")[0]
            provs = frappe.get_all("AI Provider", filters={"slug": provider_slug}, fields=["name"])
            if provs:
                stt_provider_name = provs[0].name

        if not stt_provider_name:
            if agent_doc:
                stt_provider_name = agent_doc.provider
            else:
                raise ValueError(
                    f"Could not determine provider for STT model '{model}'. "
                    "Pass an agent or a provider-prefixed model."
                )

        provider_doc = frappe.get_doc("AI Provider", stt_provider_name)
        api_key = provider_doc.get_password("api_key")
        if not api_key:
            raise ValueError(f"API key is not configured for provider '{provider_doc.provider_name}'.")

        provider_name = provider_doc.provider_name.lower()
        normalized = _normalize_model_name(model, stt_provider_name)
        return {
            "stt_model":     normalized,
            "api_key":       api_key,
            "provider_name": provider_name,
            "provider_doc":  provider_doc,
            "source":        "tool_param",
        }

    if agent_doc and getattr(agent_doc, "stt_model", None):
        stt_model_doc = frappe.get_doc("AI Model", agent_doc.stt_model)
        if not stt_model_doc.provider:
            raise ValueError(f"STT model '{agent_doc.stt_model}' has no provider linked.")

        stt_provider_doc = frappe.get_doc("AI Provider", stt_model_doc.provider)
        api_key = stt_provider_doc.get_password("api_key")
        if not api_key:
            raise ValueError(f"API key is not configured for STT provider '{stt_provider_doc.provider_name}'.")

        provider_name = stt_provider_doc.provider_name.lower()
        normalized = _normalize_model_name(stt_model_doc.model_name, stt_model_doc.provider)
        return {
            "stt_model":     normalized,
            "api_key":       api_key,
            "provider_name": provider_name,
            "provider_doc":  stt_provider_doc,
            "source":        "agent_config",
        }

    if not agent_doc:
        raise ValueError("An agent is required to resolve STT configuration.")

    provider_doc = frappe.get_doc("AI Provider", agent_doc.provider)
    api_key = provider_doc.get_password("api_key")
    if not api_key:
        raise ValueError(f"API key is not configured for provider '{provider_doc.provider_name}'.")

    provider_name = provider_doc.provider_name.lower()
    stt_model = _find_transcription_model(agent_doc.provider)

    if not stt_model:
        stt_model = _get_default_stt_model(provider_name)

    if not stt_model:
        raise ValueError(
            f"No transcription model available for provider '{provider_doc.provider_name}'. "
            "Set Agent.stt_model or add an AI Model with the Transcription modality."
        )

    normalized = _normalize_model_name(stt_model, agent_doc.provider)
    return {
        "stt_model":     normalized,
        "api_key":       api_key,
        "provider_name": provider_name,
        "provider_doc":  provider_doc,
        "source":        "provider_default",
    }


def _resolve_file_doc(file_id: str = None, file_url: str = None):
    """Resolve a Frappe File document from an ID or URL."""
    if file_id:
        return frappe.get_doc("File", file_id)

    file_doc = None
    if file_url:
        try:
            file_doc = frappe.get_doc("File", {"file_url": file_url})
        except Exception:
            # Try alternative lookup
            file_name = file_url.replace("/files/", "")
            file_doc = frappe.get_doc("File", {"file_name": file_name})
    return file_doc


def transcribe_audio_file(
    file_id: str = None,
    file_url: str = None,
    *,
    local_path: str = None,
    agent_name: str = None,
    language: str = None,
    model: str = None,
) -> dict:
    """
    Pure audio transcription: resolve the file, call the STT provider,
    return the transcript. Creates no Agent Message and emits no socket
    events - callers decide how to persist/display the result.

    Args:
        file_id: File document ID (preferred) - File must exist in Frappe.
        file_url: File URL/path (alternative) - e.g., "/files/audio.mp3".
        local_path: Absolute server path inside an allowed audio import
            directory (mutually exclusive with ``file_id``/``file_url``).
            Skips the Frappe File lookup and transcribes in place.
        agent_name: Agent whose STT configuration/provider is used.
        language: Optional language code (ISO 639-1, e.g. "en", "es").
        model: Optional explicit STT model override.

    Returns:
        dict: {"success", "transcript", "text" (alias), "file_id",
               "file_url", "local_path", "stt_model", "provider",
               "language"}
    """
    try:
        if not agent_name:
            return {"success": False, "error": "Agent name not found in context"}

        agent_doc = frappe.get_doc("Agent", agent_name)

        # Get audio file
        file_doc = None
        resolved_local_path = None
        if local_path and (file_id or file_url):
            return {"success": False, "error": "local_path is mutually exclusive with file_id/file_url"}
        if local_path:
            resolved_local_path = resolve_local_audio_path(local_path)
            file_path = resolved_local_path
        elif file_id:
            try:
                file_doc = _resolve_file_doc(file_id=file_id)
            except Exception as e:
                return {"success": False, "error": f"File not found: {e!s}"}
        elif file_url:
            file_doc = _resolve_file_doc(file_url=file_url)
            if not file_doc:
                return {"success": False, "error": f"File not found at URL: {file_url}"}
        else:
            return {"success": False, "error": "One of file_id, file_url, or local_path is required"}

        if file_doc:
            # Get file path for LiteLLM (accepts file path or file-like object)
            try:
                file_path = file_doc.get_full_path()
            except Exception as e:
                return {"success": False, "error": f"Error getting file path: {e!s}"}

        # Determine transcription model
        try:
            stt_config = resolve_stt_config(agent_name, model=model)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}

        normalized_model = stt_config["stt_model"]
        api_key          = stt_config["api_key"]
        provider_name    = stt_config["provider_name"]

        transcribed_text = _call_stt_provider(
            provider_name=provider_name,
            normalized_model=normalized_model,
            api_key=api_key,
            file_path=file_path,
            language=language,
        )
        if isinstance(transcribed_text, dict):
            # Error payload from the provider call
            return transcribed_text

        if not transcribed_text:
            return {"success": False, "error": "Transcription returned empty result"}

        return {
            "success":    True,
            "transcript": transcribed_text,
            "text":       transcribed_text,  # compatibility alias
            "file_id":    file_doc.name if file_doc else None,
            "file_url":   file_doc.file_url if file_doc else None,
            "local_path": resolved_local_path,
            "stt_model":  normalized_model,
            "provider":   provider_name,
            "language":   language or "auto-detected",
            "stt_source": stt_config["source"],
        }

    except Exception as e:
        frappe.log_error(title="Audio Transcription Service", message=f"Audio transcription error: {e!s}")
        return {"success": False, "error": str(e)}


def _call_stt_provider(
    *,
    provider_name: str,
    normalized_model: str,
    api_key: str,
    file_path: str,
    language: str = None,
):
    """
    Call the STT provider and return the transcript text.

    Gemini/Google/Vertex are handled through a multimodal completion call
    with base64 audio (no LiteLLM transcription endpoint); all other
    providers go through ``litellm.transcription``.

    Returns the transcript string, or an error dict on provider failure.
    """
    import litellm

    if provider_name in MULTIMODAL_STT_PROVIDERS:
        with open(file_path, "rb") as audio_file:
            audio_data = audio_file.read()

        mime_type = mimetypes.guess_type(file_path)[0]
        if not mime_type:
            mime_type = "audio/mp3"

        if file_path.lower().endswith(".webm") or mime_type == "video/webm":
            mime_type = "audio/webm"

        base64_audio = base64.b64encode(audio_data).decode("utf-8")
        audio_format = _get_file_extension(file_path) or "mp3"
        if audio_format == "m4a":
            audio_format = "mp4"

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Please transcribe this audio exactly as it is spoken. Do not add any extra commentary or formatting. If there are multiple languages, transcribe them as spoken. If it is silent, just write [Silence]."},
                    {"type": "input_audio", "input_audio": {"data": base64_audio, "format": audio_format}},
                ],
            }
        ]

        try:
            response = litellm.completion(
                model=normalized_model,
                messages=messages,
                api_key=api_key,
            )
            return response.choices[0].message.content
        except Exception as e:
            return {"success": False, "error": f"Transcription failed: {e!s}"}

    # Standard transcription handling (OpenAI, Deepgram, Groq, etc.)
    transcription_params = {
        "model": normalized_model,
        "file": file_path,
        "api_key": api_key,
    }

    # Add optional parameters
    if language:
        transcription_params["language"] = language

    with open(file_path, "rb") as audio_file:
        transcription_params["file"] = audio_file
        try:
            response = litellm.transcription(**transcription_params)
        except Exception as e:
            return {"success": False, "error": f"Transcription failed: {e!s}"}

    # Extract text from response
    # LiteLLM transcription returns a dict with 'text' key or object
    if hasattr(response, "text"):
        return response.text
    if isinstance(response, dict):
        return response.get("text", "")
    return str(response)


def create_audio_user_message(
    conversation_id: str,
    file_id: str,
    transcript: str,
    metadata: dict = None,
):
    """
    Create (or update) the ``Agent Message`` representing an audio user
    message: kind=Audio, voice_message file, stt_model, conversation
    counters, and the realtime socket event.

    Args:
        conversation_id: Agent Conversation the message belongs to.
        file_id: Frappe File holding the raw audio (optional).
        transcript: Transcribed text stored as the message content.
        metadata: Optional dict with keys:
            - agent_name: Agent used for the transcription.
            - message_id: Existing Agent Message to update (upsert).
            - agent_run_id: Agent Run to link on new messages.
            - stt_model: AI Model link to stamp on the message.

    Returns:
        The created/updated Agent Message document.
    """
    metadata = metadata or {}
    agent_name = metadata.get("agent_name")
    message_id = metadata.get("message_id")
    agent_run_id = metadata.get("agent_run_id")
    stt_model_link = metadata.get("stt_model")

    file_doc = frappe.get_doc("File", file_id) if file_id else None

    if not agent_name and conversation_id:
        agent_name = frappe.db.get_value("Agent Conversation", conversation_id, "agent")

    agent_doc = frappe.get_doc("Agent", agent_name) if agent_name else None

    # Get conversation_index
    last_index = frappe.db.sql(
        """
        SELECT MAX(conversation_index) as last_index
        FROM `tabAgent Message`
        WHERE conversation = %s
        """,
        (conversation_id,),
        as_dict=1,
    )

    conversation_index = (last_index[0].last_index if last_index and last_index[0].last_index is not None else 0) + 1

    # Create or Update Agent Message
    if message_id and frappe.db.exists("Agent Message", message_id):
        message_doc = frappe.get_doc("Agent Message", message_id)
        message_doc.content = transcript
        if not message_doc.kind:
            message_doc.kind = "Audio"
        if stt_model_link:
            message_doc.stt_model = stt_model_link
        if file_doc and file_doc.file_url:
            message_doc.voice_message = file_doc.file_url
        message_doc.save(ignore_permissions=True)
    else:
        message_doc = frappe.get_doc({
            "doctype": "Agent Message",
            "conversation": conversation_id,
            "role": "user",
            "content": transcript,
            "kind": "Audio",
            "agent": agent_name,
            "provider": agent_doc.provider if agent_doc else None,
            "model": agent_doc.model if agent_doc else None,
            "agent_run": agent_run_id,
            "conversation_index": conversation_index,
            "is_agent_message": 0,
            "user": frappe.session.user,
        })
        if stt_model_link:
            message_doc.stt_model = stt_model_link
        if file_doc and file_doc.file_url:
            message_doc.voice_message = file_doc.file_url
        message_doc.insert(ignore_permissions=True)

    # Check if file is already attached to this message
    if file_doc and message_doc:
        if not file_doc.attached_to_name:
            file_doc.db_set("attached_to_name", message_doc.name)
            file_doc.db_set("attached_to_doctype", "Agent Message")
            file_doc.db_set("is_private", 0)

    # Update conversation total_messages
    if not message_id:
        frappe.db.sql(
            """
            UPDATE `tabAgent Conversation`
            SET total_messages = %s, last_activity = NOW()
            WHERE name = %s
            """,
            (conversation_index, conversation_id),
        )
    else:
        frappe.db.set_value("Agent Conversation", conversation_id, "last_activity", frappe.utils.now())

    frappe.db.commit()

    # Emit socket event for new message
    try:
        frappe.publish_realtime(
            event=f"conversation:{conversation_id}",
            message={
                "type": "update_message" if message_id else "new_user_message",
                "conversation_id": conversation_id,
                "message_id": message_doc.name,
                "content": transcript,
                "kind": "Audio",
                "file": {
                    "file_name": file_doc.file_name,
                    "file_url": file_doc.file_url,
                } if file_doc else None,
                "conversation_index": conversation_index,
            },
            user=frappe.session.user,
            after_commit=False,
        )
    except Exception as e:
        frappe.log_error(
            title="Audio Transcription Socket Event",
            message=f"Error emitting new_user_message socket event: {e!s}",
        )

    return message_doc
