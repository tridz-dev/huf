"""Hide phone numbers in a real chat message before it is pinned as a sample or offered as "last real message".

Keeps the last four digits so a person still recognises the number: ``15550001111`` becomes ``****1111``. Applies to the
id fields that hold a number (sender, WhatsApp number, Telegram user, conversation) and to number-like runs inside any
text, including contact cards. Pure functions, no database.
"""

from __future__ import annotations

import re

KEEP = 4
MIN_DIGITS = 7
PREFIX = "****"
# Fields that hold a person's number or chat id as a whole value.
ID_KEYS = frozenset({"sender_id", "wa_id", "telegram_user_id", "telegram_chat_id", "conversation_id", "thread_id"})
# Values that are times, not numbers.
SKIP_KEYS = frozenset({"received_at"})

_NUMBER_RUN = re.compile(r"(?<![\w.])\+?\(?\d[\d\s().\-]{4,}\d(?![\w])")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _digits(text: str) -> str:
	return re.sub(r"\D", "", text)


def mask_phone(value) -> str:
	"""``****`` plus the last four digits of ``value``; anything with fewer than four digits is fully hidden."""
	digits = _digits(str(value or ""))
	if not digits:
		return ""
	return PREFIX + digits[-KEEP:] if len(digits) > KEEP else PREFIX


def mask_numbers_in_text(text: str) -> str:
	"""Mask every number-like run of at least seven digits inside ``text`` (dates are left alone)."""

	def repl(match: re.Match) -> str:
		run = match.group(0)
		if len(_digits(run)) < MIN_DIGITS or _DATE.match(run):
			return run
		return mask_phone(run)

	return _NUMBER_RUN.sub(repl, text)


def mask_sample(value, key: str | None = None):
	"""A copy of ``value`` (nested dicts and lists) with phone numbers masked."""
	if isinstance(value, dict):
		return {k: mask_sample(v, str(k)) for k, v in value.items()}
	if isinstance(value, (list, tuple)):
		return [mask_sample(v, key) for v in value]
	if isinstance(value, str):
		if key in SKIP_KEYS:
			return value
		if key in ID_KEYS and _digits(value):
			return mask_phone(value)
		return mask_numbers_in_text(value)
	if isinstance(value, int) and not isinstance(value, bool) and key in ID_KEYS:
		return mask_phone(value)
	return value
