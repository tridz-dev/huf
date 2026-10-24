# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Shared plumbing for the agent's fenced reply blocks (``telegram-buttons`` / ``telegram-media``).

One place for everything the two block modules have in common:

- ``scan``: find the blocks in a reply and strip them from the visible text. Tolerates ``~~~`` fences,
  language tags (``json telegram-buttons``), any case, single-line blocks and an unclosed fence at the
  end of a truncated reply; a block inside a longer-fenced or indented code sample is NOT live.
- ``loads``: JSON with trailing commas tolerated.
- ``parse_bool``: real booleans only (``"false"`` is False, garbage is reported, never ``True``).
- the error store: every validation problem is logged for the operator, noted on the Gateway Event and
  handed back to the agent on its next run in the same conversation (``feedback_line``).

Frappe-free except for the cache / logger lookups, which degrade to process-local fallbacks in unit tests.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from types import SimpleNamespace
from typing import Any

BUTTONS = "telegram-buttons"
MEDIA = "telegram-media"
NAMES = (BUTTONS, MEDIA)

ERROR_TTL_SECONDS = 24 * 3600
MAX_FEEDBACK_ERRORS = 3
MAX_ERROR_CHARS = 110
NOTE_MAX_CHARS = 500

_OPEN_OURS = re.compile(
	r"(`{3,}|~{3,})[ \t]*(?:json[ \t]+)?telegram[-_](buttons|media)(?![\w-])(?:[ \t]+json(?![\w-]))?",
	re.IGNORECASE,
)
_OPEN_ANY = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_INDENTED = re.compile(r"^(?: {4,}|\t)")

_log = logging.getLogger("huf.telegram.blocks")


# -- scanning ------------------------------------------------------------------------------------


def _closes(line: str, char: str, size: int) -> tuple[bool, str]:
	"""``(closed, body_part)`` for a line inside our block: a bare fence line or a line ending in one."""
	stripped = line.rstrip()
	if re.fullmatch(r" {0,3}" + re.escape(char) + "{" + str(size) + r",}", stripped):
		return True, ""
	if stripped.endswith(char * size):
		return True, stripped.rstrip(char)
	return False, line


def scan(text: Any) -> tuple[str, dict[str, list[str]]]:
	"""Return ``(visible_text, {block_name: [body, ...]})``; every live block is stripped from the text."""
	lines = str(text or "").split("\n")
	kept: list[str] = []
	found: dict[str, list[str]] = {}
	foreign: tuple[str, int] | None = None
	cur: dict[str, Any] | None = None
	for line in lines:
		if cur is not None:
			closed, part = _closes(line, cur["char"], cur["size"])
			cur["body"].append(part)
			if closed:
				found.setdefault(cur["name"], []).append("\n".join(cur["body"]))
				cur = None
			continue
		if foreign is not None:
			kept.append(line)
			char, size = foreign
			if re.fullmatch(r" {0,3}" + re.escape(char) + "{" + str(size) + r",}[ \t]*", line):
				foreign = None
			continue
		if _INDENTED.match(line):
			kept.append(line)
			continue
		m = _OPEN_OURS.search(line)
		if m:
			tail = line[m.end() :]
			if not tail.strip() or tail.lstrip()[:1] in ("{", "["):
				prefix = line[: m.start()]
				if prefix.strip():
					kept.append(prefix.rstrip())
				cur = {
					"name": "telegram-" + m.group(2).lower(),
					"char": m.group(1)[0],
					"size": len(m.group(1)),
					"body": [],
				}
				closed, part = _closes(tail, cur["char"], cur["size"])
				cur["body"].append(part)
				if closed:
					found.setdefault(cur["name"], []).append("\n".join(cur["body"]))
					cur = None
				continue
		m = _OPEN_ANY.match(line)
		if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
			foreign = (m.group(1)[0], len(m.group(1)))
		kept.append(line)
	if cur is not None:  # unclosed fence (truncated reply): the whole tail is the block
		found.setdefault(cur["name"], []).append("\n".join(cur["body"]))
	visible = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
	return visible, found


def strip(text: Any) -> str:
	"""Visible text with every live block removed."""
	return scan(text)[0]


# -- lenient JSON / values -----------------------------------------------------------------------


def _drop_trailing_commas(src: str) -> str:
	out: list[str] = []
	in_str = esc = False
	for i, ch in enumerate(src):
		if in_str:
			out.append(ch)
			if esc:
				esc = False
			elif ch == "\\":
				esc = True
			elif ch == '"':
				in_str = False
			continue
		if ch == '"':
			in_str = True
		elif ch == ",":
			rest = src[i + 1 :].lstrip()
			if rest[:1] in ("}", "]"):
				continue
		out.append(ch)
	return "".join(out)


def loads(body: Any) -> tuple[Any, str]:
	"""``(value, "")`` or ``(None, error)``. Trailing commas and surrounding whitespace are tolerated."""
	if not isinstance(body, str):
		return body, ""
	src = body.strip().lstrip("﻿")
	for candidate in (src, _drop_trailing_commas(src)):
		try:
			return json.loads(candidate), ""
		except ValueError:
			continue
	return None, "invalid JSON (check quotes, brackets and that the block was not cut off)"


_TRUE = {"true", "1", "yes", "on"}
_FALSE = {"false", "0", "no", "off", ""}


def parse_bool(value: Any, name: str, errors: list[str], default: bool = False) -> bool:
	if value is None:
		return default
	if isinstance(value, bool):
		return value
	if isinstance(value, (int, float)) and value in (0, 1):
		return bool(value)
	if isinstance(value, str):
		low = value.strip().lower()
		if low in _TRUE:
			return True
		if low in _FALSE:
			return False
	errors.append(f"{name}: expected true or false")
	return default


