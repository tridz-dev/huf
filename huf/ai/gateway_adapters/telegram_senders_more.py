# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""More Telegram Bot API operations for the agent tool: venue, dice, poll, checklist, forum topics, chat reads.

Pure apart from the injected ``TelegramBotClient``; no Frappe imports. Validation raises ``ValueError``
with a message the model can act on. Field names follow Bot API 10.3 (``correct_option_ids`` is a list;
``sendChecklist`` is business-only and needs ``business_connection_id``).
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from huf.ai.gateway_adapters.telegram_client import TelegramBotClient

DICE_EMOJI = ("\U0001F3B2", "\U0001F3AF", "\U0001F3C0", "⚽", "\U0001F3B3", "\U0001F3B0")
POLL_MIN_OPTIONS, POLL_MAX_OPTIONS = 2, 12
POLL_QUESTION_MAX, POLL_OPTION_MAX, POLL_EXPLANATION_MAX = 300, 100, 200
POLL_OPEN_PERIOD = (5, 2628000)
CHECKLIST_TITLE_MAX, CHECKLIST_TASK_MAX, CHECKLIST_MAX_TASKS = 255, 100, 30
TOPIC_NAME_MAX = 128
TOPIC_ICON_COLORS = (7322096, 16766590, 13338331, 9367192, 16749490, 16478047)
MAX_GET_FILE_BYTES = 20 * 1024 * 1024
_PARSE_MODES = ("HTML", "MarkdownV2", "Markdown")


def _opts(
	payload: dict[str, Any], *, reply_to: Any = None, thread_id: Any = None, markup: Mapping[str, Any] | None = None,
	silent: bool = False, protect: bool = False, effect_id: str | None = None,
) -> dict[str, Any]:
	if thread_id not in (None, ""):
		payload["message_thread_id"] = int(thread_id)
	if reply_to not in (None, ""):
		payload["reply_parameters"] = {"message_id": int(reply_to), "allow_sending_without_reply": True}
	if markup:
		payload["reply_markup"] = dict(markup)
	if silent:
		payload["disable_notification"] = True
	if protect:
		payload["protect_content"] = True
	if effect_id:
		payload["message_effect_id"] = str(effect_id)
	return payload


def _list(value: Any, label: str) -> list:
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except ValueError:
			raise ValueError(f"{label} must be a JSON list") from None
	if not isinstance(value, (list, tuple)):
		raise ValueError(f"{label} must be a list")
	return list(value)


def _bounded(value: Any, label: str, maximum: int) -> str:
	text = str(value if value is not None else "").strip()
	if not text:
		raise ValueError(f"{label} is required")
	if len(text) > maximum:
		raise ValueError(f"{label} is too long (max {maximum} characters)")
	return text


# -- messages ----------------------------------------------------------------------------------


def send_venue(
	client: TelegramBotClient, chat_id: Any, latitude: float, longitude: float, title: str, address: str, *,
	foursquare_id: str = "", google_place_id: str = "", **opts: Any,
) -> Mapping[str, Any]:
	if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
		raise ValueError("latitude must be -90..90 and longitude -180..180")
	payload = {
		"chat_id": chat_id, "latitude": latitude, "longitude": longitude,
		"title": _bounded(title, "title", 255), "address": _bounded(address, "address", 255),
	}
	if foursquare_id:
		payload["foursquare_id"] = str(foursquare_id)
	if google_place_id:
		payload["google_place_id"] = str(google_place_id)
	return client.call("sendVenue", _opts(payload, **opts))


def send_dice(client: TelegramBotClient, chat_id: Any, emoji: str = "", **opts: Any) -> Mapping[str, Any]:
	payload: dict[str, Any] = {"chat_id": chat_id}
	if emoji:
		if emoji not in DICE_EMOJI:
			raise ValueError("emoji must be one of: " + " ".join(DICE_EMOJI))
		payload["emoji"] = emoji
	return client.call("sendDice", _opts(payload, **opts))


