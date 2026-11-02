# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""setMyCommands per scope/language (WP-8e, R9). Pure builders plus thin senders over ``TelegramBotClient``.

The single validated path for command lists (the client has no ``set_my_commands`` of its own). Supports
``is_ephemeral`` (BotCommand.is_ephemeral: command replies are visible only to the sender and the bot).
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

SCOPES = (
	"default",
	"all_private_chats",
	"all_group_chats",
	"all_chat_administrators",
	"chat",
	"chat_administrators",
	"chat_member",
)
MAX_COMMANDS = 100
_NAME_RE = re.compile(r"^[a-z0-9_]{1,32}$")
_LANG_RE = re.compile(r"^[a-z]{2}$")


def build_scope(scope: str = "default", *, chat_id: Any = None, user_id: Any = None) -> dict[str, Any]:
	if scope not in SCOPES:
		raise ValueError(f"Unknown command scope: {scope}")
	out: dict[str, Any] = {"type": scope}
	if scope in ("chat", "chat_administrators", "chat_member"):
		if chat_id in (None, ""):
			raise ValueError(f"Scope {scope} needs chat_id")
		out["chat_id"] = chat_id
	if scope == "chat_member":
		if user_id in (None, ""):
			raise ValueError("Scope chat_member needs user_id")
		out["user_id"] = int(user_id)
	return out


def build_commands(commands: Sequence[Any]) -> list[dict[str, Any]]:
	"""Validate and normalise ``[(name, description[, ephemeral])]`` or ``[{command, description, is_ephemeral}]``."""
	if not commands:
		raise ValueError("At least one command is required (use delete_commands to clear)")
	if len(commands) > MAX_COMMANDS:
		raise ValueError(f"At most {MAX_COMMANDS} commands are allowed")
	out, seen = [], set()
	for c in commands:
		if isinstance(c, Mapping):
			name, desc, eph = c.get("command"), c.get("description"), bool(c.get("is_ephemeral"))
		else:
			name, desc, eph = c[0], c[1], bool(c[2]) if len(c) > 2 else False
		name = str(name or "")
		if not _NAME_RE.match(name):
			raise ValueError(f"Invalid command name '{name}': 1-32 chars of lowercase a-z, 0-9, _")
		desc = str(desc or "").strip()
		if not 1 <= len(desc) <= 256:
			raise ValueError(f"Command '{name}' description must be 1-256 characters")
		if name in seen:
			raise ValueError(f"Duplicate command '{name}'")
		seen.add(name)
		item: dict[str, Any] = {"command": name, "description": desc}
		if eph:
			item["is_ephemeral"] = True
		out.append(item)
	return out


def build_payload(
	commands: Sequence[Any],
	*,
	scope: str = "default",
	chat_id: Any = None,
	user_id: Any = None,
	language_code: str | None = None,
) -> dict[str, Any]:
	payload: dict[str, Any] = {"commands": build_commands(commands)}
	if scope != "default":
		payload["scope"] = build_scope(scope, chat_id=chat_id, user_id=user_id)
	if language_code:
		if not _LANG_RE.match(language_code):
			raise ValueError("language_code must be a two-letter lowercase ISO 639-1 code")
		payload["language_code"] = language_code
	return payload


def set_commands(client: Any, commands: Sequence[Any], **kw: Any) -> Any:
	return client.call("setMyCommands", build_payload(commands, **kw))


def _target(scope: str, chat_id: Any, user_id: Any, language_code: str | None) -> dict[str, Any]:
	payload: dict[str, Any] = {}
	if scope != "default":
		payload["scope"] = build_scope(scope, chat_id=chat_id, user_id=user_id)
	if language_code:
		payload["language_code"] = language_code
	return payload


def delete_commands(
	client: Any,
	*,
	scope: str = "default",
	chat_id: Any = None,
	user_id: Any = None,
	language_code: str | None = None,
) -> Any:
	return client.call("deleteMyCommands", _target(scope, chat_id, user_id, language_code))


def get_commands(
	client: Any,
	*,
	scope: str = "default",
	chat_id: Any = None,
	user_id: Any = None,
	language_code: str | None = None,
) -> Any:
	return client.call("getMyCommands", _target(scope, chat_id, user_id, language_code))
