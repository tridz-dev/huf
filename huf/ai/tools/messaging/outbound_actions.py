"""Per-action confirmation gating for multi-action outbound tools.

A multi-action built-in tool (``whatsapp``, ``telegram``, ``messenger``) is flagged ``is_outbound`` on its
Agent Tool Function row, but only some of its actions send anything. ``READ_ONLY_ACTIONS`` maps a tool name
to the actions that send nothing (``list_templates`` ...); every other action, including an unknown or
missing one, is treated as outbound and pauses for confirmation (fail closed).
"""

from __future__ import annotations

_TELEGRAM_READ_ONLY = frozenset(
	{
		"get_updates", "get_chat_info", "get_me", "get_file", "get_chat_member", "get_chat_administrators",
		"get_chat_member_count", "list_messages", "get_account_info", "list_templates", "preview_template",
		"send_chat_action", "answer_callback_query",
	}
)

# Fail closed: a mapped tool's action pauses unless it is listed here as read-only (or a draft-only action
# that sends nothing, like create_template).
# Decision: whatsapp create_template stays read-only (submits to Meta for review, sends nothing to customers).
READ_ONLY_ACTIONS: dict[str, frozenset] = {
	"whatsapp": frozenset({"list_messages", "get_account_info", "list_templates", "get_template_status", "create_template"}),
	"messenger": frozenset({"list_conversations", "list_messages"}),
	"telegram": _TELEGRAM_READ_ONLY,
}


def is_outbound_call(tool_name: str, args: dict | None) -> bool | None:
	"""None when the tool has no per-action map (gate on the tool flag as before); else whether this call's
	action is an outbound one (an unknown/missing action counts as outbound)."""
	read_only = READ_ONLY_ACTIONS.get(tool_name)
	if read_only is None:
		return None
	action = str((args or {}).get("action") or "").strip()
	return not action or action not in read_only


# Built-in tools that send messages/emails to people outside the system. Flagged ``is_outbound`` so they
# default to System Manager and ALWAYS pause for user confirmation (PLAN 06). Synced onto the Agent Tool
# Function row by registry.sync_discovered_tools.
OUTBOUND_TOOL_NAMES = frozenset(
	{
		"whatsapp",
		"telegram",
		"messenger",
		"slack_send_message",
		"slack_send_thread_reply",
		"discord_send_message",
		"google_chat_send_message",
		"google_chat_send_card",
		"gmail_send_email",
		"send_products",
		"send_wa_flow",
		"lms_send_certificate",
	}
)
_SUMMARIZERS = {"whatsapp": "huf.ai.tools.messaging.confirmation_summaries.whatsapp"}


def flag_outbound(tools):
	"""Mark the outbound built-in tools in ``tools`` (mutates the tool dicts) and return ``tools``."""
	for _tool in tools:
		if _tool.get("tool_name") in OUTBOUND_TOOL_NAMES:
			_tool["is_outbound"] = 1
			_tool.setdefault("confirmation_summary_path", _SUMMARIZERS.get(_tool["tool_name"], "huf.ai.tools.messaging.confirmation_summaries.single_target"))
	return tools
