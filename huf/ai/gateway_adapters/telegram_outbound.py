# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram senders: every outbound Bot API call goes through ``TelegramSender``.

Pure apart from the injected ``TelegramBotClient``; no Frappe imports.
"""

from __future__ import annotations

import mimetypes
from typing import Any, Mapping, Sequence, Union

from huf.ai.gateway_adapters.telegram_client import TelegramApiError, TelegramBotClient
from huf.ai.gateway_adapters.telegram_format import (
	MODE_HTML,
	MODE_MARKDOWN_V2,
	MODE_PLAIN,
	TELEGRAM_CAPTION_LIMIT,
	render_parts,
	to_plain,
)

# A media argument: file_id or https URL (str), raw bytes, or (filename, bytes[, mime_type]).
MediaInput = Union[str, bytes, tuple]

CHAT_ACTIONS = frozenset(
	{
		"typing",
		"upload_photo",
		"record_video",
		"upload_video",
		"record_voice",
		"upload_voice",
		"upload_document",
		"choose_sticker",
		"find_location",
		"record_video_note",
		"upload_video_note",
	}
)

# kind -> (Bot API method, payload field)
MEDIA_METHODS: dict[str, tuple[str, str]] = {
	"photo": ("sendPhoto", "photo"),
	"document": ("sendDocument", "document"),
	"file": ("sendDocument", "document"),
	"audio": ("sendAudio", "audio"),
	"voice": ("sendVoice", "voice"),
	"video": ("sendVideo", "video"),
	"animation": ("sendAnimation", "animation"),
	"video_note": ("sendVideoNote", "video_note"),
	"sticker": ("sendSticker", "sticker"),
}
_NO_CAPTION = frozenset({"sticker", "video_note"})
_DEFAULT_NAMES = {
	"photo": "photo.jpg",
	"voice": "voice.ogg",
	"audio": "audio.mp3",
	"video": "video.mp4",
	"animation": "animation.mp4",
	"sticker": "sticker.webp",
	"video_note": "video_note.mp4",
}


def _upload_part(kind: str, value: MediaInput) -> tuple[Any, tuple | None]:
	"""Return (value for the JSON payload, files entry or None)."""
	if isinstance(value, str):
		return value, None
	if isinstance(value, (bytes, bytearray)):
		name = _DEFAULT_NAMES.get(kind, "file.bin")
		return None, (name, bytes(value), mimetypes.guess_type(name)[0] or "application/octet-stream")
	if isinstance(value, tuple) and len(value) in (2, 3):
		name, content = value[0], value[1]
		mime = value[2] if len(value) == 3 else (mimetypes.guess_type(name)[0] or "application/octet-stream")
		return None, (name, bytes(content), mime)
	raise ValueError("media must be a file_id/URL string, bytes, or (filename, bytes[, mime])")


class TelegramSender:
	"""Outbound operations. ``parse_mode`` is the format applied to agent text ("" = send verbatim)."""

	def __init__(
		self, client: TelegramBotClient, *, parse_mode: str = MODE_PLAIN, reply_style: str = "parameters"
	) -> None:
		if parse_mode not in (MODE_PLAIN, MODE_HTML, MODE_MARKDOWN_V2):
			raise ValueError("parse_mode must be '', 'HTML' or 'MarkdownV2'")
		if reply_style not in ("parameters", "legacy"):
			raise ValueError("reply_style must be 'parameters' or 'legacy'")
		self.client = client
		self.parse_mode = parse_mode
		self.reply_style = reply_style

	# -- helpers -------------------------------------------------------------------------------

	def _common(
		self,
		chat_id: Any,
		*,
		reply_to: Any = None,
		thread_id: Any = None,
		markup: Mapping[str, Any] | None = None,
		silent: bool = False,
		protect: bool = False,
		effect_id: str | None = None,
		ephemeral: Mapping[str, Any] | None = None,
	) -> dict[str, Any]:
		payload: dict[str, Any] = {"chat_id": chat_id}
		if thread_id not in (None, ""):
			payload["message_thread_id"] = int(thread_id)
		if reply_to not in (None, ""):
			try:
				mid = int(reply_to)
			except (TypeError, ValueError):
				mid = None
			if mid is not None:
				if self.reply_style == "legacy":
					payload["reply_to_message_id"] = mid
				else:
					payload["reply_parameters"] = {"message_id": mid, "allow_sending_without_reply": True}
		if markup:
			payload["reply_markup"] = dict(markup)
		if silent:
			payload["disable_notification"] = True
		if protect:
			payload["protect_content"] = True
		if effect_id:
			payload["message_effect_id"] = effect_id
		if ephemeral:  # only the receiver sees it; the ephemeral quote replaces a normal reply
			payload.update({k: v for k, v in ephemeral.items() if k != "reply_parameters"})
			if reply_to not in (None, "") and ephemeral.get("reply_parameters"):
				payload["reply_parameters"] = dict(ephemeral["reply_parameters"])
			else:
				payload.pop("reply_parameters", None)
		return payload

	def _call_with_fallback(self, method: str, payload: dict[str, Any], text_key: str, plain: str) -> Any:
		"""Call; on a parse-entities error resend the same payload as plain text without parse_mode."""
		try:
			return self.client.call(method, payload)
		except TelegramApiError as exc:
			if not exc.parse_error or "parse_mode" not in payload:
				raise
			fallback = {k: v for k, v in payload.items() if k != "parse_mode"}
			fallback[text_key] = plain
			return self.client.call(method, fallback)

	# -- text ----------------------------------------------------------------------------------

	def send_text(
		self,
		chat_id: Any,
		text: str,
		*,
		reply_to: Any = None,
		thread_id: Any = None,
		markup: Mapping[str, Any] | None = None,
		silent: bool = False,
		protect: bool = False,
		link_preview: bool = True,
		effect_id: str | None = None,
		ephemeral: dict | None = None,
	) -> list[Mapping[str, Any]]:
		"""Send ``text`` as one or more messages (<= 4096 chars each); returns the Message dicts."""
		parts = render_parts(text, self.parse_mode)
		if not parts:
			raise ValueError("Reply text is required")
		results = []
		for i, part in enumerate(parts):
			last = i == len(parts) - 1
			payload = self._common(
				chat_id,
				reply_to=reply_to if i == 0 else None,
				thread_id=thread_id,
				markup=markup if last else None,
				silent=silent,
				protect=protect,
				effect_id=effect_id if i == 0 else None,
				ephemeral=ephemeral,
			)
			payload["text"] = part.text
			if part.parse_mode:
				payload["parse_mode"] = part.parse_mode
			if not link_preview:
				payload["link_preview_options"] = {"is_disabled": True}
			results.append(self._call_with_fallback("sendMessage", payload, "text", part.plain))
		return results

	def send_rich_message(
		self,
		chat_id: Any,
		*,
		markdown: str | None = None,
		html: str | None = None,
		reply_to: Any = None,
		thread_id: Any = None,
		markup: Mapping[str, Any] | None = None,
		silent: bool = False,
	) -> Mapping[str, Any]:
		"""Bot API 10.1 ``sendRichMessage``: exactly one of ``markdown`` / ``html``."""
		if (markdown is None) == (html is None):
			raise ValueError("Pass exactly one of markdown or html")
		payload = self._common(chat_id, reply_to=reply_to, thread_id=thread_id, markup=markup, silent=silent)
		payload["rich_message"] = {"markdown": markdown} if markdown is not None else {"html": html}
		return self.client.call("sendRichMessage", payload)

	def send_message_draft(
		self,
		chat_id: Any,
		draft_id: int,
		text: str = "",
		*,
		thread_id: Any = None,
		parse_mode: str | None = None,
		can_stop: bool = False,
		keep_on_stop: bool = False,
	) -> Any:
		"""Streaming preview (private chats only; ephemeral ~30s). Empty ``text`` shows "Thinking...".
		Finalize with ``send_text``. ``draft_id`` must be non-zero."""
		if not draft_id:
			raise ValueError("draft_id must be non-zero")
		payload: dict[str, Any] = {"chat_id": chat_id, "draft_id": int(draft_id), "text": text[:4096]}
		if thread_id not in (None, ""):
			payload["message_thread_id"] = int(thread_id)
		if parse_mode:
			payload["parse_mode"] = parse_mode
		if can_stop:
			payload["can_stop"] = True
		if keep_on_stop:
			payload["keep_on_stop"] = True
		return self.client.call("sendMessageDraft", payload)

	def send_rich_message_draft(
		self,
		chat_id: Any,
		draft_id: int,
		*,
		markdown: str | None = None,
		html: str | None = None,
		thread_id: Any = None,
		can_stop: bool = False,
		keep_on_stop: bool = False,
	) -> Any:
		if not draft_id:
			raise ValueError("draft_id must be non-zero")
		if (markdown is None) == (html is None):
			raise ValueError("Pass exactly one of markdown or html")
		payload: dict[str, Any] = {
			"chat_id": chat_id,
			"draft_id": int(draft_id),
			"rich_message": {"markdown": markdown} if markdown is not None else {"html": html},
		}
		if thread_id not in (None, ""):
			payload["message_thread_id"] = int(thread_id)
		if can_stop:
			payload["can_stop"] = True
		if keep_on_stop:
			payload["keep_on_stop"] = True
		return self.client.call("sendRichMessageDraft", payload)

	# -- media ---------------------------------------------------------------------------------

	def send_media(
		self,
		kind: str,
		chat_id: Any,
		media: MediaInput,
		*,
		caption: str = "",
		reply_to: Any = None,
		thread_id: Any = None,
		markup: Mapping[str, Any] | None = None,
		silent: bool = False,
		protect: bool = False,
		extra: Mapping[str, Any] | None = None,
		ephemeral: dict | None = None,
	) -> list[Mapping[str, Any]]:
		"""Send one media item. A caption over 1024 chars is sent as a follow-up text message."""
		if kind not in MEDIA_METHODS:
			raise ValueError(f"Unsupported media kind: {kind}")
		method, field = MEDIA_METHODS[kind]
		value, upload = _upload_part(kind, media)
		payload = self._common(
			chat_id,
			reply_to=reply_to,
			thread_id=thread_id,
			markup=markup,
			silent=silent,
			protect=protect,
			ephemeral=ephemeral,
		)
		files = None
		if upload:
			files = {field: upload}
		else:
			payload[field] = value
		follow_up = ""
		if caption and kind not in _NO_CAPTION:
			cap_parts = render_parts(caption, self.parse_mode, TELEGRAM_CAPTION_LIMIT)
			if len(cap_parts) == 1:
				payload["caption"] = cap_parts[0].text
				if cap_parts[0].parse_mode:
					payload["parse_mode"] = cap_parts[0].parse_mode
			else:
				follow_up = caption
		payload.update(extra or {})
		plain = to_plain(caption)[:TELEGRAM_CAPTION_LIMIT]
		try:
			result = self.client.call(method, payload, files=files)
		except TelegramApiError as exc:
			if not exc.parse_error or "parse_mode" not in payload:
				raise
			retry = {k: v for k, v in payload.items() if k != "parse_mode"}
			retry["caption"] = plain
			result = self.client.call(method, retry, files=files)
		results = [result]
		if follow_up:
			results.extend(self.send_text(chat_id, follow_up, thread_id=thread_id, silent=silent))
		return results

	def send_photo(self, chat_id: Any, media: MediaInput, **kw: Any) -> list[Mapping[str, Any]]:
		return self.send_media("photo", chat_id, media, **kw)

	def send_document(self, chat_id: Any, media: MediaInput, **kw: Any) -> list[Mapping[str, Any]]:
		return self.send_media("document", chat_id, media, **kw)

	def send_audio(self, chat_id: Any, media: MediaInput, **kw: Any) -> list[Mapping[str, Any]]:
		return self.send_media("audio", chat_id, media, **kw)

	def send_voice(self, chat_id: Any, media: MediaInput, **kw: Any) -> list[Mapping[str, Any]]:
		return self.send_media("voice", chat_id, media, **kw)

	def send_video(self, chat_id: Any, media: MediaInput, **kw: Any) -> list[Mapping[str, Any]]:
		return self.send_media("video", chat_id, media, **kw)

	def send_animation(self, chat_id: Any, media: MediaInput, **kw: Any) -> list[Mapping[str, Any]]:
		return self.send_media("animation", chat_id, media, **kw)

	def send_sticker(self, chat_id: Any, media: MediaInput, **kw: Any) -> list[Mapping[str, Any]]:
		return self.send_media("sticker", chat_id, media, **kw)

	def send_media_group(
		self,
		chat_id: Any,
		items: Sequence[Mapping[str, Any]],
		*,
		reply_to: Any = None,
		thread_id: Any = None,
		silent: bool = False,
	) -> Sequence[Mapping[str, Any]]:
		"""``items``: 2-10 dicts ``{"type": photo|video|audio|document, "media": MediaInput, "caption": str}``."""
		if not 2 <= len(items) <= 10:
			raise ValueError("A media group needs 2-10 items")
		payload = self._common(chat_id, reply_to=reply_to, thread_id=thread_id, silent=silent)
		media_json, files = [], {}
		for i, item in enumerate(items):
			kind = item.get("type", "photo")
			if kind not in ("photo", "video", "audio", "document"):
				raise ValueError("media group items must be photo, video, audio or document")
			value, upload = _upload_part(kind, item["media"])
			if upload:
				name = f"file{i}"
				files[name] = upload
				value = f"attach://{name}"
			entry: dict[str, Any] = {"type": kind, "media": value}
			if item.get("caption"):
				part = render_parts(item["caption"], self.parse_mode, TELEGRAM_CAPTION_LIMIT)[0]
				entry["caption"] = part.text
				if part.parse_mode:
					entry["parse_mode"] = part.parse_mode
			media_json.append(entry)
		payload["media"] = media_json
		return self.client.call("sendMediaGroup", payload, files=files or None)

	def send_location(
		self,
		chat_id: Any,
		latitude: float,
		longitude: float,
		*,
		reply_to: Any = None,
		thread_id: Any = None,
		markup: Mapping[str, Any] | None = None,
		silent: bool = False,
	) -> Mapping[str, Any]:
		payload = self._common(chat_id, reply_to=reply_to, thread_id=thread_id, markup=markup, silent=silent)
		payload.update({"latitude": latitude, "longitude": longitude})
		return self.client.call("sendLocation", payload)

	def send_contact(
		self,
		chat_id: Any,
		phone_number: str,
		first_name: str,
		*,
		last_name: str = "",
		reply_to: Any = None,
		thread_id: Any = None,
		markup: Mapping[str, Any] | None = None,
		silent: bool = False,
	) -> Mapping[str, Any]:
		payload = self._common(chat_id, reply_to=reply_to, thread_id=thread_id, markup=markup, silent=silent)
		payload.update({"phone_number": phone_number, "first_name": first_name})
		if last_name:
			payload["last_name"] = last_name
		return self.client.call("sendContact", payload)

	# -- interaction ---------------------------------------------------------------------------

	def set_reaction(self, chat_id: Any, message_id: Any, emoji: str | None, *, big: bool = False) -> Any:
		"""React with ``emoji`` (one per message for bots); ``None`` clears the reaction."""
		payload: dict[str, Any] = {
			"chat_id": chat_id,
			"message_id": int(message_id),
			"reaction": [{"type": "emoji", "emoji": emoji}] if emoji else [],
		}
		if big:
			payload["is_big"] = True
		return self.client.call("setMessageReaction", payload)

	def send_chat_action(self, chat_id: Any, action: str = "typing", *, thread_id: Any = None) -> Any:
		if action not in CHAT_ACTIONS:
			raise ValueError(f"Unsupported chat action: {action}")
		payload: dict[str, Any] = {"chat_id": chat_id, "action": action}
		if thread_id not in (None, ""):
			payload["message_thread_id"] = int(thread_id)
		return self.client.call("sendChatAction", payload)

	def answer_callback_query(
		self,
		callback_query_id: str,
		text: str = "",
		*,
		show_alert: bool = False,
		url: str | None = None,
		cache_time: int | None = None,
	) -> Any:
		payload: dict[str, Any] = {"callback_query_id": callback_query_id}
		if text:
			payload["text"] = text[:200]
		if show_alert:
			payload["show_alert"] = True
		if url:
			payload["url"] = url
		if cache_time is not None:
			payload["cache_time"] = cache_time
		return self.client.call("answerCallbackQuery", payload)

	# -- edit / delete / pin -------------------------------------------------------------------

	def edit_message_text(
		self,
		chat_id: Any,
		message_id: Any,
		text: str,
		*,
		markup: Mapping[str, Any] | None = None,
		link_preview: bool = True,
	) -> Mapping[str, Any] | None:
		"""Edit in place (single message, <= 4096 chars). Returns ``None`` when nothing changed."""
		parts = render_parts(text, self.parse_mode)
		if len(parts) != 1:
			raise ValueError("Edited text must fit in one Telegram message (4096 chars)")
		part = parts[0]
		payload: dict[str, Any] = {"chat_id": chat_id, "message_id": int(message_id), "text": part.text}
		if part.parse_mode:
			payload["parse_mode"] = part.parse_mode
		if markup is not None:
			payload["reply_markup"] = dict(markup)
		if not link_preview:
			payload["link_preview_options"] = {"is_disabled": True}
		try:
			return self._call_with_fallback("editMessageText", payload, "text", part.plain)
		except TelegramApiError as exc:
			if exc.message_not_modified:
				return None
			raise

	def edit_message_caption(
		self, chat_id: Any, message_id: Any, caption: str, *, markup: Mapping[str, Any] | None = None
	) -> Mapping[str, Any] | None:
		parts = render_parts(caption, self.parse_mode, TELEGRAM_CAPTION_LIMIT)
		if len(parts) != 1:
			raise ValueError("Caption must fit in 1024 characters")
		part = parts[0]
		payload: dict[str, Any] = {"chat_id": chat_id, "message_id": int(message_id), "caption": part.text}
		if part.parse_mode:
			payload["parse_mode"] = part.parse_mode
		if markup is not None:
			payload["reply_markup"] = dict(markup)
		try:
			return self._call_with_fallback("editMessageCaption", payload, "caption", part.plain)
		except TelegramApiError as exc:
			if exc.message_not_modified:
				return None
			raise

	def edit_message_reply_markup(
		self, chat_id: Any, message_id: Any, markup: Mapping[str, Any] | None = None
	) -> Any:
		"""Replace the inline keyboard; ``None`` removes it."""
		return self.client.call(
			"editMessageReplyMarkup",
			{
				"chat_id": chat_id,
				"message_id": int(message_id),
				"reply_markup": dict(markup or {"inline_keyboard": []}),
			},
		)

	def delete_message(self, chat_id: Any, message_id: Any) -> Any:
		return self.client.call("deleteMessage", {"chat_id": chat_id, "message_id": int(message_id)})

	def pin_message(self, chat_id: Any, message_id: Any, *, silent: bool = True) -> Any:
		return self.client.call(
			"pinChatMessage",
			{"chat_id": chat_id, "message_id": int(message_id), "disable_notification": silent},
		)

	def unpin_message(self, chat_id: Any, message_id: Any | None = None) -> Any:
		payload: dict[str, Any] = {"chat_id": chat_id}
		if message_id is not None:
			payload["message_id"] = int(message_id)
		return self.client.call("unpinChatMessage", payload)
