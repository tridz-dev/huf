import base64
import binascii
import json
import mimetypes

import frappe
from frappe import _
from frappe.utils.file_manager import save_file

logger = frappe.logger("huf")

from huf.ai import audio_service
from huf.ai import conversation_fork
from huf.ai import sdk_tools
from huf.ai.agent_integration import _is_truthy, _run_async_safely, run_agent_sync
from huf.ai.conversation_manager import ConversationManager


@frappe.whitelist()
def upload_audio_and_transcribe(filename: str, b64data: str, docname: str = None,
                                agent: str = None, conversation: str = None):
    if not b64data or not filename:
        frappe.throw("Filename and audio data are required")

    if "," in b64data:
        b64data = b64data.split(",", 1)[1]
    
    try:
        audio_bytes = base64.b64decode(b64data)
    except (ValueError, binascii.Error):
        frappe.throw("Invalid base64 audio data")

    if len(audio_bytes) == 0:
        return {"success": False, "error": "Audio recording was empty (0 bytes)."}

    chat = frappe.get_doc("Agent Chat", docname)
    if agent and chat.agent != agent:
        chat.db_set("agent", agent)
        chat.agent = agent

    conv_id = conversation or chat.conversation
    session_id = None
    if conv_id:
        session_id = frappe.db.get_value("Agent Conversation", conv_id, "session_id")
    
    msg = frappe.get_doc({
        "doctype": "Agent Message",
        "conversation": conv_id,
        "role": "user",
        "content": f"(voice message: {filename})",
        "kind": "Audio",
        "user": frappe.session.user,
        "session_id": session_id,
    })
    msg.insert()

    try:
        saved_file = audio_service.save_audio_upload(
            filename,
            b64data,
            attached_to_doctype="Agent Message",
            attached_to_name=msg.name,
            is_private=0,
        )
    except (frappe.DoesNotExistError, frappe.ValidationError, OSError, ValueError, KeyError, TypeError) as e:
        logger.warning(f"Save audio upload failed: {e}")
        return {"success": False, "error": str(e)}

    file_id = saved_file["file_id"]
    file_url = saved_file["file_url"]
    if file_url:
        frappe.db.set_value("Agent Message", msg.name, "voice_message", file_url)

    provider = frappe.db.get_value("Agent", chat.agent, "provider")

    stt_model_link = frappe.db.get_value("Agent", chat.agent, "stt_model")

    try:
        res = audio_service.transcribe_audio_file(
            file_id=file_id,
            agent_name=chat.agent,
        )

        conv_id = conversation or chat.conversation
        if res.get("success") and conv_id:
            try:
                audio_service.create_audio_user_message(
                    conv_id,
                    file_id,
                    res["text"],
                    metadata={
                        "agent_name": chat.agent,
                        "message_id": msg.name,
                        "stt_model": stt_model_link,
                        "status": "Completed",
                    },
                )
            except (frappe.DoesNotExistError, frappe.ValidationError, ValueError, KeyError, TypeError) as e:
                logger.warning(f"Create audio user message failed: {e!s}")
    except (frappe.DoesNotExistError, frappe.ValidationError, ValueError, KeyError, RuntimeError) as e:
        logger.warning(f"Audio transcription failed: {e!s}")
        frappe.db.set_value("Agent Message", msg.name, "status", "Failed")
        return {"success": False, "error": str(e)}

    if not res.get("success"):
        frappe.db.set_value("Agent Message", msg.name, "status", "Failed")
        return res

    transcript = res.get("text")
    frappe.db.set_value("Agent Message", msg.name, "status", "Completed")
    if stt_model_link:
        frappe.db.set_value("Agent Message", msg.name, "stt_model", stt_model_link)
    if not chat.conversation: chat.reload()
    
    run_result = run_agent_sync(
        agent_name=chat.agent,
        prompt=transcript,
        provider=provider,
        model=frappe.db.get_value("Agent", chat.agent, "model"),
        channel_id="chat",
        external_id=frappe.session.user,
        conversation_id=chat.conversation,
        skip_user_message=True
    )
    
    if run_result.get("conversation_id") and not chat.conversation:
        chat.db_set("conversation", run_result["conversation_id"])

    return {
        "success": True, 
        "transcript": transcript, 
        "run": run_result
    }