def unknown_keys(raw: dict, allowed: Any, label: str, errors: list[str]) -> None:
	extra = sorted(str(k) for k in raw if k not in allowed)
	if extra:
		errors.append(f"{label}: ignored unknown field(s) {', '.join(extra[:5])}")


# -- cache ----------------------------------------------------------------------------------------


class LocalCache:
	"""Process-local stand-in for ``frappe.cache()`` (unit tests, no site)."""

	def __init__(self) -> None:
		self.d: dict = {}

	def set_value(self, key, value, expires_in_sec=None):
		self.d[key] = value

	def get_value(self, key):
		return self.d.get(key)

	def delete_value(self, key):
		self.d.pop(key, None)


_LOCAL = LocalCache()


def get_cache(cache: Any = None) -> Any:
	if cache is not None:
		return cache
	try:
		import frappe

		return frappe.cache()
	except Exception:
		return _LOCAL


def digest(*parts: str) -> str:
	return hashlib.sha1("\x00".join(parts).encode("utf-8")).hexdigest()


# -- scopes ---------------------------------------------------------------------------------------


def scope_key(gateway_name: Any, chat_id: Any, event_name: Any) -> str:
	"""Cache scope for one reply: (gateway, chat, inbound event). Empty = unscoped (tests only)."""
	if not (gateway_name or chat_id or event_name):
		return ""
	return f"{gateway_name}|{chat_id}|{event_name}"


def conversation_scope(gateway_name: Any, chat_id: Any) -> str:
	"""The conversation a reply scope belongs to (scope minus the event)."""
	return f"{gateway_name}|{chat_id}"


def _conversation_of(scope: str) -> str:
	return scope.rsplit("|", 1)[0] if "|" in scope else scope


# -- error store ----------------------------------------------------------------------------------


def _short(err: str) -> str:
	return " ".join(str(err).split())[:MAX_ERROR_CHARS]


def record(scope: str, errors: list[str], *, cache: Any = None) -> None:
	"""Log, remember for the Gateway Event note and queue for the agent's next run. Never raises."""
	errors = [_short(e) for e in errors if e]
	if not errors:
		return
	try:
		_log.warning("Telegram reply blocks: %s", "; ".join(errors[:MAX_FEEDBACK_ERRORS]))
		try:
			import frappe

			frappe.logger("huf").warning(f"Telegram reply blocks: {'; '.join(errors[:MAX_FEEDBACK_ERRORS])}")
		except Exception:
			pass
		c = get_cache(cache)
		for key in (f"huf_tg_blkerr:{digest(scope)}", f"huf_tg_blkfb:{digest(_conversation_of(scope))}"):
			have = c.get_value(key)
			merged = (list(have) if isinstance(have, list) else []) + errors
			c.set_value(key, merged[-10:], expires_in_sec=ERROR_TTL_SECONDS)
	except Exception:
		pass


def _pop(key: str, cache: Any) -> list[str]:
	try:
		c = get_cache(cache)
		have = c.get_value(key)
		if isinstance(have, list) and have:
			try:
				c.delete_value(key)
			except Exception:
				c.set_value(key, None, expires_in_sec=1)
			return [str(e) for e in have]
	except Exception:
		pass
	return []


def take_errors(scope: str, *, cache: Any = None) -> list[str]:
	"""Pop the errors recorded for this reply (once)."""
	return _pop(f"huf_tg_blkerr:{digest(scope)}", cache)


def event_note(errors: list[str]) -> str:
	return ("Reply blocks: " + "; ".join(errors[:MAX_FEEDBACK_ERRORS]))[:NOTE_MAX_CHARS]


def attach_to_event(event: Any, scope: str, *, cache: Any = None) -> None:
	"""Store the reply's block problems on the Gateway Event (``delivery_error``). Never raises."""
	errors = take_errors(scope, cache=cache)
	if not errors:
		return
	try:
		event.db_set("delivery_error", event_note(errors), update_modified=False)
	except Exception:
		pass


def feedback_line(gateway_name: Any, chat_id: Any, *, cache: Any = None) -> str:
	"""One short line for the agent about its PREVIOUS reply in this conversation ('' when it was clean)."""
	errors = _pop(f"huf_tg_blkfb:{digest(conversation_scope(gateway_name, chat_id))}", cache)
	if not errors:
		return ""
	return (
		f"Your last reply had invalid buttons/media: {'; '.join(errors[:MAX_FEEDBACK_ERRORS])}. "
		'Valid: buttons {"inline_keyboard":[[{"text","callback_data"|"url"}]]}, '
		'media {"items":[{"type","media"}]}.'
	)


NOTE_PREFIX = "(Could not send "


def is_note(part: str) -> bool:
	"""True for the short failure note appended after the real text parts when attachments failed."""
	return str(part).startswith(NOTE_PREFIX)


def drop_notes(joined: str) -> str:
	"""``joined`` (parts joined with blank lines) without trailing failure notes."""
	chunks = str(joined).split("\n\n")
	while len(chunks) > 1 and is_note(chunks[-1]):
		chunks.pop()
	return "\n\n".join(chunks)


def problem_text(errors: list[str]) -> str:
	"""Plain text sent instead of an otherwise empty reply."""
	return f"(The buttons or attachments in this reply were invalid and not sent: {_short(errors[0])})"


def found_summary(found: dict[str, list[str]]) -> SimpleNamespace:
	return SimpleNamespace(buttons=found.get(BUTTONS, []), media=found.get(MEDIA, []))
