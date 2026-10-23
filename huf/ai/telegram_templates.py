# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram message templates: saved text + variables + media + buttons (Telegram has no native ones).

Backed by the ``Telegram Message Template`` doctype; ALL doctype access is behind ``_load`` /
``_list_rows`` / ``_touch`` / ``_file_bytes`` so tests mock them.

Rendering: ``{{var}}`` placeholders are replaced by caller variables, then the template's variable
defaults. Unknown variables are reported in ``missing`` (replaced by an empty string) and never raise
unless ``strict=True``. The body is trusted author content already written in the template's parse
mode; substituted VALUES are escaped for that mode (HTML / MarkdownV2) so a value such as ``<b>``
cannot inject markup. Variables inside ``buttons_json`` are substituted JSON-safely (no markup escape).

Permission model: this module does NOT check who may message ``chat_id``. The caller (agent tool / UI
endpoint) must already have passed the recipient-scope checks (agent_recipient_scope, allowlist, send
caps). Private Frappe Files are only read if the current session user has read permission.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from huf.ai.gateway_adapters import telegram_buttons
from huf.ai.gateway_adapters.telegram_format import (
	MODE_HTML,
	MODE_MARKDOWN_V2,
	MODE_PLAIN,
	TELEGRAM_CAPTION_LIMIT,
	TELEGRAM_TEXT_LIMIT,
	escape_html,
	escape_markdown_v2,
	to_plain,
)

_VAR = re.compile(r"\{\{\s*([A-Za-z_][\w.\-]*)\s*\}\}")
_MODES = {"": MODE_PLAIN, "plain": MODE_PLAIN, "html": MODE_HTML, "markdownv2": MODE_MARKDOWN_V2}
_NO_CAPTION = frozenset({"sticker", "video_note"})
MEDIA_TYPES = frozenset({"photo", "video", "animation", "document", "audio", "voice", "sticker"})


class TemplateError(Exception):
	"""Template missing/inactive/invalid or not sendable. ``missing`` lists unresolved variables."""

	def __init__(self, message: str, missing: list[str] | None = None) -> None:
		super().__init__(message)
		self.missing = list(missing or [])


@dataclass
class RenderedTemplate:
	text: str
	parse_mode: str
	media: dict | None = None  # {"type", "source": file_url|url|file_id, "value"}
	reply_markup: dict | None = None
	missing: list[str] = field(default_factory=list)
	errors: list[str] = field(default_factory=list)  # length / button / media problems (send refuses)


# -- doctype access (mock these) --------------------------------------------------------------


def _load(name: str) -> dict | None:
	"""Template as a plain dict (child rows under ``variables``) or None."""
	import frappe

	if not name or not frappe.db.exists("Telegram Message Template", name):
		return None
	return frappe.get_doc("Telegram Message Template", name).as_dict()


def _list_rows(gateway_name: str | None) -> list[dict]:
	import frappe

	rows = frappe.get_all(
		"Telegram Message Template",
		fields=[
			"name",
			"template_name",
			"gateway",
			"language",
			"parse_mode",
			"media_type",
			"description",
			"is_active",
			"last_used_at",
		],
		order_by="template_name asc",
	)
	return [r for r in rows if not r.get("gateway") or not gateway_name or r.get("gateway") == gateway_name]


def _touch(name: str) -> None:
	import frappe

	frappe.db.set_value(
		"Telegram Message Template", name, "last_used_at", frappe.utils.now_datetime(), update_modified=False
	)


def _file_bytes(file_url: str) -> tuple[str, bytes]:
	"""(filename, content) of a Frappe File; private files require read permission."""
	import frappe

	name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not name:
		raise TemplateError(f"Template media file not found: {file_url}")
	doc = frappe.get_doc("File", name)
	if doc.is_private:
		doc.check_permission("read")
	return doc.file_name or "file", doc.get_content()


# -- helpers ----------------------------------------------------------------------------------


def _gname(gateway: Any) -> str | None:
	if gateway is None:
		return None
	return gateway if isinstance(gateway, str) else getattr(gateway, "name", None)


def _mode(template: dict, gateway: Any) -> str:
	raw = (template.get("parse_mode") or "").strip()
	if not raw:
		raw = getattr(gateway, "telegram_parse_mode", None) or "HTML" if gateway is not None else "HTML"
	mode = _MODES.get(raw.strip().lower())
	return MODE_HTML if mode is None else mode


