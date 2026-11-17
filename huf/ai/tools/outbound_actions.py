"""Per-action confirmation gating for multi-action outbound tools.

A multi-action built-in tool (``whatsapp``, ``telegram``, ``messenger``) is flagged ``is_outbound`` on its
Agent Tool Function row, but only some of its actions send anything. ``OUTBOUND_ACTIONS`` maps a tool name
to the set of action names that reach people (and therefore pause for confirmation); read-only actions such
as ``list_templates`` run normally. Fail closed: an empty/unknown action on a mapped tool still confirms.
"""

from __future__ import annotations

from huf.ai.tools import telegram_tool_spec

_TELEGRAM_READ_ONLY = frozenset(
	{
		"get_updates", "get_chat_info", "get_me", "get_file", "get_chat_member", "get_chat_administrators",
		"get_chat_member_count", "list_messages", "get_account_info", "list_templates", "preview_template",
		"send_chat_action", "answer_callback_query",
	}
)

OUTBOUND_ACTIONS: dict[str, frozenset] = {
	"whatsapp": frozenset(
		{
			"send_message", "send_media", "send_voice_note", "send_location", "send_contact", "send_reaction",
			"send_template", "send_image", "send_video", "send_audio", "send_document", "send_sticker",
			"send_buttons", "send_list", "send_cta_url", "send_products",
		}
	),
	"messenger": frozenset({"send_message", "reply_message"}),
	"telegram": frozenset(telegram_tool_spec.ACTION_ARGS) - _TELEGRAM_READ_ONLY,
}


def is_outbound_call(tool_name: str, args: dict | None) -> bool | None:
	"""None when the tool has no per-action map (gate on the tool flag as before); else whether this call's
	action is an outbound one (an unknown/missing action counts as outbound)."""
	actions = OUTBOUND_ACTIONS.get(tool_name)
	if actions is None:
		return None
	action = str((args or {}).get("action") or "").strip()
	return not action or action in actions
