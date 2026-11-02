# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Agent-emitted Telegram buttons and button-press (callback_query) handling.

Agent format (anywhere in the reply; the whole block is stripped from the visible text)::

	```telegram-buttons
	{"inline_keyboard": [[{"text": "Approve", "callback_data": "approve:42"},
	                      {"text": "Docs", "url": "https://example.com"}]],
	 "edit": true, "once": true}
	```

The canonical shapes are Telegram's own Bot API field names. ``validate`` normalises every accepted spelling
into ONE internal form (``spec``) in ONE place, so the template editor (``telegram_templates``), the agent
block and the markup builder share it. Accepted spellings:

- inline keyboard: ``inline_keyboard`` (native) or ``rows``; also wrapped in ``reply_markup``.
- inline button: ``text`` plus exactly one of ``callback_data`` (alias ``callback``; <= 46 bytes, the press
  becomes ``[button: <text>]``), ``url``, ``web_app`` (``{"url"}`` or a bare https string), ``login_url``
  (``{"url", "forward_text", "bot_username", "request_write_access"}`` or a bare string),
  ``switch_inline_query`` / ``switch_inline_query_current_chat`` (alias ``switch_inline`` as a string, with
  ``current_chat``, or as ``{"query", "current_chat"}``), ``copy_text`` (``{"text"}`` or a bare string).
- reply keyboard: ``keyboard`` (native, with ``resize_keyboard`` / ``one_time_keyboard`` /
  ``input_field_placeholder`` / ``is_persistent``) or ``reply_keyboard`` ``{"rows", "one_time", "resize",
  "placeholder"}``; a cell is a string or ``{"text", "request_contact" | "request_location" | "request_poll" |
  "web_app" | "request_users" | "request_chat"}``. ``remove_keyboard: true`` removes it.
- ``edit``: the agent's answer to a press edits the pressed message; ``once``: the keyboard is removed on the
  first press. Both real booleans (``"false"`` is false).

Limits are Telegram's: 8 buttons per row, 100 buttons, callback data 64 BYTES (46 for our id once signed).
Nothing is dropped silently: every problem comes back from ``validate`` as an error string, and the callers
(``telegram_pipeline.make_parts``) log it, note it on the Gateway Event and tell the agent on its next run.
The keyboard goes on the final real text part. Callback data is signed (HMAC, bound to the chat), so
``b:<flags>:<id>`` fits 64 bytes; the ``once`` / ``edit`` flags travel in the payload, so no server state is
needed to honour them.

Callback flow (``handle_callback``): answerCallbackQuery FIRST (stops the spinner even if the agent
run later fails), then stale / duplicate / already-used checks, then the press becomes the agent's
next input. Pure helpers are Frappe-free; ``cache`` / ``now`` / ``sender`` are injectable.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Callable

from huf.ai.gateway_adapters import telegram_blocks as blocks
from huf.ai.gateway_adapters import telegram_keyboards as kb

FENCE = blocks.BUTTONS
MAX_PER_ROW = 8
MAX_BUTTONS = 100
MAX_COPY_TEXT = 256
MAX_INLINE_QUERY = 256
MAX_PLACEHOLDER = 64
PREFIX = "b:"
FLAGS_LEN = 2
MAX_ID_BYTES = kb.MAX_PAYLOAD_BYTES - len(PREFIX) - FLAGS_LEN - 1
STALE_SECONDS = 48 * 3600
TTL_SECONDS = 7 * 24 * 3600
PLACEHOLDER_TEXT = "Please choose:"
MSG_STALE = "This button has expired."
MSG_USED = "Already used."

_log = logging.getLogger("huf.telegram.buttons")