@frappe.whitelist()
def upload_audio_and_transcribe_web(
    filename: str,
    b64data: str,
    agent: str,
    conversation: str | None = None,
    transcribe_only: bool = False,
):
    """Web endpoint: save audio, transcribe via STT, optionally run the agent with the transcript."""
    if not b64data or not filename:
        frappe.throw(_("Filename and audio data are required"))

    if "," in b64data:
        b64data = b64data.split(",", 1)[1]

    try:
        audio_bytes = base64.b64decode(b64data)
    except (ValueError, binascii.Error):
        frappe.throw(_("Invalid base64 audio data"))

    if len(audio_bytes) == 0:
        return {"success": False, "error": "Audio recording was empty (0 bytes)."}

    if not agent:
        frappe.throw(_("agent is required"))

    # Ensure conversation exists (or create a new one)
    conv = None
    if conversation:
        try:
            conv = frappe.get_doc("Agent Conversation", conversation)
        except frappe.DoesNotExistError:
            conv = None

    if not conv:
        cm = ConversationManager(agent_name=agent, channel="Chat")
        conv = cm.create_new_conversation()

    conversation_id = conv.name

    # Create initial Agent Message representing the raw voice message
    msg = frappe.get_doc({
        "doctype": "Agent Message",
        "conversation": conversation_id,
        "role": "user",
        "content": f"(voice message: {filename})",
        "kind": "Audio",
        "user": frappe.session.user,
        "session_id": conv.session_id,
    })
    msg.insert()

    # Save file attached to Agent Message
    try:
        saved_file = audio_service.save_audio_upload(
            filename,
            b64data,
            attached_to_doctype="Agent Message",
            attached_to_name=msg.name,
            is_private=0,
        )
    except (frappe.DoesNotExistError, frappe.ValidationError, OSError, ValueError, KeyError) as e:
        logger.warning(f"Save audio upload failed (web): {e}")
        return {"success": False, "error": str(e)}

    file_id = saved_file["file_id"]
    file_url = saved_file["file_url"]
    if file_url:
        frappe.db.set_value("Agent Message", msg.name, "voice_message", file_url)

    provider = frappe.db.get_value("Agent", agent, "provider")

    # Transcribe via the canonical audio service
    try:
        res = audio_service.transcribe_audio_file(
            file_id=file_id,
            agent_name=agent,
        )
    except (frappe.DoesNotExistError, frappe.ValidationError, ValueError, KeyError, RuntimeError) as e:
        logger.warning(f"Audio transcription failed (web): {e!s}")
        frappe.db.set_value("Agent Message", msg.name, "status", "Failed")
        return {"success": False, "error": str(e)}

    if not res.get("success"):
        frappe.db.set_value("Agent Message", msg.name, "status", "Failed")
        return res

    transcript = res["text"]
    stt_model_link = frappe.db.get_value("Agent", agent, "stt_model")

    # Update user message with the actual transcript
    try:
        audio_service.create_audio_user_message(
            conversation_id,
            file_id,
            transcript,
            metadata={
                "agent_name": agent,
                "message_id": msg.name,
                "stt_model": stt_model_link,
                "status": "Completed",
            },
        )
    except (frappe.DoesNotExistError, frappe.ValidationError, ValueError, KeyError, TypeError) as e:
        logger.warning(f"Create audio user message failed (web): {e!s}")

    # Ensure the transcript is stored even if message update failed above
    frappe.db.set_value("Agent Message", msg.name, "content", transcript)
    if stt_model_link:
        frappe.db.set_value("Agent Message", msg.name, "stt_model", stt_model_link)
    frappe.db.set_value("Agent Message", msg.name, "status", "Completed")
    
    if transcribe_only:
        return {
            "success": True,
            "conversation_id": conversation_id,
            "transcript": transcript,
            "message_id": msg.name,
            "file_url": file_url,
        }

    # Run agent with transcript as prompt, within the same conversation
    run_result = run_agent_sync(
        agent_name=agent,
        prompt=transcript,
        provider=provider,
        model=frappe.db.get_value("Agent", agent, "model"),
        channel_id="Chat",
        conversation_id=conversation_id,
    )

    return {
        "success": True,
        "conversation_id": conversation_id,
        "transcript": transcript,
        "run": run_result,
    }


