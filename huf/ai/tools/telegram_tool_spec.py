"""Single declaration of the ``telegram`` tool's arguments.

Every action lists the argument names it reads and whether each is required. The same table drives:

- the registry schema shown to the model (``registry_parameters``),
- the usage text of the tool description (``usage_summary``),
- the strict validation that runs BEFORE any gate, cap or Bot API call (``validate``).

An action can only read an argument that is declared for it here; anything else is refused with the valid
names, and a missing required argument is refused instead of being sent as an empty value. The mechanics are
shared with ``telegram_admin_spec`` in ``action_args.ActionTable``.

Internal arguments are accepted but never shown to the model: the harness injects the run context
(``conversation_id``, ``agent_run_id``, ``agent_name``, ``call_id``) and Desk/flow callers may name the
``gateway`` outside a gateway conversation.

Plain data and stdlib only: the registry imports this module without touching Frappe.
"""

from __future__ import annotations

from huf.ai.tools.action_args import ActionTable, ArgumentRefusal

PARSE_MODES = ("Markdown", "HTML", "MarkdownV2")
# What Bot API sendVoice accepts; used by the registry text and by the Frappe File check in the handler.
VOICE_FORMATS = "OGG/Opus, MP3 or M4A"
INTERNAL_ARGS = ("gateway", "conversation_id", "agent_run_id", "agent_name", "call_id")

_SOURCE = "Telegram file_id, public https URL, or Frappe File name/file_url"

# name -> (JSON type, description). ``chat`` accepts an integer or a numeric/@username string.
ARG_TYPES: dict[str, tuple[str, str]] = {
	"chat_id": (
		"chat",
		"Telegram chat/channel id (numeric or @username). Optional in a gateway conversation (defaults to the "
		"current chat); outside one, give chat_id or recipient_name.",
	),
	"recipient_name": (
		"string",
		"Human-friendly recipient name from Integration Settings (alternative to chat_id; ignored in a "
		"gateway conversation).",
	),
	"text": (
		"string",
		"Message or edited text; also the callback answer text. send_speech: the text to speak (max 2000 characters).",
	),
	"parse_mode": (
		"string",
		"How YOUR text/caption/explanation is already formatted: Markdown, HTML or MarkdownV2. Omit for plain "
		"text. It is sent as is, so escape the text for that mode.",
	),
	"reply_markup": (
		"object",
		'Keyboard: {inline_keyboard: [[{text, url}|{text, callback}]]} or {keyboard: [["text"]], '
		"one_time_keyboard} or {remove_keyboard: true} or {force_reply: true}. Callback buttons are signed "
		"server-side and only work inside a Telegram gateway conversation; elsewhere use url buttons. "
		"edit_message_text, edit_message_caption and edit_message_reply_markup take inline_keyboard only; the "
		"Bot API removes the buttons of an edited message unless this is passed again, so pass it to keep or "
		"replace the buttons and omit it to remove them.",
	),
	"reply_to_message_id": ("integer", "Message id to reply to."),
	"message_thread_id": ("integer", "Forum topic id to send into."),
	"disable_notification": ("boolean", "Send silently."),
	"protect_content": ("boolean", "Prevent forwarding and saving of the sent message."),
	"message_effect_id": ("string", "Message effect id (private chats)."),
	"idempotency_key": (
		"string",
		"Unique key per intended send (1-120 chars of letters, digits, . _ : -); a repeat in the same run and "
		"chat returns the first result without sending again.",
	),
	"message_id": ("integer", "Id of the target message."),
	"from_chat_id": ("chat", "Source chat (must also be an allowed recipient)."),
	"photo": ("string", f"send_photo source: {_SOURCE} (photos up to 10 MB)."),
	"document": ("string", f"send_document source: {_SOURCE}."),
	"voice": (
		"string",
		f"send_voice source ({VOICE_FORMATS}): {_SOURCE}. send_speech: optional TTS voice name (e.g. alloy); "
		"defaults to the agent's tts_voice.",
	),
	"audio": ("string", f"send_audio source: {_SOURCE}."),
	"video": ("string", f"send_video source: {_SOURCE}."),
	"animation": ("string", f"send_animation source (GIF/MP4): {_SOURCE}."),
	"sticker": ("string", f"send_sticker source (WEBP/TGS/WEBM): {_SOURCE}."),
	"video_note": ("string", "send_video_note source (square MP4, up to 1 minute): file_id or Frappe File."),
	"caption": ("string", "Caption of a media message or copied message (max 1024 characters)."),
	"items": (
		"array",
		"send_media_group: 2-10 objects {type: photo|video|audio|document, media: source, caption}.",
	),
	"has_spoiler": ("boolean", "Hide the photo/video/animation behind a spoiler."),
	"supports_streaming": ("boolean", "send_video: the video suits streaming."),
	"duration": ("integer", "Media duration in seconds."),
	"width": ("integer", "Video/animation width in pixels."),
	"height": ("integer", "Video/animation height in pixels."),
	"length": ("integer", "send_video_note: diameter in pixels."),
	"performer": ("string", "send_audio: performer."),
	"title": (
		"string",
		"send_audio: track title; send_venue: venue name; send_checklist: checklist title.",
	),
	"latitude": ("number", "Latitude (-90..90)."),
	"longitude": ("number", "Longitude (-180..180)."),
	"address": ("string", "send_venue: street address."),
	"foursquare_id": ("string", "send_venue: Foursquare id of the venue."),
	"google_place_id": ("string", "send_venue: Google Places id of the venue."),
	"phone_number": ("string", "send_contact: phone number."),
	"first_name": ("string", "send_contact: first name."),
	"last_name": ("string", "send_contact: last name."),
	"emoji": (
		"string",
		"set_reaction: one emoji from Telegram's allowed reaction set (omit and pass remove=true to clear). "
		"send_dice: dice, dart, basketball, football, bowling or slot emoji.",
	),
	"remove": ("boolean", "set_reaction: true removes the bot's reaction (use instead of emoji)."),
	"big": ("boolean", "set_reaction: use the big reaction animation."),
	"chat_action": (
		"string",
		"typing (default), upload_photo, record_video, upload_video, record_voice, upload_voice, "
		"upload_document, choose_sticker or find_location.",
	),
	"callback_query_id": ("string", "Id of the callback query to answer."),
	"show_alert": ("boolean", "answer_callback_query: show a modal alert instead of a toast."),
	"url": ("string", "set_webhook: webhook URL."),
	"secret_token": ("string", "set_webhook: secret token for webhook verification."),
	"offset": ("integer", "get_updates: update offset (0 is a valid offset)."),
	"limit": (
		"integer",
		"get_updates: max updates (max 100). list_messages: max messages (default 20, max 50).",
	),
	"question": ("string", "send_poll: question (1-300 chars)."),
	"options": ("array", "send_poll: 2-12 answer option strings (1-100 chars each)."),
	"is_anonymous": ("boolean", "send_poll: anonymous votes (default true)."),
	"poll_type": ("string", "send_poll: regular (default) or quiz."),
	"correct_option_id": ("integer", "send_poll quiz: 0-based index of the correct option."),
	"correct_option_ids": (
		"array",
		"send_poll quiz with several correct answers: 0-based option indexes.",
	),
	"explanation": ("string", "send_poll quiz: shown after a wrong answer (max 200 chars)."),
	"allows_multiple_answers": ("boolean", "send_poll: allow several answers."),
	"open_period": ("integer", "send_poll: seconds the poll stays open (5-2628000)."),
	"business_connection_id": ("string", "send_checklist: connected business account id."),
	"tasks": ("array", "send_checklist: 1-30 task strings."),
	"others_can_add_tasks": ("boolean", "send_checklist: let other users add tasks."),
	"others_can_mark_tasks_as_done": ("boolean", "send_checklist: let other users mark tasks done."),
	"gateway": (
		"string",
		"Telegram Gateway name. Ignored inside a Telegram gateway conversation (that conversation's gateway is "
		"used). Required outside one, and only for gateways you are allowed to manage.",
	),
	"template_name": ("string", "Telegram Message Template name."),
	"variables": ("object", "{variable: value} for the template's {{var}} placeholders."),
	"file_id": ("string", "get_file: Telegram file_id to download (up to 20 MB)."),
	"user_id": ("integer", "get_chat_member: Telegram user id."),
}

