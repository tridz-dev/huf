import frappe
from frappe.utils import now
import json
from collections import defaultdict
from typing import Any


def _is_tool_message(msg) -> bool:
    """Return True if the context message represents a tool result."""
    return isinstance(msg, dict) and msg.get("role") == "tool"


def _tool_call_ids_from_assistant(msg: dict) -> list:
    """Extract tool_call ids from an assistant message."""
    if not isinstance(msg, dict):
        return []
    ids = []
    for tc in msg.get("tool_calls") or []:
        tc_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
        if tc_id:
            ids.append(tc_id)
    return ids


def _tool_call_group_intervals(history: list) -> list:
    """
    Return intervals (start_index, end_index) of assistant/tool-call groups.
    A group starts at the assistant message that declared a tool_call and ends
    at the last matching role='tool' result message.
    """
    if not history:
        return []

    declarations = {}
    for idx, msg in enumerate(history):
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            for cid in _tool_call_ids_from_assistant(msg):
                if cid not in declarations:
                    declarations[cid] = idx

    intervals = []
    seen = set()
    for idx, msg in enumerate(history):
        if isinstance(msg, dict) and msg.get("role") == "tool":
            cid = msg.get("tool_call_id")
            if cid and cid in declarations and cid not in seen:
                start = declarations[cid]
                intervals.append((start, idx))
                seen.add(cid)
    return intervals


def safe_history_slice(history: list, limit: int) -> list:
    """
    Return the last `limit` messages without splitting tool-call pairs.

    OpenAI requires every role='tool' message to follow an assistant message
    that declared the matching tool_call. A naive slice can drop the assistant
    message while keeping its tool results, causing BadRequestError. This
    helper shifts the cut point backward until it no longer starts inside a
    tool-call result group.
    """
    if not history or len(history) <= limit:
        return history

    intervals = _tool_call_group_intervals(history)

    cut_index = len(history) - limit
    # Move cut point backward while it would start inside an open tool-call group
    while cut_index > 0:
        inside = any(start < cut_index <= end for start, end in intervals)
        if not inside:
            break
        cut_index -= 1

    return history[cut_index:]


def safe_history_split(history: list, split_index: int) -> tuple:
    """
    Split history into (left, right) at a boundary that does not break
    assistant/tool-call pairs. The right (remaining) part is guaranteed not
    to start with an orphaned tool message.
    """
    if not history:
        return [], []

    if split_index <= 0:
        return [], list(history)

    if split_index >= len(history):
        return list(history), []

    intervals = _tool_call_group_intervals(history)

    # Move split backward while it would leave the right side starting inside a group
    while split_index > 0:
        inside = any(start < split_index <= end for start, end in intervals)
        if not inside:
            break
        split_index -= 1

    return history[:split_index], history[split_index:]


def _synthesize_assistant_tool_call(tool_call_id: str, conversation_name: str | None) -> dict | None:
    """
    Try to rebuild an assistant tool_calls message from the persisted
    Agent Tool Call document. Returns None if no matching record exists.
    """
    if not tool_call_id or not conversation_name:
        return None
    try:
        doc = frappe.db.get_value(
            "Agent Tool Call",
            {"conversation": conversation_name, "call_id": tool_call_id},
            ["tool", "tool_args"],
            as_dict=True,
        )
        if not doc:
            return None
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": doc.tool or "",
                        "arguments": doc.tool_args or "{}",
                    },
                }
            ],
        }
    except Exception:
        return None