def build_poll(
	question: Any, options: Any, *, is_anonymous: bool | None = None, poll_type: str = "regular",
	allows_multiple_answers: bool = False, correct_option_id: Any = None, correct_option_ids: Any = None,
	explanation: str = "", parse_mode: str | None = None, open_period: Any = None,
) -> dict[str, Any]:
	"""Validated sendPoll fields (without chat/common options)."""
	items = _list(options, "options")
	if not POLL_MIN_OPTIONS <= len(items) <= POLL_MAX_OPTIONS:
		raise ValueError(f"a poll needs {POLL_MIN_OPTIONS}-{POLL_MAX_OPTIONS} options")
	built = []
	for item in items:
		text = item.get("text") if isinstance(item, Mapping) else item
		built.append({"text": _bounded(text, "each option", POLL_OPTION_MAX)})
	if len({o["text"] for o in built}) != len(built):
		raise ValueError("poll options must be unique")
	poll_type = (poll_type or "regular").strip().lower()
	if poll_type not in ("regular", "quiz"):
		raise ValueError("type must be regular or quiz")
	fields: dict[str, Any] = {
		"question": _bounded(question, "question", POLL_QUESTION_MAX), "options": built, "type": poll_type,
	}
	if is_anonymous is not None:
		fields["is_anonymous"] = bool(is_anonymous)
	if poll_type == "quiz":
		ids = correct_option_ids if correct_option_ids not in (None, "", []) else (
			[correct_option_id] if correct_option_id not in (None, "") else []
		)
		try:
			ids = sorted({int(i) for i in _list(ids, "correct_option_id")})
		except (TypeError, ValueError):
			raise ValueError("correct_option_id must be a 0-based option index") from None
		if not ids:
			raise ValueError("a quiz needs correct_option_id (0-based index of the right option)")
		if any(i < 0 or i >= len(built) for i in ids):
			raise ValueError("correct_option_id is outside the options")
		if len(ids) > 1 and not allows_multiple_answers:
			raise ValueError("several correct options need allows_multiple_answers")
		fields["correct_option_ids"] = ids
		if explanation:
			fields["explanation"] = _bounded(explanation, "explanation", POLL_EXPLANATION_MAX)
			if parse_mode in _PARSE_MODES:
				fields["explanation_parse_mode"] = parse_mode
	elif correct_option_id not in (None, "") or correct_option_ids not in (None, "", []) or explanation:
		raise ValueError("correct_option_id and explanation apply to type=quiz only")
	if allows_multiple_answers:
		fields["allows_multiple_answers"] = True
	if open_period not in (None, "", 0):
		try:
			period = int(open_period)
		except (TypeError, ValueError):
			raise ValueError("open_period must be a number of seconds") from None
		if not POLL_OPEN_PERIOD[0] <= period <= POLL_OPEN_PERIOD[1]:
			raise ValueError(f"open_period must be {POLL_OPEN_PERIOD[0]}-{POLL_OPEN_PERIOD[1]} seconds")
		fields["open_period"] = period
	return fields


def send_poll(client: TelegramBotClient, chat_id: Any, poll: Mapping[str, Any], **opts: Any) -> Mapping[str, Any]:
	return client.call("sendPoll", _opts({"chat_id": chat_id, **poll}, **opts))


def stop_poll(client: TelegramBotClient, chat_id: Any, message_id: Any) -> Mapping[str, Any]:
	return client.call("stopPoll", {"chat_id": chat_id, "message_id": int(message_id)})


def build_checklist(title: Any, tasks: Any, *, parse_mode: str | None = None, others_can_add: bool = False,
	others_can_mark: bool = False) -> dict[str, Any]:
	items = _list(tasks, "tasks")
	if not 1 <= len(items) <= CHECKLIST_MAX_TASKS:
		raise ValueError(f"a checklist needs 1-{CHECKLIST_MAX_TASKS} tasks")
	built = []
	for n, item in enumerate(items, 1):
		text = item.get("text") if isinstance(item, Mapping) else item
		task = {"id": n, "text": _bounded(text, "each task", CHECKLIST_TASK_MAX)}
		if parse_mode in _PARSE_MODES:
			task["parse_mode"] = parse_mode
		built.append(task)
	checklist: dict[str, Any] = {"title": _bounded(title, "title", CHECKLIST_TITLE_MAX), "tasks": built}
	if parse_mode in _PARSE_MODES:
		checklist["parse_mode"] = parse_mode
	if others_can_add:
		checklist["others_can_add_tasks"] = True
	if others_can_mark:
		checklist["others_can_mark_tasks_as_done"] = True
	return checklist