ENUMS = {"parse_mode": PARSE_MODES}

_TARGET = ("chat_id", "recipient_name")
_REPLY = ("reply_to_message_id", "message_thread_id", "disable_notification", "protect_content")
_SEND = (*_REPLY, "message_effect_id", "reply_markup", "idempotency_key")
_CAPTION = ("caption", "parse_mode")


def _spec(*required: str, optional: tuple[str, ...] = (), target: bool = True) -> dict[str, bool]:
	"""``{argument: required}`` in display order: required first, then optional, then the target chat."""
	out = dict.fromkeys(required, True)
	out.update(dict.fromkeys((*optional, *(_TARGET if target else ())), False))
	return out


# action -> {argument: required}. Order is the display order. This is the ONLY place arguments are declared.
ACTION_ARGS: dict[str, dict[str, bool]] = {
	"send_message": _spec("text", optional=("parse_mode", *_SEND)),
	"reply_to_message": _spec("text", "reply_to_message_id", optional=("parse_mode", *_SEND[1:])),
	"send_photo": _spec("photo", optional=(*_CAPTION, "has_spoiler", *_SEND)),
	"send_document": _spec("document", optional=(*_CAPTION, *_SEND)),
	"send_voice": _spec("voice", optional=(*_CAPTION, "duration", *_SEND)),
	"send_speech": _spec("text", optional=("voice", "caption", *_SEND)),
	"send_audio": _spec("audio", optional=(*_CAPTION, "duration", "performer", "title", *_SEND)),
	"send_video": _spec(
		"video",
		optional=(*_CAPTION, "duration", "width", "height", "supports_streaming", "has_spoiler", *_SEND),
	),
	"send_animation": _spec(
		"animation", optional=(*_CAPTION, "duration", "width", "height", "has_spoiler", *_SEND)
	),
	"send_sticker": _spec("sticker", optional=_SEND),
	"send_media_group": _spec("items", optional=("parse_mode", *_REPLY, "idempotency_key")),
	"send_location": _spec(
		"latitude",
		"longitude",
		optional=(
			"reply_to_message_id",
			"message_thread_id",
			"disable_notification",
			"reply_markup",
			"idempotency_key",
		),
	),
	"send_contact": _spec(
		"phone_number",
		"first_name",
		optional=(
			"last_name",
			"reply_to_message_id",
			"message_thread_id",
			"disable_notification",
			"reply_markup",
			"idempotency_key",
		),
	),
	"set_reaction": _spec("message_id", optional=("emoji", "remove", "big")),
	"send_chat_action": _spec(optional=("chat_action", "message_thread_id")),
	"edit_message_text": _spec("message_id", "text", optional=("parse_mode", "reply_markup")),
	"edit_message_caption": _spec("message_id", "caption", optional=("parse_mode", "reply_markup")),
	"edit_message_reply_markup": _spec("message_id", optional=("reply_markup",)),
	"delete_message": _spec("message_id"),
	"forward_message": _spec(
		"from_chat_id",
		"message_id",
		optional=("message_thread_id", "disable_notification", "protect_content", "idempotency_key"),
	),
	"copy_message": _spec(
		"from_chat_id",
		"message_id",
		optional=(
			*_CAPTION,
			"reply_markup",
			"message_thread_id",
			"disable_notification",
			"protect_content",
			"idempotency_key",
		),
	),
	"answer_callback_query": _spec("callback_query_id", optional=("text", "show_alert"), target=False),
	"get_updates": _spec(optional=("offset", "limit"), target=False),
	"get_chat_info": _spec(),
	"get_me": _spec(target=False),
	"set_webhook": _spec("url", optional=("secret_token",), target=False),
	"delete_webhook": _spec(target=False),
	"send_video_note": _spec("video_note", optional=("duration", "length", *_SEND)),
	"send_venue": _spec(
		"latitude",
		"longitude",
		"title",
		"address",
		optional=("foursquare_id", "google_place_id", *_SEND),
	),
	"send_dice": _spec(optional=("emoji", *_SEND)),
	"send_poll": _spec(
		"question",
		"options",
		optional=(
			"is_anonymous",
			"poll_type",
			"correct_option_id",
			"correct_option_ids",
			"explanation",
			"allows_multiple_answers",
			"open_period",
			"parse_mode",
			*_SEND,
		),
	),
	"stop_poll": _spec("message_id"),
	"send_checklist": _spec(
		"business_connection_id",
		"title",
		"tasks",
		optional=(
			"parse_mode",
			"others_can_add_tasks",
			"others_can_mark_tasks_as_done",
			"reply_to_message_id",
			"disable_notification",
			"protect_content",
			"message_effect_id",
			"reply_markup",
			"idempotency_key",
		),
	),
	"send_template": _spec(
		"template_name",
		optional=(
			"variables",
			"gateway",
			"reply_to_message_id",
			"message_thread_id",
			"disable_notification",
			"protect_content",
			"idempotency_key",
		),
	),
	"list_templates": _spec(optional=("gateway",), target=False),
	"preview_template": _spec("template_name", optional=("variables", "gateway"), target=False),
	"get_file": _spec("file_id", target=False),
	"get_chat_member": _spec("user_id"),
	"get_chat_administrators": _spec(),
	"get_chat_member_count": _spec(),
	"list_messages": _spec(optional=("limit", "gateway")),
	"get_account_info": _spec(optional=("gateway",), target=False),
}

TABLE = ActionTable(ARG_TYPES, ACTION_ARGS, internal=INTERNAL_ARGS, enums=ENUMS)

# Actions that take a target chat (checked against the gateway scope).
CHAT_ACTIONS = frozenset(a for a, s in ACTION_ARGS.items() if "chat_id" in s)
# Actions that create a new message (counted against the per-run / per-day caps): they accept ``idempotency_key``.
SEND_ACTIONS = frozenset(a for a, s in ACTION_ARGS.items() if "idempotency_key" in s)

CHOICES = TABLE.choices
usage = TABLE.usage
usage_summary = TABLE.usage_summary
registry_parameters = TABLE.registry_parameters


def validate(action: str, args: dict) -> dict:
	"""Return ``args`` after checking names, presence and types against the table; raise ``ArgumentRefusal``."""
	return TABLE.validate(action, args)  # type: ignore[return-value]


__all__ = ["ACTION_ARGS", "ARG_TYPES", "ArgumentRefusal", "validate"]
