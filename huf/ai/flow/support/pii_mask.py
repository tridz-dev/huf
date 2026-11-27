"""Remove phone numbers, email addresses and people's names from a value before it is written to a run trace or log.

``mask_pii`` returns a masked copy and never changes its input. It is pure: no database and no hooks, so app-specific
field names (hook ``huf_flow_pii_fields``) are passed in by the caller as ``extra_fields``.

- Phone and email addresses are found by field name and inside any text. Phones keep their last four digits.
- Names are found by field name; a name found that way is also removed from the other text in the same value. A name
  that only ever appears in free text cannot be recognised.
- Hash-named ids (hex, 32 characters or more) and ISO dates are never altered.
- Fail-closed: a field that cannot be masked is left out, never written raw.
"""

from __future__ import annotations

import datetime
import json
import re
from decimal import Decimal

from huf.ai.flow.gateways.phone_mask import ID_KEYS, mask_phone
from huf.ai.flow.support.redact import drop_webhook_secrets

EMAIL_MASK = "[email]"
NAME_MASK = "[name]"
PHONE_MASK = "[phone]"
MAX_DEPTH = 20
MIN_NAME_PART = 3

PHONE_FIELDS = frozenset(
	{
		"phone",
		"phone_no",
		"phone_number",
		"mobile",
		"mobile_no",
		"mobile_number",
		"whatsapp",
		"whatsapp_no",
		"whatsapp_number",
		"contact_no",
		"contact_number",
		"msisdn",
	}
)
EMAIL_FIELDS = frozenset({"email", "email_id", "email_address", "mail"})
NAME_FIELDS = frozenset(
	{
		"name",
		"full_name",
		"first_name",
		"middle_name",
		"last_name",
		"customer_name",
		"member_name",
		"contact_name",
		"sender_name",
		"recipient_name",
		"profile_name",
		"push_name",
		"display_name",
		"lead_name",
		"employee_name",
		"user_name",
	}
)

_EMAIL = re.compile(r"[\w.+'%\-]+@[\w\-]+(?:\.[\w\-]+)+")
_HASH_ID = r"(?<![0-9A-Za-z])(?=[0-9]*[a-fA-F])[0-9a-fA-F]{32,}(?![0-9A-Za-z])"
_ISO_DATE = (
	r"(?<!\d)\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])"
	r"(?:[T ](?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d+)?)?)?(?!\d)"
)
_PROTECTED = re.compile(f"({_HASH_ID}|{_ISO_DATE})")
# Seven or more digits, allowing the usual separators between them.
_PHONE = re.compile(r"(?<!\d)\+?\(?\d(?:[\s().\-]{0,3}\d){6,}(?!\d)")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


class _Drop(Exception):
	"""The value cannot be masked safely."""


def mask_pii(value, extra_fields=()):
	"""A masked copy of ``value``. Returns ``None`` if the whole value cannot be masked.

	``extra_fields`` are more field names whose whole value is personal data.
	"""
	try:
		extra = frozenset(_field(f) for f in extra_fields)
		names: set[str] = set()
		_collect_names(value, names, 0)
		return _Masker(extra, names).mask(value, None, 0)
	except Exception:  # noqa: BLE001 - fail closed
		return None


def _field(key) -> str:
	return _CAMEL.sub("_", str(key)).strip().lower().replace("-", "_").replace(" ", "_")


def _kind(field: str | None) -> str | None:
	if field is None:
		return None
	if field in PHONE_FIELDS or field.endswith(("_phone", "_mobile", "_phone_number", "_mobile_no")):
		return PHONE_MASK
	if field in EMAIL_FIELDS or field.endswith(("_email", "_email_id")):
		return EMAIL_MASK
	if field in NAME_FIELDS:
		return NAME_MASK
	return None


def _is_hash_id(value) -> bool:
	return isinstance(value, str) and re.fullmatch(_HASH_ID, value) is not None


