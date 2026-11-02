# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Agent-emitted Telegram media: a ``telegram-media`` fenced block attached to the normal reply.

Agent format (anywhere in the reply; the whole block is stripped from the visible text)::

	```telegram-media
	{"items": [{"type": "photo", "media": "https://example.com/a.png", "caption": "Chart",
	            "has_spoiler": true},
	           {"type": "location", "latitude": 52.5, "longitude": 13.4}]}
	```

The canonical shapes are Telegram's Bot API field names; ``validate`` normalises every accepted spelling
into ONE internal item form in ONE place (nothing is dropped silently: every problem is returned as an
error string and surfaced by ``telegram_pipeline.make_parts``).

Accepted shapes: ``{"items": [...]}``, a bare list, ``{"media": [...]}`` (sendMediaGroup) or ONE top-level
item. Item types: photo, video, animation, audio, voice, document, sticker, video_note (file types; aliases
image/picture -> photo, gif -> animation, videonote -> video_note, file -> document) and location, contact,
venue, poll, quiz (a poll), dice. File location: ``media`` / ``value`` (a string), or ``url`` / ``file_id`` /
``file_url`` or a field named like the type (``"photo": "..."``); ``source`` (file_url | file_id | url) is
inferred when missing: http(s) -> url, ``/files/...`` or ``/private/files/...`` -> file_url, a long bare
token -> file_id; anything else is an error. Text-type fields sit at item level or inside ``value``.
Per item options: ``disable_notification`` (silent), ``protect_content`` (protect), ``reply_to_message_id``
(reply_to), ``message_thread_id`` (thread_id), ``message_effect_id`` (effect), and for photo/video/animation
``has_spoiler`` and ``show_caption_above_media``.

Limits: 10 items, upload <= 50MB (photo 10MB), poll question 300 / option 100 / 12 options. A caption over
1024 is not cut here: the sender sends the overflow as a follow-up text. 2-10 consecutive plain photo/video
items (or audio-only / document-only runs) go out as an album via sendMediaGroup; an item with its own
options (spoiler, caption above, silent, ...) or a caption over 1024 is sent on its own so nothing is lost.
Media is sent BEFORE the text; a media failure never loses the text (the caller appends a short note).

Pure helpers are Frappe-free; ``cache``, ``resolve_file`` and ``check_url`` are injectable.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from types import SimpleNamespace
from typing import Any, Callable

from huf.ai.gateway_adapters import telegram_blocks as blocks

