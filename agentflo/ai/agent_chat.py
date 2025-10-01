import frappe
import json
from frappe import _
from agentflo.ai.agent_integration import run_agent_sync
from agentflo.ai.conversation_manager import ConversationManager


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