@frappe.whitelist()
def get_history(conversation_id: str = None, limit: int = 200):
    """Return conversation history for chat UI"""
    if not conversation_id:
        return []

    messages = frappe.get_all(
        "Agent Message",
        filters={"conversation": conversation_id},
        fields=["role", "content", "creation", "user", "conversation_index"],
        order_by="conversation_index asc",
        limit=limit
    )

    def _norm(m):
        content = m.content
        try:
            if not isinstance(content, str):
                content = json.dumps(content)
        except (TypeError, ValueError):
            pass
        return {
            "role": m.role,
            "content": content,
            "creation": m.creation,
            "user": m.user,
            "conversation_index": m.conversation_index,
        }

    return [_norm(m) for m in messages]


@frappe.whitelist()
def send_message(docname: str, message: str, agent: str = None):
    """Send a chat message via Agent Chat."""
    if not docname:
        frappe.throw(_("docname is required"))

    chat = frappe.get_doc("Agent Chat", docname)

    if agent:
        if chat.agent != agent:
            chat.db_set("agent", agent)
            chat.agent = agent

    if not chat.agent:
        frappe.throw(_("Agent must be set before sending a message"))

    result = run_agent_sync(
        agent_name=chat.agent,
        prompt=message,
        provider=frappe.db.get_value("Agent", chat.agent, "provider"),
        model=frappe.db.get_value("Agent", chat.agent, "model"),
        channel_id="chat",
        external_id=frappe.session.user,
        conversation_id=chat.conversation,
    )

    if result.get("conversation_id") and not chat.conversation:
        chat.db_set("conversation", result["conversation_id"])

    return result


@frappe.whitelist()
def render_markdown(content: str = "") -> str:
    """
    Render Markdown to sanitized HTML using frappe's built-in markdown util.
    Returns safe HTML string.
    """
    try:
        if not isinstance(content, str):
            content = json.dumps(content, indent=2)

        from frappe.utils import markdown as md
        return md(content or "")
    except Exception:
        # Broad boundary: any markdown failure should fall back to escaped HTML safely.
        logger.warning(f"render_markdown failed: {frappe.get_traceback()}")
        return frappe.utils.escape_html(content or "")


@frappe.whitelist()
def create_conversation(agent: str, channel: str = "Chat"):
    """Create a new Agent Conversation without running the agent."""
    if not agent:
        frappe.throw(_("agent is required"))

    try:
        cm = ConversationManager(agent_name=agent, channel=channel)
        conversation = cm.create_new_conversation()
        return {
            "success": True,
            "conversation_id": conversation.name,
        }
    except Exception:  # boundary exception handler: API endpoint
        # API boundary: log unexpected failure with traceback, then re-raise.
        frappe.log_error(
            message=f"create_conversation error: {frappe.get_traceback()}",
            title="Huf API",
        )
        raise

@frappe.whitelist()
def fork_conversation(conversation_id: str, mode: str, title: str | None = None):
    """Fork an existing Agent Conversation into a new one."""
    try:
        return conversation_fork.fork_conversation_impl(conversation_id, mode, title)
    except Exception:  # boundary exception handler: API endpoint
        frappe.log_error(
            message=f"fork_conversation error: {frappe.get_traceback()}",
            title="Huf API",
        )
        raise


