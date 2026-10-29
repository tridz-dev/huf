"""Plain-language text for data a person has to read (approvals, mail, Slack, messages in a run).

Frappe-free and pure, so it can be unit tested without a site. It mirrors the front-end rules in
``frontend/src/lib/flow/humanize.ts``:

* an object becomes ``Label: value`` rows (internal and secret keys and empty values are dropped);
* a list becomes ``N items`` (with the first names when there are any);
* an ISO date or date-time becomes ``29 Oct 2026, 10:42``;
* ``true`` / ``false`` become ``Yes`` / ``No``;
* ids and Python/JSON syntax never appear: a fact is a label and a value.

The text in a user-facing message is written for the person who reads it (the approver, the customer
who gets the email); the agent prompt is the one place where raw JSON is still fine, because a model
reads it, and that path does not use this module.
"""

from __future__ import annotations

import html
import re
from datetime import date, datetime
from typing import Any, Mapping

MAX_VALUE_CHARS = 120
MAX_INLINE_PAIRS = 3
MAX_FACTS = 4
_MAX_DEPTH = 2

# Keys that are bookkeeping, not facts a person asked about.
INTERNAL_KEYS = frozenset(
	{
		"doctype", "docstatus", "idx", "owner", "creation", "modified", "modified_by", "parent", "parenttype",
		"parentfield", "naming_series", "amended_from", "workflow_state_field", "flow_run", "flow_id",
		"run_id", "node_id", "trigger_type", "event", "gateway_event",
	}
)
_SECRET_KEY = re.compile(r"pass(word|wd)?|secret|token|api[_-]?key|authorization|credential|private[_-]?key|signature", re.I)

ACRONYMS = {
	"id": "ID", "url": "URL", "uri": "URI", "sku": "SKU", "api": "API", "sms": "SMS", "ip": "IP", "pdf": "PDF",
	"gst": "GST", "vat": "VAT", "utm": "UTM", "crm": "CRM", "csv": "CSV", "json": "JSON", "html": "HTML",
	"qr": "QR", "po": "PO", "otp": "OTP", "ui": "UI", "ceo": "CEO", "eta": "ETA",
}

# Keys that say what a record is: the first one present is its short name.
HEADLINE_KEYS = ("name", "full_name", "customer_name", "title", "subject", "label", "display_name", "email")
# Facts a reader looks for first (earlier is better).
PREFERRED_KEYS = (
	"customer", "customer_name", "client", "name", "full_name", "title", "subject", "order", "invoice",
	"amount", "total", "grand_total", "price", "status", "reason", "description", "summary", "email",
	"due_date", "date", "priority",
)
# A key that only means something next to its parent: "customer.name" reads as "Customer".
_NAME_KEYS = frozenset({"name", "title", "full_name", "label", "display_name", "subject"})
_NUMBER_KEYS = {"id": "ID", "number": "number", "no": "number", "code": "code", "ref": "reference", "reference": "reference"}

_ISO = re.compile(
	r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?\s*(Z|[+-]\d{2}:?\d{2})?)?$"
)
_TAG = re.compile(r"<[^>]*>")
_SPACE = re.compile(r"\s+")


# --------------------------------------------------------------------------- labels
def label_for(key: Any, labels: Mapping[str, str] | None = None) -> str:
	"""``customer_name`` -> ``Customer name``; ``orderTotal`` -> ``Order total``; ``order_url`` -> ``Order URL``."""
	text = str(key)
	if labels and text in labels and labels[text]:
		return str(labels[text])
	text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
	words = [w for w in re.split(r"[\s_\-.]+", text) if w]
	if not words:
		return ""
	out = [ACRONYMS.get(w.lower(), w.lower()) for w in words]
	if out[0] == out[0].lower():
		out[0] = out[0][:1].upper() + out[0][1:]
	return " ".join(out)


def is_internal_key(key: Any) -> bool:
	text = str(key)
	return text.startswith("_") or text.lower() in INTERNAL_KEYS or bool(_SECRET_KEY.search(text))


