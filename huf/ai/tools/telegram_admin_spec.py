"""Single declaration of the ``telegram_admin`` tool's arguments.

Every action lists the argument names it reads and whether each is required. The same table drives:

- the registry schema shown to the model (``registry_parameters``),
- the strict validation that runs BEFORE any gate, cap or human-approval request (``validate``),
- the readable approval card (``telegram_admin_tools.describe_action``).

An action can only read an argument that is declared here; anything else is refused with the valid names,
and a missing required argument is refused instead of silently defaulting to an empty value.

Plain data and stdlib only: the registry imports this module without touching Frappe.
"""

from __future__ import annotations

import json
from typing import Any

# name -> (JSON type, description). ``chat`` accepts an integer or a numeric/@username string.
ARG_TYPES: dict[str, tuple[str, str]] = {
	"chat_id": ("chat", "Target chat (numeric id or @username). Group actions default to the current chat."),
	"user_id": ("integer", "Target Telegram user id."),
	"message_id": ("integer", "Target message id."),
	"message_ids": ("array", "Message ids to delete (list of integers)."),
	"reply_to_message_id": ("integer", "Message id to reply to."),
	"business_connection_id": ("string", "Business connection id."),
	"text": ("string", "Message text."),
	"title": ("string", "New chat title (max 128 characters)."),
	"description": (
		"string",
		"New description (max 255 characters for a chat, 512 for the bot). Empty string clears it.",
	),
	"name": (
		"string",
		"Name (max 64 characters for the bot, 32 for an invite link). Empty string clears the bot name.",
	),
	"short_description": (
		"string",
		"New bot short description shown on the profile page (max 120 characters). Empty string clears it.",
	),
	"language_code": (
		"string",
		"Two-letter language code the profile text applies to; omit for the default.",
	),
	"commands": (
		"array",
		"Bot commands: [{command, description, is_ephemeral}]. Empty list clears the list.",
	),
	"command_scope": (
		"string",
		"Command scope: default, all_private_chats, all_group_chats, all_chat_administrators, chat, "
		"chat_administrators or chat_member (the last three need chat_id; chat_member also user_id).",
	),
	"menu_button": ("object", "Menu button: {type: commands|default|web_app, text, web_app: {url}}."),
	"until_date": ("integer", "Unix time when the restriction or ban ends."),
	"duration_minutes": ("integer", "Length of the restriction or ban in minutes."),
	"revoke_messages": ("boolean", "ban: also delete the user's messages."),
	"preset": ("string", "Restriction preset: mute, no_media, no_links, read_only or no_invites_or_pins."),
	"permissions": ("object", "Explicit chat permissions {can_send_messages: false, ...}; replaces preset."),
	"rights": (
		"array",
		"Admin rights to grant (list of can_* names; can_promote_members is never grantable).",
	),
	"invite_link": ("string", "The invite link to revoke."),
	"expire_date": ("integer", "Unix time when the invite link expires."),
	"member_limit": ("integer", "Max members who may join via the invite link."),
	"creates_join_request": (
		"boolean",
		"Invite link requires admin approval (cannot combine with member_limit).",
	),
	"notify": ("boolean", "pin: notify members (default silent)."),
	"return_bots": ("boolean", "get_admins: include bot administrators."),
	"all_messages": (
		"boolean",
		"delete_business_messages: also other people's messages (needs recipient scope 'Any number').",
	),
}

# action -> {argument: required}. Order is the display order. This is the ONLY place arguments are declared.
ACTION_ARGS: dict[str, dict[str, bool]] = {
	"ban": {
		"chat_id": False,
		"user_id": True,
		"until_date": False,
		"duration_minutes": False,
		"revoke_messages": False,
	},
	"unban": {"chat_id": False, "user_id": True},
	"restrict": {
		"chat_id": False,
		"user_id": True,
		"preset": False,
		"permissions": False,
		"until_date": False,
		"duration_minutes": False,
	},
	"unrestrict": {"chat_id": False, "user_id": True},
	"promote": {"chat_id": False, "user_id": True, "rights": True},
	"demote": {"chat_id": False, "user_id": True},
	"set_chat_title": {"chat_id": False, "title": True},
	"set_chat_description": {"chat_id": False, "description": True},
	"pin": {"chat_id": False, "message_id": True, "notify": False},
	"unpin": {"chat_id": False, "message_id": False},
	"delete_message": {"chat_id": False, "message_id": True},
	"approve_join_request": {"chat_id": False, "user_id": True},
	"decline_join_request": {"chat_id": False, "user_id": True},
	"create_invite_link": {
		"chat_id": False,
		"name": False,
		"expire_date": False,
		"member_limit": False,
		"creates_join_request": False,
	},
	"revoke_invite_link": {"chat_id": False, "invite_link": True},
	"get_admins": {"chat_id": False, "return_bots": False},
	"set_my_commands": {
		"commands": True,
		"command_scope": False,
		"language_code": False,
		"chat_id": False,
		"user_id": False,
	},
	"set_my_name": {"name": True, "language_code": False},
	"set_my_description": {"description": True, "language_code": False},
	"set_my_short_description": {"short_description": True, "language_code": False},
	"set_chat_menu_button": {"menu_button": True, "chat_id": False},
	"get_business_connection": {"business_connection_id": True},
	"send_business_message": {
		"business_connection_id": True,
		"chat_id": True,
		"text": True,
		"reply_to_message_id": False,
	},
	"read_business_message": {"business_connection_id": True, "chat_id": True, "message_id": True},
	"delete_business_messages": {
		"business_connection_id": True,
		"message_ids": True,
		"chat_id": False,
		"all_messages": False,
	},
}