FENCE = blocks.MEDIA
MAX_ITEMS = 10
MAX_CAPTION = 1024
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_PHOTO_BYTES = 10 * 1024 * 1024
MAX_POLL_OPTIONS = 12
MAX_QUESTION = 300
MAX_OPTION = 100
MAX_EXPLANATION = 200
TTL_SECONDS = 24 * 3600
MEDIA_ONLY_PREFIX = "⁣tg-media:"  # placeholder part when the reply had media but no text
FILE_TYPES = ("photo", "video", "animation", "audio", "voice", "document", "sticker", "video_note")
TEXT_TYPES = ("location", "contact", "venue", "poll", "dice")
SOURCES = ("file_url", "file_id", "url", "text")
TYPE_ALIASES = {
	"image": "photo",
	"img": "photo",
	"picture": "photo",
	"gif": "animation",
	"videonote": "video_note",
	"round_video": "video_note",
	"file": "document",
	"quiz": "poll",
	"live_location": "location",
}
_ALBUM_TYPES = ("photo", "video")
_DICE_EMOJI = ("🎲", "🎯", "🏀", "⚽", "🎳", "🎰")
_DICE_NAMES = {
	"dice": "🎲",
	"dart": "🎯",
	"darts": "🎯",
	"basketball": "🏀",
	"football": "⚽",
	"soccer": "⚽",
	"bowling": "🎳",
	"slot": "🎰",
	"slots": "🎰",
	"slot_machine": "🎰",
}
_EXTRA_KEYS = ("title", "performer", "duration", "width", "height", "length", "supports_streaming")
# item-level option spellings -> internal name (one table; the sender kwargs use the internal names)
OPTION_ALIASES = {
	"disable_notification": "silent",
	"silent": "silent",
	"protect_content": "protect",
	"protect": "protect",
	"reply_to_message_id": "reply_to",
	"reply_to": "reply_to",
	"message_thread_id": "thread_id",
	"thread_id": "thread_id",
	"message_effect_id": "effect_id",
	"effect_id": "effect_id",
	"effect": "effect_id",
}
FILE_LOCATORS = ("media", "value", "url", "file_id", "file_url", *FILE_TYPES)
FILE_KEYS = (
	"type",
	"source",
	*FILE_LOCATORS,
	"caption",
	"has_spoiler",
	"show_caption_above_media",
	"filename",
	*_EXTRA_KEYS,
	*OPTION_ALIASES,
)
POLL_KEYS = (
	"question",
	"options",
	"is_anonymous",
	"allows_multiple_answers",
	"quiz",
	"poll_type",
	"correct_option_id",
	"correct_option_ids",
	"explanation",
	"open_period",
)
TEXT_KEYS = {
	"location": ("latitude", "longitude", "live_period"),
	"venue": ("latitude", "longitude", "title", "address"),
	"contact": ("phone_number", "first_name", "last_name", "vcard"),
	"poll": POLL_KEYS,
	"dice": ("emoji",),
}
ACCEPTED_KEYS = frozenset(
	{
		"items",
		"value",
		"type",
		*FILE_KEYS,
		*(k for keys in TEXT_KEYS.values() for k in keys),
		*TYPE_ALIASES,
		*FILE_TYPES,
		*TEXT_TYPES,
	}
)
_FILE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{20,}$")


def _num(value: Any) -> float | None:
	try:
		return float(value)
	except (TypeError, ValueError):
		return None


def _int(value: Any) -> int | None:
	if isinstance(value, bool):
		return None
	try:
		return int(value)
	except (TypeError, ValueError):
		return None


# -- validation: one normaliser ------------------------------------------------------------------


def _kind(raw: dict) -> str:
	kind = str(raw.get("type") or "").strip().lower().replace("-", "_").replace(" ", "_")
	return TYPE_ALIASES.get(kind, kind)


def _fields(raw: dict) -> dict:
	"""Fields of a text-source item: ``value`` dict merged under top-level keys."""
	out = dict(raw["value"]) if isinstance(raw.get("value"), dict) else {}
	out.update({k: v for k, v in raw.items() if k not in ("value", "type", "source")})
	return out


def _options(raw: dict, label: str, errors: list[str]) -> dict:
	"""Per-item send options (silent, protect, reply_to, thread_id, effect_id), validated."""
	out: dict[str, Any] = {}
	for key, name in OPTION_ALIASES.items():
		if raw.get(key) in (None, ""):
			continue
		value = raw[key]
		if name in ("silent", "protect"):
			if blocks.parse_bool(value, f"{label} {key}", errors):
				out[name] = True
		elif name == "effect_id":
			out[name] = str(value)[:64]
		else:
			number = _int(value)
			if number is None:
				errors.append(f"{label}: {key} must be a number")
			else:
				out[name] = number
	return out