def send_checklist(
	client: TelegramBotClient, chat_id: Any, business_connection_id: str, checklist: Mapping[str, Any], *,
	reply_to: Any = None, markup: Mapping[str, Any] | None = None, silent: bool = False, protect: bool = False,
	effect_id: str | None = None,
) -> Mapping[str, Any]:
	if not str(business_connection_id or "").strip():
		raise ValueError("business_connection_id is required (sendChecklist works only for a connected business account)")
	payload = {"business_connection_id": str(business_connection_id).strip(), "chat_id": chat_id,
		"checklist": dict(checklist)}
	return client.call("sendChecklist", _opts(payload, reply_to=reply_to, markup=markup, silent=silent,
		protect=protect, effect_id=effect_id))


# -- forum topics ------------------------------------------------------------------------------


def create_forum_topic(client: TelegramBotClient, chat_id: Any, name: Any, *, icon_color: Any = None,
	icon_custom_emoji_id: str = "") -> Mapping[str, Any]:
	payload: dict[str, Any] = {"chat_id": chat_id, "name": _bounded(name, "name", TOPIC_NAME_MAX)}
	if icon_color not in (None, ""):
		if int(icon_color) not in TOPIC_ICON_COLORS:
			raise ValueError("icon_color must be one of " + ", ".join(str(c) for c in TOPIC_ICON_COLORS))
		payload["icon_color"] = int(icon_color)
	if icon_custom_emoji_id:
		payload["icon_custom_emoji_id"] = str(icon_custom_emoji_id)
	return client.call("createForumTopic", payload)


def edit_forum_topic(client: TelegramBotClient, chat_id: Any, thread_id: Any, *, name: Any = "",
	icon_custom_emoji_id: str | None = None) -> Mapping[str, Any]:
	payload: dict[str, Any] = {"chat_id": chat_id, "message_thread_id": int(thread_id)}
	if name:
		payload["name"] = _bounded(name, "name", TOPIC_NAME_MAX)
	if icon_custom_emoji_id is not None:
		payload["icon_custom_emoji_id"] = str(icon_custom_emoji_id)
	if len(payload) == 2:
		raise ValueError("edit_forum_topic needs name or icon_custom_emoji_id")
	return client.call("editForumTopic", payload)


def topic_call(client: TelegramBotClient, method: str, chat_id: Any, thread_id: Any) -> Mapping[str, Any]:
	if method not in ("closeForumTopic", "reopenForumTopic", "deleteForumTopic"):
		raise ValueError("unsupported topic method")
	return client.call(method, {"chat_id": chat_id, "message_thread_id": int(thread_id)})


def bot_can_manage_topics(client: TelegramBotClient, chat_id: Any, *, deleting: bool = False) -> str | None:
	"""None when the bot may manage topics in ``chat_id``, else a short reason."""
	me = client.get_me() or {}
	member = client.call("getChatMember", {"chat_id": chat_id, "user_id": int(me.get("id") or 0)}) or {}
	status = member.get("status")
	if status == "creator":
		return None
	if status != "administrator":
		return "the bot is not an administrator of that chat"
	if not member.get("can_manage_topics"):
		return "the bot lacks the manage topics right in that chat"
	if deleting and not member.get("can_delete_messages"):
		return "the bot lacks the delete messages right in that chat"
	return None


# -- reads -------------------------------------------------------------------------------------

_MEMBER_KEYS = ("status", "is_anonymous", "custom_title", "until_date", "is_member", "can_manage_topics")


def _public_user(user: Any) -> dict[str, Any]:
	user = user if isinstance(user, Mapping) else {}
	return {k: user.get(k) for k in ("id", "is_bot", "first_name", "last_name", "username") if user.get(k) is not None}


def _public_member(member: Any) -> dict[str, Any]:
	member = member if isinstance(member, Mapping) else {}
	out = {"user": _public_user(member.get("user"))}
	out.update({k: member[k] for k in _MEMBER_KEYS if k in member})
	out["rights"] = sorted(k for k, v in member.items() if k.startswith("can_") and v is True)
	return out


def get_chat_member(client: TelegramBotClient, chat_id: Any, user_id: Any) -> dict[str, Any]:
	return _public_member(client.call("getChatMember", {"chat_id": chat_id, "user_id": int(user_id)}))


def get_chat_administrators(client: TelegramBotClient, chat_id: Any) -> list[dict[str, Any]]:
	rows: Sequence = client.call("getChatAdministrators", {"chat_id": chat_id}) or []
	return [_public_member(m) for m in rows]


def get_chat_member_count(client: TelegramBotClient, chat_id: Any) -> Any:
	return client.call("getChatMemberCount", {"chat_id": chat_id})