@frappe.whitelist()
def new_conversation(agent: str, message: str, skip_user_message=0, files=None):

    if not agent:
        frappe.throw(_("agent is required"))
    if not message:
        frappe.throw(_("message is required"))

    try:
        cm = ConversationManager(agent_name=agent, channel="Chat")
        conversation = cm.create_new_conversation()

        run_result = run_agent_sync(
            agent_name=agent,
            prompt=message,
            provider=frappe.db.get_value("Agent", agent, "provider"),
            model=frappe.db.get_value("Agent", agent, "model"),
            channel_id="Chat",
            conversation_id=conversation.name,
            skip_user_message=_is_truthy(skip_user_message),
            files=files,
        )

        if run_result.get("conversation_id"):
            try:
                frappe.db.set_value("Agent Conversation", conversation.name, "name", conversation.name)
            except (frappe.DoesNotExistError, frappe.ValidationError, frappe.PermissionError, frappe.TimestampMismatchError):
                # Best-effort defensive update; ignore known validation failures.
                pass

        return {
            "success": True,
            "conversation_id": conversation.name,
            "run": run_result
        }

    except Exception as e:  # boundary exception handler: API endpoint
        # API boundary: log unexpected failure with traceback, then re-raise.
        frappe.log_error(message=f"new_conversation error: {frappe.get_traceback()}", title="Huf API")
        raise


@frappe.whitelist()
def send_message_to_conversation(conversation: str, message: str, skip_user_message=0, files=None):
    if not conversation:
        frappe.throw(_("conversation is required"))
    if not message:
        frappe.throw(_("message is required"))

    try:
        try:
            conv_doc = frappe.get_doc("Agent Conversation", conversation)
        except frappe.DoesNotExistError:
            frappe.throw(_("Conversation not found: {0}").format(conversation))

        if not conv_doc.is_active:
            frappe.throw(_("Conversation is not active"))

        agent_name = conv_doc.agent
        if not agent_name:
            frappe.throw(_("Conversation has no agent set"))

        result = run_agent_sync(
            agent_name=agent_name,
            prompt=message,
            provider=frappe.db.get_value("Agent", agent_name, "provider"),
            model=frappe.db.get_value("Agent", agent_name, "model"),
            channel_id=conv_doc.channel or "Chat",
            conversation_id=conv_doc.name,
            skip_user_message=_is_truthy(skip_user_message),
            files=files,
        )

        if result.get("conversation_id") and not conv_doc.name:
            conv_doc.db_set("conversation", result["conversation_id"])

        return result

    except Exception as e:  # boundary exception handler: API endpoint
        # API boundary: log unexpected failure with traceback, then re-raise.
        frappe.log_error(message=f"send_message_to_conversation error: {frappe.get_traceback()}", title="Huf API")
        raise

