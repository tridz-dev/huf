import frappe
import json
from frappe import _
from agentflo.ai.agent_integration import run_agent_sync
from agentflo.ai.conversation_manager import ConversationManager
import base64
from frappe.utils.file_manager import save_file
from agentflo.ai import sdk_tools

@frappe.whitelist()
def upload_audio_and_transcribe(docname: str, filename: str, b64data: str,
                                agent: str = None, conversation: str = None):
    """
    Save audio on Agent Message -> transcribe -> send transcript to agent -> return agent reply.
    """
    if not b64data or not filename:
        frappe.throw(_("filename and b64data are required"))

    if "," in b64data:
        b64data = b64data.split(",", 1)[1]

    try:
        audio_bytes = base64.b64decode(b64data)
    except Exception:
        frappe.throw(_("Invalid base64 audio"))

    if not docname:
        frappe.throw(_("docname is required"))
    chat = frappe.get_doc("Agent Chat", docname)
    if agent and chat.agent != agent:
        chat.db_set("agent", agent)
        chat.agent = agent
    if not chat.agent:
        frappe.throw(_("Agent must be set before uploading audio"))

    msg = frappe.get_doc({
        "doctype": "Agent Message",
        "conversation": conversation or chat.conversation,
        "role": "user",
        "content": f"(voice message: {filename})",
        "user": frappe.session.user if hasattr(frappe, "session") else None
    })
    msg.insert(ignore_permissions=True)

    file_doc = save_file(
        filename,        
        audio_bytes,     
        "Agent Message", 
        msg.name,        
        is_private=False
    )
    file_id = getattr(file_doc, "name", None) or (file_doc.get("name") if isinstance(file_doc, dict) else None)

    provider = frappe.db.get_value("Agent", chat.agent, "provider")
    res = sdk_tools.handle_speech_to_text(
        file_id=file_id,
        provider=provider,
        conversation=conversation or chat.conversation,
        reference_doctype="Agent Message",
        document_id=msg.name,
        message_id=msg.name,  
    )

    if not res or not res.get("success"):
        return {"success": False, "error": (res or {}).get("error", "Transcription failed")}

    transcript = (res.get("text") or "").strip()
    if not transcript:
        transcript = "(empty transcript)"
        frappe.db.set_value("Agent Message", msg.name, "content", transcript, update_modified=True)

    if not chat.conversation:
        chat.reload()

    run_result = run_agent_sync(
        agent_name=chat.agent,
        prompt=transcript,
        provider=provider,
        model=frappe.db.get_value("Agent", chat.agent, "model"),
        channel_id="chat",
        external_id=frappe.session.user,
        conversation_id=chat.conversation,
    )  

    if run_result.get("conversation_id") and not chat.conversation:
        chat.db_set("conversation", run_result["conversation_id"])

    return {
        "success": True,
        "transcript": transcript,
        "file_id": file_id,
        "message_id": msg.name,
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