def update_tool_call_message(
    message_name: str,
    tool_call_id: str,
    tool_call: dict | list,
    result_content: Any,
    agent_doc=None,
) -> bool:
    """
    Update an existing 'Tool Call' Agent Message with the tool result so the
    request and result live in a single message row.

    Args:
        message_name: Name of the Agent Message to update.
        tool_call_id: LLM-generated tool call id.
        tool_call: Tool call payload (dict or list) to persist in tool_calls.
        result_content: Raw result returned by the tool.
        agent_doc: Agent DocType (used for max_context_chars threshold).

    Returns:
        True if the message was updated, False otherwise.
    """
    if not message_name:
        return False

    try:
        msg_doc = frappe.get_doc("Agent Message", message_name)
    except Exception as e:
        frappe.log_error(
            f"Could not load Agent Message '{message_name}' for tool result update: {e}",
            "Tool Call Message Update"
        )
        return False

    try:
        if isinstance(result_content, str):
            result_str = result_content
        else:
            result_str = json.dumps(result_content, default=str)

        result_summary = (result_str[:200] + "...") if len(result_str) > 200 else result_str

        max_context_chars = 2000
        if agent_doc:
            try:
                max_context_chars = int(getattr(agent_doc, "max_context_chars", 2000) or 2000)
            except Exception:
                max_context_chars = 2000
        max_context_chars = max(max_context_chars, 500)

        use_reference = len(result_str) > max_context_chars

        existing_content = msg_doc.content or ""
        if "**Tool Result:**" not in existing_content:
            msg_doc.content = existing_content + f"\n\n**Tool Result:**\n{result_str}"

        msg_doc.kind = "Tool Result"
        msg_doc.record_kind = "tool_result"
        msg_doc.context_policy = "include_reference" if use_reference else "include_full"
        msg_doc.context_summary = result_summary
        msg_doc.reference_doctype = "Agent Tool Call"
        if msg_doc.tool_call:
            msg_doc.reference_name = msg_doc.tool_call
        msg_doc.tool_call_id = tool_call_id
        if tool_call is not None:
            msg_doc.tool_calls = (
                json.dumps(tool_call, default=str)
                if not isinstance(tool_call, str)
                else tool_call
            )

        msg_doc.save(ignore_permissions=True)
        return True
    except Exception as e:
        frappe.log_error(
            f"Error updating tool call message '{message_name}': {e}",
            "Tool Call Message Update"
        )
        return False