@frappe.whitelist()
def upload_file_and_process(docname: str, filename: str, b64data: str, agent: str = None, conversation: str = None):
    """
    Upload a file (PDF/Image/Audio) and process it with OCR/Vision/STT.
    Returns the extracted text and optionally creates an Agent Message.
    """
    if not b64data or not filename:
        frappe.throw(_("Filename and file data are required"))

    # Decode base64
    if "," in b64data:
        b64data = b64data.split(",", 1)[1]
    
    try:
        file_bytes = base64.b64decode(b64data)
    except (ValueError, binascii.Error):
        frappe.throw(_("Invalid base64 data"))

    # Get Chat Doc
    chat = frappe.get_doc("Agent Chat", docname)
    if agent and chat.agent != agent:
        chat.db_set("agent", agent)
        chat.agent = agent

    # select provider/model based on agent
    if not chat.agent:
         frappe.throw(_("Agent must be selected"))
    
    # Save file
    
    conv_id = conversation or chat.conversation
    session_id = None
    if conv_id:
        session_id = frappe.db.get_value("Agent Conversation", conv_id, "session_id")
        
    try:
        msg = frappe.get_doc({
            "doctype": "Agent Message",
            "conversation": conv_id,
            "role": "user",
            "kind":"Message",
            "content": f"Uploaded file: {filename}",
            "user": frappe.session.user,
            "session_id": session_id,
        })
        msg.insert()

        saved_file = save_file(
            filename, 
            file_bytes, 
            "Agent Message", 
            msg.name, 
            is_private=False
        )
    except (frappe.DoesNotExistError, frappe.ValidationError, OSError, ValueError, KeyError) as e:
        logger.warning(f"File save failed: {e!s}")
        frappe.throw(_("Failed to save file"))

    file_id = saved_file.name

    try:
        if audio_service.is_audio_file(filename):
            result = audio_service.transcribe_audio_file(
                file_id=file_id,
                agent_name=chat.agent,
            )
        else:
            result = _run_async_safely(
                sdk_tools.handle_ocr_document(
                    file_id=file_id,
                    agent_name=chat.agent,
                    conversation_id=conversation or chat.conversation,
                )
            )

        if not result.get("success"):
            return result

        return result

    except (frappe.DoesNotExistError, frappe.ValidationError, ValueError, KeyError, RuntimeError) as e:
        logger.warning(f"File processing failed: {e!s}")
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def upload_file_and_process_web(
    filename: str,
    b64data: str,
    agent: str,
    conversation: str | None = None,
):
    """Web endpoint: save an uploaded document/image/audio against a real Agent Conversation
    and extract its text via OCR/vision or STT transcription, honoring the agent's upload capability flags.
    """
    if not b64data or not filename:
        frappe.throw(_("Filename and file data are required"))

    if not agent:
        frappe.throw(_("agent is required"))

    agent_doc = frappe.get_doc("Agent", agent)

    if not agent_doc.get("allow_file_upload"):
        return {"success": False, "error": _("File uploads are disabled for this agent.")}

    if "," in b64data:
        b64data = b64data.split(",", 1)[1]

    try:
        file_bytes = base64.b64decode(b64data)
    except (ValueError, binascii.Error):
        frappe.throw(_("Invalid base64 data"))

    max_upload_size_mb = agent_doc.get("max_upload_size_mb") or 25
    max_upload_size_bytes = min(max_upload_size_mb, 25) * 1024 * 1024
    if len(file_bytes) > max_upload_size_bytes:
        return {
            "success": False,
            "error": _("File exceeds the maximum allowed size of {0} MB.").format(min(max_upload_size_mb, 25)),
        }

    # Audio attachments bypass the OCR/Vision modality gate: they only need a
    # resolvable STT configuration for the agent.
    is_audio = audio_service.is_audio_file(filename)
    if is_audio:
        try:
            audio_service.resolve_stt_config(agent)
        except ValueError:
            return {
                "success": False,
                "error": _("This agent has no transcription model configured for audio files."),
            }
    else:
        model_name = agent_doc.get("model")
        modalities = (frappe.db.get_value("AI Model", model_name, "modalities") or "") if model_name else ""
        supported = {m.strip() for m in modalities.split(",") if m.strip()}

        is_image_or_pdf = filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf"))
        use_ocr = bool(agent_doc.get("enable_ocr")) or ("OCR" in supported)
        use_vision = "Vision" in supported and is_image_or_pdf

        if not use_ocr and not use_vision:
            return {"success": False, "error": _("This model does not support file analysis.")}

    # Ensure conversation exists (or create a new one)
    conv = None
    if conversation:
        try:
            conv = frappe.get_doc("Agent Conversation", conversation)
        except frappe.DoesNotExistError:
            conv = None

        if conv and conv.owner != frappe.session.user:
            frappe.throw(_("You do not have permission to upload to this conversation."), frappe.PermissionError)

    if not conv:
        cm = ConversationManager(agent_name=agent, channel="Chat")
        conv = cm.create_new_conversation()

    conversation_id = conv.name

    msg = frappe.get_doc({
        "doctype": "Agent Message",
        "conversation": conversation_id,
        "role": "user",
        "kind": "Message",
        "content": f"Uploaded file: {filename}",
        "user": frappe.session.user,
        "session_id": conv.session_id,
    })
    msg.insert()

    try:
        saved_file = save_file(filename, file_bytes, "Agent Message", msg.name, is_private=True)
    except (frappe.DoesNotExistError, frappe.ValidationError, OSError, ValueError, KeyError) as e:
        logger.warning(f"Save file failed (web): {e}")
        return {"success": False, "error": "Could not save file to database."}

    file_id = getattr(saved_file, "name", None) or (
        saved_file.get("name") if isinstance(saved_file, dict) else None
    )
    if not file_id:
        return {"success": False, "error": "File was saved but ID could not be retrieved."}

    try:
        if is_audio:
            result = audio_service.transcribe_audio_file(
                file_id=file_id,
                agent_name=agent,
            )
        else:
            result = _run_async_safely(
                sdk_tools.handle_ocr_document(
                    file_id=file_id,
                    agent_name=agent,
                    conversation_id=conversation_id,
                )
            )
    except (frappe.DoesNotExistError, frappe.ValidationError, ValueError, KeyError, RuntimeError) as e:
        logger.warning(f"File processing failed (web): {e!s}")
        return {"success": False, "error": str(e)}

    if not result.get("success"):
        return result

    return {
        "success": True,
        "conversation_id": conversation_id,
        "message_id": msg.name,
        **result,
    }


