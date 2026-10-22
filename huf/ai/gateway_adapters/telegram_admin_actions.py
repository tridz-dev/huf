# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Group / channel administration helpers over the Bot API (WP-8c). Pure; no Frappe imports.

These are plain functions taking an injected ``TelegramBotClient``. They are NOT agent-callable: the
admin cockpit (WP-9) is the only intended caller, behind its own role / confirm / audit checks.

Every helper raises ``AdminActionError`` (a ``ValueError``) on failure, with a stable ``code`` and an
operator-readable message, instead of leaking a raw Bot API description. Codes: ``not_enough_rights``,
``not_admin``, ``chat_not_found``, ``user_not_in_chat``, ``cannot_target_admin``, ``request_gone``,
``message_gone``, ``flood``, ``bad_request``, ``api_error``.
"""

from __future__ import annotations

from typing import Any, Mapping

from huf.ai.gateway_adapters.telegram_client import TelegramApiError, TelegramBotClient

# promoteChatMember rights (Bot API 10.3). All optional booleans; pass False to demote.
ADMIN_RIGHTS: tuple[str, ...] = (
	"is_anonymous",
	"can_manage_chat",
	"can_delete_messages",
	"can_manage_video_chats",
	"can_restrict_members",
	"can_promote_members",
	"can_change_info",
	"can_invite_users",
	"can_post_stories",
	"can_edit_stories",
	"can_delete_stories",
	"can_post_messages",
	"can_edit_messages",
	"can_pin_messages",
	"can_manage_topics",
	"can_manage_direct_messages",
	"can_manage_tags",
	"can_send_welcome_messages",
)

# ChatPermissions (restrictChatMember).
CHAT_PERMISSIONS: tuple[str, ...] = (
	"can_send_messages",
	"can_send_audios",
	"can_send_documents",
	"can_send_photos",
	"can_send_videos",
	"can_send_video_notes",
	"can_send_voice_notes",
	"can_send_polls",
	"can_send_other_messages",
	"can_add_web_page_previews",
	"can_react_to_messages",
	"can_change_info",
	"can_invite_users",
	"can_pin_messages",
	"can_manage_topics",
)

JOIN_RESULTS = ("approve", "decline", "queue")


class AdminActionError(ValueError):
	def __init__(self, method: str, code: str, message: str, *, cause: TelegramApiError | None = None) -> None:
		self.method = method
		self.code = code
		self.cause = cause
		super().__init__(message)


def classify_error(method: str, exc: TelegramApiError) -> AdminActionError:
	d = (exc.description or "").lower()
	if "not enough rights" in d or "chat_admin_required" in d or "need administrator rights" in d or (
		"administrator rights" in d
	) or "have no rights" in d:
		code, msg = "not_enough_rights", (
			f"The bot lacks the administrator right needed for {method}. Grant it in the chat's admin settings."
		)
	elif "bot is not a member" in d or "bot was kicked" in d or "bot is not an administrator" in d:
		code, msg = "not_admin", f"The bot is not an administrator of this chat ({method})."
	elif exc.chat_not_found:
		code, msg = "chat_not_found", f"Chat not found for {method}."
	elif "user_not_participant" in d or "participant_id_invalid" in d or "user not found" in d:
		code, msg = "user_not_in_chat", f"The user is not a member of this chat ({method})."
	elif "can't remove chat owner" in d or "user is an administrator" in d or "can't restrict" in d or (
		"can't demote" in d
	) or "method is available for supergroup" in d:
		code, msg = "cannot_target_admin", f"{method} cannot be applied to this user or chat type: {exc.description}"
	elif "hide_requester_missing" in d or "user_already_participant" in d or "join request" in d:
		code, msg = "request_gone", "The join request was already handled or no longer exists."
	elif "message to delete not found" in d or "message to pin not found" in d or "message can't be deleted" in d:
		code, msg = "message_gone", f"The message is gone or cannot be changed ({method})."
	elif exc.flood_control:
		code, msg = "flood", f"Telegram rate limit hit on {method}; retry after {exc.retry_after or '?'}s."
	elif exc.error_code == 400:
		code, msg = "bad_request", f"Telegram rejected {method}: {exc.description}"
	else:
		code, msg = "api_error", f"Telegram {method} failed: {exc.description}"
	return AdminActionError(method, code, msg, cause=exc)


def _call(client: TelegramBotClient, method: str, payload: Mapping[str, Any]) -> Any:
	try:
		return client.call(method, dict(payload))
	except TelegramApiError as exc:
		raise classify_error(method, exc) from None


def _id(value: Any) -> int | str:
	if isinstance(value, str) and not value.lstrip("-").isdigit():
		return value  # @username
	return int(value)


# -- join requests -----------------------------------------------------------------------------


def approve_join_request(client, chat_id, user_id):
	"""approveChatJoinRequest. Needs the ``can_invite_users`` admin right."""
	return _call(client, "approveChatJoinRequest", {"chat_id": _id(chat_id), "user_id": int(user_id)})


def decline_join_request(client, chat_id, user_id):
	"""declineChatJoinRequest. Needs the ``can_invite_users`` admin right."""
	return _call(client, "declineChatJoinRequest", {"chat_id": _id(chat_id), "user_id": int(user_id)})


def answer_join_request_query(client, query_id: str, result: str):
	"""Guard mode: answerChatJoinRequestQuery (approve | decline | queue), within 10s of the update."""
	if result not in JOIN_RESULTS:
		raise ValueError(f"result must be one of {JOIN_RESULTS}")
	return _call(client, "answerChatJoinRequestQuery", {"chat_join_request_query_id": str(query_id), "result": result})


def send_join_request_web_app(client, query_id: str, web_app_url: str):
	"""Guard mode: show a Mini App to the requester; resolve later with ``answer_join_request_query``."""
	if not str(web_app_url).startswith("https://"):
		raise ValueError("web_app_url must be an HTTPS URL")
	return _call(
		client, "sendChatJoinRequestWebApp", {"chat_join_request_query_id": str(query_id), "web_app_url": web_app_url}
	)


# -- members -----------------------------------------------------------------------------------


def ban_member(client, chat_id, user_id, *, until_date: int | None = None, revoke_messages: bool = False):
	payload: dict[str, Any] = {"chat_id": _id(chat_id), "user_id": int(user_id)}
	if until_date:
		payload["until_date"] = int(until_date)
	if revoke_messages:
		payload["revoke_messages"] = True
	return _call(client, "banChatMember", payload)


def unban_member(client, chat_id, user_id, *, only_if_banned: bool = True):
	return _call(
		client, "unbanChatMember", {"chat_id": _id(chat_id), "user_id": int(user_id), "only_if_banned": only_if_banned}
	)


def _flags(allowed: tuple[str, ...], values: Mapping[str, Any], what: str) -> dict[str, bool]:
	unknown = sorted(set(values) - set(allowed))
	if unknown:
		raise ValueError(f"unknown {what}: {', '.join(unknown)}")
	return {k: bool(v) for k, v in values.items()}


def restrict_member(client, chat_id, user_id, permissions: Mapping[str, bool], *, until_date: int | None = None):
	"""restrictChatMember with an explicit ChatPermissions set (omitted permissions are denied)."""
	perms = {k: False for k in CHAT_PERMISSIONS}
	perms.update(_flags(CHAT_PERMISSIONS, permissions, "permission"))
	payload: dict[str, Any] = {
		"chat_id": _id(chat_id),
		"user_id": int(user_id),
		"permissions": perms,
		"use_independent_chat_permissions": True,
	}
	if until_date:
		payload["until_date"] = int(until_date)
	return _call(client, "restrictChatMember", payload)


def unrestrict_member(client, chat_id, user_id):
	"""Lift restrictions: pass True for every permission."""
	return restrict_member(client, chat_id, user_id, {k: True for k in CHAT_PERMISSIONS})


def promote_member(client, chat_id, user_id, rights: Mapping[str, bool]):
	"""promoteChatMember with EXACTLY the given rights (none implied; unnamed rights are sent as False)."""
	if not rights:
		raise ValueError("rights must name the admin rights explicitly; use demote_member to remove all")
	body = {k: False for k in ADMIN_RIGHTS}
	body.update(_flags(ADMIN_RIGHTS, rights, "admin right"))
	return _call(client, "promoteChatMember", {"chat_id": _id(chat_id), "user_id": int(user_id), **body})


def demote_member(client, chat_id, user_id):
	return _call(
		client, "promoteChatMember", {"chat_id": _id(chat_id), "user_id": int(user_id), **{k: False for k in ADMIN_RIGHTS}}
	)


# -- chat --------------------------------------------------------------------------------------


def set_chat_title(client, chat_id, title: str):
	title = (title or "").strip()
	if not 1 <= len(title) <= 128:
		raise ValueError("chat title must be 1-128 characters")
	return _call(client, "setChatTitle", {"chat_id": _id(chat_id), "title": title})


def set_chat_description(client, chat_id, description: str):
	if len(description or "") > 255:
		raise ValueError("chat description must be at most 255 characters")
	return _call(client, "setChatDescription", {"chat_id": _id(chat_id), "description": description or ""})


def pin_message(client, chat_id, message_id, *, silent: bool = True):
	return _call(
		client,
		"pinChatMessage",
		{"chat_id": _id(chat_id), "message_id": int(message_id), "disable_notification": bool(silent)},
	)


def delete_message(client, chat_id, message_id):
	return _call(client, "deleteMessage", {"chat_id": _id(chat_id), "message_id": int(message_id)})


def get_chat_member(client, chat_id, user_id):
	return _call(client, "getChatMember", {"chat_id": _id(chat_id), "user_id": int(user_id)})


def get_admins(client, chat_id, *, return_bots: bool = False) -> list:
	"""getChatAdministrators (``return_bots`` per Bot API 10.0)."""
	payload: dict[str, Any] = {"chat_id": _id(chat_id)}
	if return_bots:
		payload["return_bots"] = True
	return _call(client, "getChatAdministrators", payload) or []