# --------------------------------------------------------------------------- scalars
def format_datetime(value: str) -> str | None:
	"""``2026-10-29T10:42:00Z`` -> ``29 Oct 2026, 10:42 UTC``; a date alone -> ``29 Oct 2026``; None when it is not ISO."""
	m = _ISO.match(value.strip())
	if not m:
		return None
	year, month, day, hour, minute, _second, zone = m.groups()
	try:
		moment = date(int(year), int(month), int(day))
	except ValueError:
		return None
	text = f"{moment.day} {moment.strftime('%b %Y')}"
	if hour is None:
		return text
	if hour == "00" and minute == "00" and zone is None:
		return text  # a date stored as a midnight timestamp
	text += f", {hour}:{minute}"
	if zone in ("Z", "+00:00", "+0000"):
		text += " UTC"
	elif zone:
		text += f" ({zone})"
	return text


def _plain_text(value: str) -> str:
	text = html.unescape(_TAG.sub(" ", value)) if "<" in value else html.unescape(value)
	return _SPACE.sub(" ", text).strip()


def _clip(text: str, limit: int = MAX_VALUE_CHARS) -> str:
	return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def format_scalar(value: Any) -> str | None:
	"""A single value as a person reads it, or None when there is nothing to show."""
	if value is None:
		return None
	if isinstance(value, bool):
		return "Yes" if value else "No"
	if isinstance(value, int):
		return str(value)
	if isinstance(value, float):
		return str(int(value)) if value.is_integer() else f"{value:.2f}".rstrip("0").rstrip(".")
	if isinstance(value, datetime):
		return format_datetime(value.isoformat()) or str(value)
	if isinstance(value, date):
		return format_datetime(value.isoformat()) or str(value)
	text = _plain_text(str(value))
	if not text:
		return None
	return _clip(format_datetime(text) or text)


# --------------------------------------------------------------------------- summaries
def _is_scalar(value: Any) -> bool:
	return not isinstance(value, (Mapping, list, tuple, set))


def headline(record: Mapping[str, Any]) -> str | None:
	"""The short name of a record (``Ada Lovelace``), when it has one."""
	for key in HEADLINE_KEYS:
		if key in record and _is_scalar(record[key]):
			text = format_scalar(record[key])
			if text:
				return text
	return None


def _shown_items(items: Any) -> list:
	return [i for i in items if i is not None and i != "" and i != [] and i != {}]


def _plural(n: int, one: str, many: str) -> str:
	return f"{n} {one if n == 1 else many}"


def _preference(key: Any) -> int:
	"""Where a key sits in the order a reader looks for facts (unknown keys keep their own order, after the known ones)."""
	lowered = str(key).lower()
	return PREFERRED_KEYS.index(lowered) if lowered in PREFERRED_KEYS else len(PREFERRED_KEYS)


def summarize(value: Any, labels: Mapping[str, str] | None = None, _depth: int = 0) -> str | None:
	"""One short line for any value, or None when it is empty.

	``Ada Lovelace`` for a record with a name, ``Total: 450, Status: paid`` for one without, ``3 items: A, B and 1 more``
	for a list, ``Yes`` for true, ``29 Oct 2026`` for a date.
	"""
	if _is_scalar(value):
		return format_scalar(value)
	if isinstance(value, Mapping):
		name = headline(value)
		if name:
			return name
		if _depth >= _MAX_DEPTH:
			return None
		pairs = []
		for key, item in sorted(value.items(), key=lambda kv: _preference(kv[0])):
			if is_internal_key(key):
				continue
			text = summarize(item, labels, _depth + 1)
			if text:
				pairs.append(f"{label_for(key, labels)}: {text}")
			if len(pairs) >= MAX_INLINE_PAIRS:
				break
		return ", ".join(pairs) or None
	items = _shown_items(value)
	if not items:
		return None
	names = [summarize(i, labels, _depth + 1) if not isinstance(i, Mapping) else headline(i) for i in items]
	count = _plural(len(items), "item", "items")
	if any(n is None for n in names[:2]):
		return count
	shown = [_clip(n, 40) for n in names[:2]]
	if len(items) == 1:
		return f"{count}: {shown[0]}"
	if len(items) == 2:
		return f"{count}: {shown[0]} and {shown[1]}"
	return f"{count}: {shown[0]}, {shown[1]} and {len(items) - 2} more"


def humanize_value(value: Any, labels: Mapping[str, str] | None = None) -> str:
	"""Text for a whole value: ``Label: value`` lines for an object, ``N items`` for a list, readable scalars."""
	if isinstance(value, Mapping):
		lines = []
		for key, item in value.items():
			if is_internal_key(key):
				continue
			text = summarize(item, labels, 1)
			if text:
				lines.append(f"{label_for(key, labels)}: {text}")
		return "\n".join(lines)
	return summarize(value, labels) or ""