def repair_message_sequence(messages: list, conversation_name: str | None = None) -> list:
    """
    Ensure OpenAI-compatible tool-call pairing in a message list.

    Instead of silently dropping orphaned role='tool' messages, this function:
      1. Drops assistant messages that declare tool_calls but no longer have
         matching tool results in the sequence (unfulfilled declarations).
      2. Attempts to repair orphaned tool results by synthesising the missing
         assistant tool_calls message from the Agent Tool Call document.
      3. Drops only tool results that cannot be repaired.

    This makes history resilient to context-window trimming, FIFO slicing,
    summarisation, and legacy data that is missing assistant tool_calls.
    """
    if not messages:
        return messages

    # First pass: identify assistant declarations and tool results.
    assistant_declarations = []  # (index, message, call_ids)
    tool_results_by_id = defaultdict(list)  # call_id -> [(index, message)]

    for idx, msg in enumerate(messages):
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role == "assistant" and msg.get("tool_calls"):
            call_ids = _tool_call_ids_from_assistant(msg)
            if call_ids:
                assistant_declarations.append((idx, msg, call_ids))
        elif role == "tool":
            cid = msg.get("tool_call_id")
            if cid:
                tool_results_by_id[cid].append((idx, msg))

    # Determine which assistant declarations are fully fulfilled by later tool results.
    keep_assistant_indices = set()
    keep_call_ids = set()
    for aidx, _msg, call_ids in assistant_declarations:
        if all(
            any(ridx > aidx for ridx, _ in tool_results_by_id.get(cid, []))
            for cid in call_ids
        ):
            keep_assistant_indices.add(aidx)
            keep_call_ids.update(call_ids)

    # Attempt to repair orphaned tool results whose assistant was dropped or missing.
    repaired = {}  # tool result index -> synthetic assistant message to insert before it
    for cid, entries in tool_results_by_id.items():
        if cid in keep_call_ids:
            continue
        for ridx, _ in entries:
            # If an assistant declared this call but the group is incomplete,
            # prefer dropping the whole group rather than synthesising a duplicate.
            has_declared_assistant = any(
                cid in call_ids and aidx < ridx for aidx, _, call_ids in assistant_declarations
            )
            if has_declared_assistant:
                continue
            synthetic = _synthesize_assistant_tool_call(cid, conversation_name)
            if synthetic:
                repaired[ridx] = synthetic
                keep_call_ids.add(cid)

    # Build final sequence.
    final = []
    dropped_tool = 0
    dropped_assistant = 0
    inserted = 0

    for idx, msg in enumerate(messages):
        if not isinstance(msg, dict):
            final.append(msg)
            continue

        role = msg.get("role")
        if role == "assistant" and msg.get("tool_calls"):
            if idx in keep_assistant_indices:
                final.append(msg)
            else:
                dropped_assistant += 1
        elif role == "tool":
            cid = msg.get("tool_call_id")
            if cid in keep_call_ids:
                if idx in repaired:
                    final.append(repaired[idx])
                    inserted += 1
                final.append(msg)
            else:
                dropped_tool += 1
        else:
            final.append(msg)

    if dropped_tool or dropped_assistant or inserted:
        frappe.log_error(
            f"repair_message_sequence conversation={conversation_name}: "
            f"dropped_orphaned_tools={dropped_tool}, "
            f"dropped_unfulfilled_assistants={dropped_assistant}, "
            f"repaired_assistants_inserted={inserted}",
            "LiteLLM Message Repair",
        )

    return final


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
        tool_call=None,
        tool_call_id=None,
        tool_calls=None,
        raw_payload=None,
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

            # Backward compatibility: older callers passed the Agent Tool Call link
            # name via the ``tool_call_id`` argument. New callers should use
            # ``tool_call`` for the link and ``tool_call_id`` for the LLM call id.
            tool_call_link = tool_call
            if tool_call_link is None and tool_call_id is not None:
                tool_call_link = tool_call_id
                tool_call_id = None

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
                "tool_call": tool_call_link,
                "tool_call_id": tool_call_id,
            }

            if tool_calls is not None:
                doc_data["tool_calls"] = (
                    json.dumps(tool_calls) if not isinstance(tool_calls, str) else tool_calls
                )

            if raw_payload is not None:
                doc_data["raw_payload"] = (
                    json.dumps(raw_payload) if not isinstance(raw_payload, str) else raw_payload
                )

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
                "tool_call_id",
                "tool_calls",
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

    def _resolve_tool_call_details(self, tool_call_id: str, tool_call_link: str):
        """Return (call_id, tool_name, tool_args) for a tool call, preferring the
        persisted ``tool_call_id`` but falling back to the linked Agent Tool Call."""
        call_id = tool_call_id
        tool_name = ""
        tool_args = "{}"

        if tool_call_link and not call_id:
            tool_call_doc = frappe.db.get_value(
                "Agent Tool Call",
                tool_call_link,
                ["call_id", "tool", "tool_args"],
                as_dict=True,
            )
            if tool_call_doc:
                call_id = tool_call_doc.call_id or tool_call_link
                tool_name = tool_call_doc.tool or ""
                tool_args = tool_call_doc.tool_args or "{}"

        return call_id or tool_call_link or "", tool_name, tool_args

    def _message_to_context(self, msg):
        """Apply context policy to a single message. Returns dict for inclusion, None to omit, or a list of dicts."""
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
        stored_tool_call_id = msg.get("tool_call_id")
        stored_tool_calls = msg.get("tool_calls")
        msg_kind = msg.get("kind")

        # Assistant message that issued one or more tool calls.
        if role_mapped == "assistant" and (
            msg_kind == "Tool Call"
            or tool_call_link
            or stored_tool_call_id
            or stored_tool_calls
        ):
            tool_calls = []
            if stored_tool_calls:
                try:
                    parsed = (
                        json.loads(stored_tool_calls)
                        if isinstance(stored_tool_calls, str)
                        else stored_tool_calls
                    )
                    if isinstance(parsed, list):
                        tool_calls = parsed
                except Exception:
                    tool_calls = []

            if not tool_calls and (stored_tool_call_id or tool_call_link):
                call_id, tool_name, tool_args = self._resolve_tool_call_details(
                    stored_tool_call_id, tool_call_link
                )
                tool_calls = [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {"name": tool_name, "arguments": tool_args},
                    }
                ]

            if tool_calls:
                # Assistant tool-call messages should not leak UI text into the
                # model context; OpenAI expects content null or string when
                # tool_calls are present.
                return {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": tool_calls,
                }

        # Tool result message (combined UI mutation pattern from streaming).
        if msg_kind == "Tool Result" and role_mapped == "assistant":
            call_id, tool_name, tool_args = self._resolve_tool_call_details(
                stored_tool_call_id, tool_call_link
            )
            assistant_msg = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {"name": tool_name, "arguments": tool_args},
                    }
                ],
            }
            tool_msg = {
                "role": "tool",
                "tool_call_id": call_id,
                "name": tool_name,
                "content": content,
            }
            return [assistant_msg, tool_msg]

        # Separate tool result message.
        if role_mapped == "tool":
            call_id, tool_name, tool_args = self._resolve_tool_call_details(
                stored_tool_call_id, tool_call_link
            )
            return {
                "role": "tool",
                "content": content,
                "tool_call_id": call_id,
                "name": tool_name,
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
        to_summarize, remaining = safe_history_split(history, split_index)

        summary_prompt = "Summarize the following conversation history concisely, capturing key information, context, and decisions. Maintain the flow of information."

        return to_summarize, remaining

    def get_stored_summary(self, conversation_name):
        return frappe.db.get_value("Agent Conversation", conversation_name, "summary")

    def update_stored_summary(self, conversation_name, new_summary):
        frappe.db.set_value("Agent Conversation", conversation_name, "summary", new_summary)

