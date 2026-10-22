# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram operations missing from ``TelegramSender`` (forward/copy) and reply-markup validation.

Pure apart from the injected ``TelegramBotClient``; no Frappe imports.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Mapping

from huf.ai.gateway_adapters.telegram_client import TelegramBotClient
from huf.ai.gateway_adapters.telegram_keyboards import (
	callback_button,
	force_reply,
	inline_keyboard,
	remove_keyboard,
	reply_keyboard,
	url_button,
)

MAX_KEYBOARD_BUTTONS = 100
MAX_ROW_BUTTONS = 8
_URL_SCHEMES = ("http://", "https://", "tg://")


def _opt(payload: dict[str, Any], *, thread_id: Any, silent: bool, protect: bool) -> None:
	if thread_id not in (None, ""):
		payload["message_thread_id"] = int(thread_id)
	if silent:
		payload["disable_notification"] = True
	if protect:
		payload["protect_content"] = True


def forward_message(
	client: TelegramBotClient, chat_id: Any, from_chat_id: Any, message_id: Any, *, thread_id: Any = None,
	silent: bool = False, protect: bool = False,
) -> Mapping[str, Any]:
	payload: dict[str, Any] = {"chat_id": chat_id, "from_chat_id": from_chat_id, "message_id": int(message_id)}
	_opt(payload, thread_id=thread_id, silent=silent, protect=protect)
	return client.call("forwardMessage", payload)


def copy_message(
	client: TelegramBotClient, chat_id: Any, from_chat_id: Any, message_id: Any, *, caption: str | None = None,
	parse_mode: str | None = None, markup: Mapping[str, Any] | None = None, thread_id: Any = None,
	silent: bool = False, protect: bool = False,
) -> Mapping[str, Any]:
	payload: dict[str, Any] = {"chat_id": chat_id, "from_chat_id": from_chat_id, "message_id": int(message_id)}
	if caption:
		payload["caption"] = caption
		if parse_mode:
			payload["parse_mode"] = parse_mode
	if markup:
		payload["reply_markup"] = dict(markup)
	_opt(payload, thread_id=thread_id, silent=silent, protect=protect)
	return client.call("copyMessage", payload)


# -- reply_markup passthrough ------------------------------------------------------------------


def _as_object(raw: Any) -> Any:
	if isinstance(raw, (str, bytes)):
		try:
			return json.loads(raw)
		except ValueError:
			raise ValueError("reply_markup must be valid JSON") from None
	return raw


def _text(button: Any) -> str:
	text = button if isinstance(button, str) else (button or {}).get("text")
	if not isinstance(text, str) or not text.strip():
		raise ValueError("every keyboard button needs non-empty text")
	return text


def _inline_button(button: Any, sign: Callable[[str], str] | None) -> dict[str, Any]:
	if not isinstance(button, Mapping):
		raise ValueError("inline buttons must be objects")
	text = _text(button)
	url = button.get("url")
	callback = button.get("callback")
	if callback is None and button.get("callback_data") is not None:
		callback = button.get("callback_data")
	if url and callback:
		raise ValueError("an inline button takes either url or callback, not both")
	if url:
		if not isinstance(url, str) or not url.lower().startswith(_URL_SCHEMES):
			raise ValueError("button url must start with http://, https:// or tg://")
		return url_button(text, url)
	if callback:
		if sign is None:
			raise ValueError("callback buttons are not available here; use url buttons")
		return callback_button(text, sign(str(callback)))
	raise ValueError("an inline button needs a url or a callback")


def normalize_reply_markup(raw: Any, *, sign: Callable[[str], str] | None = None) -> dict[str, Any] | None:
	"""Validate model-supplied ``reply_markup`` and rebuild it through the keyboard builders.

	Accepts a JSON string or object with exactly one of ``inline_keyboard`` (rows of ``{text, url}`` or
	``{text, callback}``; callbacks are signed by ``sign``), ``keyboard`` (rows of text buttons),
	``remove_keyboard`` or ``force_reply``. Anything else (web_app, login_url, raw callback_data
	that was not signed, unknown keys) is rejected. ``None``/empty returns ``None``.
	"""
	if raw in (None, "", {}, []):
		return None
	obj = _as_object(raw)
	if not isinstance(obj, Mapping):
		raise ValueError("reply_markup must be a JSON object")
	kinds = [k for k in ("inline_keyboard", "keyboard", "remove_keyboard", "force_reply") if obj.get(k)]
	if len(kinds) != 1:
		raise ValueError("reply_markup needs exactly one of inline_keyboard, keyboard, remove_keyboard, force_reply")
	kind = kinds[0]
	if kind == "remove_keyboard":
		return remove_keyboard(selective=bool(obj.get("selective")))
	if kind == "force_reply":
		return force_reply(placeholder=obj.get("input_field_placeholder"), selective=bool(obj.get("selective")))
	rows = obj[kind]
	if not isinstance(rows, list) or not all(isinstance(r, list) for r in rows):
		raise ValueError(f"{kind} must be a list of button rows")
	if sum(len(r) for r in rows) > MAX_KEYBOARD_BUTTONS or any(len(r) > MAX_ROW_BUTTONS for r in rows):
		raise ValueError(f"keyboard too large (max {MAX_KEYBOARD_BUTTONS} buttons, {MAX_ROW_BUTTONS} per row)")
	if kind == "inline_keyboard":
		built = inline_keyboard([[_inline_button(b, sign) for b in row] for row in rows])
		if not built["inline_keyboard"]:
			raise ValueError("inline_keyboard has no buttons")
		return built
	for row in rows:
		for b in row:
			if isinstance(b, Mapping) and set(b) - {"text", "request_contact", "request_location"}:
				raise ValueError("reply keyboard buttons allow only text, request_contact, request_location")
	built = reply_keyboard(
		[[b if isinstance(b, str) else {k: v for k, v in b.items() if v} for b in row] for row in rows if row],
		resize=bool(obj.get("resize_keyboard", True)), one_time=bool(obj.get("one_time_keyboard")),
		placeholder=obj.get("input_field_placeholder"), persistent=bool(obj.get("is_persistent")),
		selective=bool(obj.get("selective")),
	)
	for row in built["keyboard"]:
		for b in row:
			_text(b)
	return built