# --------------------------------------------------------------------------- key facts
def _fact_label(path: tuple, labels: Mapping[str, str] | None) -> str:
	key = str(path[-1])
	parent = str(path[-2]) if len(path) > 1 else None
	if parent is not None and not isinstance(path[-2], int):
		lowered = key.lower()
		if lowered in _NAME_KEYS:
			return label_for(parent, labels)
		if lowered in _NUMBER_KEYS:
			word = _NUMBER_KEYS[lowered]
			base = label_for(parent, labels)
			return f"{base} {word}" if word == "ID" else f"{base} {word}"
	return label_for(key, labels)


def _candidates(obj: Mapping, path: tuple, depth: int, out: list) -> None:
	for key, value in obj.items():
		if is_internal_key(key):
			continue
		here = path + (key,)
		if isinstance(value, Mapping):
			if depth < _MAX_DEPTH:
				_candidates(value, here, depth + 1, out)
			continue
		out.append((here, value, depth))


def key_facts(payload: Any, labels: Mapping[str, str] | None = None, n: int = MAX_FACTS) -> list[dict]:
	"""The few facts that tell a reader what this is about: ``[{"label": "Customer", "value": "Ada Lovelace"}]``.

	Scalars and lists are candidates (lists as ``3 items``); nested objects are read two levels down; internal
	and secret-looking keys and empty values are skipped. Well-known keys (customer, name, amount, total,
	status...) come first, then the rest in the order they appear.
	"""
	if not isinstance(payload, Mapping):
		return []
	found: list = []
	_candidates(payload, (), 0, found)
	ranked = []
	for order, (path, value, depth) in enumerate(found):
		last = str(path[-1]).lower()
		parent = str(path[-2]).lower() if len(path) > 1 else ""
		pref = len(PREFERRED_KEYS) + 1
		for probe in (last, parent if last in _NAME_KEYS or last in _NUMBER_KEYS else ""):
			if probe in PREFERRED_KEYS:
				pref = min(pref, PREFERRED_KEYS.index(probe))
		text = summarize(value, labels)
		if not text:
			continue
		ranked.append((pref, depth, order, _fact_label(path, labels), text))
	ranked.sort()
	facts, seen = [], set()
	for _pref, _depth, _order, label, text in ranked:
		if label.lower() in seen:
			continue
		seen.add(label.lower())
		facts.append({"label": label, "value": text})
		if len(facts) >= n:
			break
	return facts


# --------------------------------------------------------------------------- approval wording
def approval_headline(flow_name: str | None) -> str:
	"""``Approval needed: Refund review`` (never ``Approval Required: Approval Required``)."""
	name = (flow_name or "").strip()
	return f"Approval needed: {name}" if name else "Approval needed"


def _sentence(text: str) -> str:
	text = _SPACE.sub(" ", text or "").strip()
	return text if not text or text[-1] in ".!?:" else text + "."


def facts_sentence(facts: list[dict] | None) -> str:
	"""``Customer: Ada Lovelace, Total: 450.`` or an empty string."""
	parts = [f"{f.get('label')}: {f.get('value')}" for f in (facts or []) if f.get("label") and f.get("value")]
	return _sentence(", ".join(parts)) if parts else ""


def approval_lead(flow_name: str | None, message: str | None) -> str:
	"""The first sentence: what the flow's author wrote, else a plain statement that a decision is needed."""
	text = _sentence(message or "")
	if text:
		return text
	name = (flow_name or "").strip()
	return f"{name} is waiting for your decision." if name else "A flow is waiting for your decision."


def approval_sentence(flow_name: str | None, step_title: str | None, message: str | None, facts: list[dict] | None, ask: bool = False) -> str:
	"""One readable paragraph for a bell, mail or Slack card: the message first, then the key facts.

	``step_title`` is accepted so every channel passes the same arguments; the sentence does not repeat it
	(a person reads the flow name in the headline and the message below it).
	"""
	parts = [approval_lead(flow_name, message), facts_sentence(facts)]
	if ask:
		parts.append("Approve or reject.")
	return " ".join(p for p in parts if p)
