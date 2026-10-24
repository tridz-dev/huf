# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Agent-emitted Telegram buttons and button-press (callback_query) handling.

Agent format (put it anywhere in the reply; it is stripped from the visible text)::

	```telegram-buttons
	{"rows": [[{"text": "Approve", "callback": "approve:42"},
	           {"text": "Docs", "url": "https://example.com"}]],
	 "edit": true, "once": true}
	```

Top level keys (exactly one of ``rows`` / ``reply_keyboard`` / ``remove_keyboard``):

- ``rows``: inline keyboard, list of rows of buttons. Each button has ``text`` and exactly one of
  ``callback`` (id <= 46 bytes; the next agent input becomes ``[button: <text>]``), ``url``,
  ``web_app`` (``{"url": "https://..."}``, Telegram's own shape), ``switch_inline`` (query;
  ``"current_chat": true`` for the same chat), ``copy_text`` (<= 256 chars), ``login_url``
  (``{"url": "https://..."}``). Message templates store the same two kinds as a bare https string; the
  validator accepts both and normalises to one internal form.
- ``edit``: true = the agent's answer to a button press edits the original message in place.
- ``once``: true = the keyboard is removed on the first press (double taps are ignored).
- ``reply_keyboard``: ``{"rows": [["A", "B"], ["C"]], "one_time": bool, "resize": bool,
  "placeholder": str}`` (a cell may be ``{"text", "request_contact"|"request_location"}``).
- ``remove_keyboard``: true removes a previously shown reply keyboard.

Limits: 8 buttons per row, 10 rows, 40 buttons. Invalid buttons are dropped; the block is always
stripped. The keyboard goes on the LAST message part. Callback data is signed (HMAC, bound to the
chat), so ``b:<flags>:<id>`` fits 64 bytes; the ``once`` / ``edit`` flags travel in the payload, so
no server state is needed to honour them.

Callback flow (``handle_callback``): answerCallbackQuery FIRST (stops the spinner even if the agent
run later fails), then stale / duplicate / already-used checks, then the press becomes the agent's
next input. Pure helpers are Frappe-free; ``cache`` / ``now`` / ``sender`` are injectable.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any, Callable

from huf.ai.gateway_adapters import telegram_keyboards as kb

FENCE = "telegram-buttons"
_FENCE_RE = re.compile(r"```[ \t]*" + FENCE + r"[ \t]*\r?\n(.*?)(?:\r?\n)?```", re.DOTALL)
MAX_PER_ROW = 8
MAX_ROWS = 10
MAX_BUTTONS = 40
MAX_TEXT = 64
MAX_COPY_TEXT = 256
PREFIX = "b:"
FLAGS_LEN = 2
MAX_ID_BYTES = kb.MAX_PAYLOAD_BYTES - len(PREFIX) - FLAGS_LEN - 1
STALE_SECONDS = 48 * 3600
TTL_SECONDS = 7 * 24 * 3600
PLACEHOLDER_TEXT = "Please choose:"
MSG_STALE = "This button has expired."
MSG_USED = "Already used."

AGENT_INSTRUCTIONS = (
	"On Telegram you can attach buttons by adding a fenced block ```telegram-buttons with JSON: "
	'{"rows": [[{"text": "Yes", "callback": "yes"}, {"text": "Site", "url": "https://..."}]], '
	'"edit": false, "once": true}. Button kinds: callback (id <= 46 bytes), url, web_app {"url": https}, '
	"switch_inline, copy_text, login_url {\"url\": https}. Alternatives: reply_keyboard {rows, one_time, resize, placeholder} or "
	"remove_keyboard true. A press arrives as '[button: <text>]'. Max 8 buttons per row, 10 rows."
)

_KINDS = ("callback", "url", "web_app", "switch_inline", "copy_text", "login_url")


# -- parsing -------------------------------------------------------------------------------------


def extract(text: str) -> tuple[str, dict | None, list[str]]:
	"""Return ``(visible_text, validated_spec | None, errors)``; every fenced block is stripped."""
	text = str(text or "")
	blocks = _FENCE_RE.findall(text)
	if not blocks:
		return text, None, []
	visible = _FENCE_RE.sub("", text)
	visible = re.sub(r"\n{3,}", "\n\n", visible).strip()
	spec, errors = validate(blocks[-1])
	return visible, spec, errors


def _id_ok(value: Any) -> bool:
	return isinstance(value, str) and 0 < len(value.encode("utf-8")) <= MAX_ID_BYTES


def _is_url(value: Any, schemes: tuple[str, ...]) -> bool:
	return isinstance(value, str) and any(value.lower().startswith(s) for s in schemes) and len(value) <= 2048


def _button(raw: Any, errors: list[str]) -> dict | None:
	if not isinstance(raw, dict) or not isinstance(raw.get("text"), str) or not raw["text"].strip():
		errors.append("button needs a text")
		return None
	kinds = [k for k in _KINDS if raw.get(k) not in (None, "")]
	if len(kinds) != 1:
		errors.append(f"button {raw['text'][:20]!r} needs exactly one of {', '.join(_KINDS)}")
		return None
	kind, value = kinds[0], raw[kinds[0]]
	if kind in ("web_app", "login_url") and isinstance(value, dict):
		value = value.get("url")  # Telegram's own shape ``{"url": "https://..."}``; models write it naturally
	text = raw["text"].strip()[:MAX_TEXT]
	ok = {
		"callback": _id_ok(value),
		"url": _is_url(value, ("https://", "http://", "tg://")),
		"web_app": _is_url(value, ("https://",)),
		"login_url": _is_url(value, ("https://",)),
		"switch_inline": isinstance(value, str) and len(value) <= 256,
		"copy_text": isinstance(value, str) and 0 < len(value) <= MAX_COPY_TEXT,
	}[kind]
	if not ok:
		errors.append(f"button {text[:20]!r}: invalid {kind}")
		return None
	out = {"text": text, kind: value}
	if kind == "switch_inline" and raw.get("current_chat"):
		out["current_chat"] = True
	return out