def _escaper(mode: str) -> Callable[[str], str]:
	return {MODE_HTML: escape_html, MODE_MARKDOWN_V2: escape_markdown_v2}.get(mode, lambda s: s)


def _values(template: dict, variables: dict | None) -> dict[str, str]:
	vals: dict[str, str] = {}
	for row in template.get("variables") or []:
		key = (row.get("variable") or "").strip()
		if key and row.get("default_value") not in (None, ""):
			vals[key] = str(row["default_value"])
	for k, v in (variables or {}).items():
		if v is not None:
			vals[str(k)] = str(v)
	return vals


def _substitute(src: str, vals: dict[str, str], conv: Callable[[str], str], missing: list[str]) -> str:
	def repl(m: re.Match) -> str:
		key = m.group(1)
		if key not in vals:
			if key not in missing:
				missing.append(key)
			return ""
		return conv(vals[key])

	return _VAR.sub(repl, src or "")


def _json_safe(s: str) -> str:
	return json.dumps(s)[1:-1]


def _media(template: dict, errors: list[str]) -> dict | None:
	mtype = (template.get("media_type") or "none").strip().lower()
	value = (template.get("media") or "").strip()
	if mtype in ("", "none") or not value:
		return None
	if mtype not in MEDIA_TYPES:
		errors.append(f"unsupported media type: {mtype}")
		return None
	if value.startswith(("http://", "https://")):
		return {"type": mtype, "source": "url", "value": value}
	if value.startswith("/"):
		return {"type": mtype, "source": "file_url", "value": value}
	return {"type": mtype, "source": "file_id", "value": value}


def _markup(
	raw: str, vals: dict[str, str], sign: Callable[[str], str] | None, missing: list[str], errors: list[str]
) -> dict | None:
	if not (raw or "").strip():
		return None
	filled = _substitute(raw, vals, _json_safe, missing)
	spec, errs = telegram_buttons.validate(filled)
	errors.extend(f"buttons: {e}" for e in errs)
	if not spec:
		return None
	if sign is None:
		needs = spec["mode"] == "rows" and any("callback" in b for row in spec["rows"] for b in row)
		if needs:
			errors.append("buttons: callback buttons need a signer (sign)")
			return None
		sign = lambda p: p
	return telegram_buttons.build_markup(spec, sign)


# -- public API -------------------------------------------------------------------------------


def render_template(
	name: str,
	variables: dict | None = None,
	gateway: Any = None,
	*,
	sign: Callable[[str], str] | None = None,
	strict: bool = False,
) -> RenderedTemplate:
	"""Render without sending. Raises TemplateError if not found / inactive / wrong gateway, or (strict) on missing vars."""
	template = _load(name)
	if not template:
		raise TemplateError(f"Telegram template not found: {name}")
	if not template.get("is_active", 1):
		raise TemplateError(f"Telegram template is inactive: {name}")
	gname = _gname(gateway)
	if template.get("gateway") and gname and template["gateway"] != gname:
		raise TemplateError(f"Template {name} belongs to gateway {template['gateway']}")
	mode = _mode(template, gateway)
	vals = _values(template, variables)
	missing: list[str] = []
	errors: list[str] = []
	text = _substitute(template.get("body") or "", vals, _escaper(mode), missing)
	media = _media(template, errors)
	markup = _markup(template.get("buttons_json") or "", vals, sign, missing, errors)
	if strict and missing:
		raise TemplateError(f"Missing template variables: {', '.join(missing)}", missing)
	limit = TELEGRAM_TEXT_LIMIT
	if len(text) > limit:
		errors.append(f"text is {len(text)} chars (limit {limit})")
	if not text.strip() and not media:
		errors.append("template renders empty")
	return RenderedTemplate(
		text=text, parse_mode=mode, media=media, reply_markup=markup, missing=missing, errors=errors
	)


def list_templates(gateway: Any = None) -> list[dict]:
	"""Active templates usable on ``gateway`` (templates with no gateway are global)."""
	return [r for r in _list_rows(_gname(gateway)) if r.get("is_active", 1)]