def _text_item(kind: str, raw: dict, errors: list[str], quiz: bool = False) -> dict | None:
	f = _fields(raw)
	blocks.unknown_keys(f, ACCEPTED_KEYS, kind, errors)
	item: dict[str, Any] = {"type": kind, "source": "text", **_options(f, kind, errors)}
	if kind in ("location", "venue"):
		lat, lng = _num(f.get("latitude")), _num(f.get("longitude"))
		if lat is None or lng is None or not -90 <= lat <= 90 or not -180 <= lng <= 180:
			errors.append(f"{kind}: needs valid latitude and longitude")
			return None
		item.update(latitude=lat, longitude=lng)
		if kind == "venue":
			title, address = str(f.get("title") or "").strip(), str(f.get("address") or "").strip()
			if not title or not address:
				errors.append("venue: needs title and address")
				return None
			item.update(title=title[:256], address=address[:256])
		elif f.get("live_period") not in (None, ""):
			period = _int(f["live_period"])
			if period is None or not 60 <= period <= 86400:
				errors.append("location: live_period ignored (60-86400 seconds)")
			else:
				item["live_period"] = period
	elif kind == "contact":
		phone, first = str(f.get("phone_number") or "").strip(), str(f.get("first_name") or "").strip()
		if not phone or not first:
			errors.append("contact: needs phone_number and first_name")
			return None
		item.update(phone_number=phone[:64], first_name=first[:64])
		if f.get("last_name"):
			item["last_name"] = str(f["last_name"])[:64]
		if f.get("vcard"):
			item["vcard"] = str(f["vcard"])[:2048]
	elif kind == "poll":
		return _poll(item, f, errors, quiz)
	elif kind == "dice":
		emoji = str(f.get("emoji") or "🎲").replace("️", "").strip()
		emoji = _DICE_NAMES.get(emoji.lower(), emoji)
		if emoji not in _DICE_EMOJI:
			errors.append(f"dice: emoji must be one of {' '.join(_DICE_EMOJI)}")
			return None
		item["emoji"] = emoji
	return item


def _poll(item: dict, f: dict, errors: list[str], quiz: bool) -> dict | None:
	question = str(f.get("question") or "").strip()
	raw_opts = f.get("options") if isinstance(f.get("options"), list) else []
	opts = [str(o.get("text") if isinstance(o, dict) else o).strip() for o in raw_opts]
	opts = [o for o in opts if o]
	if not question or len(opts) < 2:
		errors.append("poll: needs a question and 2-12 options")
		return None
	if len(opts) > MAX_POLL_OPTIONS:
		errors.append(f"poll: {len(opts)} options; Telegram allows {MAX_POLL_OPTIONS}, the rest were dropped")
		opts = opts[:MAX_POLL_OPTIONS]
	if len(question) > MAX_QUESTION:
		errors.append(f"poll: question cut to {MAX_QUESTION} characters")
	if any(len(o) > MAX_OPTION for o in opts):
		errors.append(f"poll: options cut to {MAX_OPTION} characters")
	item.update(
		question=question[:MAX_QUESTION],
		options=[o[:MAX_OPTION] for o in opts],
		is_anonymous=blocks.parse_bool(f.get("is_anonymous"), "poll is_anonymous", errors, default=True),
	)
	if blocks.parse_bool(f.get("allows_multiple_answers"), "poll allows_multiple_answers", errors):
		item["allows_multiple_answers"] = True
	quiz = (
		quiz
		or "quiz" in (str(f.get("poll_type") or "").lower(), str(f.get("type") or "").lower())
		or blocks.parse_bool(f.get("quiz"), "poll quiz", errors)
	)
	if f.get("open_period") not in (None, ""):
		period = _int(f["open_period"])
		if period is None or not 5 <= period <= 600:
			errors.append("poll: open_period ignored (5-600 seconds)")
		else:
			item["open_period"] = period
	if quiz:
		ids = f.get("correct_option_ids")
		ids = ids if isinstance(ids, list) else [f.get("correct_option_id")]
		ids = [_int(i) for i in ids if i not in (None, "")]
		if not ids or any(i is None or not 0 <= i < len(item["options"]) for i in ids):
			errors.append("poll: a quiz needs correct_option_id (an index into options, starting at 0)")
			return None
		item.update(quiz=True, correct_option_ids=ids)
		if f.get("explanation"):
			explanation = str(f["explanation"])
			if len(explanation) > MAX_EXPLANATION:
				errors.append(f"poll: explanation cut to {MAX_EXPLANATION} characters")
			item["explanation"] = explanation[:MAX_EXPLANATION]
	return item


