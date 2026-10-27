# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Pure builders and validators for every outbound (non-template) WhatsApp message type.

No ``frappe`` import and no network: each ``build_*_payload`` takes plain values and returns
``(payload, errors)``. ``payload`` is the full Graph ``POST /{phone_id}/messages`` body (or ``None`` when
``errors`` is not empty); ``errors`` is a list of ``{"field", "code", "message"}`` dicts, the same shape the
template validators use (``whatsapp_templates.validation_error`` wraps them for callers).

Source of every shape/limit (Meta docs fetched 2026-10-21 from
https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/ and
.../business-phone-numbers/media). ``verified`` = stated on the page; ``unverified`` = from memory, third
party material or a Huf-chosen safety cap (the page is silent). The table is also in the T5 report.

verified   image/video/audio/document/sticker: ``{id | link}`` (one of); image caption <= 1024; document caption <= 1024
           and ``filename`` (no length given); audio ``voice: true`` = voice note (Ogg/Opus mono only); sticker is
           webp, static <= 100 KB, animated <= 500 KB; image jpeg/png <= 5 MB; video mp4/3gp <= 16 MB; audio
           aac/amr/mp3/m4a/ogg-opus <= 16 MB; document txt/xls(x)/doc(x)/ppt(x)/pdf <= 100 MB.
verified   location: ``{latitude, longitude, name?, address?}`` (page documents no ranges or lengths).
verified   contacts: ``contacts[]`` (<= 257), ``name.formatted_name`` required, optional first/last/middle name,
           suffix, prefix, ``birthday`` YYYY-MM-DD, ``addresses[]``, ``emails[]``, ``org``, ``phones[]`` (``wa_id``
           makes it a Message/Save contact card), ``urls[]``.
verified   reaction: ``{message_id, emoji}``; target <= 30 days old, not deleted, not itself a reaction, else error
           131009 and no delivery. Removal payload is NOT on the page: empty ``emoji`` is from memory (unverified).
verified   reply buttons: <= 3 ``reply`` buttons, id required <= 256, title required <= 20 and unique, body <= 1024,
           footer <= 60, optional header document/image/text/video (text-header length unstated: 60 assumed).
verified   list: body <= 4096, header text only <= 60, footer <= 60, button <= 20, sections <= 10, rows <= 10 in
           total, section title <= 24, row id <= 200, row title <= 24, row description <= 72.
verified   CTA URL: body <= 1024, header text <= 60 or image/video/document, footer <= 60, ``display_text`` <= 20,
           ``url`` required (opens in the browser; length unstated: 2000 assumed, https required by Huf policy).
verified   location request: ``interactive{type: location_request_message, body{text <= 1024}, action{name: send_location}}``.
unverified flow (the page returned no content): ``interactive{type: flow, action{name: flow, parameters{
           flow_message_version, flow_id | flow_name, flow_cta, flow_token, flow_action, flow_action_payload, mode}}}``.
           Gated: ``flow_id_required`` unless flow_id (or flow_name) is given. Never sent live yet.
unverified location latitude/longitude ranges (-90..90 / -180..180) and name <= 100 / address <= 300 (Huf caps);
           contact field lengths (Huf caps); numeric (not string) coordinates; list row id uniqueness and the
           "section title required with more than one section" rule; reply-button id charset; ``context.message_id``.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any
from urllib.parse import urlparse

_KB = 1024
_MB = 1024 * 1024

MEDIA_KINDS = ("image", "document", "audio", "video", "sticker")

# kind -> (max bytes, accepted mime types); verified (business-phone-numbers/media)
MEDIA_RULES: dict[str, tuple[int, tuple[str, ...]]] = {
	"image": (5 * _MB, ("image/jpeg", "image/png")),
	"video": (16 * _MB, ("video/mp4", "video/3gpp")),
	"audio": (16 * _MB, ("audio/aac", "audio/amr", "audio/mpeg", "audio/mp4", "audio/ogg")),
	"document": (
		100 * _MB,
		(
			"text/plain",
			"application/pdf",
			"application/vnd.ms-excel",
			"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
			"application/msword",
			"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
			"application/vnd.ms-powerpoint",
			"application/vnd.openxmlformats-officedocument.presentationml.presentation",
		),
	),
	"sticker": (500 * _KB, ("image/webp",)),  # static stickers are further capped at 100 KB
}
STICKER_STATIC_MAX = 100 * _KB
STICKER_ANIMATED_MAX = 500 * _KB

MAX_CAPTION = 1024
MAX_FILENAME = 240  # unverified (page gives none)
MAX_REACTION_ID = 256  # unverified

# location (ranges + lengths unverified)
MAX_LOCATION_NAME = 100
MAX_LOCATION_ADDRESS = 300

# contacts
MAX_CONTACTS = 257  # verified
MAX_CONTACT_FIELD = 200  # unverified Huf cap on every free-text contact field
MAX_CONTACT_ENTRIES = 20  # unverified Huf cap on phones/emails/urls/addresses per contact
CONTACT_NAME_KEYS = ("formatted_name", "first_name", "last_name", "middle_name", "suffix", "prefix")

