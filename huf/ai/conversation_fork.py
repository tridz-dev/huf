# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""Fork an existing Agent Conversation into a new conversation.

Supported fork modes:
- full_history: copy every Agent Message row from the source conversation.
- summary: generate an LLM summary of the source conversation and seed the new
  conversation with that summary plus the last user/assistant exchange.
- last_output: copy only the final assistant message into a new conversation.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import now

from huf.ai.agent_integration import _run_async_safely
from huf.ai.conversation_manager import ConversationManager
from huf.ai.providers.litellm import get_simple_completion


logger = frappe.logger("huf")

FORK_MODES = {"full_history", "summary", "last_output"}
_TITLE_MAX_LENGTH = 140


def fork_conversation_impl(
    conversation_id: str | None = None,
    mode: str | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    """Create a new Agent Conversation forked from an existing one.

    Args:
        conversation_id: Name of the source Agent Conversation.
        mode: One of ``full_history``, ``summary``, ``last_output``.
        title: Optional title for the new conversation.

    Returns:
        dict with ``success``, ``conversation_id``, and ``title``.
    """
    if not conversation_id:
        frappe.throw(_("conversation_id is required"))
    if not mode:
        frappe.throw(_("mode is required"))
    if mode not in FORK_MODES:
        frappe.throw(_("Invalid fork mode: {0}").format(mode))

    try:
        source = frappe.get_doc("Agent Conversation", conversation_id)
    except frappe.DoesNotExistError:
        frappe.throw(_("Conversation not found: {0}").format(conversation_id))

    if not _can_fork(source):
        frappe.throw(
            _("You do not have permission to fork this conversation."),
            frappe.PermissionError,
        )

    if not frappe.has_permission("Agent Conversation", "create"):
        frappe.throw(
            _("Not permitted to create Agent Conversation"),
            frappe.PermissionError,
        )

    agent_name = source.agent
    if not agent_name:
        frappe.throw(_("Source conversation has no agent"))

    agent_doc = frappe.get_doc("Agent", agent_name)

    from huf.ai.agent_access import assert_agent_access

    assert_agent_access(agent_doc)

    provider = agent_doc.provider
    model = source.model or agent_doc.model

    cm = ConversationManager(
        agent_name=agent_name,
        channel="Chat",
        external_id=frappe.session.user,
    )

    target_title = _default_fork_title(title, source.title)
    target = cm.create_new_conversation(title=target_title)

    try:
        if mode == "full_history":
            _fork_full_history(source, target, cm)
        elif mode == "summary":
            _fork_summary(source, target, cm, agent_doc, provider, model)
        elif mode == "last_output":
            _fork_last_output(source, target, cm)
    except Exception:
        # Roll back the empty conversation we created so we don't leave a
        # partial fork behind.
        try:
            frappe.delete_doc("Agent Conversation", target.name, ignore_permissions=True)
        except Exception:
            logger.warning(f"Could not roll back partial fork {target.name}")
        raise

    return {
        "success": True,
        "conversation_id": target.name,
        "title": target.title,
    }


def _can_fork(source) -> bool:
    """Return True when the current user may fork the source conversation."""
    if source.owner == frappe.session.user:
        return True
    if "System Manager" in frappe.get_roles():
        return True
    return False


def _default_fork_title(provided_title: str | None, source_title: str | None) -> str:
    """Return a title for the forked conversation."""
    if provided_title:
        return provided_title[:_TITLE_MAX_LENGTH]

    base = source_title or _("Untitled Chat")
    candidate = _("{0} (Fork)").format(base)
    if len(candidate) > _TITLE_MAX_LENGTH:
        candidate = candidate[: _TITLE_MAX_LENGTH - 1] + "…"
    return candidate


def _copy_message(
    source_msg,
    target,
    cm: ConversationManager,
    conversation_index: int,
) -> None:
    """Insert a copy of ``source_msg`` into ``target`` at ``conversation_index``."""
    user_value = frappe.session.user if source_msg.role == "user" else "Agent"

    doc_data = {
        "doctype": "Agent Message",
        "conversation": target.name,
        "session_id": target.session_id,
        "conversation_index": conversation_index,
        "role": source_msg.role,
        "content": source_msg.content,
        "kind": source_msg.kind,
        "is_agent_message": source_msg.is_agent_message,
        "user": user_value,
        "agent": source_msg.agent or target.agent,
        "provider": source_msg.provider,
        "model": source_msg.model,
        # Do not carry over links to the original run / tool call to avoid
        # dangling references across conversations.
        "agent_run": None,
        "tool_call": None,
        "tool_call_id": source_msg.tool_call_id,
        "tool_calls": source_msg.tool_calls,
        "tool_name": source_msg.tool_name,
        "tool_args": source_msg.tool_args,
        "tool_status": source_msg.tool_status,
        "generated_image": source_msg.generated_image,
        "generated_audio": source_msg.generated_audio,
        "generated_video": source_msg.generated_video,
        "voice_message": source_msg.voice_message,
        "stt_model": source_msg.stt_model,
        "status": source_msg.status,
        "content_type": source_msg.content_type,
        "context_policy": source_msg.context_policy,
        "context_summary": source_msg.context_summary,
        "record_kind": source_msg.record_kind,
        "reference_doctype": source_msg.reference_doctype,
        "reference_name": source_msg.reference_name,
        "visibility": source_msg.visibility,
        "token_estimate": source_msg.token_estimate,
        "raw_payload": source_msg.raw_payload,
    }

    # Remove None values for optional fields so Frappe uses defaults/empties.
    doc_data = {k: v for k, v in doc_data.items() if v is not None}

    msg = frappe.get_doc(doc_data)
    if not frappe.has_permission("Agent Message", "create"):
        frappe.throw(
            _("Not permitted to create Agent Message"),
            frappe.PermissionError,
        )
    msg.insert()


def _fork_full_history(source, target, cm: ConversationManager) -> None:
    """Copy every message from ``source`` into ``target``."""
    messages = frappe.get_all(
        "Agent Message",
        filters={"conversation": source.name},
        fields=["name"],
        order_by="conversation_index asc",
    )

    for idx, msg_ref in enumerate(messages, start=1):
        source_msg = frappe.get_doc("Agent Message", msg_ref["name"])
        _copy_message(source_msg, target, cm, idx)

    _update_total_messages(target, len(messages))


def _fork_last_output(source, target, cm: ConversationManager) -> None:
    """Copy only the last assistant message from ``source`` into ``target``."""
    messages = frappe.get_all(
        "Agent Message",
        filters={"conversation": source.name, "role": "agent"},
        fields=["name"],
        order_by="conversation_index desc",
        limit=1,
    )

    if not messages:
        # No assistant output to fork; leave the empty conversation.
        _update_total_messages(target, 0)
        return

    source_msg = frappe.get_doc("Agent Message", messages[0]["name"])
    _copy_message(source_msg, target, cm, 1)
    _update_total_messages(target, 1)


def _fork_summary(
    source,
    target,
    cm: ConversationManager,
    agent_doc,
    provider: str,
    model: str,
) -> None:
    """Seed ``target`` with an LLM summary of ``source`` plus the last exchange."""
    history = cm.get_conversation_history(source.name, limit=200)

    if not history:
        _update_total_messages(target, 0)
        return

    summary_text = _generate_conversation_summary(history, provider, model)
    if not summary_text:
        frappe.throw(_("Could not generate a summary for this conversation."))

    # Insert the summary as a system message so it is visible context but does
    # not masquerade as an assistant turn.
    summary_msg = cm.add_message(
        conversation=target,
        role="system",
        content=summary_text,
        provider=provider,
        model=model,
        agent=agent_doc.name,
        record_kind="summary",
        context_policy="include_full",
    )

    last_exchange = _get_last_user_assistant_exchange(source.name)
    idx = 2
    for source_msg in last_exchange:
        _copy_message(source_msg, target, cm, idx)
        idx += 1

    _update_total_messages(target, 1 + len(last_exchange))

    # Carry forward conversation memory only in full-history mode; summary mode
    # intentionally starts with a clean slate.
    target.db_set("summary", summary_msg.content)


def _generate_conversation_summary(
    history: list[dict[str, Any]], provider: str, model: str
) -> str:
    """Ask the configured LLM to summarize the conversation history."""
    prompt = _(
        "Summarize the following conversation concisely. Capture the key "
        "topic, user intent, important context, and any decisions or outputs. "
        "Keep it to a few sentences.\n\n{0}"
    ).format(json.dumps(history, indent=2, default=str))

    messages = [{"role": "user", "content": prompt}]
    try:
        summary = _run_async_safely(get_simple_completion(model, messages, provider))
    except Exception as e:
        logger.warning(f"Summary generation failed: {e!s}")
        frappe.throw(_("Failed to generate conversation summary."))

    if not isinstance(summary, str):
        summary = str(summary) if summary is not None else ""

    return summary.strip()


def _get_last_user_assistant_exchange(conversation_name: str) -> list:
    """Return the last user message and the assistant response that follows it.

    The returned list is ordered by conversation_index (user first, then agent).
    """
    messages = frappe.get_all(
        "Agent Message",
        filters={"conversation": conversation_name},
        fields=["name", "role", "conversation_index"],
        order_by="conversation_index desc",
        limit=50,
    )

    if not messages:
        return []

    # Find the most recent user message, then the agent message right after it.
    user_index = None
    for msg in messages:
        if msg.role == "user":
            user_index = msg.conversation_index
            break

    if user_index is None:
        return []

    names = [msg.name for msg in messages if msg.conversation_index in (user_index, user_index + 1)]
    if not names:
        return []

    exchange = frappe.get_all(
        "Agent Message",
        filters={"name": ["in", names]},
        fields=["name"],
        order_by="conversation_index asc",
    )

    return [frappe.get_doc("Agent Message", row.name) for row in exchange]


def _update_total_messages(target, total: int) -> None:
    """Update the denormalized counters on the forked conversation."""
    frappe.db.set_value(
        "Agent Conversation",
        target.name,
        {
            "total_messages": total,
            "last_activity": now(),
        },
    )
