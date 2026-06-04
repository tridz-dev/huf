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
        conv.insert(ignore_permissions=True)
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
        conv.insert(ignore_permissions=True)
        return conv

    def add_message(
        self,
        conversation,
        role,
        content,
        provider,
        model,
        agent,
        run_name=None,
        kind="Message",
        tool_call_id=None,
        record_kind=None,
        context_policy=None,
        context_summary=None,
        reference_doctype=None,
        reference_name=None,
        visibility=None,
        token_estimate=None
    ):
        """Add message to conversation with optional context policy."""
        try:
            last_index = frappe.db.sql("""
                SELECT MAX(conversation_index) as last_index
                FROM `tabAgent Message`
                WHERE conversation = %s
            """, (conversation.name,), as_dict=1)

            last_index = last_index[0].last_index if last_index and last_index[0].last_index is not None else 0

            doc_data = {
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
                "tool_call": tool_call_id,
            }

            # Context policy fields (all optional)
            if record_kind is not None:
                doc_data["record_kind"] = record_kind
            if context_policy is not None:
                doc_data["context_policy"] = context_policy
            if context_summary is not None:
                doc_data["context_summary"] = context_summary
            if reference_doctype is not None:
                doc_data["reference_doctype"] = reference_doctype
            if reference_name is not None:
                doc_data["reference_name"] = reference_name
            if visibility is not None:
                doc_data["visibility"] = visibility
            if token_estimate is not None:
                doc_data["token_estimate"] = token_estimate

            message = frappe.get_doc(doc_data)
            message.insert(ignore_permissions=True)

            frappe.db.set_value("Agent Conversation", conversation.name, {
                "total_messages": last_index + 1,
                "last_activity": now()
            })

            return message
        except Exception as e:
            frappe.log_error(f"Error adding message: {str(e)}", "Conversation Manager")
            raise

    def get_conversation_history(self, conversation_name, limit=20):
        """Get conversation history for model context, applying context policies."""
        messages = frappe.get_all(
            "Agent Message",
            filters={"conversation": conversation_name},
            fields=[
                "role",
                "kind",
                "content",
                "context_policy",
                "context_summary",
                "reference_doctype",
                "reference_name",
                "record_kind",
                "tool_call",
                "creation"
            ],
            order_by="conversation_index desc",
            limit=limit if limit else 1000
        )

        messages.reverse()

        result = []
        for msg in messages:
            ctx = self._message_to_context(msg)
            if ctx is not None:
                if isinstance(ctx, list):
                    result.extend(ctx)
                else:
                    result.append(ctx)
        return result

    def _message_to_context(self, msg):
        """Apply context policy to a single message. Returns dict for inclusion, None to omit."""
        policy = msg.get("context_policy") or "include_full"  # NULL = backward compat

        # Policies that exclude the message entirely
        if policy in ("exclude", "transient_only", "include_on_demand"):
            return None

        role_mapped = "assistant" if msg.get("role") == "agent" else msg.get("role")
        
        # Determine the content based on policy
        content = ""
        if policy == "include_full":
            content = msg.get("content")
        elif policy == "include_summary":
            content = msg.get("context_summary") or msg.get("content")
        elif policy == "include_reference":
            record_kind = msg.get("record_kind") or "record"
            summary = msg.get("context_summary") or record_kind
            ref_doctype = msg.get("reference_doctype") or ""
            ref_name = msg.get("reference_name") or ""
            if ref_doctype and ref_name:
                content = f"[{record_kind}: {summary} · handle={ref_doctype}/{ref_name}]"
            else:
                content = f"[{record_kind}: {summary}]"
        elif policy == "token_budgeted":
            content = msg.get("context_summary") or msg.get("content")
        elif policy == "provider_cached":
            content = msg.get("content")
        else:
            content = msg.get("content")

        tool_call_link = msg.get("tool_call")
        msg_kind = msg.get("kind")
        
        if tool_call_link:
            call_id = tool_call_link
            tool_name = ""
            tool_args = "{}"
            
            tool_call_doc = frappe.db.get_value(
                "Agent Tool Call",
                tool_call_link,
                ["call_id", "tool", "tool_args"],
                as_dict=True
            )
            if tool_call_doc:
                call_id = tool_call_doc.call_id or call_id
                tool_name = tool_call_doc.tool or ""
                tool_args = tool_call_doc.tool_args or "{}"

            # If this is a combined Tool Result message from the UI mutation pattern
            if msg_kind == "Tool Result" and role_mapped == "assistant":
                # Create the Assistant message containing the tool call
                assistant_msg = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": tool_args
                        }
                    }]
                }
                
                # Create the subsequent Tool message containing the result
                tool_msg = {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": tool_name,
                    "content": content
                }
                return [assistant_msg, tool_msg]
            
            # Legacy or separate message handling
            if role_mapped == "assistant":
                return {
                    "role": "assistant",
                    "content": None if not msg.get("content") else content,
                    "tool_calls": [{
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": tool_args
                        }
                    }]
                }
            elif role_mapped == "tool":
                return {
                    "role": "tool",
                    "content": content,
                    "tool_call_id": call_id,
                    "name": tool_name
                }

        return {
            "role": role_mapped,
            "content": content
        }

    def close_conversation(self, conversation_name):
        """Mark conversation as inactive"""
        frappe.db.set_value("Agent Conversation", conversation_name, "is_active", 0)

    def summarize_conversation(self, conversation_name, history, provider, model, agent_name, limit=20, ratio=0.7):
        """Summarize conversation if it exceeds the limit"""
        if len(history) <= limit:
            return None, history

        split_index = int(len(history) * ratio)
        to_summarize = history[:split_index]
        remaining = history[split_index:]

        summary_prompt = "Summarize the following conversation history concisely, capturing key information, context, and decisions. Maintain the flow of information."
        
        return to_summarize, remaining
    
    def get_stored_summary(self, conversation_name):
        return frappe.db.get_value("Agent Conversation", conversation_name, "summary")

    def update_stored_summary(self, conversation_name, new_summary):
        frappe.db.set_value("Agent Conversation", conversation_name, "summary", new_summary)