# interactive
BUTTONS_MAX = 3
BUTTON_ID_MAX = 256
BUTTON_TITLE_MAX = 20
BODY_BUTTONS_MAX = 1024
BODY_LIST_MAX = 4096
BODY_CTA_MAX = 1024
BODY_LOCATION_REQUEST_MAX = 1024
HEADER_TEXT_MAX = 60
FOOTER_MAX = 60
LIST_BUTTON_MAX = 20
LIST_SECTIONS_MAX = 10
LIST_ROWS_MAX = 10
LIST_SECTION_TITLE_MAX = 24
LIST_ROW_ID_MAX = 200
LIST_ROW_TITLE_MAX = 24
LIST_ROW_DESC_MAX = 72
CTA_TEXT_MAX = 20
CTA_URL_MAX = 2000  # unverified
FLOW_CTA_MAX = 20  # unverified
FLOW_ACTIONS = ("navigate", "data_exchange")
FLOW_MODES = ("draft", "published")
INTERACTIVE_KINDS = ("buttons", "list", "cta_url", "flow", "location_request")
HEADER_MEDIA_TYPES = ("image", "video", "document")

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_SPACE_RE = re.compile(r"\s")
_BIRTHDAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def err(field: str, code: str, message: str) -> dict[str, str]:
	return {"field": field, "code": code, "message": message}


def _text(value: Any) -> str:
	return "" if value is None else str(value).strip()


def is_http_url(value: Any) -> bool:
	p = urlparse(str(value or ""))
	return p.scheme in ("http", "https") and bool(p.hostname)


def is_https_url(value: Any) -> bool:
	p = urlparse(str(value or ""))
	return p.scheme == "https" and bool(p.hostname) and not _SPACE_RE.search(str(value))


def _base(to: str, mtype: str, reply_to: str | None) -> dict[str, Any]:
	data: dict[str, Any] = {
		"messaging_product": "whatsapp",
		"recipient_type": "individual",
		"to": to,
		"type": mtype,
	}
	if reply_to:
		data["context"] = {"message_id": str(reply_to)}
	return data


def _finish(payload: dict[str, Any], errors: list[dict[str, str]]) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
	return (None if errors else payload), errors


def _check_to(to: Any, errors: list[dict[str, str]]) -> str:
	to = _text(to)
	if not to:
		errors.append(err("to", "required", "Recipient number is required."))
	return to


# ---------------------------------------------------------------- media files
def normalize_mime(mime: Any) -> str:
	"""Lower-cased mime type without parameters (``audio/ogg; codecs=opus`` -> ``audio/ogg``)."""
	return str(mime or "").split(";", 1)[0].strip().lower()


def kind_for_mime(mime: Any) -> str:
	"""The outbound kind a mime type belongs to ('' when WhatsApp does not accept it)."""
	m = normalize_mime(mime)
	for kind in ("image", "video", "audio", "document", "sticker"):
		if m in MEDIA_RULES[kind][1]:
			return kind
	return ""


def webp_is_animated(head: bytes) -> bool:
	"""True when a WebP header declares an animation (VP8X chunk, animation flag 0x02)."""
	return len(head) >= 21 and head[:4] == b"RIFF" and head[8:12] == b"WEBP" and head[12:16] == b"VP8X" and bool(head[20] & 0x02)


def validate_media_file(kind: Any, mime: Any, size: int, head: bytes = b"", voice: bool = False) -> list[dict[str, str]]:
	"""Check an upload candidate against the per-kind mime and size rules (verified, see module docstring)."""
	errors: list[dict[str, str]] = []
	kind = _text(kind).lower()
	if kind not in MEDIA_RULES:
		return [err("kind", "invalid_kind", f"Media kind must be one of {', '.join(MEDIA_KINDS)}.")]
	max_bytes, mimes = MEDIA_RULES[kind]
	m = normalize_mime(mime)
	if m not in mimes:
		errors.append(err("mime_type", "unsupported_mime", f"{kind} files must be one of: {', '.join(mimes)} (got {m or 'unknown'})."))
		return errors
	if not size or size <= 0:
		errors.append(err("file", "empty_file", "The file is empty."))
		return errors
	limit = max_bytes
	if kind == "sticker":
		animated = webp_is_animated(head)
		limit = STICKER_ANIMATED_MAX if animated else STICKER_STATIC_MAX
		if size > limit:
			label = "animated" if animated else "static"
			errors.append(err("file", "too_large", f"A {label} sticker is at most {limit // _KB} KB."))
			return errors
	elif size > limit:
		errors.append(err("file", "too_large", f"{kind} files are at most {limit // _MB} MB."))
	if voice and kind == "audio":
		raw = str(mime or "").lower()
		if m != "audio/ogg" or ("codecs" in raw and "opus" not in raw):
			errors.append(err("voice", "voice_needs_ogg_opus", "A voice note must be an Ogg file with the Opus codec."))
	return errors


VOICE_LINK_EXTENSIONS = (".ogg", ".opus", ".oga")


def validate_voice_link(link: Any) -> list[dict[str, str]]:
	"""A voice note sent by public link must point at an Ogg/Opus file (the mime type is only known after upload)."""
	path = _text(link).split("?", 1)[0].split("#", 1)[0].lower()
	if path.endswith(VOICE_LINK_EXTENSIONS):
		return []
	return [err("link", "voice_needs_ogg_opus", "A voice note must be an Ogg file with the Opus codec (.ogg/.opus).")]


