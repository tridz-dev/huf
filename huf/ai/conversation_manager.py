import frappe
from frappe.utils import now
import json

class ConversationManager:
    def __init__(self, agent_name, channel=None, external_id=None, session_id=None):
        self.agent_name = agent_name
        self.channel = channel
        self.external_id = external_id
        if session_id:
            self.session_id = session_id
        elif channel and external_id:
            self.session_id = f"{channel}:{external_id}"
        else:
            self.session_id = f"{channel}:{frappe.session.user}"

    def create_new_conversation(self, title=None):
        """Always create a fresh conversation"""
        title = title or f"Conversation with {self.agent_name}"
        conv = frappe.get_doc({
            "doctype": "Agent Conversation",
            "title": title,
            "agent": self.agent_name,
            "session_id": self.session_id,
            "channel": self.channel,
            "external_id": self.external_id,
            "created_at": now(),
            "last_activity": now(),
            "is_active": 1,
            "model": frappe.db.get_value("Agent", self.agent_name, "model")
        })
        conv.insert()
        return conv

    def get_or_create_conversation(self, title=None, conversation_id=None):
        """Get active conversation or create new one"""
        if conversation_id:
            try:
                conversation = frappe.get_doc("Agent Conversation", conversation_id)
                if conversation.is_active:
                    return conversation
            except frappe.DoesNotExistError:
                pass

        # Try to get existing active conversation
        conversation = frappe.get_all(
            "Agent Conversation",
            filters={
                "agent": self.agent_name,
                "session_id": self.session_id,
                "is_active": 1
            },
            order_by="creation desc",
            limit=1
        )

        if conversation:
            return frappe.get_doc("Agent Conversation", conversation[0].name)

        # Create new conversation
        title = title or f"Conversation with {self.agent_name}"
        conv = frappe.get_doc({
            "doctype": "Agent Conversation",
            "title": title,
            "agent": self.agent_name,
            "session_id": self.session_id,
            "channel": self.channel,
            "external_id": self.external_id,
            "created_at": now(),
            "last_activity": now(),
            "is_active": 1,
            "model": frappe.db.get_value("Agent", self.agent_name, "model")
        })
        conv.insert()
        return conv

    def add_message(self, conversation, role, content, provider, model, agent, run_name=None, kind="Message", tool_call_id=None):
        """Add message to conversation"""
        try:
            last_index = frappe.db.sql("""
                SELECT MAX(conversation_index) as last_index
                FROM `tabAgent Message`
                WHERE conversation = %s
            """, (conversation.name,), as_dict=1)

            last_index = last_index[0].last_index if last_index and last_index[0].last_index is not None else 0
            message = frappe.get_doc({
                "doctype": "Agent Message",
                "conversation": conversation.name,
                "role": role,
                "content": content if isinstance(content, str) else json.dumps(content),
                "user": self.external_id or frappe.session.user if role == "user" else "Agent",
                "session_id": self.session_id,
                "kind": kind,
                "agent_run": run_name,
                "agent": agent,
                "provider": provider,
                "model": model,
                "conversation_index": last_index + 1,
                "is_agent_message": 1 if role == "agent" else 0,
                "tool_calll": tool_call_id 
            })
            message.insert()

            frappe.db.set_value("Agent Conversation", conversation.name, {
                "total_messages": last_index + 1,
                "last_activity": now()
            })

            return message
        except Exception as e:
            frappe.log_error(f"Error adding message: {str(e)}", "Conversation Manager")
            raise

    def get_conversation_history(self, conversation_name, limit=20):
        """Get conversation history for context"""
        messages = frappe.get_all(
            "Agent Message",
            filters={"conversation": conversation_name},
            fields=["role", "content", "creation"],
            order_by="conversation_index asc",
            limit=limit if limit else 1000
        )

        return [
            {
                "role": "assistant" if msg.role == "agent" else msg.role,
                "content": msg.content
            }
            for msg in messages
        ]

    def close_conversation(self, conversation_name):
        """Mark conversation as inactive"""
        frappe.db.set_value("Agent Conversation", conversation_name, "is_active", 0)

    def summarize_conversation(self, conversation_name, history, provider, model, agent_name, limit=20):
        """Summarize conversation if it exceeds the limit"""
        if len(history) <= limit:
            return None, history

        split_index = int(len(history) * 0.7)
        to_summarize = history[:split_index]
        remaining = history[split_index:]

        summary_prompt = "Summarize the following conversation history concisely, capturing key information, context, and decisions. Maintain the flow of information."
        
        return to_summarize, remaining