def _locate(raw: dict, kind: str, errors: list[str]) -> tuple[str, str] | None:
	"""``(source, value)`` for a file item from any accepted spelling, or ``None`` (error added)."""
	found: list[tuple[str, str]] = []
	for key in FILE_LOCATORS:
		if key in FILE_TYPES and key != kind:
			continue
		value = raw.get(key)
		if isinstance(value, dict):  # {"media": {"url": ...}} / {"photo": {"file_id": ...}}
			value = value.get("file_id") or value.get("url") or value.get("file_url") or value.get("value")
		if isinstance(value, str) and value.strip():
			found.append((key, value.strip()))
	if not found:
		errors.append(f"{kind}: missing media (https url, Telegram file_id or Frappe file_url)")
		return None
	if len({v for _k, v in found}) > 1:
		errors.append(f"{kind}: give the media once (found {', '.join(k for k, _v in found)})")
		return None
	key, value = found[0]
	source = str(raw.get("source") or "").strip().lower()
	if key in ("url", "file_id", "file_url"):
		source = source or key
	if source and source not in SOURCES[:3]:
		errors.append(f"{kind}: unsupported source {source!r}")
		return None
	if not source:
		low = value.lower()
		if low.startswith(("http://", "https://")):
			source = "url"
		elif value.startswith("/"):
			source = "file_url"
		elif _FILE_ID_RE.match(value):
			source = "file_id"
		else:
			errors.append(
				f"{kind}: cannot tell whether {value[:30]!r} is a url, file_id or file_url; add source"
			)
			return None
	if source == "url" and not value.lower().startswith(("http://", "https://")):
		errors.append(f"{kind}: a url source must start with http:// or https://")
		return None
	return source, value


def _file_item(kind: str, raw: dict, errors: list[str]) -> dict | None:
	blocks.unknown_keys(raw, ACCEPTED_KEYS, kind, errors)
	located = _locate(raw, kind, errors)
	if not located:
		return None
	source, value = located
	item: dict[str, Any] = {"type": kind, "source": source, "value": value, **_options(raw, kind, errors)}
	caption = str(raw.get("caption") or "")
	if caption:
		if kind in ("sticker", "video_note"):
			errors.append(f"{kind}: captions are not supported; ignored")
		else:
			item["caption"] = caption  # >1024 is fine: the sender sends the overflow as follow-up text
	for flag in ("has_spoiler", "show_caption_above_media"):
		if blocks.parse_bool(raw.get(flag), f"{kind} {flag}", errors):
			if kind in ("photo", "video", "animation"):
				item[flag] = True
			else:
				errors.append(f"{kind}: {flag} is not supported; ignored")
	for key in _EXTRA_KEYS:
		if raw.get(key) in (None, ""):
			continue
		if key in ("title", "performer"):
			item[key] = str(raw[key])[:256]
		elif key == "supports_streaming":
			if blocks.parse_bool(raw[key], f"{kind} {key}", errors):
				item[key] = True
		elif _int(raw[key]) is None:
			errors.append(f"{kind}: {key} must be a number; ignored")
		else:
			item[key] = _int(raw[key])
	if raw.get("filename"):
		name = os.path.basename(str(raw["filename"]).replace("\\", "/"))[:100]
		if name:
			item["filename"] = name
	return item


def _item(entry: Any, errors: list[str]) -> dict | None:
	if not isinstance(entry, dict):
		errors.append("item must be an object")
		return None
	kind = _kind(entry)
	if not kind:  # type-less item: infer from a field named like the type
		named = [k for k in FILE_TYPES if isinstance(entry.get(k), (str, dict))]
		if len(named) != 1:
			errors.append("item needs a type")
			return None
		kind = named[0]
	quiz = str(entry.get("type") or "").strip().lower() == "quiz"
	if kind in TEXT_TYPES:
		return _text_item(kind, entry, errors, quiz)
	if kind in FILE_TYPES:
		return _file_item(kind, entry, errors)
	errors.append(f"unsupported item type: {str(entry.get('type'))[:30]}")
	return None


def _entries(raw: Any, errors: list[str]) -> list:
	if isinstance(raw, dict):
		if isinstance(raw.get("items"), list):
			return raw["items"]
		if isinstance(raw.get("media"), list):
			return raw["media"]
		if raw.get("type") or any(isinstance(raw.get(k), (str, dict)) for k in FILE_TYPES):
			return [raw]  # a single top-level item
		return []
	return raw if isinstance(raw, list) else []


