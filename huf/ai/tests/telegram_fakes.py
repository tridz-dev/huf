"""In-memory fake Telegram Bot API for adapter tests (implements injected http_post / http_get)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "telegram"
TOKEN = "123456:ABCdefGhIJKlmNoPQRsTUVwxyZ"
SECRET = "shh-secret"


def load_fixture(name: str) -> dict:
	return json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))


class FakeResponse:
	def __init__(self, body: Any = None, status_code: int = 200, content: bytes | None = None) -> None:
		self.body = body
		self.status_code = status_code
		self.content = content

	def json(self) -> Any:
		return self.body

	def raise_for_status(self) -> None:
		if self.status_code >= 400:
			raise RuntimeError(f"HTTP {self.status_code}")

# -- strict Bot API contract ----------------------------------------------------------------------------
# One table: method -> "param:type[!]" specs ("!" = required). Types: id (int|str), i, s, b, f (number),
# o (object/dict), l (list), file (file_id | URL | attach://name | uploaded via ``files``).
# A method suffixed ``*`` (set LENIENT) is a newer Bot API method whose full parameter list is not pinned here:
# required params and types of the listed params are still enforced, extra params are allowed.

_COMMON = (
	"business_connection_id:s chat_id:id! message_thread_id:i direct_messages_topic_id:i disable_notification:b "
	"protect_content:b allow_paid_broadcast:b message_effect_id:s suggested_post_parameters:o "
	"reply_parameters:o reply_markup:o"
)
_CAPTION = "caption:s parse_mode:s caption_entities:l show_caption_above_media:b"
_CAPTION_PLAIN = "caption:s parse_mode:s caption_entities:l"
_MEDIA = f"{_COMMON} {_CAPTION} has_spoiler:b"  # photo / video / animation only
_ID_FIELDS = "chat_id:id! message_id:i!"

METHODS: dict[str, str] = {
	"getMe": "",
	"getWebhookInfo": "",
	"getUpdates": "offset:i limit:i timeout:i allowed_updates:l",
	"setWebhook": (
		"url:s! certificate:file ip_address:s max_connections:i allowed_updates:l drop_pending_updates:b "
		"secret_token:s"
	),
	"deleteWebhook": "drop_pending_updates:b",
	"getFile": "file_id:s!",
	"sendMessage": f"{_COMMON} text:s! parse_mode:s entities:l link_preview_options:o",
	"sendPhoto": f"{_MEDIA} photo:file!",
	"sendAudio": f"{_COMMON} {_CAPTION_PLAIN} audio:file! duration:i performer:s title:s thumbnail:file",
	"sendDocument": f"{_COMMON} {_CAPTION_PLAIN} document:file! thumbnail:file disable_content_type_detection:b",
	"sendVideo": (
		f"{_MEDIA} video:file! duration:i width:i height:i thumbnail:file cover:file start_timestamp:i "
		"supports_streaming:b"
	),
	"sendAnimation": f"{_MEDIA} animation:file! duration:i width:i height:i thumbnail:file",
	"sendVoice": f"{_COMMON} {_CAPTION_PLAIN} voice:file! duration:i",
	"sendVideoNote": f"{_COMMON} video_note:file! duration:i length:i thumbnail:file",
	"sendSticker": f"{_COMMON} sticker:file! emoji:s",
	"sendMediaGroup": f"business_connection_id:s chat_id:id! message_thread_id:i disable_notification:b protect_content:b "
	"allow_paid_broadcast:b message_effect_id:s reply_parameters:o media:l!",
	"sendLocation": (
		f"{_COMMON} latitude:f! longitude:f! horizontal_accuracy:f live_period:i heading:i "
		"proximity_alert_radius:i"
	),
	"sendVenue": (
		f"{_COMMON} latitude:f! longitude:f! title:s! address:s! foursquare_id:s foursquare_type:s "
		"google_place_id:s google_place_type:s"
	),
	"sendContact": f"{_COMMON} phone_number:s! first_name:s! last_name:s vcard:s",
	"sendPoll": (  # correct_option_ids: multi-answer quizzes (newer Bot API)
		
		f"{_COMMON} question:s! question_parse_mode:s question_entities:l options:l! is_anonymous:b type:s "
		"allows_multiple_answers:b correct_option_id:i correct_option_ids:l explanation:s explanation_parse_mode:s "
		"explanation_entities:l open_period:i close_date:i is_closed:b"
	),
	"sendDice": f"{_COMMON} emoji:s",
	"sendChatAction": "business_connection_id:s chat_id:id! message_thread_id:i action:s!",
	"sendChecklist": "business_connection_id:s! chat_id:id! checklist:o! disable_notification:b protect_content:b "
	"message_effect_id:s reply_parameters:o reply_markup:o*",
	"sendMessageDraft": "chat_id:id! message_thread_id:i draft_id:i! text:s! parse_mode:s entities:l*",
	"sendRichMessage": f"{_COMMON} rich_message:o!*",
	"sendRichMessageDraft": "chat_id:id! message_thread_id:i draft_id:i! rich_message:o!*",
	"setMessageReaction": "chat_id:id! message_id:i! reaction:l is_big:b",
	"forwardMessage": (
		"chat_id:id! message_thread_id:i from_chat_id:id! video_start_timestamp:i disable_notification:b "
		"protect_content:b message_id:i!"
	),
	"copyMessage": (
		f"chat_id:id! message_thread_id:i from_chat_id:id! message_id:i! video_start_timestamp:i {_CAPTION} "
		"disable_notification:b protect_content:b allow_paid_broadcast:b reply_parameters:o reply_markup:o"
	),
	"editMessageText": (
		"business_connection_id:s chat_id:id message_id:i inline_message_id:s text:s! parse_mode:s entities:l "
		"link_preview_options:o reply_markup:o"
	),
	"editMessageCaption": (
		f"business_connection_id:s chat_id:id message_id:i inline_message_id:s {_CAPTION} reply_markup:o"
	),
	"editMessageReplyMarkup": "business_connection_id:s chat_id:id message_id:i inline_message_id:s reply_markup:o",
	"deleteMessage": _ID_FIELDS,
	"deleteMessages": "chat_id:id! message_ids:l!",
	"answerCallbackQuery": "callback_query_id:s! text:s show_alert:b url:s cache_time:i",
	"answerInlineQuery": (
		"inline_query_id:s! results:l! cache_time:i is_personal:b next_offset:s button:o"
	),
	"answerGuestQuery": "guest_query_id:s! result:o text:s result_id:s*",
	"answerChatJoinRequestQuery": "chat_join_request_query_id:s! result:s!*",
	"sendChatJoinRequestWebApp": "chat_join_request_query_id:s! web_app_url:s!*",
	"approveChatJoinRequest": "chat_id:id! user_id:i!",
	"declineChatJoinRequest": "chat_id:id! user_id:i!",
	"banChatMember": "chat_id:id! user_id:i! until_date:i revoke_messages:b",
	"unbanChatMember": "chat_id:id! user_id:i! only_if_banned:b",
	"restrictChatMember": "chat_id:id! user_id:i! permissions:o! use_independent_chat_permissions:b until_date:i",
	"promoteChatMember": "chat_id:id! user_id:i! is_anonymous:b can_manage_chat:b can_delete_messages:b "
	"can_manage_video_chats:b can_restrict_members:b can_promote_members:b can_change_info:b "
	"can_invite_users:b can_post_stories:b can_edit_stories:b can_delete_stories:b can_post_messages:b "
	"can_edit_messages:b can_pin_messages:b can_manage_topics:b can_manage_direct_messages:b can_manage_tags:b can_send_welcome_messages:b",
	"setChatPermissions": "chat_id:id! permissions:o! use_independent_chat_permissions:b",
	"createChatInviteLink": "chat_id:id! name:s expire_date:i member_limit:i creates_join_request:b",
	"pinChatMessage": "business_connection_id:s chat_id:id! message_id:i! disable_notification:b",
	"unpinChatMessage": "business_connection_id:s chat_id:id! message_id:i",
	"leaveChat": "chat_id:id!",
	"getChat": "chat_id:id!",
	"getChatAdministrators": "chat_id:id! return_bots:b*",
	"getChatMemberCount": "chat_id:id!",
	"getChatMember": "chat_id:id! user_id:i!",
	"setChatTitle": "chat_id:id! title:s!",
	"setChatDescription": "chat_id:id! description:s",
	"createForumTopic": "chat_id:id! name:s! icon_color:i icon_custom_emoji_id:s",
	"editForumTopic": "chat_id:id! message_thread_id:i! name:s icon_custom_emoji_id:s",
	"deleteForumTopic": "chat_id:id! message_thread_id:i!",
	"stopPoll": "business_connection_id:s chat_id:id! message_id:i! reply_markup:o",
	"revokeChatInviteLink": "chat_id:id! invite_link:s!",
	"closeForumTopic": "chat_id:id! message_thread_id:i!",
	"reopenForumTopic": "chat_id:id! message_thread_id:i!",
	"readBusinessMessage": "business_connection_id:s! chat_id:id! message_id:i!*",
	"getBusinessConnection": "business_connection_id:s!",
	"deleteBusinessMessages": "business_connection_id:s! message_ids:l!",
	"getAccountInfo": "*",
	"setMyCommands": "commands:l! scope:o language_code:s",
	"getMyCommands": "scope:o language_code:s",
	"deleteMyCommands": "scope:o language_code:s",
	"setMyName": "name:s language_code:s",
	"getMyName": "language_code:s",
	"setMyDescription": "description:s language_code:s",
	"getMyDescription": "language_code:s",
	"setMyShortDescription": "short_description:s language_code:s",
	"getMyShortDescription": "language_code:s",
	"setChatMenuButton": "chat_id:i menu_button:o",
	"getChatMenuButton": "chat_id:i",
}


class BotApiContractError(AssertionError):
	"""The call would be rejected by the real Bot API (unknown method, missing/ill-typed parameter)."""


def _parse_spec(spec: str) -> tuple[dict[str, tuple[str, bool]], bool]:
	params: dict[str, tuple[str, bool]] = {}
	lenient = False
	for token in spec.split():
		if token == "*":
			lenient = True
			continue
		if token.endswith("*"):
			lenient = True
			token = token[:-1]
		name, _, typ = token.partition(":")
		required = typ.endswith("!")
		params[name] = (typ.rstrip("!"), required)
	return params, lenient


_PARSED = {name: _parse_spec(spec) for name, spec in METHODS.items()}
_SCALARS = {"id": (int, str), "i": (int,), "s": (str,), "b": (bool,), "f": (int, float), "file": (str,)}


def _check_type(method: str, name: str, typ: str, value: Any, multipart: bool, has_file: bool) -> None:
	where = f"{method}.{name}"
	if typ in ("o", "l"):
		want = dict if typ == "o" else list
		if isinstance(value, str) and multipart:
			try:
				value = json.loads(value)
			except ValueError:
				value = None
		if not isinstance(value, want):
			raise BotApiContractError(
				f"{where} must be a {'JSON object' if typ == 'o' else 'JSON array'} (got {type(value).__name__}"
				"; nested params must not be JSON strings in a JSON body)"
			)
		return
	if typ == "file" and has_file:
		return
	ok = _SCALARS[typ]
	if typ == "i" and isinstance(value, str) and value.lstrip("-").isdigit():
		return  # the Bot API server parses numeric strings for Integer parameters
	if multipart and isinstance(value, str) and typ in ("i", "b", "f"):
		return  # form fields are strings on the wire
	if isinstance(value, bool) and typ != "b":
		raise BotApiContractError(f"{where} must be {typ}, got bool")
	if not isinstance(value, ok):
		raise BotApiContractError(f"{where} must be {typ}, got {type(value).__name__} {value!r}")
	if typ == "id" and isinstance(value, str) and not value.strip():
		raise BotApiContractError(f"{where} is empty")


def validate_call(
	method: str, payload: Mapping[str, Any], *, multipart: bool = False, files: Mapping[str, Any] | None = None
) -> None:
	"""Raise ``BotApiContractError`` unless ``method(payload)`` would be accepted by the Bot API."""
	if method not in _PARSED:
		raise BotApiContractError(f"unknown Bot API method {method!r}")
	params, lenient = _PARSED[method]
	files = files or {}
	for name, (typ, required) in params.items():
		if required and (payload.get(name) is None and name not in files):
			raise BotApiContractError(f"{method}: missing required parameter {name!r}")
	for name, value in payload.items():
		if name not in params:
			if lenient:
				continue
			raise BotApiContractError(f"{method}: unknown parameter {name!r}")
		if value is None:
			raise BotApiContractError(f"{method}.{name} is None (omit the key instead)")
		_check_type(method, name, params[name][0], value, multipart, name in files)
	if method == "sendMediaGroup":
		media = payload["media"]
		if isinstance(media, str):
			media = json.loads(media)
		if not 2 <= len(media) <= 10 or not all(isinstance(m, dict) and m.get("type") and m.get("media") for m in media):
			raise BotApiContractError("sendMediaGroup.media must be 2-10 InputMedia objects with type+media")
	if method == "sendPoll":
		opts = payload["options"]
		if isinstance(opts, str):
			opts = json.loads(opts)
		if not 2 <= len(opts) <= 12:
			raise BotApiContractError("sendPoll.options needs 2-12 entries")
	if method in ("sendMessage", "editMessageText") and not str(payload.get("text", "x")).strip():
		raise BotApiContractError(f"{method}: message text is empty")


class FakeBotApi:
	"""Records every call; replies ``ok`` with an incrementing message_id unless a reply is queued.

	``queue(method, *responses)`` queues bodies (dicts) or callables(payload) -> body consumed in order;
	``error(description, error_code, retry_after=None)`` builds a Bot API error body.
	"""

	def __init__(self) -> None:
		self.calls: list[dict[str, Any]] = []
		self.gets: list[str] = []
		self._queues: dict[str, list[Any]] = {}
		self._next_id = 100
		self.file_bytes = b"file-bytes"

	@staticmethod
	def error(description: str, error_code: int, retry_after: int | None = None) -> dict:
		body: dict[str, Any] = {"ok": False, "error_code": error_code, "description": description}
		if retry_after is not None:
			body["parameters"] = {"retry_after": retry_after}
		return body

	def queue(self, method: str, *responses: Any) -> None:
		self._queues.setdefault(method, []).extend(responses)

	def of(self, method: str) -> list[dict[str, Any]]:
		return [c for c in self.calls if c["method"] == method]

	def last(self, method: str | None = None) -> dict[str, Any]:
		items = self.of(method) if method else self.calls
		return items[-1]

	def http_post(
		self,
		url: str,
		*,
		json_data: Mapping[str, Any] | None = None,
		data: Mapping[str, Any] | None = None,
		files: Mapping[str, Any] | None = None,
		timeout: int | None = None,
	) -> FakeResponse:
		method = url.rsplit("/", 1)[-1]
		payload = dict(json_data if json_data is not None else (data or {}))
		validate_call(method, payload, multipart=json_data is None and (data is not None or bool(files)), files=files)
		self.calls.append(
			{"method": method, "payload": payload, "files": dict(files) if files else None, "url": url}
		)
		queued = self._queues.get(method)
		if queued:
			body = queued.pop(0)
			body = body(payload) if callable(body) else body
			return FakeResponse(body, status_code=body.get("error_code", 200) if not body.get("ok") else 200)
		if method == "getFile":
			return FakeResponse(
				{"ok": True, "result": {"file_id": payload.get("file_id"), "file_path": "photos/f.jpg"}}
			)
		if method.startswith("send"):
			self._next_id += 1
			if method == "sendMediaGroup":
				return FakeResponse(
					{"ok": True, "result": [{"message_id": self._next_id}, {"message_id": self._next_id + 1}]}
				)
			return FakeResponse(
				{"ok": True, "result": {"message_id": self._next_id, "chat": {"id": payload.get("chat_id")}}}
			)
		if method == "getWebhookInfo":
			return FakeResponse({"ok": True, "result": {"url": "https://x/h", "pending_update_count": 0}})
		return FakeResponse({"ok": True, "result": True})

	def http_get(self, url: str, *, timeout: int | None = None) -> FakeResponse:
		self.gets.append(url)
		return FakeResponse(content=self.file_bytes)


# -- isolation helpers (tests must behave the same in the unit runner and on a real site with redis) --


def set_local_flags(testcase, **values) -> None:
	"""Give ``frappe.local.flags`` a complete ``frappe._dict`` for the test, then restore exactly what was there.

	``patch.object(frappe.local, "flags", ..., create=True)`` is unsafe: on a site the attribute lives on the
	werkzeug-style proxy, so mock deletes it on exit and later frappe code raises ``AttributeError: flags``.
	"""
	import frappe

	missing = object()
	old = getattr(frappe.local, "flags", missing)
	new = frappe._dict(old) if old is not missing and old else frappe._dict()
	new.update(values)
	frappe.local.flags = new

	def restore():
		if old is missing:
			try:
				del frappe.local.flags
			except Exception:
				pass
		else:
			frappe.local.flags = old

	testcase.addCleanup(restore)


def clear_update_dedup() -> None:
	"""Drop persisted ``huf_tg_upd:*`` update-id claims from a real redis cache (no-op without a site cache)."""
	try:
		import frappe

		if not getattr(frappe.local, "site", None):
			return
		cache = frappe.cache() if callable(frappe.cache) else frappe.cache
		cache.delete_keys("huf_tg_upd:*")
	except Exception:
		pass


def isolate_update_dedup(testcase) -> None:
	clear_update_dedup()
	testcase.addCleanup(clear_update_dedup)


def isolate_admin_cache(testcase, admin_module, cache) -> None:
	"""Route ``telegram_admin`` rate-limit / nonce / session state to ``cache`` instead of the site's redis."""
	from unittest.mock import patch

	p = patch.object(admin_module, "_cache", lambda c=None: c if c is not None else cache)
	p.start()
	testcase.addCleanup(p.stop)
