# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram message templates: saved text + variables + media + buttons (Telegram has no native ones).

Backed by the ``Telegram Message Template`` doctype; ALL doctype access is behind ``_load`` /
``_list_rows`` / ``_touch`` / ``_file_bytes`` so tests mock them.

Rendering is ONE implementation (``render_values``) shared by send, the agent preview and the
management preview, so what a user previews is what is sent. ``{{var}}`` placeholders are replaced by
caller variables, then the template's variable defaults (a blank caller value counts as unset; previews
may also fall back to the variable's ``example``). Variable names are ``[A-Za-z_][A-Za-z0-9_]*``.
Unknown variables are reported in ``missing`` (replaced by an empty string) and never raise unless
``strict=True``. The body is trusted author content already written in the template's parse mode;
substituted VALUES are escaped for that mode (HTML / MarkdownV2) so a value such as ``<b>`` cannot
inject markup, and a value inside an HTML tag (``<a href="{{u}}">``) is also quote-escaped so it cannot
break out of the attribute. ``{{var|url}}`` percent-encodes the value for use inside a URL (query values
in a body link or a button url); a plain ``{{var}}`` is the raw value, which is what a whole-URL variable
needs. Variables inside ``buttons_json`` are substituted JSON-safely (no markup escape).

Permission model: this module does NOT check who may message ``chat_id``. The caller (agent tool / UI
endpoint) must already have passed the recipient-scope checks (agent_recipient_scope, allowlist, send
caps). Private Frappe Files are only read if the current session user has read permission.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html import escape as _html_attr_escape
from typing import Any, Callable
from urllib.parse import quote

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

# One grammar for template names, variable names and placeholders: the doctype, the management API,
# the frontend (mirrored in telegramTemplatesApi.ts / previewModel.ts) and the renderer all use these.
TEMPLATE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
TEMPLATE_NAME_HELP = (
	"Use lowercase letters, digits, dashes and underscores, starting with a letter or digit (max 63)."
)
VAR_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
VAR_RE = re.compile(r"\{\{\s*(" + VAR_NAME_RE.pattern + r")\s*(?:\|\s*(url)\s*)?\}\}")
_ANY_PLACEHOLDER = re.compile(r"\{\{[^{}]*\}\}")
# Save-time stand-in for every placeholder in buttons_json: valid for every button kind (https URL).
BUTTON_PROBE = "https://a.co/x"
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
	caption_inline: bool = False  # text rides as the media caption (one message) instead of a 2nd message
	missing: list[str] = field(default_factory=list)
	errors: list[str] = field(default_factory=list)  # length / button / media problems (send refuses)

	@property
	def split(self) -> bool:
		"""Media and text go out as two messages (text too long for a caption, or a caption-less media kind)."""
		return bool(self.media and self.text and not self.caption_inline)


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
		raw = getattr(gateway, "telegram_parse_mode", None) or "HTML"
	mode = _MODES.get(raw.strip().lower())
	return MODE_HTML if mode is None else mode


def _escaper(mode: str) -> Callable[[str], str]:
	return {MODE_HTML: escape_html, MODE_MARKDOWN_V2: escape_markdown_v2}.get(mode, lambda s: s)


def _values(template: dict, variables: dict | None, examples: bool = False) -> dict[str, str]:
	"""Caller value, else the variable's default, else (previews only) its example. Blank means unset."""
	vals: dict[str, str] = {}
	for column in ("example", "default_value") if examples else ("default_value",):
		for row in template.get("variables") or []:
			key = (row.get("variable") or "").strip()
			if key and row.get(column) not in (None, ""):
				vals[key] = str(row[column])
	for k, v in (variables or {}).items():
		if v not in (None, ""):
			vals[str(k)] = str(v)
	return vals


def _in_html_tag(src: str, pos: int) -> bool:
	return src.rfind("<", 0, pos) > src.rfind(">", 0, pos)