def validate(raw: Any) -> tuple[list[dict], list[str]]:
	"""Validate a JSON string / dict / list into normalised items ``(items, errors)``. Never raises.

	``errors`` also carries non-fatal notes (an ignored field, a dropped item)."""
	errors: list[str] = []
	if isinstance(raw, str):
		raw, err = blocks.loads(raw)
		if err:
			return [], [err]
	entries = _entries(raw, errors)
	if not entries:
		return [], ["spec needs a non-empty items list"]
	if len(entries) > MAX_ITEMS:
		errors.append(
			f"{len(entries)} items; Telegram albums and this block allow {MAX_ITEMS}, the rest were dropped"
		)
	items = [i for i in (_item(e, errors) for e in entries[:MAX_ITEMS]) if i]
	return items, errors


def parse(bodies: list[str]) -> tuple[list[dict], list[str]]:
	"""Validate the bodies of every ``telegram-media`` block of one reply; their items are concatenated."""
	items: list[dict] = []
	errors: list[str] = []
	for body in bodies:
		got, errs = validate(body)
		items.extend(got)
		errors.extend(errs)
	if len(items) > MAX_ITEMS:
		errors.append(f"{len(items)} items in all; only the first {MAX_ITEMS} are sent")
		items = items[:MAX_ITEMS]
	return items, errors


def extract(text: str) -> tuple[str, list[dict], list[str]]:
	"""Return ``(visible_text, items, errors)``; every live block is stripped, several blocks are merged."""
	visible, found = blocks.scan(text)
	items, errors = parse(found.get(FENCE, []))
	return visible, items, errors


# -- remembering the items between make_parts and send_parts ------------------------------------


def _cache(cache: Any = None) -> Any:
	return blocks.get_cache(cache)


def _key(part: str, scope: str = "") -> str:
	return "huf_tg_media:" + hashlib.sha1(f"{scope}\x00{part}".encode("utf-8")).hexdigest()


def is_media_only(part: str) -> bool:
	return str(part).startswith(MEDIA_ONLY_PREFIX)


def remember(visible: str, items: list[dict], *, cache: Any = None, scope: str = "") -> str:
	"""Remember ``items`` under the first part of the FINAL visible text; returns the text to split.

	A unique placeholder part is returned when the reply has media but no text (``send_parts`` skips
	it, so no text message goes out).
	"""
	if not items:
		return visible
	if not visible:
		visible = (
			MEDIA_ONLY_PREFIX + hashlib.sha1(json.dumps(items, sort_keys=True).encode()).hexdigest()[:10]
		)
	try:
		from huf.ai.gateway_adapters.telegram_format import split_message

		first = (split_message(visible) or [visible])[0]
		_cache(cache).set_value(_key(first, scope), items, expires_in_sec=TTL_SECONDS)
	except Exception:
		pass
	return visible


def take_items(parts: list[str], *, cache: Any = None, scope: str = "") -> list[dict]:
	"""Pop the remembered items for these parts (once: a retry never re-sends the media)."""
	try:
		c = _cache(cache)
		for part in parts:
			items = c.get_value(_key(part, scope))
			if isinstance(items, list):
				try:
					c.delete_value(_key(part, scope))
				except Exception:
					c.set_value(_key(part, scope), None, expires_in_sec=1)
				return items
	except Exception:
		pass
	return []


# -- resolving + sending -----------------------------------------------------------------------


def _file_allowed_for_chat(doc: Any, chat_id: Any) -> bool:
	"""Agent-emitted media may only name public Files or Files Telegram inbound saved for THIS chat."""
	import frappe

	if not doc.is_private:
		return True
	if chat_id in (None, "") or doc.attached_to_doctype != "Gateway Event" or not doc.attached_to_name:
		return False
	conv = frappe.db.get_value("Gateway Event", doc.attached_to_name, "conversation_id")
	return bool(conv) and str(conv).startswith(str(chat_id))