# Accepted spellings. The agent instructions (telegram_agent_context) list only names found here.
INLINE_KEYS = ("inline_keyboard", "rows")
REPLY_KEYS = ("keyboard", "reply_keyboard")
KIND_ALIASES = {"callback": "callback_data", "switch_inline": "switch_inline_query"}
BUTTON_KINDS = (
	"callback_data",
	"url",
	"web_app",
	"login_url",
	"switch_inline_query",
	"switch_inline_query_current_chat",
	"copy_text",
)
LOGIN_FIELDS = ("url", "forward_text", "bot_username", "request_write_access")
REPLY_OPTIONS = {
	"resize_keyboard": "resize",
	"resize": "resize",
	"one_time_keyboard": "one_time",
	"one_time": "one_time",
	"input_field_placeholder": "placeholder",
	"placeholder": "placeholder",
	"is_persistent": "persistent",
	"persistent": "persistent",
}
CELL_REQUESTS = (
	"request_contact",
	"request_location",
	"request_poll",
	"web_app",
	"request_users",
	"request_chat",
)
USERS_FIELDS = (
	"request_id",
	"user_is_bot",
	"user_is_premium",
	"max_quantity",
	"request_name",
	"request_username",
	"request_photo",
)
CHAT_FIELDS = (
	"request_id",
	"chat_is_channel",
	"chat_is_forum",
	"chat_has_username",
	"chat_is_created",
	"bot_is_member",
	"request_title",
	"request_username",
	"request_photo",
)
TOP_KEYS = (*INLINE_KEYS, *REPLY_KEYS, "remove_keyboard", "reply_markup", "edit", "once", *REPLY_OPTIONS)
BUTTON_KEYS = ("text", "current_chat", *KIND_ALIASES, *BUTTON_KINDS)
ACCEPTED_KEYS = frozenset(
	{*TOP_KEYS, *BUTTON_KEYS, *LOGIN_FIELDS, *CELL_REQUESTS, *USERS_FIELDS, *CHAT_FIELDS, "query", "type"}
)

AGENT_INSTRUCTIONS = (
	'Buttons (Telegram Bot API field names): end the reply with a ```telegram-buttons JSON block, e.g. {"inline_keyboard":'
	'[[{"text":"Yes","callback_data":"yes"},{"text":"Docs","url":"https://..."}]],"once":true}. A button has text and ONE of '
	"callback_data (<=46 bytes; the press arrives as '[button: <text>]'), url, web_app{url}, login_url{url,forward_text,"
	"bot_username,request_write_access}, switch_inline_query, switch_inline_query_current_chat, copy_text{text}. Max 8 per row. "
	'Reply keyboard: {"keyboard":[["A",{"text":"Phone","request_contact":true}]],"one_time_keyboard":true,"resize_keyboard":'
	'true,"input_field_placeholder":"..."}; cells also take request_location, request_poll, web_app, request_users, request_chat. '
	'{"remove_keyboard":true} removes it. edit:true edits the pressed message; once:true removes the keyboard on first press.'
)

_INTERNAL_KINDS = (
	"callback",
	"url",
	"web_app",
	"login_url",
	"switch_inline_query",
	"switch_inline_query_current_chat",
	"copy_text",
)


# -- parsing -------------------------------------------------------------------------------------


def extract(text: str) -> tuple[str, dict | None, list[str]]:
	"""Return ``(visible_text, validated_spec | None, errors)``; every live block is stripped."""
	visible, found = blocks.scan(text)
	spec, errors = parse(found.get(FENCE, []))
	return visible, spec, errors


def parse(bodies: list[str]) -> tuple[dict | None, list[str]]:
	"""Validate the bodies of every ``telegram-buttons`` block of one reply (the last one wins, reported)."""
	if not bodies:
		return None, []
	spec, errors = validate(bodies[-1])
	if len(bodies) > 1:
		errors.insert(0, f"{len(bodies)} telegram-buttons blocks; only the last is used")
	return spec, errors


def _text(raw: Any) -> str:
	return raw.strip() if isinstance(raw, str) else ""


def _is_url(value: Any, schemes: tuple[str, ...]) -> bool:
	return isinstance(value, str) and any(value.lower().startswith(s) for s in schemes) and len(value) <= 2048