_GENERIC_VALUE_NAMES = frozenset({"text", "value", "content", "message", "body", "string"})

# Short, per-action usage line for the tool description (generated, so it cannot drift).
CHOICES = "|".join(ACTION_ARGS)


def usage(action: str) -> str:
	spec = ACTION_ARGS[action]
	return f"{action}({', '.join(k if req else k + '?' for k, req in spec.items())})"


def usage_summary() -> str:
	return "; ".join(usage(a) for a in ACTION_ARGS)


def registry_parameters(p) -> list[dict]:
	"""Registry parameter rows (``p`` is the registry's ``_p`` row builder) generated from the table."""
	rows = [
		p(
			"action",
			required=True,
			description=f"Action to perform. One of: {CHOICES}",
		)
	]
	names: list[str] = []
	for spec in ACTION_ARGS.values():
		for n in spec:
			if n not in names:
				names.append(n)
	for name in names:
		kind, desc = ARG_TYPES[name]
		used = [a for a, s in ACTION_ARGS.items() if name in s]
		req = [a for a in used if ACTION_ARGS[a][name]]
		note = f" Used by: {', '.join(used)}."
		if req:
			note += f" Required for: {', '.join(req)}."
		rows.append(p(name, type="string" if kind == "chat" else kind, description=desc + note))
	return rows


def _bad(action: str, name: str, expect: str):
	from huf.ai.tools.telegram_admin_tools import Refused

	return Refused(
		"invalid_argument",
		f"argument '{name}' for {action} must be {expect}",
		valid_arguments=list(ACTION_ARGS[action]),
	)


def _coerce(action: str, name: str, value: Any) -> Any:
	kind = ARG_TYPES[name][0]
	if kind == "chat":
		if isinstance(value, bool) or not isinstance(value, (int, str)):
			raise _bad(action, name, "a numeric chat id or @username")
	elif kind == "integer":
		if isinstance(value, bool) or not (
			isinstance(value, int) or (isinstance(value, str) and value.strip().lstrip("-").isdigit())
		):
			raise _bad(action, name, "an integer")
	elif kind == "boolean":
		if not (
			isinstance(value, bool)
			or str(value).strip().lower() in ("true", "false", "1", "0", "yes", "no", "on", "off")
		):
			raise _bad(action, name, "true or false")
	elif kind == "string":
		if not isinstance(value, str):
			raise _bad(action, name, "a string")
	elif kind in ("array", "object"):
		want = list if kind == "array" else dict
		if isinstance(value, str):
			try:
				parsed = json.loads(value)
			except ValueError:
				parsed = None
			ok = isinstance(parsed, want) or (
				kind == "array" and name in ("rights", "message_ids") and value.strip()
			)
			if not ok:
				raise _bad(action, name, f"a {kind} (or its JSON text)")
		elif not isinstance(value, want):
			raise _bad(action, name, f"a {kind}")
	return value


def validate(action: str, args: dict) -> dict:
	"""Return ``args`` after checking names, presence and types against the table; raise ``Refused`` otherwise."""
	from huf.ai.tools.telegram_admin_tools import Refused

	spec = ACTION_ARGS[action]
	valid = list(spec)
	unknown = [k for k in args if k not in spec]
	if unknown:
		hints = []
		for k in unknown:
			near = [a for a in spec if k in a or a in k]
			if not near and k in _GENERIC_VALUE_NAMES:
				near = [a for a, req in spec.items() if req and ARG_TYPES[a][0] == "string"][:1]
			hints.append(f"unknown argument '{k}' for {action}" + (f"; use '{near[0]}'" if near else ""))
		raise Refused(
			"invalid_argument",
			"; ".join(hints) + f". Valid arguments for {action}: {', '.join(valid) or '(none)'}.",
			unknown_arguments=unknown,
			valid_arguments=valid,
		)
	missing = [k for k, req in spec.items() if req and args.get(k) is None]
	if missing:
		raise Refused(
			"invalid_argument",
			f"missing required argument(s) for {action}: {', '.join(missing)}. "
			f"Valid arguments for {action}: {', '.join(valid)}.",
			missing_arguments=missing,
			valid_arguments=valid,
		)
	for k, v in args.items():
		if v is not None:
			_coerce(action, k, v)
	return args
