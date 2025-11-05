import frappe
import json
from frappe import _
from agentflo.ai.agent_integration import run_agent_sync, run_agent_sync_stream
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


def format_sse_event(event_type: str, data: dict) -> str:
    """Format data as Server-Sent Event"""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


@frappe.whitelist(allow_guest=False)
def send_message_stream(docname: str = None, message: str = None, agent: str = None):
    """
    Send message with streaming response via Server-Sent Events (SSE).
    
    This endpoint streams agent responses in real-time, including:
    - Tool calling feedback (start, progress, complete, error)
    - Streaming text chunks as they're generated
    - Final response when complete
    
    Supports both GET (for EventSource) and POST requests.
    
    Args:
        docname: Agent Chat document name
        message: User message to send
        agent: Optional agent name (overrides chat's agent)
    
    Returns:
        Generator that yields SSE-formatted strings
    """
    # Handle GET requests (EventSource only supports GET)
    if not docname:
        docname = frappe.form_dict.get("docname") or frappe.request.args.get("docname")
    if not message:
        message = frappe.form_dict.get("message") or frappe.request.args.get("message")
    if not agent:
        agent = frappe.form_dict.get("agent") or frappe.request.args.get("agent")
    
    if not docname:
        frappe.throw(_("docname is required"))
    if not message:
        frappe.throw(_("message is required"))
    
    try:
        chat = frappe.get_doc("Agent Chat", docname)
    except frappe.DoesNotExistError:
        def error_generator():
            yield format_sse_event("error", {"error": "Agent Chat not found"})
        return error_generator()
    
    if agent:
        if chat.agent != agent:
            chat.db_set("agent", agent)
            chat.agent = agent
    
    if not chat.agent:
        def error_generator():
            yield format_sse_event("error", {"error": "Agent must be set before sending a message"})
        return error_generator()
    
    def event_generator():
        try:
            # Get provider and model
            provider = frappe.db.get_value("Agent", chat.agent, "provider")
            model = frappe.db.get_value("Agent", chat.agent, "model")
            
            if not provider or not model:
                yield format_sse_event("error", {"error": "Agent provider or model not configured"})
                return
            
            # Stream events from agent execution
            for event in run_agent_sync_stream(
                agent_name=chat.agent,
                prompt=message,
                provider=provider,
                model=model,
                channel_id="chat",
                external_id=frappe.session.user,
                conversation_id=chat.conversation,
            ):
                event_type = event.get("type", "unknown")
                event_data = event.get("data", event)
                
                # Format and yield SSE event
                yield format_sse_event(event_type, event_data)
                
                # Update conversation ID if provided in response_complete event
                if event_type == "response_complete":
                    conv_id = event_data.get("conversation_id")
                    if conv_id and not chat.conversation:
                        chat.db_set("conversation", conv_id)
        
        except Exception as e:
            frappe.log_error(f"Streaming error: {frappe.get_traceback()}", "Agent Chat Streaming")
            yield format_sse_event("error", {"error": str(e)})
    
    # Return generator wrapped in Frappe response
    from frappe.utils.response import build_response
    return build_response(
        event_generator(),
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )
