# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Agent-emitted Telegram media: a ``telegram-media`` fenced block attached to the normal reply.

Agent format (anywhere in the reply; it is stripped from the visible text)::

	```telegram-media
	{"items": [{"type": "photo", "source": "file_url", "value": "/private/files/a.png",
	            "caption": "Chart", "has_spoiler": false},
	           {"type": "location", "source": "text", "latitude": 52.5, "longitude": 13.4}]}
	```

Types: photo, video, animation, audio, voice, document, sticker, video_note (file types) and
location, contact, venue, poll, dice (``source: "text"``, fields at item level or in ``value``).
Sources: ``file_url`` (a Frappe File, permission-checked as the gateway execution user), ``file_id``
(Telegram), ``url`` (public http(s), SSRF-guarded). Limits: 10 items, captions 1024, upload <= 50MB
(photo 10MB). 2-10 consecutive photo/video items (or audio-only / document-only runs) go out as an
album via sendMediaGroup. Media is sent BEFORE the text; a media failure never loses the text (the
caller appends a short note instead).

Pure helpers are Frappe-free; ``cache``, ``resolve_file`` and ``check_url`` are injectable.
"""

from __future__ import annotations

import hashlib
import json
import re
from types import SimpleNamespace
from typing import Any, Callable

FENCE = "telegram-media"
_FENCE_RE = re.compile(r"```[ \t]*" + FENCE + r"[ \t]*\r?\n(.*?)(?:\r?\n)?```", re.DOTALL)
MAX_ITEMS = 10
MAX_CAPTION = 1024
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_PHOTO_BYTES = 10 * 1024 * 1024
TTL_SECONDS = 24 * 3600
MEDIA_ONLY_PREFIX = "⁣tg-media:"  # placeholder part when the reply had media but no text
FILE_TYPES = ("photo", "video", "animation", "audio", "voice", "document", "sticker", "video_note")
TEXT_TYPES = ("location", "contact", "venue", "poll", "dice")
SOURCES = ("file_url", "file_id", "url", "text")
_ALBUM_TYPES = ("photo", "video")
_DICE_EMOJI = ("🎲", "🎯", "🏀", "⚽", "🎳", "🎰")
_EXTRA_KEYS = (
	"title",
	"performer",
	"duration",
	"width",
	"height",
	"length",
	"filename",
	"supports_streaming",
)

AGENT_INSTRUCTIONS = (
	"To send media with your reply add a fenced block ```telegram-media with JSON "
	'{"items": [{"type": "photo|video|animation|audio|voice|document|sticker|video_note", '
	'"source": "file_url|file_id|url", "value": "...", "caption": "", "has_spoiler": false}, '
	'{"type": "location|contact|venue|poll|dice", "source": "text", ...fields}]}. '
	"Max 10 items; media goes out before your text."
)


def _num(value: Any) -> float | None:
	try:
		return float(value)
	except (TypeError, ValueError):
		return None


def _int(value: Any) -> int | None:
	try:
		return int(value)
	except (TypeError, ValueError):
		return None


def _fields(raw: dict) -> dict:
	"""Fields of a text-source item: ``value`` dict merged under top-level keys."""
	out = dict(raw["value"]) if isinstance(raw.get("value"), dict) else {}
	out.update({k: v for k, v in raw.items() if k not in ("value", "type", "source")})
	return out


def _text_item(kind: str, raw: dict, errors: list[str]) -> dict | None:
	f = _fields(raw)
	item: dict[str, Any] = {"type": kind, "source": "text"}
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
		elif _int(f.get("live_period")):
			item["live_period"] = _int(f["live_period"])
	elif kind == "contact":
		phone, first = str(f.get("phone_number") or "").strip(), str(f.get("first_name") or "").strip()
		if not phone or not first:
			errors.append("contact: needs phone_number and first_name")
			return None
		item.update(phone_number=phone[:64], first_name=first[:64])
		if f.get("last_name"):
			item["last_name"] = str(f["last_name"])[:64]
	elif kind == "poll":
		question = str(f.get("question") or "").strip()
		opts = [str(o.get("text") if isinstance(o, dict) else o).strip() for o in (f.get("options") or [])]
		opts = [o[:100] for o in opts if o][:12]
		if not question or len(opts) < 2:
			errors.append("poll: needs a question and 2-12 options")
			return None
		item.update(
			question=question[:300], options=opts, is_anonymous=f.get("is_anonymous", True) is not False
		)
		if f.get("poll_type") == "quiz" or f.get("quiz"):
			cid = _int(f.get("correct_option_id"))
			if cid is None or not 0 <= cid < len(opts):
				errors.append("poll: quiz needs a valid correct_option_id")
				return None
			item.update(poll_type="quiz", correct_option_id=cid)
			if f.get("explanation"):
				item["explanation"] = str(f["explanation"])[:200]
		elif f.get("allows_multiple_answers"):
			item["allows_multiple_answers"] = True
	elif kind == "dice":
		emoji = str(f.get("emoji") or "🎲")
		item["emoji"] = emoji if emoji in _DICE_EMOJI else "🎲"
	return item


def _file_item(kind: str, source: str, raw: dict, errors: list[str]) -> dict | None:
	value = raw.get("value")
	if not isinstance(value, str) or not value.strip():
		errors.append(f"{kind}: missing value")
		return None
	item: dict[str, Any] = {"type": kind, "source": source, "value": value.strip()}
	caption = str(raw.get("caption") or "")
	if len(caption) > MAX_CAPTION:
		errors.append(f"{kind}: caption cut to {MAX_CAPTION} chars")
		caption = caption[:MAX_CAPTION]
	if caption and kind not in ("sticker", "video_note"):
		item["caption"] = caption
	if raw.get("has_spoiler") and kind in ("photo", "video", "animation"):
		item["has_spoiler"] = True
	for key in _EXTRA_KEYS:
		if raw.get(key) not in (None, ""):
			item[key] = raw[key]
	return item


def validate(raw: Any) -> tuple[list[dict], list[str]]:
	"""Validate a JSON string / dict / list into normalised items. Never raises."""
	errors: list[str] = []
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except ValueError:
			return [], ["invalid JSON"]
	if isinstance(raw, dict):
		raw = raw.get("items")
	if not isinstance(raw, list) or not raw:
		return [], ["spec needs a non-empty items list"]
	if len(raw) > MAX_ITEMS:
		errors.append(f"too many items; only the first {MAX_ITEMS} are sent")
	items = []
	for entry in raw[:MAX_ITEMS]:
		if not isinstance(entry, dict):
			errors.append("item must be an object")
			continue
		kind, source = str(entry.get("type") or "").lower(), str(entry.get("source") or "").lower()
		if kind == "gif":
			kind = "animation"
		if kind in TEXT_TYPES:
			item = _text_item(kind, entry, errors)
		elif kind in FILE_TYPES and source in ("file_url", "file_id", "url"):
			item = _file_item(kind, source, entry, errors)
		else:
			errors.append(f"unsupported item type/source: {kind or '?'}/{source or '?'}")
			continue
		if item:
			items.append(item)
	return items, errors


def extract(text: str) -> tuple[str, list[dict], list[str]]:
	"""Return ``(visible_text, items, errors)``; every fenced block is stripped, the last one wins."""
	text = str(text or "")
	blocks = _FENCE_RE.findall(text)
	if not blocks:
		return text, [], []
	visible = re.sub(r"\n{3,}", "\n\n", _FENCE_RE.sub("", text)).strip()
	items, errors = validate(blocks[-1])
	return visible, items, errors


# -- remembering the items between make_parts and send_parts ------------------------------------


class _LocalCache:
	def __init__(self) -> None:
		self.d: dict = {}

	def set_value(self, key, value, expires_in_sec=None):
		self.d[key] = value

	def get_value(self, key):
		return self.d.get(key)

	def delete_value(self, key):
		self.d.pop(key, None)


_LOCAL = _LocalCache()


def _cache(cache: Any = None) -> Any:
	if cache is not None:
		return cache
	try:
		import frappe

		return frappe.cache()
	except Exception:
		return _LOCAL


def scope_key(gateway_name: Any, chat_id: Any, event_name: Any) -> str:
	"""Cache scope for one reply: (gateway, chat, inbound event). Empty = unscoped (tests/legacy only)."""
	if not (gateway_name or chat_id or event_name):
		return ""
	return f"{gateway_name}|{chat_id}|{event_name}"


def _key(part: str, scope: str = "") -> str:
	return "huf_tg_media:" + hashlib.sha1(f"{scope}\x00{part}".encode("utf-8")).hexdigest()


def is_media_only(part: str) -> bool:
	return str(part).startswith(MEDIA_ONLY_PREFIX)


def strip_reply(response: str) -> tuple[str, list[dict]]:
	"""Strip the media block from ``response``; returns ``(visible_text, items)`` (items [] = none)."""
	if not _FENCE_RE.search(str(response or "")):
		return str(response or ""), []
	visible, items, _errors = extract(response)
	return visible, items


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


def prepare_reply(response: str, *, cache: Any = None, scope: str = "") -> str:
	"""``strip_reply`` + ``remember`` in one call (use when there is no other block to strip)."""
	visible, items = strip_reply(response)
	return remember(visible, items, cache=cache, scope=scope)


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


def _albums(items: list[dict]) -> list[list[dict]]:
	"""Group consecutive compatible file items (photo+video, audio only, document only) into albums."""
	groups: list[list[dict]] = []
	for it in items:
		kind = it["type"]
		cat = "pv" if kind in _ALBUM_TYPES else kind if kind in ("audio", "document") else None
		if (
			cat
			and it["source"] != "text"
			and groups
			and groups[-1][0].get("_cat") == cat
			and len(groups[-1]) < 10
		):
			groups[-1].append(it)
		else:
			groups.append([it])
			it["_cat"] = cat
	return groups


def _send_one(sender: Any, chat_id: Any, item: dict, media: Any, thread_id: Any, reply_to: Any) -> list:
	kind = item["type"]
	if kind == "location":
		extra = {"live_period": item["live_period"]} if item.get("live_period") else None
		payload = sender._common(chat_id, reply_to=reply_to, thread_id=thread_id)
		payload.update(latitude=item["latitude"], longitude=item["longitude"], **(extra or {}))
		return _ids(sender.client.call("sendLocation", payload))
	if kind == "venue":
		payload = sender._common(chat_id, reply_to=reply_to, thread_id=thread_id)
		payload.update({k: item[k] for k in ("latitude", "longitude", "title", "address")})
		return _ids(sender.client.call("sendVenue", payload))
	if kind == "contact":
		return _ids(
			sender.send_contact(
				chat_id,
				item["phone_number"],
				item["first_name"],
				last_name=item.get("last_name", ""),
				reply_to=reply_to,
				thread_id=thread_id,
			)
		)
	if kind == "poll":
		payload = sender._common(chat_id, reply_to=reply_to, thread_id=thread_id)
		payload.update(
			question=item["question"],
			options=[{"text": o} for o in item["options"]],
			is_anonymous=item["is_anonymous"],
		)
		if item.get("poll_type") == "quiz":
			payload.update(type="quiz", correct_option_id=item["correct_option_id"])
			if item.get("explanation"):
				payload["explanation"] = item["explanation"]
		elif item.get("allows_multiple_answers"):
			payload["allows_multiple_answers"] = True
		return _ids(sender.client.call("sendPoll", payload))
	if kind == "dice":
		payload = sender._common(chat_id, reply_to=reply_to, thread_id=thread_id)
		payload["emoji"] = item["emoji"]
		return _ids(sender.client.call("sendDice", payload))
	extra = {
		k: item[k]
		for k in ("title", "performer", "duration", "width", "height", "length", "supports_streaming")
		if k in item
	}
	if item.get("has_spoiler"):
		extra["has_spoiler"] = True
	return _ids(
		sender.send_media(
			kind,
			chat_id,
			media,
			caption=item.get("caption", ""),
			reply_to=reply_to,
			thread_id=thread_id,
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
	return f"(Could not send {len(errors)} attachment{'s' if len(errors) != 1 else ''}: {errors[0]})"