def validate(raw: Any) -> tuple[dict | None, list[str]]:
	"""Validate a JSON string / dict into a normalised spec. Never raises."""
	errors: list[str] = []
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except ValueError:
			return None, ["invalid JSON"]
	if not isinstance(raw, dict):
		return None, ["spec must be a JSON object"]
	modes = [k for k in ("rows", "reply_keyboard", "remove_keyboard") if raw.get(k)]
	if not modes:
		return None, ["spec needs rows, reply_keyboard or remove_keyboard"]
	if len(modes) > 1:
		errors.append(f"only one of rows/reply_keyboard/remove_keyboard allowed; using {modes[0]}")
	mode = modes[0]
	spec: dict[str, Any] = {"mode": mode}
	if mode == "remove_keyboard":
		return spec, errors
	if mode == "reply_keyboard":
		rk = raw["reply_keyboard"]
		rows_in = rk.get("rows") if isinstance(rk, dict) else None
		rows = []
		for row in (rows_in if isinstance(rows_in, list) else [])[:MAX_ROWS]:
			cells = []
			for cell in (row if isinstance(row, list) else [])[:MAX_PER_ROW]:
				if isinstance(cell, str) and cell.strip():
					cells.append({"text": cell.strip()[:MAX_TEXT]})
				elif isinstance(cell, dict) and isinstance(cell.get("text"), str) and cell["text"].strip():
					c = {"text": cell["text"].strip()[:MAX_TEXT]}
					for flag in ("request_contact", "request_location"):
						if cell.get(flag):
							c[flag] = True
					cells.append(c)
			if cells:
				rows.append(cells)
		if not rows:
			return None, errors + ["reply_keyboard has no valid buttons"]
		spec.update(
			rows=rows,
			one_time=bool(rk.get("one_time")),
			resize=rk.get("resize", True) is not False,
			placeholder=str(rk.get("placeholder") or "")[:64],
		)
		return spec, errors
	rows, total = [], 0
	for row in raw["rows"][:MAX_ROWS] if isinstance(raw["rows"], list) else []:
		cells = []
		for b in (row if isinstance(row, list) else [])[:MAX_PER_ROW]:
			if total >= MAX_BUTTONS:
				errors.append("too many buttons; extra dropped")
				break
			btn = _button(b, errors)
			if btn:
				cells.append(btn)
				total += 1
		if cells:
			rows.append(cells)
	if not rows:
		return None, errors + ["no valid buttons"]
	spec.update(rows=rows, edit=bool(raw.get("edit")), once=bool(raw.get("once")))
	return spec, errors


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
		)
	rows = []
	for row in spec["rows"]:
		out = []
		for b in row:
			text = b["text"]
			if "callback" in b:
				out.append(
					kb.callback_button(
						text, sign(encode_payload(b["callback"], once=spec["once"], edit=spec["edit"]))
					)
				)
			elif "url" in b:
				out.append(kb.url_button(text, b["url"]))
			elif "web_app" in b:
				out.append(kb.web_app_button(text, b["web_app"]))
			elif "switch_inline" in b:
				key = "switch_inline_query_current_chat" if b.get("current_chat") else "switch_inline_query"
				out.append({"text": text, key: b["switch_inline"]})
			elif "copy_text" in b:
				out.append({"text": text, "copy_text": {"text": b["copy_text"]}})
			elif "login_url" in b:
				out.append({"text": text, "login_url": {"url": b["login_url"]}})
		rows.append(out)
	return kb.inline_keyboard(rows)


def _cache(cache: Any = None) -> Any:
	if cache is not None:
		return cache
	try:
		import frappe

		return frappe.cache()
	except Exception:
		return _LOCAL  # no site (unit tests): process-local best effort


class _LocalCache:
	def __init__(self) -> None:
		self.d: dict = {}

	def set_value(self, key, value, expires_in_sec=None):
		self.d[key] = value

	def get_value(self, key):
		return self.d.get(key)


_LOCAL = _LocalCache()


def _hash(text: str) -> str:
	return hashlib.sha1(str(text).encode("utf-8")).hexdigest()


def prepare_reply(response: str, *, cache: Any = None, scope: str = "") -> str:
	"""Strip the button block from ``response``; remember its spec keyed by the final text's last part.

	Called by ``telegram_pipeline.make_parts`` before splitting. Returns the visible text (a short
	placeholder when only buttons were given, so Telegram has a message to attach them to).
	"""
	if not _FENCE_RE.search(str(response or "")):
		return str(response or "")
	visible, spec, _errors = extract(response)
	if spec is not None:
		if not visible:
			visible = PLACEHOLDER_TEXT
		remember_spec(visible, spec, cache=cache, scope=scope)
	return visible


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
	"""``reply_markup_for`` implementation. Never raises: a button failure must not block the reply."""
	try:
		from huf.ai.gateway_adapters.telegram_media_reply import scope_key

		scope = scope_key(
			getattr(gateway, "name", ""), getattr(event, "conversation_id", ""), getattr(event, "name", "")
		)
		spec = spec_for_text(response_text, cache=cache, scope=scope)
		if spec is None:
			return None
		return build_markup(spec, signer or default_signer(event, gateway))
	except Exception:
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