def _validate_web_file_upload(agent: str, filename: str, file_bytes: bytes):
    """Shared validation for web chat file uploads."""
    if not agent:
        frappe.throw(_("agent is required"))

    agent_doc = frappe.get_doc("Agent", agent)

    if not agent_doc.get("allow_file_upload"):
        return None, {"success": False, "error": _("File uploads are disabled for this agent.")}

    max_upload_size_mb = agent_doc.get("max_upload_size_mb") or 25
    max_upload_size_bytes = min(max_upload_size_mb, 25) * 1024 * 1024
    if len(file_bytes) > max_upload_size_bytes:
        return None, {
            "success": False,
            "error": _("File exceeds the maximum allowed size of {0} MB.").format(min(max_upload_size_mb, 25)),
        }

    # Audio attachments bypass the OCR/Vision modality gate: they only need a
    # resolvable STT configuration for the agent.
    if audio_service.is_audio_file(filename):
        try:
            audio_service.resolve_stt_config(agent)
        except ValueError:
            return None, {
                "success": False,
                "error": _("This agent has no transcription model configured for audio files."),
            }
        return agent_doc, None

    model_name = agent_doc.get("model")
    modalities = (frappe.db.get_value("AI Model", model_name, "modalities") or "") if model_name else ""
    supported = {m.strip() for m in modalities.split(",") if m.strip()}

    is_image_or_pdf = filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf"))
    use_ocr = bool(agent_doc.get("enable_ocr")) or ("OCR" in supported)
    use_vision = "Vision" in supported and is_image_or_pdf

    if not use_ocr and not use_vision:
        return None, {"success": False, "error": _("This model does not support file analysis.")}

    return agent_doc, None


def _ensure_web_chat_conversation(agent: str, conversation: str | None = None):
    conv = None
    if conversation:
        try:
            conv = frappe.get_doc("Agent Conversation", conversation)
        except frappe.DoesNotExistError:
            conv = None

        if conv and conv.owner != frappe.session.user:
            frappe.throw(_("You do not have permission to upload to this conversation."), frappe.PermissionError)

    if not conv:
        cm = ConversationManager(agent_name=agent, channel="Chat")
        conv = cm.create_new_conversation()

    return conv


@frappe.whitelist()
def upload_file_attachment_web(filename: str, b64data: str, agent: str):
    """Stage a chat attachment upload. Saves the file and returns file_id without OCR or agent run."""
    if not b64data or not filename:
        frappe.throw(_("Filename and file data are required"))

    if "," in b64data:
        b64data = b64data.split(",", 1)[1]

    try:
        file_bytes = base64.b64decode(b64data)
    except (ValueError, binascii.Error):
        frappe.throw(_("Invalid base64 data"))

    _, error = _validate_web_file_upload(agent, filename, file_bytes)
    if error:
        return error

    try:
        saved_file = save_file(filename, file_bytes, "Agent", agent, is_private=True)
    except (frappe.DoesNotExistError, frappe.ValidationError, OSError, ValueError, KeyError) as e:
        logger.warning(f"Attachment upload failed (web): {e}")
        return {"success": False, "error": "Could not save file to database."}

    file_id = getattr(saved_file, "name", None) or (
        saved_file.get("name") if isinstance(saved_file, dict) else None
    )
    file_url = getattr(saved_file, "file_url", None) or (
        saved_file.get("file_url") if isinstance(saved_file, dict) else None
    )
    if not file_id:
        return {"success": False, "error": "File was saved but ID could not be retrieved."}
    if not file_url:
        file_url = frappe.db.get_value("File", file_id, "file_url")

    return {
        "success": True,
        "file_id": file_id,
        "file_url": file_url,
        "filename": filename,
    }