def _embedded_json(text: str):
	"""The dict or list written as JSON in ``text``, else ``None``."""
	if not text.lstrip().startswith(("{", "[")):
		return None
	try:
		parsed = json.loads(text)
	except ValueError:
		return None
	return parsed if isinstance(parsed, dict | list) else None


def _collect_names(value, names: set, depth: int, is_name: bool = False) -> None:
	if depth > MAX_DEPTH:
		return
	if isinstance(value, dict):
		for key, item in value.items():
			_collect_names(item, names, depth + 1, is_name or _kind(_field(key)) == NAME_MASK)
	elif isinstance(value, list | tuple):
		for item in value:
			_collect_names(item, names, depth + 1, is_name)
	elif isinstance(value, str):
		parsed = _embedded_json(value)
		if parsed is not None:
			_collect_names(parsed, names, depth + 1, is_name)
		elif is_name and not _is_hash_id(value) and value != NAME_MASK:
			parts = [value.strip(), *value.split()]
			names.update(p for p in parts if len(p) >= MIN_NAME_PART and any(c.isalpha() for c in p))


class _Masker:
	def __init__(self, extra: frozenset, names: set):
		self.extra = extra
		ordered = sorted(names, key=len, reverse=True)
		self.names = (
			re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, ordered)) + r")(?!\w)", re.I)
			if ordered
			else None
		)

	def mask(self, value, field: str | None, depth: int):
		if depth > MAX_DEPTH:
			raise _Drop
		if value is None or isinstance(value, bool) or _is_hash_id(value):
			return value
		if field in self.extra:
			return "[redacted]" if value != "" else value
		kind = _kind(field)
		if kind:
			return self._sensitive(value, kind)
		if isinstance(value, dict):
			return self._mapping(value, depth)
		if isinstance(value, list | tuple):
			return self._items(value, field, depth)
		if isinstance(value, str):
			return self._string(value, field, depth)
		if isinstance(value, int):
			is_number = (field in ID_KEYS) or 10 <= len(str(abs(value))) <= 15
			return mask_phone(value) if is_number else value
		if isinstance(value, float | Decimal | datetime.date | datetime.time | datetime.timedelta):
			return value
		raise _Drop

	def _sensitive(self, value, kind: str):
		if value == "":
			return value
		if kind == PHONE_MASK and isinstance(value, str | int):
			return mask_phone(value) or PHONE_MASK
		return kind

	def _mapping(self, value: dict, depth: int) -> dict:
		if "nodes" in value:
			value = drop_webhook_secrets(value)
		out = {}
		for key, item in value.items():
			try:
				masked = self.mask(item, _field(key), depth + 1)
				new_key = self._text(key) if isinstance(key, str) else self.mask(key, None, depth + 1)
			except Exception:  # noqa: BLE001, S112 - fail closed
				continue
			base, n = new_key, 2
			while new_key in out:
				new_key, n = f"{base}#{n}", n + 1
			out[new_key] = masked
		return out

	def _items(self, value, field: str | None, depth: int) -> list:
		out = []
		for item in value:
			try:
				out.append(self.mask(item, field, depth + 1))
			except Exception:  # noqa: BLE001, S112 - fail closed
				continue
		return out

	def _string(self, value: str, field: str | None, depth: int) -> str:
		parsed = _embedded_json(value)
		if parsed is not None:
			return json.dumps(self.mask(parsed, field, depth + 1), default=str, ensure_ascii=False)
		if field in ID_KEYS and re.fullmatch(r"\+?[\d\s().\-]+", value):
			return mask_phone(value)
		return self._text(value)

	def _text(self, text: str) -> str:
		text = _EMAIL.sub(EMAIL_MASK, text)
		parts = _PROTECTED.split(text)
		# Odd positions are the protected ids and dates.
		for i in range(0, len(parts), 2):
			if self.names:
				parts[i] = self.names.sub(NAME_MASK, parts[i])
			parts[i] = _PHONE.sub(lambda m: mask_phone(m.group(0)), parts[i])
		return "".join(parts)