def default_resolve_file(file_url: str, chat_id: Any = None) -> tuple[str, bytes]:
	"""Read a Frappe File for an agent-emitted media item; raises on missing/forbidden.

	Beyond the execution user's read permission, only public Files and private Files attached to a Gateway
	Event of this chat (Telegram inbound media) are allowed, so a prompt-injected agent cannot exfiltrate
	arbitrary private files (e.g. ``/private/files/...``) the gateway user can read.
	"""
	import frappe

	name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not name:
		raise ValueError("file not found")
	doc = frappe.get_doc("File", name)
	doc.check_permission("read")
	if not _file_allowed_for_chat(doc, chat_id):
		raise ValueError("file not allowed: agents may only send public files or files received in this chat")
	content = doc.get_content()
	if isinstance(content, str):
		content = content.encode("utf-8")
	return doc.file_name or file_url.rsplit("/", 1)[-1], content


def default_check_url(url: str) -> tuple[bool, str]:
	from huf.ai.http_handler import validate_url

	return validate_url(url)


def _resolve(item: dict, resolve_file: Callable, check_url: Callable) -> Any:
	"""Value for the sender: file_id/URL string or ``(name, bytes)``. Raises ``ValueError``."""
	source, value, kind = item["source"], item["value"], item["type"]
	if source == "file_id":
		return value
	if source == "url":
		# Documented: the URL is fetched by Telegram's servers, not Huf; validate_url blocks private targets.
		ok, why = check_url(value)
		if not ok:
			raise ValueError(f"url rejected: {why}")
		return value
	name, content = resolve_file(value)
	limit = MAX_PHOTO_BYTES if kind == "photo" else MAX_UPLOAD_BYTES
	if len(content) > limit:
		raise ValueError(f"file is {len(content)} bytes (limit {limit})")
	return (item.get("filename") or name or "file", content)


def _ids(result: Any) -> list:
	rows = result if isinstance(result, list) else [result]
	return [r.get("message_id") for r in rows if isinstance(r, dict) and r.get("message_id") is not None]


def _ids(result: Any) -> list:
	rows = result if isinstance(result, list) else [result]
	return [r.get("message_id") for r in rows if isinstance(r, dict) and r.get("message_id") is not None]


def _album_ok(item: dict) -> bool:
	"""A plain item can join an album; one with its own options or an over-long caption goes alone."""
	own = (
		"has_spoiler",
		"show_caption_above_media",
		"silent",
		"protect",
		"reply_to",
		"thread_id",
		"effect_id",
	)
	return (
		item["source"] != "text"
		and not any(item.get(k) for k in own)
		and len(item.get("caption", "")) <= MAX_CAPTION
	)


def _albums(items: list[dict]) -> list[list[dict]]:
	"""Group consecutive compatible file items (photo+video, audio only, document only) into albums."""
	groups: list[list[dict]] = []
	cats: list[str | None] = []
	for it in items:
		kind = it["type"]
		cat = (
			("pv" if kind in _ALBUM_TYPES else kind if kind in ("audio", "document") else None)
			if _album_ok(it)
			else None
		)
		if cat and groups and cats[-1] == cat and len(groups[-1]) < 10:
			groups[-1].append(it)
		else:
			groups.append([it])
			cats.append(cat)
	return groups


def _payload(sender: Any, chat_id: Any, item: dict, thread_id: Any, reply_to: Any) -> dict:
	return sender._common(
		chat_id,
		reply_to=item.get("reply_to") or reply_to,
		thread_id=item.get("thread_id") or thread_id,
		silent=bool(item.get("silent")),
		protect=bool(item.get("protect")),
		effect_id=item.get("effect_id"),
	)