def _substitute(
	src: str,
	vals: dict[str, str],
	convert: Callable[[str], str],
	missing: list[str],
	*,
	attr_aware: bool = False,
) -> str:
	def repl(m: re.Match) -> str:
		key, filt = m.group(1), m.group(2)
		if key not in vals:
			if key not in missing:
				missing.append(key)
			return ""
		value = quote(vals[key], safe="") if filt == "url" else vals[key]
		if attr_aware and _in_html_tag(m.string, m.start()):
			return _html_attr_escape(value, quote=True)
		return convert(value)

	return VAR_RE.sub(repl, src or "")


def _json_safe(s: str) -> str:
	return json.dumps(s)[1:-1]


def detect_variables(*texts: str) -> list[str]:
	"""Variable names used in the given texts, in first-seen order."""
	seen: list[str] = []
	for text in texts:
		for m in VAR_RE.finditer(text or ""):
			if m.group(1) not in seen:
				seen.append(m.group(1))
	return seen


def placeholder_problems(*texts: str) -> list[str]:
	"""``{{...}}`` groups that are not a valid placeholder (they would be sent literally)."""
	bad: list[str] = []
	for text in texts:
		for m in _ANY_PLACEHOLDER.finditer(text or ""):
			if not VAR_RE.fullmatch(m.group(0)) and m.group(0) not in bad:
				bad.append(m.group(0))
	return [f"{b} is not a valid placeholder (use {{{{name}}}} or {{{{name|url}}}})" for b in bad]


def button_problems(raw: Any) -> list[str]:
	"""Save-time check of a buttons JSON string: placeholders become a valid https URL, so
	``{"web_app": "{{url}}"}`` passes. The send-time render validates the real values strictly."""
	text = raw if isinstance(raw, str) else json.dumps(raw)
	spec, errors = telegram_buttons.validate(VAR_RE.sub(BUTTON_PROBE, text))
	return list(errors) or ([] if spec else ["no valid buttons"])


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


def render_values(
	template: dict,
	variables: dict | None = None,
	gateway: Any = None,
	*,
	sign: Callable[[str], str] | None = None,
	examples: bool = False,
) -> RenderedTemplate:
	"""THE render: a template as a plain dict (saved row or unsaved editor values) -> what will be sent.

	Pure (no doctype access). ``examples=True`` (previews) falls back to each variable's example."""
	mode = _mode(template, gateway)
	vals = _values(template, variables, examples)
	missing: list[str] = []
	errors: list[str] = []
	text = _substitute(
		template.get("body") or "", vals, _escaper(mode), missing, attr_aware=mode == MODE_HTML
	).strip()
	media = _media(template, errors)
	markup = _markup(template.get("buttons_json") or "", vals, sign, missing, errors)
	inline = bool(media and text and len(text) <= TELEGRAM_CAPTION_LIMIT and media["type"] not in _NO_CAPTION)
	if len(text) > TELEGRAM_TEXT_LIMIT:
		errors.append(f"text is {len(text)} chars (limit {TELEGRAM_TEXT_LIMIT})")
	if not text and not media:
		errors.append("template renders empty")
	return RenderedTemplate(
		text=text,
		parse_mode=mode,
		media=media,
		reply_markup=markup,
		caption_inline=inline,
		missing=missing,
		errors=errors,
	)


def render_template(
	name: str,
	variables: dict | None = None,
	gateway: Any = None,
	*,
	sign: Callable[[str], str] | None = None,
	strict: bool = False,
	examples: bool = False,
) -> RenderedTemplate:
	"""Render a saved template without sending. Raises TemplateError if not found / inactive / wrong
	gateway, or (strict) on missing variables."""
	template = _load(name)
	if not template:
		raise TemplateError(f"Telegram template not found: {name}")
	if not template.get("is_active", 1):
		raise TemplateError(f"Telegram template is inactive: {name}")
	gname = _gname(gateway)
	if template.get("gateway") and gname and template["gateway"] != gname:
		raise TemplateError(f"Template {name} belongs to gateway {template['gateway']}")
	r = render_values(template, variables, gateway, sign=sign, examples=examples)
	if strict and r.missing:
		raise TemplateError(f"Missing template variables: {', '.join(r.missing)}", r.missing)
	return r


