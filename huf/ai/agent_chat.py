import frappe
import json
from frappe import _
from huf.ai.agent_integration import run_agent_sync
from huf.ai.conversation_manager import ConversationManager
import base64
from frappe.utils.file_manager import save_file
from huf.ai import sdk_tools
from huf.ai import transcription_handler


@frappe.whitelist()
def upload_audio_and_transcribe(docname: str, filename: str, b64data: str,
                                agent: str = None, conversation: str = None):
    if not b64data or not filename:
        frappe.throw("Filename and audio data are required")

    if "," in b64data:
        b64data = b64data.split(",", 1)[1]
    
    try:
        audio_bytes = base64.b64decode(b64data)
    except Exception:
        frappe.throw("Invalid base64 audio data")

    if len(audio_bytes) == 0:
        return {"success": False, "error": "Audio recording was empty (0 bytes)."}

    chat = frappe.get_doc("Agent Chat", docname)
    if agent and chat.agent != agent:
        chat.db_set("agent", agent)
        chat.agent = agent

    msg = frappe.get_doc({
        "doctype": "Agent Message",
        "conversation": conversation or chat.conversation,
        "role": "user",
        "content": f"(voice message: {filename})",
        "user": frappe.session.user
    })
    msg.insert(ignore_permissions=True)

    try:
        saved_file = save_file(
            filename, 
            audio_bytes, 
            "Agent Message", 
            msg.name, 
            is_private=False
        )
    except Exception as e:
        frappe.log_error(message=f"Save File Failed: {e}", title="Save File Failed")
        return {"success": False, "error": "Could not save audio file to database."}

    file_id = None
    if hasattr(saved_file, "name"):
        file_id = saved_file.name
    elif isinstance(saved_file, dict):
        file_id = saved_file.get("name")
    
    if not file_id:
        file_id = frappe.db.get_value("File", {
            "attached_to_doctype": "Agent Message", 
            "attached_to_name": msg.name
        }, "name", order_by="creation desc")

    if not file_id:
        return {"success": False, "error": "File was saved but ID could not be retrieved."}

    provider = frappe.db.get_value("Agent", chat.agent, "provider")
    
    res = transcription_handler.handle_speech_to_text(
        file_id=file_id,
        provider=provider,
        conversation=conversation or chat.conversation,
        message_id=msg.name
    )

    if not res.get("success"):
        return res

    transcript = res.get("text")
    if not chat.conversation: chat.reload()
    
    run_result = run_agent_sync(
        agent_name=chat.agent,
        prompt=transcript,
        provider=provider,
        model=frappe.db.get_value("Agent", chat.agent, "model"),
        channel_id="chat",
        external_id=frappe.session.user,
        conversation_id=chat.conversation
    )
    
    if run_result.get("conversation_id") and not chat.conversation:
        chat.db_set("conversation", run_result["conversation_id"])

    return {
        "success": True, 
        "transcript": transcript, 
        "run": run_result
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
        except Exception:
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

        from frappe.utils.markdown import markdown as md
        return md(content or "")
    except Exception:
        return frappe.utils.escape_html(content or "")

@frappe.whitelist()
def new_conversation(agent: str, message: str):
    
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
            conversation_id=conversation.name
        )

        if run_result.get("conversation_id"):
            try:
                frappe.db.set_value("Agent Conversation", conversation.name, "name", conversation.name)
            except Exception:
                pass

        return {
            "success": True,
            "conversation_id": conversation.name,
            "run": run_result
        }

    except Exception as e:
        frappe.log_error(message=f"new_conversation error: {frappe.get_traceback()}", title="Huf API")
        raise


@frappe.whitelist()
def send_message_to_conversation(conversation: str, message: str):
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
            conversation_id=conv_doc.name
        )

        if result.get("conversation_id") and not conv_doc.name:
            conv_doc.db_set("conversation", result["conversation_id"])

        return result

    except Exception as e:
        frappe.log_error(message=f"send_message_to_conversation error: {frappe.get_traceback()}", title="Huf API")
        raise