def _send_one(sender: Any, chat_id: Any, item: dict, media: Any, thread_id: Any, reply_to: Any) -> list:
	kind = item["type"]
	if kind in TEXT_TYPES:
		payload = _payload(sender, chat_id, item, thread_id, reply_to)
		if kind in ("location", "venue"):
			keys = (
				("latitude", "longitude", "title", "address")
				if kind == "venue"
				else ("latitude", "longitude", "live_period")
			)
			payload.update({k: item[k] for k in keys if k in item})
			return _ids(sender.client.call("sendVenue" if kind == "venue" else "sendLocation", payload))
		if kind == "contact":
			payload.update(
				{k: item[k] for k in ("phone_number", "first_name", "last_name", "vcard") if k in item}
			)
			return _ids(sender.client.call("sendContact", payload))
		if kind == "dice":
			payload["emoji"] = item["emoji"]
			return _ids(sender.client.call("sendDice", payload))
		payload.update(
			question=item["question"],
			options=[{"text": o} for o in item["options"]],
			is_anonymous=item["is_anonymous"],
		)
		if item.get("allows_multiple_answers"):
			payload["allows_multiple_answers"] = True
		if item.get("open_period"):
			payload["open_period"] = item["open_period"]
		if item.get("quiz"):
			ids = item["correct_option_ids"]
			payload["type"] = "quiz"
			payload.update({"correct_option_id": ids[0]} if len(ids) == 1 else {"correct_option_ids": ids})
			if item.get("explanation"):
				payload["explanation"] = item["explanation"]
		return _ids(sender.client.call("sendPoll", payload))
	extra = {
		k: item[k]
		for k in ("title", "performer", "duration", "width", "height", "length", "supports_streaming")
		if k in item
	}
	for flag in ("has_spoiler", "show_caption_above_media"):
		if item.get(flag):
			extra[flag] = True
	if item.get("effect_id"):
		extra["message_effect_id"] = item["effect_id"]
	return _ids(
		sender.send_media(
			kind,
			chat_id,
			media,
			caption=item.get("caption", ""),
			reply_to=item.get("reply_to") or reply_to,
			thread_id=item.get("thread_id") or thread_id,
			silent=bool(item.get("silent")),
			protect=bool(item.get("protect")),
			extra=extra or None,
		)
	)


def send_media_items(
	sender: Any,
	chat_id: Any,
	items: list[dict],
	thread_id: Any = None,
	reply_to: Any = None,
	*,
	resolve_file: Callable | None = None,
	check_url: Callable | None = None,
) -> SimpleNamespace:
	"""Send ``items`` in order. Never raises: returns ``sent_ids`` and human-readable ``errors``."""
	resolve_file = resolve_file or (lambda url: default_resolve_file(url, chat_id))
	check_url = check_url or default_check_url
	sent: list = []
	errors: list[str] = []
	first = True
	for group in _albums([dict(i) for i in items[:MAX_ITEMS]]):
		target = reply_to if first else None
		label = group[0]["type"]
		resolved: list[tuple[dict, Any]] = []
		for it in group:  # one bad item must not sink the rest of the album
			try:
				resolved.append(
					(it, _resolve(it, resolve_file, check_url) if it["source"] != "text" else None)
				)
			except Exception as exc:
				errors.append(f"{it['type']}: {_safe(exc)}")
		try:
			if len(resolved) >= 2:
				entries = [
					{"type": it["type"], "media": m, "caption": it.get("caption", "")} for it, m in resolved
				]
				sent.extend(
					_ids(sender.send_media_group(chat_id, entries, reply_to=target, thread_id=thread_id))
				)
			elif resolved:
				sent.extend(_send_one(sender, chat_id, resolved[0][0], resolved[0][1], thread_id, target))
			first = first and not resolved
		except Exception as exc:
			errors.append(f"{label}: {_safe(exc)}")
	return SimpleNamespace(sent_ids=sent, errors=errors)


def _safe(exc: BaseException) -> str:
	text = " ".join(str(exc).split())
	text = re.sub(r"\d{6,}:[\w-]{20,}", "[token]", text)
	return text[:160] or exc.__class__.__name__


def failure_note(errors: list[str]) -> str:
	"""Short plain-text note appended to the reply when attachments could not be sent."""
	return f"{blocks.NOTE_PREFIX}{len(errors)} attachment{'s' if len(errors) != 1 else ''}: {errors[0]})"