def _load_staged_chat_file(file_id: str, agent: str):
    """Load a file staged via upload_file_attachment_web and re-attach it to a message."""
    if not file_id:
        frappe.throw(_("file_id is required"))

    file_doc = frappe.get_doc("File", file_id)

    if file_doc.owner != frappe.session.user:
        frappe.throw(_("You do not have permission to use this file."), frappe.PermissionError)

    if file_doc.attached_to_doctype == "Agent" and file_doc.attached_to_name != agent:
        frappe.throw(_("This file does not belong to the selected agent."), frappe.PermissionError)

    if file_doc.attached_to_doctype not in (None, "", "Agent"):
        frappe.throw(_("This file has already been sent."), frappe.ValidationError)

    return file_doc


@frappe.whitelist()
def prepare_message_with_file_web(
    agent: str,
    conversation: str | None = None,
    message: str = "",
    file_id: str | None = None,
    filename: str | None = None,
    b64data: str | None = None,
):
    """Attach a staged file to a conversation message and prepare the agent prompt without running the agent."""
    if not file_id and (not b64data or not filename):
        frappe.throw(_("Either file_id or filename and file data are required"))

    file_bytes = None
    if not file_id:
        if "," in b64data:
            b64data = b64data.split(",", 1)[1]
        try:
            file_bytes = base64.b64decode(b64data)
        except (ValueError, binascii.Error):
            frappe.throw(_("Invalid base64 data"))

        _, error = _validate_web_file_upload(agent, filename, file_bytes)
        if error:
            return error

    conv = _ensure_web_chat_conversation(agent, conversation)
    conversation_id = conv.name

    resolved_filename = filename
    resolved_file_id = file_id
    resolved_file_url = None

    if file_id:
        file_doc = _load_staged_chat_file(file_id, agent)
        resolved_filename = resolved_filename or file_doc.file_name
        resolved_file_id = file_doc.name
        resolved_file_url = file_doc.file_url
    else:
        resolved_filename = filename

    display_content = (message or "").strip() or f"📎 {resolved_filename}"

    msg = frappe.get_doc({
        "doctype": "Agent Message",
        "conversation": conversation_id,
        "role": "user",
        "kind": "Message",
        "content": display_content,
        "user": frappe.session.user,
        "session_id": conv.session_id,
    })
    msg.insert()

    if file_id:
        frappe.db.set_value(
            "File",
            resolved_file_id,
            {
                "attached_to_doctype": "Agent Message",
                "attached_to_name": msg.name,
            },
        )
    else:
        try:
            saved_file = save_file(resolved_filename, file_bytes, "Agent Message", msg.name, is_private=True)
        except (frappe.DoesNotExistError, frappe.ValidationError, OSError, ValueError, KeyError) as e:
            logger.warning(f"Save file failed (web): {e}")
            return {"success": False, "error": "Could not save file to database."}

        resolved_file_id = getattr(saved_file, "name", None) or (
            saved_file.get("name") if isinstance(saved_file, dict) else None
        )
        resolved_file_url = getattr(saved_file, "file_url", None) or (
            saved_file.get("file_url") if isinstance(saved_file, dict) else None
        )

    if not resolved_file_id:
        return {"success": False, "error": "File was saved but ID could not be retrieved."}
    if not resolved_file_url:
        resolved_file_url = frappe.db.get_value("File", resolved_file_id, "file_url")

    mime_type, _unused = mimetypes.guess_type(resolved_filename)
    is_image = bool(mime_type and mime_type.startswith("image/"))
    is_audio = audio_service.is_audio_file(resolved_filename, mime_type)

    agent_prompt = display_content
    files_payload = None

    if is_image and resolved_file_url:
        files_payload = [{
            "file_id": resolved_file_id,
            "file_url": resolved_file_url,
            "filename": resolved_filename,
            "is_image": 1,
        }]
    elif is_audio:
        result = audio_service.transcribe_audio_file(
            file_id=resolved_file_id,
            agent_name=agent,
        )

        if not result.get("success"):
            return result

        transcript = result.get("transcript") or result.get("text") or ""
        agent_prompt = transcript

        msg_meta = frappe.get_meta("Agent Message")
        msg_updates = {
            "kind": "Audio",
            "content": transcript
        }
        if resolved_file_url and msg_meta.get_field("voice_message"):
            msg_updates["voice_message"] = resolved_file_url
        if result.get("stt_model") and msg_meta.get_field("stt_model"):
            msg_updates["stt_model"] = result["stt_model"]
        if msg_updates:
            frappe.db.set_value("Agent Message", msg.name, msg_updates, update_modified=False)

        return {
            "success": True,
            "conversation_id": conversation_id,
            "message_id": msg.name,
            "agent_prompt": agent_prompt,
            "is_audio": True,
            "transcript": transcript,
            "voice_message": resolved_file_url,
            "stt_model": result.get("stt_model"),
            "files": files_payload,
        }
    else:
        try:
            result = _run_async_safely(
                sdk_tools.handle_ocr_document(
                    file_id=resolved_file_id,
                    agent_name=agent,
                    conversation_id=conversation_id,
                    create_message=False,
                )
            )
        except (frappe.DoesNotExistError, frappe.ValidationError, ValueError, KeyError, RuntimeError) as e:
            logger.warning(f"OCR processing failed (web prepare): {e!s}")
            return {"success": False, "error": str(e)}

        if not result.get("success"):
            return result

        extracted_text = result.get("text") or ""
        file_hash = result.get("file_hash", "n/a")
        if extracted_text:
            agent_prompt = f"""{display_content}

Attached File Content (OCR Extracted):
The following text was extracted from attached files. Use this as context:

--- File: {resolved_filename} (hash: {file_hash}) ---
{extracted_text}
"""

    return {
        "success": True,
        "conversation_id": conversation_id,
        "message_id": msg.name,
        "agent_prompt": agent_prompt,
        "files": files_payload,
    }