def build_voice_note_payload(
	to: str, link: Any = None, media_id: Any = None, reply_to: str | None = None
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
	"""Audio message with ``audio.voice: true`` (Meta: voice messages must be Ogg/Opus, mono, <= 16 MB)."""
	link = _text(link)
	if link and not media_id:
		errors = validate_voice_link(link)
		if errors:
			return None, errors
	return build_media_payload(to, "audio", link=link, media_id=media_id, voice=True, reply_to=reply_to)


def validate_upload(
	mime: Any, content: bytes, kind: Any = None, voice: bool = False
) -> tuple[str, list[dict[str, str]]]:
	"""``(kind, errors)`` for uploading ``content``; the kind is inferred from the mime type when not given."""
	m = normalize_mime(mime)
	kind = _text(kind).lower() or kind_for_mime(m)
	if not kind:
		return "", [err("mime_type", "unsupported_mime", f"WhatsApp does not accept {m or 'this file type'} media.")]
	content = content or b""
	return kind, validate_media_file(kind, mime, len(content), content[:32], voice)


# ---------------------------------------------------------------------- media
def validate_media_message(
	kind: Any, link: Any, media_id: Any, caption: Any, filename: Any, voice: Any = None
) -> tuple[dict[str, Any], list[dict[str, str]]]:
	"""Validate an outbound media send; returns the normalised request and errors."""
	errors: list[dict[str, str]] = []
	kind = _text(kind).lower()
	link = _text(link)
	media_id = _text(media_id)
	caption = "" if caption is None else str(caption)
	filename = _text(filename)
	voice_on = voice is True or str(voice).strip().lower() in ("1", "true", "yes")
	if kind not in MEDIA_KINDS:
		errors.append(err("kind", "invalid_kind", f"Media kind must be one of {', '.join(MEDIA_KINDS)}."))
	if bool(link) == bool(media_id):
		errors.append(err("link", "link_or_id", "Provide exactly one of link or media_id."))
	elif link and not is_http_url(link):
		errors.append(err("link", "invalid_link", "Media link must be a public http(s) URL."))
	if caption and kind in ("audio", "sticker"):
		errors.append(err("caption", "not_allowed", f"{kind.capitalize()} messages cannot have a caption."))
	if len(caption) > MAX_CAPTION:
		errors.append(err("caption", "too_long", f"Caption is longer than {MAX_CAPTION} characters."))
	if filename and kind != "document":
		filename = ""  # only documents carry a filename
	if len(filename) > MAX_FILENAME:
		errors.append(err("filename", "too_long", f"Filename is longer than {MAX_FILENAME} characters."))
	if voice_on and kind != "audio":
		errors.append(err("voice", "not_allowed", "Only audio can be sent as a voice note."))
	return {
		"kind": kind, "link": link, "media_id": media_id, "caption": caption, "filename": filename,
		"voice": voice_on and kind == "audio",
	}, errors


def build_media_message_payload(to: str, media: dict[str, Any], reply_to: str | None = None) -> dict[str, Any]:
	"""Graph body for a request validated by :func:`validate_media_message`."""
	kind = media["kind"]
	obj: dict[str, Any] = {"id": media["media_id"]} if media.get("media_id") else {"link": media["link"]}
	if media.get("caption") and kind in ("image", "video", "document"):
		obj["caption"] = media["caption"]
	if media.get("filename") and kind == "document":
		obj["filename"] = media["filename"]
	if media.get("voice") and kind == "audio":
		obj["voice"] = True
	data = _base(to, kind, reply_to)
	data[kind] = obj
	return data


def build_media_payload(
	to: str, kind: Any, link: Any = None, media_id: Any = None, caption: Any = None, filename: Any = None,
	voice: Any = None, reply_to: str | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
	"""Validate and build an image/video/audio/document/sticker message."""
	media, errors = validate_media_message(kind, link, media_id, caption, filename, voice)
	to = _check_to(to, errors)
	return _finish(build_media_message_payload(to, media, reply_to) if not errors else {}, errors)


def build_sticker_payload(
	to: str, link: Any = None, media_id: Any = None, reply_to: str | None = None
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
	return build_media_payload(to, "sticker", link=link, media_id=media_id, reply_to=reply_to)


# ------------------------------------------------------------------- location
def _coordinate(field: str, value: Any, low: float, high: float, errors: list[dict[str, str]]) -> float | None:
	if value is None or isinstance(value, bool) or str(value).strip() == "":
		errors.append(err(field, "required", f"{field} is required."))
		return None
	try:
		number = float(str(value).strip())
	except ValueError:
		errors.append(err(field, "invalid_coordinate", f"{field} must be a decimal number."))
		return None
	if not (low <= number <= high) or number != number:
		errors.append(err(field, "out_of_range", f"{field} must be between {low:g} and {high:g}."))
		return None
	return number


def build_location_payload(
	to: str, latitude: Any, longitude: Any, name: Any = None, address: Any = None, reply_to: str | None = None
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
	errors: list[dict[str, str]] = []
	to = _check_to(to, errors)
	lat = _coordinate("latitude", latitude, -90, 90, errors)
	lng = _coordinate("longitude", longitude, -180, 180, errors)
	name, address = _text(name), _text(address)
	if len(name) > MAX_LOCATION_NAME:
		errors.append(err("name", "too_long", f"Location name is longer than {MAX_LOCATION_NAME} characters."))
	if len(address) > MAX_LOCATION_ADDRESS:
		errors.append(err("address", "too_long", f"Location address is longer than {MAX_LOCATION_ADDRESS} characters."))
	data = _base(to, "location", reply_to)
	data["location"] = {"latitude": lat, "longitude": lng}
	if name:
		data["location"]["name"] = name
	if address:
		data["location"]["address"] = address
	return _finish(data, errors)


# ------------------------------------------------------------------- contacts
def _field_text(path: str, value: Any, errors: list[dict[str, str]], required: bool = False) -> str:
	if value is None or (isinstance(value, str) and not value.strip()):
		if required:
			errors.append(err(path, "required", f"{path} is required."))
		return ""
	if not isinstance(value, (str, int)) or isinstance(value, bool):
		errors.append(err(path, "invalid_type", f"{path} must be text."))
		return ""
	text = str(value).strip()
	if len(text) > MAX_CONTACT_FIELD:
		errors.append(err(path, "too_long", f"{path} is longer than {MAX_CONTACT_FIELD} characters."))
	return text


def _entries(path: str, raw: Any, errors: list[dict[str, str]]) -> list[dict[str, Any]]:
	if raw in (None, ""):
		return []
	if not isinstance(raw, list):
		errors.append(err(path, "invalid_type", f"{path} must be a list."))
		return []
	if len(raw) > MAX_CONTACT_ENTRIES:
		errors.append(err(path, "too_many", f"{path} has more than {MAX_CONTACT_ENTRIES} entries."))
		raw = raw[:MAX_CONTACT_ENTRIES]
	out = []
	for i, item in enumerate(raw):
		if not isinstance(item, dict):
			errors.append(err(f"{path}[{i}]", "invalid_type", f"{path}[{i}] must be an object."))
			continue
		out.append(item)
	return out


def _unknown_keys(path: str, obj: dict, allowed: tuple[str, ...], errors: list[dict[str, str]]) -> None:
	extra = sorted(set(obj) - set(allowed))
	if extra:
		errors.append(err(path, "unknown_field", f"{path} has unsupported field(s): {', '.join(extra)}."))


def normalize_contact(index: int, raw: Any, errors: list[dict[str, str]]) -> dict[str, Any]:
	"""One validated contact object (verified shape; field caps are Huf's)."""
	path = f"contacts[{index}]"
	if not isinstance(raw, dict):
		errors.append(err(path, "invalid_type", f"{path} must be an object."))
		return {}
	_unknown_keys(path, raw, ("name", "phones", "emails", "urls", "addresses", "org", "birthday"), errors)
	out: dict[str, Any] = {}
	name_raw = raw.get("name")
	if isinstance(name_raw, str):  # convenience: a bare string is the formatted name
		name_raw = {"formatted_name": name_raw}
	if not isinstance(name_raw, dict):
		errors.append(err(f"{path}.name.formatted_name", "required", "A contact needs name.formatted_name."))
		name: dict[str, str] = {}
	else:
		_unknown_keys(f"{path}.name", name_raw, CONTACT_NAME_KEYS, errors)
		name = {}
		for key in CONTACT_NAME_KEYS:
			value = _field_text(f"{path}.name.{key}", name_raw.get(key), errors, required=key == "formatted_name")
			if value:
				name[key] = value
	out["name"] = name

	phones = []
	for i, item in enumerate(_entries(f"{path}.phones", raw.get("phones"), errors)):
		_unknown_keys(f"{path}.phones[{i}]", item, ("phone", "type", "wa_id"), errors)
		phone = _field_text(f"{path}.phones[{i}].phone", item.get("phone"), errors)
		wa_id = _field_text(f"{path}.phones[{i}].wa_id", item.get("wa_id"), errors)
		if not phone and not wa_id:
			errors.append(err(f"{path}.phones[{i}].phone", "required", "A phone entry needs phone or wa_id."))
		entry = {k: v for k, v in (("phone", phone), ("type", _field_text(f"{path}.phones[{i}].type", item.get("type"), errors)), ("wa_id", wa_id)) if v}
		phones.append(entry)
	if phones:
		out["phones"] = phones

	emails = []
	for i, item in enumerate(_entries(f"{path}.emails", raw.get("emails"), errors)):
		_unknown_keys(f"{path}.emails[{i}]", item, ("email", "type"), errors)
		email = _field_text(f"{path}.emails[{i}].email", item.get("email"), errors, required=True)
		if email and not _EMAIL_RE.match(email):
			errors.append(err(f"{path}.emails[{i}].email", "invalid_email", "Email address is not valid."))
		entry = {k: v for k, v in (("email", email), ("type", _field_text(f"{path}.emails[{i}].type", item.get("type"), errors))) if v}
		emails.append(entry)
	if emails:
		out["emails"] = emails

	urls = []
	for i, item in enumerate(_entries(f"{path}.urls", raw.get("urls"), errors)):
		_unknown_keys(f"{path}.urls[{i}]", item, ("url", "type"), errors)
		url = _field_text(f"{path}.urls[{i}].url", item.get("url"), errors, required=True)
		if url and not is_http_url(url):
			errors.append(err(f"{path}.urls[{i}].url", "invalid_url", "URL must start with http:// or https://."))
		entry = {k: v for k, v in (("url", url), ("type", _field_text(f"{path}.urls[{i}].type", item.get("type"), errors))) if v}
		urls.append(entry)
	if urls:
		out["urls"] = urls

	addresses = []
	for i, item in enumerate(_entries(f"{path}.addresses", raw.get("addresses"), errors)):
		keys = ("street", "city", "state", "zip", "country", "country_code", "type")
		_unknown_keys(f"{path}.addresses[{i}]", item, keys, errors)
		entry = {k: _field_text(f"{path}.addresses[{i}].{k}", item.get(k), errors) for k in keys}
		cc = entry.get("country_code", "")
		if cc and not re.match(r"^[A-Za-z]{2}$", cc):
			errors.append(err(f"{path}.addresses[{i}].country_code", "invalid_country_code", "country_code must be a two-letter ISO code."))
		addresses.append({k: v for k, v in entry.items() if v})
	if addresses:
		out["addresses"] = addresses

	org_raw = raw.get("org")
	if org_raw not in (None, ""):
		if not isinstance(org_raw, dict):
			errors.append(err(f"{path}.org", "invalid_type", f"{path}.org must be an object."))
		else:
			_unknown_keys(f"{path}.org", org_raw, ("company", "department", "title"), errors)
			org = {k: _field_text(f"{path}.org.{k}", org_raw.get(k), errors) for k in ("company", "department", "title")}
			org = {k: v for k, v in org.items() if v}
			if org:
				out["org"] = org

	birthday = _field_text(f"{path}.birthday", raw.get("birthday"), errors)
	if birthday:
		valid = bool(_BIRTHDAY_RE.match(birthday))
		if valid:
			try:
				date.fromisoformat(birthday)
			except ValueError:
				valid = False
		if not valid:
			errors.append(err(f"{path}.birthday", "invalid_birthday", "birthday must be a real date as YYYY-MM-DD."))
		else:
			out["birthday"] = birthday
	return out


def build_contacts_payload(
	to: str, contacts: Any, reply_to: str | None = None
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
	errors: list[dict[str, str]] = []
	to = _check_to(to, errors)
	if isinstance(contacts, dict):
		contacts = [contacts]
	if not isinstance(contacts, list) or not contacts:
		errors.append(err("contacts", "required", "Provide at least one contact."))
		return _finish({}, errors)
	if len(contacts) > MAX_CONTACTS:
		errors.append(err("contacts", "too_many", f"At most {MAX_CONTACTS} contacts can be sent in one message."))
		return _finish({}, errors)
	data = _base(to, "contacts", reply_to)
	data["contacts"] = [normalize_contact(i, c, errors) for i, c in enumerate(contacts)]
	return _finish(data, errors)


def simple_contact(name: Any, phone: Any = None, email: Any = None, org: Any = None, url: Any = None) -> dict[str, Any]:
	"""A one-person contact object from flat values (tool / UI convenience)."""
	contact: dict[str, Any] = {"name": {"formatted_name": _text(name)}}
	if _text(phone):
		contact["phones"] = [{"phone": _text(phone), "type": "CELL"}]
	if _text(email):
		contact["emails"] = [{"email": _text(email), "type": "WORK"}]
	if _text(url):
		contact["urls"] = [{"url": _text(url)}]
	if _text(org):
		contact["org"] = {"company": _text(org)}
	return contact


# ------------------------------------------------------------------- reaction
_ZWJ, _VS15, _VS16, _KEYCAP = 0x200D, 0xFE0E, 0xFE0F, 0x20E3
_SINGLE_SYMBOLS = {0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139, 0x3030, 0x303D, 0x3297, 0x3299}


def _pictograph(cp: int) -> bool:
	return 0x1F000 <= cp <= 0x1FAFF or 0x2190 <= cp <= 0x2BFF or cp in _SINGLE_SYMBOLS


def is_single_emoji(text: str) -> bool:
	"""True when ``text`` is exactly one emoji grapheme (flags, keycaps, skin tones and ZWJ sequences included)."""
	cps = [ord(c) for c in text]
	if not cps or len(cps) > 32:
		return False
	first = cps[0]
	if chr(first) in "#*0123456789":
		return cps[1:] in ([_VS16, _KEYCAP], [_KEYCAP])
	if 0x1F1E6 <= first <= 0x1F1FF:
		return len(cps) == 2 and 0x1F1E6 <= cps[1] <= 0x1F1FF
	if not _pictograph(first):
		return False
	i = 1
	while i < len(cps):
		cp = cps[i]
		if cp in (_VS15, _VS16) or 0x1F3FB <= cp <= 0x1F3FF or 0xE0020 <= cp <= 0xE007F:
			i += 1
		elif cp == _ZWJ:
			if i + 1 >= len(cps) or not _pictograph(cps[i + 1]):
				return False
			i += 2
		else:
			return False
	return True


def build_reaction_payload(
	to: str, message_id: Any, emoji: Any = "", remove: bool = False
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
	"""React to (or, with an empty emoji / ``remove``, un-react) an inbound message.

	Meta (verified): the target must be at most 30 days old, not deleted and not itself a reaction, otherwise
	nothing is delivered and error 131009 arrives. Only presence of ``message_id`` is checked here.
	"""
	errors: list[dict[str, str]] = []
	to = _check_to(to, errors)
	mid = _text(message_id)
	if not mid:
		errors.append(err("message_id", "required", "message_id of the message to react to is required."))
	elif len(mid) > MAX_REACTION_ID or _SPACE_RE.search(mid):
		errors.append(err("message_id", "invalid_message_id", "message_id looks invalid."))
	emoji_text = "" if remove else ("" if emoji is None else str(emoji).strip())
	if emoji_text and not is_single_emoji(emoji_text):
		errors.append(err("emoji", "invalid_emoji", "emoji must be exactly one emoji (or empty to remove the reaction)."))
	data = _base(to, "reaction", None)
	data["reaction"] = {"message_id": mid, "emoji": emoji_text}
	return _finish(data, errors)


# ----------------------------------------------------------------- interactive
def _bounded(field: str, value: Any, limit: int, errors: list[dict[str, str]], required: bool = True) -> str:
	text = _text(value)
	if not text:
		if required:
			errors.append(err(field, "required", f"{field} is required."))
		return ""
	if len(text) > limit:
		errors.append(err(field, "too_long", f"{field} is longer than {limit} characters."))
	return text


def _header(raw: Any, errors: list[dict[str, str]], text_only: bool = False) -> dict[str, Any] | None:
	"""Header from a text string or ``{"type": text|image|video|document, text | link | media_id, filename?}``."""
	if raw in (None, "", {}):
		return None
	if isinstance(raw, str):
		raw = {"type": "text", "text": raw}
	if not isinstance(raw, dict):
		errors.append(err("header", "invalid_type", "header must be text or an object."))
		return None
	htype = _text(raw.get("type") or ("text" if raw.get("text") else "")).lower()
	if htype == "text":
		text = _bounded("header.text", raw.get("text"), HEADER_TEXT_MAX, errors)
		return {"type": "text", "text": text} if text else None
	if text_only:
		errors.append(err("header", "text_only", "This message type supports a text header only."))
		return None
	if htype not in HEADER_MEDIA_TYPES:
		errors.append(err("header.type", "invalid_type", "header.type must be text, image, video or document."))
		return None
	link, media_id = _text(raw.get("link")), _text(raw.get("media_id") or raw.get("id"))
	if bool(link) == bool(media_id):
		errors.append(err("header", "link_or_id", "A media header needs exactly one of link or media_id."))
		return None
	if link and not is_http_url(link):
		errors.append(err("header.link", "invalid_link", "Header link must be a public http(s) URL."))
		return None
	obj: dict[str, Any] = {"id": media_id} if media_id else {"link": link}
	if htype == "document" and _text(raw.get("filename")):
		obj["filename"] = _text(raw.get("filename"))  # unverified for headers
	return {"type": htype, htype: obj}


def _interactive(to: str, body: str, itype: str, action: dict[str, Any], header: dict | None, footer: str, reply_to: str | None):
	inter: dict[str, Any] = {"type": itype}
	if header:
		inter["header"] = header
	inter["body"] = {"text": body}
	if footer:
		inter["footer"] = {"text": footer}
	inter["action"] = action
	data = _base(to, "interactive", reply_to)
	data["interactive"] = inter
	return data


def build_reply_buttons_payload(
	to: str, body: Any, buttons: Any, header: Any = None, footer: Any = None, reply_to: str | None = None
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
	"""Quick-reply buttons: 1..3, id <= 256 (unique), title <= 20 (unique). A bare string is both id and title."""
	errors: list[dict[str, str]] = []
	to = _check_to(to, errors)
	body_t = _bounded("body", body, BODY_BUTTONS_MAX, errors)
	footer_t = _bounded("footer", footer, FOOTER_MAX, errors, required=False)
	hdr = _header(header, errors)
	rows: list[dict[str, Any]] = []
	if not isinstance(buttons, list) or not buttons:
		errors.append(err("buttons", "required", "Provide 1 to 3 buttons."))
	else:
		if len(buttons) > BUTTONS_MAX:
			errors.append(err("buttons", "too_many", f"At most {BUTTONS_MAX} reply buttons are allowed."))
		ids: set[str] = set()
		titles: set[str] = set()
		for i, raw in enumerate(buttons[: BUTTONS_MAX + 5]):
			if isinstance(raw, str):
				raw = {"id": raw, "title": raw}
			if not isinstance(raw, dict):
				errors.append(err(f"buttons[{i}]", "invalid_type", "Each button must be {id, title}."))
				continue
			reply = raw.get("reply") if isinstance(raw.get("reply"), dict) else raw
			bid = _bounded(f"buttons[{i}].id", reply.get("id"), BUTTON_ID_MAX, errors)
			title = _bounded(f"buttons[{i}].title", reply.get("title"), BUTTON_TITLE_MAX, errors)
			if bid and bid in ids:
				errors.append(err(f"buttons[{i}].id", "duplicate", "Button ids must be unique."))
			if title and title.lower() in titles:
				errors.append(err(f"buttons[{i}].title", "duplicate", "Button titles must be unique."))
			ids.add(bid)
			titles.add(title.lower())
			rows.append({"type": "reply", "reply": {"id": bid, "title": title}})
	return _finish(_interactive(to, body_t, "button", {"buttons": rows}, hdr, footer_t, reply_to), errors)


def build_list_payload(
	to: str, body: Any, button_text: Any, sections: Any, header: Any = None, footer: Any = None, reply_to: str | None = None
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
	"""List message: <= 10 sections and <= 10 rows in total; ``sections`` may also be a flat list of rows."""
	errors: list[dict[str, str]] = []
	to = _check_to(to, errors)
	body_t = _bounded("body", body, BODY_LIST_MAX, errors)
	footer_t = _bounded("footer", footer, FOOTER_MAX, errors, required=False)
	button_t = _bounded("button_text", button_text, LIST_BUTTON_MAX, errors)
	hdr = _header(header, errors, text_only=True)
	out: list[dict[str, Any]] = []
	if isinstance(sections, list) and sections and all(isinstance(s, dict) and "rows" not in s for s in sections):
		sections = [{"rows": sections}]
	if not isinstance(sections, list) or not sections:
		errors.append(err("sections", "required", "Provide at least one section with rows."))
	else:
		if len(sections) > LIST_SECTIONS_MAX:
			errors.append(err("sections", "too_many", f"At most {LIST_SECTIONS_MAX} sections are allowed."))
		total = 0
		ids: set[str] = set()
		for si, sec in enumerate(sections[: LIST_SECTIONS_MAX + 5]):
			if not isinstance(sec, dict) or not isinstance(sec.get("rows"), list) or not sec["rows"]:
				errors.append(err(f"sections[{si}].rows", "required", "Each section needs at least one row."))
				continue
			title = _bounded(f"sections[{si}].title", sec.get("title"), LIST_SECTION_TITLE_MAX, errors, required=len(sections) > 1)
			rows = []
			for ri, row in enumerate(sec["rows"]):
				total += 1
				path = f"sections[{si}].rows[{ri}]"
				if not isinstance(row, dict):
					errors.append(err(path, "invalid_type", "Each row must be {id, title, description?}."))
					continue
				rid = _bounded(f"{path}.id", row.get("id"), LIST_ROW_ID_MAX, errors)
				rtitle = _bounded(f"{path}.title", row.get("title"), LIST_ROW_TITLE_MAX, errors)
				desc = _bounded(f"{path}.description", row.get("description"), LIST_ROW_DESC_MAX, errors, required=False)
				if rid and rid in ids:
					errors.append(err(f"{path}.id", "duplicate", "Row ids must be unique."))
				ids.add(rid)
				item = {"id": rid, "title": rtitle}
				if desc:
					item["description"] = desc
				rows.append(item)
			section: dict[str, Any] = {"rows": rows}
			if title:
				section = {"title": title, "rows": rows}
			out.append(section)
		if total > LIST_ROWS_MAX:
			errors.append(err("sections", "too_many_rows", f"A list holds at most {LIST_ROWS_MAX} rows in total."))
	action = {"button": button_t, "sections": out}
	return _finish(_interactive(to, body_t, "list", action, hdr, footer_t, reply_to), errors)


def build_cta_url_payload(
	to: str, body: Any, display_text: Any, url: Any, header: Any = None, footer: Any = None, reply_to: str | None = None
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
	errors: list[dict[str, str]] = []
	to = _check_to(to, errors)
	body_t = _bounded("body", body, BODY_CTA_MAX, errors)
	footer_t = _bounded("footer", footer, FOOTER_MAX, errors, required=False)
	text = _bounded("display_text", display_text, CTA_TEXT_MAX, errors)
	link = _text(url)
	if not link:
		errors.append(err("url", "required", "url is required."))
	elif not is_https_url(link):
		errors.append(err("url", "invalid_url", "url must be an https:// address."))
	elif len(link) > CTA_URL_MAX:
		errors.append(err("url", "too_long", f"url is longer than {CTA_URL_MAX} characters."))
	hdr = _header(header, errors)
	action = {"name": "cta_url", "parameters": {"display_text": text, "url": link}}
	return _finish(_interactive(to, body_t, "cta_url", action, hdr, footer_t, reply_to), errors)


def build_location_request_payload(to: str, body: Any, reply_to: str | None = None) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
	"""Ask the user to share their location (they answer with an inbound ``location`` message)."""
	errors: list[dict[str, str]] = []
	to = _check_to(to, errors)
	body_t = _bounded("body", body, BODY_LOCATION_REQUEST_MAX, errors)
	data = _base(to, "interactive", reply_to)
	data["interactive"] = {"type": "location_request_message", "body": {"text": body_t}, "action": {"name": "send_location"}}
	return _finish(data, errors)


def build_flow_payload(
	to: str, body: Any, flow_id: Any = None, flow_name: Any = None, flow_cta: Any = None, flow_token: Any = None,
	flow_action: Any = None, screen: Any = None, flow_data: Any = None, mode: Any = None, header: Any = None,
	footer: Any = None, flow_message_version: Any = "3", reply_to: str | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
	"""UNTESTED / unverified (Meta's flow page returned no content). Refuses without ``flow_id`` (or ``flow_name``)."""
	errors: list[dict[str, str]] = []
	to = _check_to(to, errors)
	body_t = _bounded("body", body, BODY_BUTTONS_MAX, errors)
	footer_t = _bounded("footer", footer, FOOTER_MAX, errors, required=False)
	hdr = _header(header, errors)
	fid, fname = _text(flow_id), _text(flow_name)
	if not fid and not fname:
		errors.append(err("flow_id", "flow_id_required", "flow_id is required to send a Flow message (Flows are not sent without one)."))
	if fid and fname:
		errors.append(err("flow_id", "flow_id_or_name", "Give flow_id or flow_name, not both."))
	cta = _bounded("flow_cta", flow_cta, FLOW_CTA_MAX, errors)
	action_name = _text(flow_action).lower() or "navigate"
	if action_name not in FLOW_ACTIONS:
		errors.append(err("flow_action", "invalid_action", f"flow_action must be one of {', '.join(FLOW_ACTIONS)}."))
	mode_t = _text(mode).lower()
	if mode_t and mode_t not in FLOW_MODES:
		errors.append(err("mode", "invalid_mode", f"mode must be one of {', '.join(FLOW_MODES)}."))
	params: dict[str, Any] = {"flow_message_version": _text(flow_message_version) or "3"}
	params["flow_id" if fid else "flow_name"] = fid or fname
	params["flow_cta"] = cta
	if _text(flow_token):
		params["flow_token"] = _text(flow_token)
	params["flow_action"] = action_name
	if action_name == "navigate" and (_text(screen) or flow_data):
		payload: dict[str, Any] = {}
		if _text(screen):
			payload["screen"] = _text(screen)
		if flow_data:
			if not isinstance(flow_data, dict):
				errors.append(err("flow_data", "invalid_type", "flow_data must be an object."))
			else:
				payload["data"] = flow_data
		params["flow_action_payload"] = payload
	if mode_t:
		params["mode"] = mode_t
	action = {"name": "flow", "parameters": params}
	return _finish(_interactive(to, body_t, "flow", action, hdr, footer_t, reply_to), errors)


def build_interactive_payload(
	to: str, kind: Any, spec: dict[str, Any], reply_to: str | None = None
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
	"""Dispatch on ``kind`` (buttons | list | cta_url | flow | location_request); ``spec`` holds that kind's fields."""
	kind = _text(kind).lower()
	spec = spec or {}
	if kind == "buttons":
		return build_reply_buttons_payload(to, spec.get("body"), spec.get("buttons"), spec.get("header"), spec.get("footer"), reply_to)
	if kind == "list":
		return build_list_payload(
			to, spec.get("body"), spec.get("button_text"), spec.get("sections"), spec.get("header"), spec.get("footer"), reply_to
		)
	if kind == "cta_url":
		return build_cta_url_payload(
			to, spec.get("body"), spec.get("display_text"), spec.get("url"), spec.get("header"), spec.get("footer"), reply_to
		)
	if kind == "location_request":
		return build_location_request_payload(to, spec.get("body"), reply_to)
	if kind == "flow":
		return build_flow_payload(
			to, spec.get("body"), spec.get("flow_id"), spec.get("flow_name"), spec.get("flow_cta"), spec.get("flow_token"),
			spec.get("flow_action"), spec.get("screen"), spec.get("flow_data"), spec.get("mode"), spec.get("header"),
			spec.get("footer"), spec.get("flow_message_version") or "3", reply_to,
		)
	return None, [err("kind", "invalid_kind", f"Interactive kind must be one of {', '.join(INTERACTIVE_KINDS)}.")]


# --------------------------------------------------------------------- mirror
def mirror_summary(payload: dict[str, Any]) -> tuple[str, str]:
	"""``(WhatsApp Message.content_type, readable text)`` of a built payload, for the audit row."""
	mtype = payload.get("type")
	obj = payload.get(mtype) or {}
	if mtype in ("image", "video", "document"):
		return mtype, str(obj.get("caption") or obj.get("filename") or f"[{mtype}]")
	if mtype == "audio":
		return "audio", "[voice note]" if obj.get("voice") else "[audio]"
	if mtype == "sticker":
		return "image", "[sticker]"
	if mtype == "location":
		label = " ".join(p for p in (obj.get("name"), obj.get("address")) if p)
		return "location", f"{obj.get('latitude')},{obj.get('longitude')} {label}".strip()
	if mtype == "contacts":
		names = ", ".join(str((c.get("name") or {}).get("formatted_name") or "") for c in payload.get("contacts") or [])
		return "contact", names
	if mtype == "reaction":
		return "reaction", str(obj.get("emoji") or "")
	if mtype == "interactive":
		return "interactive", str((obj.get("body") or {}).get("text") or "")
	return "text", ""