def _url_value(value: Any, field: str = "url") -> Any:
	"""A bare string or the native ``{"url": ...}`` object."""
	return value.get(field) if isinstance(value, dict) else value


def _kind_value(kind: str, value: Any, raw: dict, label: str, errors: list[str]) -> tuple[Any, bool]:
	"""Normalise one button kind value into its internal (Telegram-native) form. ``(value, ok)``."""
	if kind == "callback_data":
		value = str(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else value
		if not (isinstance(value, str) and 0 < len(value.encode("utf-8")) <= MAX_ID_BYTES):
			errors.append(f"{label}: callback_data must be 1-{MAX_ID_BYTES} bytes")
			return None, False
		return value, True
	if kind == "url":
		if not _is_url(value, ("https://", "http://", "tg://")):
			errors.append(f"{label}: url must start with https://, http:// or tg://")
			return None, False
		return value, True
	if kind == "web_app":
		url = _url_value(value)
		if not _is_url(url, ("https://",)):
			errors.append(f'{label}: web_app needs {{"url": "https://..."}}')
			return None, False
		return {"url": url}, True
	if kind == "login_url":
		url = _url_value(value)
		if not _is_url(url, ("https://",)):
			errors.append(f'{label}: login_url needs {{"url": "https://..."}}')
			return None, False
		out: dict[str, Any] = {"url": url}
		extra = value if isinstance(value, dict) else {}
		blocks.unknown_keys(extra, LOGIN_FIELDS, f"{label} login_url", errors)
		if _text(extra.get("forward_text")):
			out["forward_text"] = _text(extra["forward_text"])
		if _text(extra.get("bot_username")):
			out["bot_username"] = _text(extra["bot_username"]).lstrip("@")
		if blocks.parse_bool(extra.get("request_write_access"), f"{label} request_write_access", errors):
			out["request_write_access"] = True
		return out, True
	if kind == "copy_text":
		value = value.get("text") if isinstance(value, dict) else value
		if not (isinstance(value, str) and 0 < len(value) <= MAX_COPY_TEXT):
			errors.append(f"{label}: copy_text must be 1-{MAX_COPY_TEXT} characters")
			return None, False
		return {"text": value}, True
	# switch_inline_query / switch_inline_query_current_chat: an empty query is valid
	if not (isinstance(value, str) and len(value) <= MAX_INLINE_QUERY):
		errors.append(f"{label}: {kind} must be text of at most {MAX_INLINE_QUERY} characters")
		return None, False
	return value, True


def _button(raw: Any, errors: list[str]) -> dict | None:
	if not isinstance(raw, dict):
		errors.append("button must be an object with text and one action")
		return None
	text = _text(raw.get("text"))
	if not text:
		errors.append("button needs a text")
		return None
	label = f"button {text[:20]!r}"
	blocks.unknown_keys(raw, BUTTON_KEYS, label, errors)
	present: dict[str, Any] = {}
	for key, value in raw.items():
		kind = KIND_ALIASES.get(key, key)
		if kind not in BUTTON_KINDS or value is None:
			continue
		if value == "" and not kind.startswith("switch_inline"):
			continue
		present[kind] = (key, value)
	if len(present) != 1:
		errors.append(f"{label} needs exactly one of {', '.join(BUTTON_KINDS)}")
		return None
	kind, (key, value) = next(iter(present.items()))
	if key == "switch_inline":  # our shorter spelling: string (+ current_chat) or {"query", "current_chat"}
		current = raw.get("current_chat")
		if isinstance(value, dict):
			current = value.get("current_chat", current)
			value = value.get("query", "")
		if blocks.parse_bool(current, f"{label} current_chat", errors):
			kind = "switch_inline_query_current_chat"
	value, ok = _kind_value(kind, value, raw, label, errors)
	if not ok:
		return None
	return {"text": text, ("callback" if kind == "callback_data" else kind): value}


def _inline_rows(raw_rows: Any, errors: list[str]) -> list[list[dict]]:
	if not isinstance(raw_rows, list):
		return []
	rows, total = [], 0
	for r, row in enumerate(raw_rows, 1):
		if isinstance(row, dict):
			errors.append(f"row {r}: rows must be lists of buttons; treated as its own row")
			row = [row]
		if not isinstance(row, list):
			errors.append(f"row {r}: must be a list of buttons")
			continue
		if len(row) > MAX_PER_ROW:
			errors.append(
				f"row {r}: {len(row)} buttons; Telegram allows {MAX_PER_ROW}, the rest were dropped"
			)
			row = row[:MAX_PER_ROW]
		cells = []
		for b in row:
			if total >= MAX_BUTTONS:
				errors.append(f"too many buttons; Telegram allows {MAX_BUTTONS}, the rest were dropped")
				break
			btn = _button(b, errors)
			if btn:
				cells.append(btn)
				total += 1
		if cells:
			rows.append(cells)
	return rows


def _cell(raw: Any, errors: list[str]) -> dict | None:
	if isinstance(raw, str):
		return {"text": raw.strip()} if raw.strip() else None
	if not isinstance(raw, dict) or not _text(raw.get("text")):
		errors.append("keyboard cell needs a text")
		return None
	text = _text(raw["text"])
	label = f"keyboard cell {text[:20]!r}"
	blocks.unknown_keys(raw, ("text", *CELL_REQUESTS), label, errors)
	out: dict[str, Any] = {"text": text}
	for flag in ("request_contact", "request_location"):
		if blocks.parse_bool(raw.get(flag), f"{label} {flag}", errors):
			out[flag] = True
	poll = raw.get("request_poll")
	if poll:
		kind = poll.get("type") if isinstance(poll, dict) else None
		if kind not in (None, "quiz", "regular"):
			errors.append(f"{label}: request_poll type must be quiz or regular")
		out["request_poll"] = {"type": kind} if kind in ("quiz", "regular") else {}
	if raw.get("web_app"):
		url = _url_value(raw["web_app"])
		if _is_url(url, ("https://",)):
			out["web_app"] = {"url": url}
		else:
			errors.append(f"{label}: web_app needs an https url")
	for name, allowed in (("request_users", USERS_FIELDS), ("request_chat", CHAT_FIELDS)):
		spec = raw.get(name)
		if spec in (None, False):
			continue
		if not isinstance(spec, dict) or not isinstance(spec.get("request_id"), int):
			errors.append(f"{label}: {name} needs an integer request_id; button dropped")
			return None
		blocks.unknown_keys(spec, allowed, f"{label} {name}", errors)
		out[name] = {k: v for k, v in spec.items() if k in allowed}
	if (
		sum(
			1
			for k in (
				"request_contact",
				"request_location",
				"request_poll",
				"web_app",
				"request_users",
				"request_chat",
			)
			if k in out
		)
		> 1
	):
		errors.append(f"{label}: use only one request_* / web_app option per cell; kept the first")
		keep = next(k for k in CELL_REQUESTS if k in out)
		out = {"text": text, keep: out[keep]}
	return out


def _reply_keyboard(raw: dict, errors: list[str]) -> dict | None:
	source = raw.get("keyboard") if raw.get("keyboard") else raw.get("reply_keyboard")
	opts = dict(raw)
	rows_in = source
	if isinstance(source, dict):  # {"rows": [...], "one_time": ...}
		opts = {**raw, **source}
		rows_in = source.get("rows") or source.get("keyboard")
	rows = []
	for r, row in enumerate(rows_in if isinstance(rows_in, list) else [], 1):
		if not isinstance(row, list):
			errors.append(f"keyboard row {r}: must be a list of cells")
			continue
		if len(row) > MAX_PER_ROW:
			errors.append(
				f"keyboard row {r}: {len(row)} cells; Telegram allows {MAX_PER_ROW}, the rest were dropped"
			)
			row = row[:MAX_PER_ROW]
		cells = [c for c in (_cell(cell, errors) for cell in row) if c]
		if cells:
			rows.append(cells)
	if not rows:
		errors.append("keyboard has no valid buttons")
		return None
	flags: dict[str, Any] = {"one_time": False, "resize": True, "persistent": False, "placeholder": ""}
	for key, name in REPLY_OPTIONS.items():
		if key not in opts:
			continue
		if name == "placeholder":
			text = str(opts[key] or "")
			if len(text) > MAX_PLACEHOLDER:
				errors.append(f"input_field_placeholder cut to {MAX_PLACEHOLDER} characters")
			flags[name] = text[:MAX_PLACEHOLDER]
		else:
			flags[name] = blocks.parse_bool(opts[key], key, errors, default=flags[name])
	return {"mode": "reply_keyboard", "rows": rows, **flags}


def validate(raw: Any) -> tuple[dict | None, list[str]]:
	"""Validate a JSON string / dict into a normalised spec ``(spec | None, errors)``. Never raises.

	``errors`` also carries non-fatal notes (a dropped button, an ignored field); ``spec`` is ``None`` only
	when nothing usable is left.
	"""
	errors: list[str] = []
	if isinstance(raw, str):
		raw, err = blocks.loads(raw)
		if err:
			return None, [err]
	if isinstance(raw, list):  # a bare list of rows is the inline keyboard
		raw = {"inline_keyboard": raw}
	if not isinstance(raw, dict):
		return None, ["spec must be a JSON object"]
	if isinstance(raw.get("reply_markup"), dict):
		raw = {**{k: v for k, v in raw.items() if k != "reply_markup"}, **raw["reply_markup"]}
	blocks.unknown_keys(raw, TOP_KEYS, "buttons", errors)
	modes = [
		m
		for m, keys in (
			("rows", INLINE_KEYS),
			("reply_keyboard", REPLY_KEYS),
			("remove_keyboard", ("remove_keyboard",)),
		)
		if any(raw.get(k) for k in keys)
	]
	if not modes:
		return None, errors + ["spec needs inline_keyboard, keyboard or remove_keyboard"]
	if len(modes) > 1:
		errors.append(f"only one of inline_keyboard/keyboard/remove_keyboard allowed; using {modes[0]}")
	mode = modes[0]
	if mode == "remove_keyboard":
		if not blocks.parse_bool(raw.get("remove_keyboard"), "remove_keyboard", errors):
			return None, errors + ["remove_keyboard must be true"]
		return {"mode": mode}, errors
	if mode == "reply_keyboard":
		spec = _reply_keyboard(raw, errors)
		return spec, errors
	inline = next(raw[k] for k in INLINE_KEYS if raw.get(k))
	rows = _inline_rows(inline, errors)
	if not rows:
		return None, errors + ["no valid buttons"]
	spec = {
		"mode": "rows",
		"rows": rows,
		"edit": blocks.parse_bool(raw.get("edit"), "edit", errors),
		"once": blocks.parse_bool(raw.get("once"), "once", errors),
	}
	return spec, errors


def has_callbacks(spec: dict) -> bool:
	"""True when the inline keyboard has callback buttons (they need a signer)."""
	return spec.get("mode") == "rows" and any("callback" in b for row in spec["rows"] for b in row)


# -- markup --------------------------------------------------------------------------------------


def encode_payload(button_id: str, *, once: bool, edit: bool) -> str:
	return f"{PREFIX}{'o' if once else '-'}{'e' if edit else '-'}:{button_id}"


def decode_payload(payload: str) -> dict | None:
	"""``{"id", "once", "edit"}`` for our payloads, else ``None`` (foreign payload)."""
	if (
		not isinstance(payload, str)
		or not payload.startswith(PREFIX)
		or payload[2 + FLAGS_LEN : 3 + FLAGS_LEN] != ":"
	):
		return None
	flags = payload[2 : 2 + FLAGS_LEN]
	return {"id": payload[3 + FLAGS_LEN :], "once": flags[0] == "o", "edit": flags[1] == "e"}


def build_markup(spec: dict, sign: Callable[[str], str]) -> dict:
	"""Telegram ``reply_markup`` for a validated spec. ``sign(payload) -> callback_data``."""
	mode = spec["mode"]
	if mode == "remove_keyboard":
		return kb.remove_keyboard()
	if mode == "reply_keyboard":
		return kb.reply_keyboard(
			spec["rows"],
			resize=spec["resize"],
			one_time=spec["one_time"],
			placeholder=spec["placeholder"] or None,
			persistent=spec.get("persistent", False),
		)
	rows = []
	for row in spec["rows"]:
		out = []
		for b in row:
			if "callback" in b:
				data = sign(encode_payload(b["callback"], once=spec["once"], edit=spec["edit"]))
				out.append(kb.callback_button(b["text"], data))
			else:
				out.append(dict(b))  # already Telegram's own shape
		rows.append(out)
	return kb.inline_keyboard(rows)


def _cache(cache: Any = None) -> Any:
	return blocks.get_cache(cache)


def _hash(text: str) -> str:
	return hashlib.sha1(str(text).encode("utf-8")).hexdigest()


def remember_spec(visible: str, spec: dict, *, cache: Any = None, scope: str = "") -> None:
	"""Store ``spec`` under the hash of the last paragraph-chunk(s) of ``visible`` (retry-safe)."""
	try:
		from huf.ai.gateway_adapters.telegram_format import split_message

		parts = split_message(visible) or [visible]
		_cache(cache).set_value(
			f"huf_tg_btn:{_hash(scope + chr(0) + parts[-1])}", spec, expires_in_sec=TTL_SECONDS
		)
	except Exception:
		pass


def spec_for_text(joined: str, *, cache: Any = None, scope: str = "") -> dict | None:
	"""Find the remembered spec for the (possibly partially-sent) parts joined with blank lines."""
	try:
		c = _cache(cache)
		candidate = str(joined)
		while True:
			spec = c.get_value(f"huf_tg_btn:{_hash(scope + chr(0) + candidate)}")
			if isinstance(spec, dict):
				return spec
			if "\n\n" not in candidate:
				return None
			candidate = candidate.split("\n\n", 1)[1]
	except Exception:
		return None


def default_signer(event: Any, gateway: Any) -> Callable[[str], str]:
	from huf.ai.gateway_webhook import event_contact_name, get_gateway_adapter

	adapter = get_gateway_adapter(gateway, event_contact_name(event))
	chat = event.conversation_id
	return lambda payload: adapter.sign_callback_data(payload, chat)


def markup_for(
	event: Any, gateway: Any, response_text: str, *, signer: Any = None, cache: Any = None
) -> dict | None:
	"""``reply_markup_for`` implementation. Never raises: a button failure must not block the reply.

	A failure is logged, noted for the operator and fed back to the agent (it is never silent)."""
	scope = ""
	try:
		scope = blocks.scope_key(
			getattr(gateway, "name", ""), getattr(event, "conversation_id", ""), getattr(event, "name", "")
		)
		spec = spec_for_text(blocks.drop_notes(response_text), cache=cache, scope=scope)
		if spec is None:
			return None
		return build_markup(spec, signer or default_signer(event, gateway))
	except Exception as exc:
		blocks.record(scope, [f"buttons could not be attached ({type(exc).__name__})"], cache=cache)
		return None


# -- callbacks -----------------------------------------------------------------------------------


def _msg(raw_update: dict) -> dict:
	cq = raw_update.get("callback_query") if isinstance(raw_update, dict) else None
	msg = cq.get("message") if isinstance(cq, dict) else None
	return msg if isinstance(msg, dict) else {}


def button_label(raw_update: dict, callback_data: str) -> str:
	"""Visible text of the pressed button, read from the keyboard Telegram echoes back."""
	markup = _msg(raw_update).get("reply_markup") or {}
	for row in markup.get("inline_keyboard") or []:
		for b in row:
			if isinstance(b, dict) and b.get("callback_data") == callback_data:
				return str(b.get("text") or "")
	return ""


def is_stale(raw_update: dict, now: float | None = None) -> bool:
	"""Unknown/inaccessible message (no date) or older than 48h."""
	date = _msg(raw_update).get("date")
	if not isinstance(date, (int, float)) or date <= 0:
		return True
	return (now if now is not None else time.time()) - date > STALE_SECONDS


def _claim(c: Any, key: str) -> bool:
	"""True the first time ``key`` is seen (best-effort get-then-set)."""
	try:
		if c.get_value(key):
			return False
		c.set_value(key, 1, expires_in_sec=TTL_SECONDS)
	except Exception:
		pass
	return True


def callback_input_text(label: str, button_id: str) -> str:
	return f"[button: {label or button_id}]\ncallback_data: {button_id}"


def handle_callback(
	parsed: Any,
	payload: str | None,
	sender: Any,
	gateway_name: str,
	*,
	cache: Any = None,
	now: float | None = None,
) -> dict:
	"""Decide what to do with a callback_query. Answers the query FIRST.

	``payload`` is the verified payload (None = bad signature). ``sender`` is a ``TelegramSender``.
	Returns ``{"action": "ingest"|"ignore", "text": str, "edit_message_id": str, "reason": str}``.
	"""
	cqid = parsed.callback_query_id

	def answer(text: str = "") -> None:
		try:
			if cqid:
				sender.answer_callback_query(cqid, text)
		except Exception:
			pass

	def ignore(reason: str, toast: str = "") -> dict:
		answer(toast)
		return {"action": "ignore", "reason": reason, "text": "", "edit_message_id": ""}

	c = _cache(cache)
	if payload is None:
		return ignore("invalid_signature", MSG_STALE)
	if is_stale(parsed.raw, now):
		return ignore("stale", MSG_STALE)
	if cqid and not _claim(c, f"huf_tg_cbq:{gateway_name}:{cqid}"):
		return ignore("duplicate")
	info = decode_payload(payload)
	if (
		info
		and info["once"]
		and not _claim(c, f"huf_tg_once:{gateway_name}:{parsed.chat_id}:{parsed.message_id}")
	):
		return ignore("already_used", MSG_USED)
	answer()
	if info and info["once"] and parsed.message_id:
		try:
			sender.edit_message_reply_markup(parsed.chat_id, parsed.message_id, None)
		except Exception:
			pass
	if info is None:
		return {"action": "ingest", "text": payload, "edit_message_id": "", "reason": "foreign"}
	return {
		"action": "ingest",
		"text": callback_input_text(button_label(parsed.raw, parsed.callback_data), info["id"]),
		"edit_message_id": parsed.message_id if info["edit"] else "",
		"reason": "button",
	}


def edit_target(event: Any) -> int | None:
	"""Message id to edit in place for this (callback) event, or None to send a new message."""
	raw = getattr(event, "raw_payload", None)
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except ValueError:
			return None
	if not isinstance(raw, dict):
		return None
	mid = (raw.get("telegram_meta") or {}).get("edit_message_id")
	try:
		return int(mid) if mid else None
	except (TypeError, ValueError):
		return None


def try_edit(sender: Any, event: Any, parts: list[str], markup: dict | None) -> Any:
	"""Edit the pressed message in place when the spec asked for it (single part, inline markup only).

	Returns a ``SimpleNamespace`` shaped like ``send_parts_with``'s result, or ``None`` to send normally.
	"""
	target = edit_target(event)
	if not target or len(parts) != 1:
		return None
	if markup is not None and "inline_keyboard" not in markup:
		return None
	try:
		sender.edit_message_text(
			event.conversation_id,
			target,
			parts[0],
			markup=markup if markup is not None else {"inline_keyboard": []},
		)
	except Exception:
		return None
	from types import SimpleNamespace

	return SimpleNamespace(
		provider_message_id=str(target), provider_response={"message_ids": [target], "edited": True}
	)
