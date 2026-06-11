import json

import frappe
from frappe import _

from .agent_integration import run_agent_sync, _is_user_allowed
from .conversation_manager import ConversationManager


def _as_bool(value) -> bool:
    """Parse Frappe/API boolean values consistently."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return False


@frappe.whitelist(allow_guest=True)
def run_agent_sync_chat(
    agent_name: str,
    prompt: str = None,
    provider: str = None,
    model: str = None,
    channel_id: str = None,
    external_id: str = None,
    conversation_id: str = None,
    create_new=False,
    parent_run_id: str = None,
    orchestration_id: str = None,
    response_format=None,
    flow_run_id: str = None,
    flow_node_id: str = None,
    run_kind: str = None,
    prompt_template: str = None,
    prompt_version=None,
    parent_conversation_id: str = None,
    invoked_by_agent: str = None,
    prompt_cache_options=None,
):
    """Sync chat API with explicit new-conversation support.

    Existing ``run_agent_sync`` reuses the latest active conversation for the
    same agent + session when ``conversation_id`` is omitted. That behavior is
    useful for simple integrations but ambiguous for ChatGPT-style UIs where a
    logged-in user can create and switch between multiple chats.

    Set ``create_new=true`` to force a fresh Agent Conversation, then run the
    first message inside that new conversation. Subsequent turns should pass the
    returned ``conversation_id``.
    """
    if not agent_name:
        frappe.throw(_("Agent Name is required"))

    if not channel_id:
        channel_id = "api"

    if _as_bool(create_new):
        agent_doc = frappe.get_doc("Agent", agent_name)

        if frappe.session.user == "Guest" and not agent_doc.allow_guest:
            frappe.throw(_("Access denied. This agent does not allow guest access."), frappe.PermissionError)

        if not _is_user_allowed(agent_doc, frappe.session.user):
            frappe.throw(_("You are not authorized to use this agent."), frappe.PermissionError)

        conv_manager = ConversationManager(
            agent_name=agent_name,
            channel=channel_id,
            external_id=external_id,
        )
        conversation = conv_manager.create_new_conversation(
            title=f"Chat with {agent_name}"
        )
        conversation_id = conversation.name

    return run_agent_sync(
        agent_name=agent_name,
        prompt=prompt,
        provider=provider,
        model=model,
        channel_id=channel_id,
        external_id=external_id,
        conversation_id=conversation_id,
        parent_run_id=parent_run_id,
        orchestration_id=orchestration_id,
        response_format=response_format,
        flow_run_id=flow_run_id,
        flow_node_id=flow_node_id,
        run_kind=run_kind,
        prompt_template=prompt_template,
        prompt_version=prompt_version,
        parent_conversation_id=parent_conversation_id,
        invoked_by_agent=invoked_by_agent,
        prompt_cache_options=prompt_cache_options,
    )