def preview_template(name: str, variables: dict | None = None, gateway: Any = None) -> dict:
	"""No send. ``{text, parse_mode, media, markup, markup_json, missing, errors}`` for the UI.

	Callback payloads are shown unsigned (placeholder)."""
	r = render_template(name, variables, gateway, sign=lambda p: p)
	return {
		"template": name,
		"text": r.text,
		"parse_mode": r.parse_mode,
		"media": r.media,
		"markup": r.reply_markup,
		"markup_json": json.dumps(r.reply_markup, sort_keys=True) if r.reply_markup else "",
		"missing": r.missing,
		"errors": r.errors,
	}


def _build_sender(gateway: Any):
	from huf.ai.gateway_adapters.telegram_outbound import TelegramSender
	from huf.ai.gateway_webhook import get_gateway_adapter

	return TelegramSender(get_gateway_adapter(gateway).client)


def _ids(msgs: Any) -> list:
	return [
		m.get("message_id") for m in msgs or [] if isinstance(m, dict) and m.get("message_id") is not None
	]


def _send_text(sender: Any, chat_id: Any, text: str, mode: str, **kw: Any) -> list:
	"""Send already-final text in ``mode`` (no markdown conversion); retry plain on entity-parse errors."""
	link_preview = kw.pop("link_preview", True)
	payload = sender._common(chat_id, **kw)
	payload["text"] = text
	if mode:
		payload["parse_mode"] = mode
	if not link_preview:
		payload["link_preview_options"] = {"is_disabled": True}
	plain = (
		to_plain(text)
		if mode == MODE_MARKDOWN_V2
		else re.sub(r"<[^>]+>", "", text)
		if mode == MODE_HTML
		else text
	)
	return [sender._call_with_fallback("sendMessage", payload, "text", plain)]


def send_template(
	gateway: Any,
	chat_id: Any,
	name: str,
	variables: dict | None = None,
	*,
	thread_id: Any = None,
	reply_to: Any = None,
	sender: Any = None,
	sign: Callable[[str], str] | None = None,
	allow_missing: bool = False,
) -> dict:
	"""Render and send. Returns ``{message_ids, template, missing}``.

	Refuses (TemplateError) on render errors, and on missing variables unless ``allow_missing``.
	Media + caption when text <= 1024 (and the media kind takes captions); otherwise media then text.
	The keyboard rides on the last message. Honours gateway telegram_silent_replies /
	telegram_protect_content / preview_url when present."""
	r = render_template(name, variables, gateway, sign=sign)
	if r.errors:
		raise TemplateError("; ".join(r.errors), r.missing)
	if r.missing and not allow_missing:
		raise TemplateError(f"Missing template variables: {', '.join(r.missing)}", r.missing)
	sender = sender or _build_sender(gateway)
	opts = {
		"thread_id": thread_id,
		"silent": bool(getattr(gateway, "telegram_silent_replies", 0)),
		"protect": bool(getattr(gateway, "telegram_protect_content", 0)),
	}
	link_preview = bool(getattr(gateway, "preview_url", 1)) if hasattr(gateway, "preview_url") else True
	ids: list = []
	text = r.text.strip()
	media = r.media
	if media:
		value: Any = media["value"]
		if media["source"] == "file_url":
			fname, content = _file_bytes(value)
			value = (fname, content)
		inline = bool(text) and len(text) <= TELEGRAM_CAPTION_LIMIT and media["type"] not in _NO_CAPTION
		extra = (
			{"caption": text, **({"parse_mode": r.parse_mode} if r.parse_mode else {})} if inline else None
		)
		msgs = sender.send_media(
			media["type"],
			chat_id,
			value,
			reply_to=reply_to,
			extra=extra,
			markup=r.reply_markup if (inline or not text) else None,
			**opts,
		)
		ids += _ids(msgs)
		if text and not inline:
			ids += _ids(
				_send_text(
					sender,
					chat_id,
					text,
					r.parse_mode,
					markup=r.reply_markup,
					link_preview=link_preview,
					**opts,
				)
			)
	else:
		ids += _ids(
			_send_text(
				sender,
				chat_id,
				text,
				r.parse_mode,
				reply_to=reply_to,
				markup=r.reply_markup,
				link_preview=link_preview,
				**opts,
			)
		)
	try:
		_touch(name)
	except Exception:
		pass
	return {"message_ids": ids, "template": name, "missing": r.missing}