def list_templates(gateway: Any = None) -> list[dict]:
	"""Active templates usable on ``gateway`` (templates with no gateway are global)."""
	return [r for r in _list_rows(_gname(gateway)) if r.get("is_active", 1)]


def preview_payload(r: RenderedTemplate, name: str = "") -> dict:
	"""The preview shape shared by the agent action and the management endpoint."""
	return {
		"template": name,
		"text": r.text,
		"parse_mode": r.parse_mode,
		"media": r.media,
		"split": r.split,
		"markup": r.reply_markup,
		"markup_json": json.dumps(r.reply_markup, sort_keys=True) if r.reply_markup else "",
		"missing": r.missing,
		"errors": r.errors,
	}


def preview_template(
	name: str, variables: dict | None = None, gateway: Any = None, *, examples: bool = False
) -> dict:
	"""No send. Callback payloads are shown unsigned (placeholder). ``examples`` (the editor UI) fills
	blanks with each variable's example; without it ``missing`` predicts exactly what a send would refuse."""
	return preview_payload(
		render_template(name, variables, gateway, sign=lambda p: p, examples=examples), name
	)


def preview_values(
	values: dict, variables: dict | None = None, gateway: Any = None, *, examples: bool = True
) -> dict:
	"""Preview of unsaved editor values: the same render as a saved template."""
	return preview_payload(render_values(values, variables, gateway, sign=lambda p: p, examples=examples))


def build_sender(gateway: Any) -> tuple[Any, Callable[[str], str]]:
	"""``(TelegramSender, callback signer for chat)`` on the gateway's own credentials."""
	from huf.ai.gateway_adapters.telegram_outbound import TelegramSender
	from huf.ai.gateway_webhook import get_gateway_adapter

	adapter = get_gateway_adapter(gateway)
	return TelegramSender(adapter.client), adapter.sign_callback_data


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
	silent: bool = False,
	protect: bool = False,
	sender: Any = None,
	sign: Callable[[str], str] | None = None,
	allow_missing: bool = False,
) -> dict:
	"""Render and send. Returns ``{message_ids, template, missing}``.

	``gateway`` is the Gateway document (its silent / protect-content / link-preview / parse-mode
	settings apply; ``silent`` / ``protect`` can only add to them). Without ``sender`` the gateway's own
	bot is used and callback buttons are signed for ``chat_id``.
	Refuses (TemplateError) on render errors, and on missing variables unless ``allow_missing``.
	Media + caption when the render says ``caption_inline``; otherwise media then text.
	The keyboard rides on the last message."""
	if sender is None:
		sender, signer = build_sender(gateway)
		sign = sign or (lambda payload: signer(payload, chat_id))
	r = render_template(name, variables, gateway, sign=sign)
	if r.errors:
		raise TemplateError("; ".join(r.errors), r.missing)
	if r.missing and not allow_missing:
		raise TemplateError(f"Missing template variables: {', '.join(r.missing)}", r.missing)
	opts = {
		"thread_id": thread_id,
		"silent": bool(silent or getattr(gateway, "telegram_silent_replies", 0)),
		"protect": bool(protect or getattr(gateway, "telegram_protect_content", 0)),
	}
	link_preview = getattr(gateway, "preview_url", None) == "On"  # Default (off) and Off send no previews
	ids: list = []
	text = r.text
	media = r.media
	if media:
		value: Any = media["value"]
		if media["source"] == "file_url":
			value = _file_bytes(value)
		extra = (
			{"caption": text, **({"parse_mode": r.parse_mode} if r.parse_mode else {})}
			if r.caption_inline
			else None
		)
		msgs = sender.send_media(
			media["type"],
			chat_id,
			value,
			reply_to=reply_to,
			extra=extra,
			markup=r.reply_markup if (r.caption_inline or not text) else None,
			**opts,
		)
		ids += _ids(msgs)
		if r.split:
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