@frappe.whitelist()
def add_message(
    conversation_id: str,
    role: str,
    content: str,
    record_kind: str = None,
    context_policy: str = None,
    context_summary: str = None,
    reference_doctype: str = None,
    reference_name: str = None,
    visibility: str = None,
    token_estimate: int = None
):
    """
    Exposes ConversationManager.add_message as a public API.
    Used for creating context artifacts, tool results, and out-of-band context.
    """
    if not conversation_id or not role:
        frappe.throw(_("conversation_id and role are required"))

    try:
        conv_doc = frappe.get_doc("Agent Conversation", conversation_id)
        agent_name = conv_doc.agent

        cm = ConversationManager(agent_name=agent_name)
        provider = frappe.db.get_value("Agent", agent_name, "provider")
        model = frappe.db.get_value("Agent", agent_name, "model")

        msg = cm.add_message(
            conversation=conv_doc,
            role=role,
            content=content,
            provider=provider,
            model=model,
            agent=agent_name,
            record_kind=record_kind,
            context_policy=context_policy,
            context_summary=context_summary,
            reference_doctype=reference_doctype,
            reference_name=reference_name,
            visibility=visibility,
            token_estimate=token_estimate
        )

        return {
            "success": True,
            "message_id": msg.name
        }
    except Exception as e:  # boundary exception handler: API endpoint
        # API boundary: log unexpected failure with traceback, then re-raise.
        frappe.log_error(message=f"add_message API error: {frappe.get_traceback()}", title="Huf API")
        raise
