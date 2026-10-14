# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Pure helpers for rich WhatsApp templates and outbound media.

No database or network access lives here. The module validates template
definitions against Meta's published limits, normalises them into the shape
the ``WhatsApp Templates`` doctype (frappe_whatsapp) stores, and builds the
Graph API ``components`` / media payloads for sends. Validation problems are
returned as a list of ``{"field", "code", "message"}`` dicts so callers can
return one structured error with every problem at once.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

BODY_MAX = 1024
HEADER_TEXT_MAX = 60
FOOTER_MAX = 60
BUTTON_TEXT_MAX = 25
URL_MAX = 2000
PHONE_MAX = 20
MAX_QUICK_REPLIES = 3
MAX_CTA_BUTTONS = 2
MAX_PHONE_BUTTONS = 1
MAX_CAPTION = 1024
MAX_PARAM_LEN = 1024

# header_type values defined by the WhatsApp Templates doctype (no VIDEO option).
HEADER_TYPES = ("TEXT", "IMAGE", "DOCUMENT")
MEDIA_HEADER_TYPES = ("IMAGE", "DOCUMENT")
BUTTON_TYPES = ("QUICK_REPLY", "URL", "PHONE_NUMBER")
MEDIA_KINDS = ("image", "document", "audio", "video")

# API button type -> WhatsApp Button.button_type option
DOCTYPE_BUTTON_TYPE = {"QUICK_REPLY": "Quick Reply", "URL": "Visit Website", "PHONE_NUMBER": "Call Phone"}
_BUTTON_ALIASES = {
	"QUICK_REPLY": "QUICK_REPLY",
	"QUICK REPLY": "QUICK_REPLY",
	"URL": "URL",
	"VISIT WEBSITE": "URL",
	"PHONE_NUMBER": "PHONE_NUMBER",
	"PHONE NUMBER": "PHONE_NUMBER",
	"CALL PHONE": "PHONE_NUMBER",
}

_PLACEHOLDER_RE = re.compile(r"\{\{\s*(\d+)\s*\}\}")
_ANY_BRACES_RE = re.compile(r"\{\{|\}\}")
_PHONE_CLEAN_RE = re.compile(r"[\s\-().]")
_PHONE_RE = re.compile(r"^\+[1-9]\d{4,18}$")
_BAD_PARAM_RE = re.compile(r"[\n\r\t]| {4,}")


def _e(field: str, code: str, message: str) -> dict[str, str]:
	return {"field": field, "code": code, "message": message}


def placeholders(text: str) -> list[int]:
	"""Placeholder numbers in order of first appearance."""
	seen: list[int] = []
	for m in _PLACEHOLDER_RE.finditer(text or ""):
		n = int(m.group(1))
		if n not in seen:
			seen.append(n)
	return seen


def _check_variables(field: str, text: str, errors: list[dict[str, str]]) -> list[int]:
	holes = placeholders(text)
	stripped = _PLACEHOLDER_RE.sub("", text or "")
	if _ANY_BRACES_RE.search(stripped):
		errors.append(_e(field, "bad_placeholder", "Placeholders must look like {{1}}."))
	if sorted(holes) != list(range(1, len(holes) + 1)):
		errors.append(_e(field, "placeholder_sequence", "Placeholders must be numbered {{1}}, {{2}}, ... without gaps."))
	return holes


def is_http_url(value: str) -> bool:
	parsed = urlparse(str(value or ""))
	return parsed.scheme in ("http", "https") and bool(parsed.hostname)


def _split_samples(raw: Any) -> list[str]:
	if raw is None:
		return []
	if isinstance(raw, (list, tuple)):
		return [str(s).strip() for s in raw]
	text = str(raw).strip()
	return [s.strip() for s in text.split(",")] if text else []


def normalize_button_type(raw: Any) -> str | None:
	return _BUTTON_ALIASES.get(str(raw or "").strip().upper().replace("-", "_"))


def validate_template_spec(payload: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
	"""Validate a template definition; return ``(normalised_spec, errors)``.

	Accepted payload keys (flat, mirroring the doctype): ``template``/``body``,
	``sample_values`` (comma string or list), ``header`` (text, or a dict with
	``type``/``text``/``example``), ``header_type``, ``sample`` (header sample:
	example text for TEXT, file reference for IMAGE/DOCUMENT), ``footer`` and
	``buttons`` (list of ``{type, text, url, phone_number, example}``).
	"""
	errors: list[dict[str, str]] = []

	body = str(payload.get("template") if payload.get("template") is not None else payload.get("body") or "")
	if not body.strip():
		errors.append(_e("body", "required", "Body is required."))
	elif len(body) > BODY_MAX:
		errors.append(_e("body", "too_long", f"Body is {len(body)} characters; the limit is {BODY_MAX}."))
	body_holes = _check_variables("body", body, errors) if body else []
	samples = _split_samples(payload.get("sample_values"))
	if body_holes:
		if len(samples) != len(body_holes):
			errors.append(
				_e("sample_values", "sample_count", f"Provide exactly {len(body_holes)} sample value(s) for the body placeholders.")
			)
		elif any(not s for s in samples):
			errors.append(_e("sample_values", "sample_empty", "Every body placeholder needs a non-empty sample value."))
	if isinstance(payload.get("sample_values"), (list, tuple)):
		if any("," in str(s) for s in payload["sample_values"]):
			errors.append(_e("sample_values", "sample_comma", "Sample values cannot contain commas."))
	elif not body_holes and samples:
		samples = []  # stray samples without placeholders are dropped

	# ---- header
	header_raw = payload.get("header")
	header_type = str(payload.get("header_type") or "").strip().upper()
	header_text = ""
	header_sample = str(payload.get("sample") or "").strip()
	if isinstance(header_raw, dict):
		header_type = str(header_raw.get("type") or header_raw.get("format") or header_type).strip().upper()
		header_text = str(header_raw.get("text") or "")
		header_sample = str(header_raw.get("example") or header_raw.get("sample") or header_sample).strip()
	elif header_raw not in (None, ""):
		header_text = str(header_raw)
		header_type = header_type or "TEXT"
	if header_text and not header_type:
		header_type = "TEXT"
	if header_type and header_type not in HEADER_TYPES:
		hint = " (VIDEO headers are not supported by the WhatsApp Templates doctype)" if header_type == "VIDEO" else ""
		errors.append(
			_e("header_type", "unsupported_header_type", f"Header type must be one of {', '.join(HEADER_TYPES)}{hint}.")
		)
	elif header_type == "TEXT":
		if not header_text.strip():
			errors.append(_e("header", "required", "A TEXT header needs header text."))
		else:
			if len(header_text) > HEADER_TEXT_MAX:
				errors.append(
					_e("header", "too_long", f"Header text is {len(header_text)} characters; the limit is {HEADER_TEXT_MAX}.")
				)
			holes = _check_variables("header", header_text, errors)
			if len(holes) > 1:
				errors.append(_e("header", "too_many_variables", "A text header allows at most one variable."))
			elif len(holes) == 1:
				if not header_sample:
					errors.append(_e("sample", "required", "A header with a variable needs one example value in 'sample'."))
				elif ", " in header_sample or "," in header_sample:
					errors.append(_e("sample", "sample_comma", "The header example must be a single value without commas."))
			else:
				header_sample = ""
	elif header_type in MEDIA_HEADER_TYPES:
		if header_text.strip():
			errors.append(_e("header", "not_allowed", f"An {header_type} header carries media, not text."))
			header_text = ""
		if not header_sample:
			errors.append(_e("sample", "required", f"An {header_type} header needs a sample file (URL or uploaded file path)."))
		elif not (is_http_url(header_sample) or header_sample.startswith("/files/") or header_sample.startswith("/private/files/")):
			errors.append(_e("sample", "invalid_sample", "Sample must be an http(s) URL or an uploaded file path such as /files/x.png."))
	else:
		header_text = ""
		header_sample = ""

	# ---- footer
	footer = str(payload.get("footer") or "")
	if footer:
		if len(footer) > FOOTER_MAX:
			errors.append(_e("footer", "too_long", f"Footer is {len(footer)} characters; the limit is {FOOTER_MAX}."))
		if "{{" in footer:
			errors.append(_e("footer", "no_variables", "Footers cannot contain variables."))

	# ---- buttons
	buttons, button_errors = _validate_buttons(payload.get("buttons"))
	errors.extend(button_errors)

	spec = {
		"body": body,
		"sample_values": samples if body_holes else [],
		"header_type": header_type if header_type in HEADER_TYPES else "",
		"header_text": header_text,
		"header_sample": header_sample,
		"footer": footer,
		"buttons": buttons,
	}
	return spec, errors


def _validate_buttons(raw: Any) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
	errors: list[dict[str, str]] = []
	if raw in (None, "", []):
		return [], errors
	if not isinstance(raw, (list, tuple)):
		return [], [_e("buttons", "invalid", "buttons must be a list.")]
	out: list[dict[str, Any]] = []
	for i, item in enumerate(raw):
		field = f"buttons[{i}]"
		if not isinstance(item, dict):
			errors.append(_e(field, "invalid", "Each button must be an object."))
			continue
		btype = normalize_button_type(item.get("type") or item.get("button_type"))
		if not btype:
			errors.append(_e(f"{field}.type", "invalid_type", "Button type must be QUICK_REPLY, URL or PHONE_NUMBER."))
			continue
		text = str(item.get("text") or item.get("button_label") or "").strip()
		btn: dict[str, Any] = {"type": btype, "text": text}
		if not text:
			errors.append(_e(f"{field}.text", "required", "Button text is required."))
		elif len(text) > BUTTON_TEXT_MAX:
			errors.append(_e(f"{field}.text", "too_long", f"Button text is {len(text)} characters; the limit is {BUTTON_TEXT_MAX}."))
		if btype == "URL":
			url = str(item.get("url") or item.get("website_url") or "").strip()
			btn["url"] = url
			dynamic_holes = placeholders(url)
			if not is_http_url(url.replace("{{1}}", "")) and not is_http_url(url):
				errors.append(_e(f"{field}.url", "invalid_url", "URL must start with http:// or https://."))
			elif len(url) > URL_MAX:
				errors.append(_e(f"{field}.url", "too_long", f"URL is longer than {URL_MAX} characters."))
			if dynamic_holes:
				stripped = _PLACEHOLDER_RE.sub("", url)
				if dynamic_holes != [1] or len(_PLACEHOLDER_RE.findall(url)) != 1 or not url.endswith("{{1}}") or _ANY_BRACES_RE.search(stripped):
					errors.append(_e(f"{field}.url", "bad_placeholder", "A URL button allows a single {{1}} placeholder, at the very end."))
				example = str(item.get("example") or item.get("example_url") or "").strip()
				btn["example"] = example
				prefix = url[: -len("{{1}}")]
				if not example:
					errors.append(_e(f"{field}.example", "required", "A dynamic URL needs an example full URL."))
				elif "," in example:
					errors.append(_e(f"{field}.example", "sample_comma", "The example URL cannot contain commas."))
				elif not example.startswith(prefix) or example == prefix:
					errors.append(_e(f"{field}.example", "invalid_example", "The example must start with the URL prefix and add a value for {{1}}."))
			btn["dynamic"] = bool(dynamic_holes)
		elif btype == "PHONE_NUMBER":
			phone = _PHONE_CLEAN_RE.sub("", str(item.get("phone_number") or item.get("phone") or ""))
			if phone and not phone.startswith("+") and phone.isdigit():
				phone = "+" + phone
			btn["phone_number"] = phone
			if not _PHONE_RE.match(phone) or len(phone) > PHONE_MAX:
				errors.append(_e(f"{field}.phone_number", "invalid_phone", "Phone number must be in international format, e.g. +15551234567."))
		out.append(btn)

	quick = [b for b in out if b["type"] == "QUICK_REPLY"]
	cta = [b for b in out if b["type"] != "QUICK_REPLY"]
	if len(quick) > MAX_QUICK_REPLIES:
		errors.append(_e("buttons", "too_many_quick_replies", f"At most {MAX_QUICK_REPLIES} quick-reply buttons are allowed."))
	if len(cta) > MAX_CTA_BUTTONS:
		errors.append(_e("buttons", "too_many_cta_buttons", f"At most {MAX_CTA_BUTTONS} call-to-action (URL/phone) buttons are allowed."))
	if sum(1 for b in cta if b["type"] == "PHONE_NUMBER") > MAX_PHONE_BUTTONS:
		errors.append(_e("buttons", "too_many_phone_buttons", "Only one phone-number button is allowed."))
	kinds = [b["type"] == "QUICK_REPLY" for b in out]
	switches = sum(1 for a, b in zip(kinds, kinds[1:]) if a != b)
	if switches > 1:
		errors.append(_e("buttons", "buttons_not_grouped", "Quick-reply buttons and call-to-action buttons must each be grouped together."))
	return out, errors


def button_rows(spec: dict[str, Any]) -> list[dict[str, Any]]:
	"""Map normalised buttons onto ``WhatsApp Button`` child rows (frappe_whatsapp field names)."""
	rows = []
	for i, b in enumerate(spec.get("buttons") or [], start=1):
		row: dict[str, Any] = {
			"button_type": DOCTYPE_BUTTON_TYPE[b["type"]],
			"button_label": b["text"],
			"sequence": i,
		}
		if b["type"] == "URL":
			row["website_url"] = b["url"]
			row["url_type"] = "Dynamic" if b.get("dynamic") else "Static"
			if b.get("dynamic"):
				row["example_url"] = b.get("example") or ""
		elif b["type"] == "PHONE_NUMBER":
			row["phone_number"] = b["phone_number"]
		rows.append(row)
	return rows


def build_meta_components(spec: dict[str, Any], media_header: dict[str, Any] | None = None) -> list[dict[str, Any]]:
	"""FULL Graph ``components`` array for a validated spec (create or edit).

	``media_header`` is a ready-made IMAGE/DOCUMENT header component (with its upload
	handle) to reuse; media headers cannot be rebuilt without a fresh upload.
	"""
	body: dict[str, Any] = {"type": "BODY", "text": spec["body"]}
	if spec.get("sample_values"):
		body["example"] = {"body_text": [list(spec["sample_values"])]}
	components: list[dict[str, Any]] = []
	htype = spec.get("header_type")
	if htype == "TEXT":
		header: dict[str, Any] = {"type": "HEADER", "format": "TEXT", "text": spec["header_text"]}
		if spec.get("header_sample"):
			header["example"] = {"header_text": [spec["header_sample"]]}
		components.append(header)
	elif htype in MEDIA_HEADER_TYPES and media_header:
		components.append(media_header)
	components.append(body)
	if spec.get("footer"):
		components.append({"type": "FOOTER", "text": spec["footer"]})
	if spec.get("buttons"):
		buttons: list[dict[str, Any]] = []
		for b in spec["buttons"]:
			out: dict[str, Any] = {"type": b["type"], "text": b["text"]}
			if b["type"] == "URL":
				out["url"] = b["url"]
				if b.get("dynamic") and b.get("example"):
					out["example"] = [b["example"]]
			elif b["type"] == "PHONE_NUMBER":
				out["phone_number"] = b["phone_number"]
			buttons.append(out)
		components.append({"type": "BUTTONS", "buttons": buttons})
	return components


def components_to_view(components: Any) -> dict[str, Any]:
	"""Meta components -> ``{header, body, footer, buttons}`` for display (defensive)."""
	view: dict[str, Any] = {"header": None, "body": None, "footer": None, "buttons": []}
	for comp in components if isinstance(components, list) else []:
		if not isinstance(comp, dict):
			continue
		ctype = str(comp.get("type") or "").upper()
		if ctype == "HEADER":
			view["header"] = {"type": str(comp.get("format") or "TEXT").upper(), "text": comp.get("text") or ""}
		elif ctype == "BODY":
			ex = (comp.get("example") or {}).get("body_text")
			view["body"] = {"text": comp.get("text") or "", "sample_values": list(ex[0]) if ex and isinstance(ex[0], list) else []}
		elif ctype == "FOOTER":
			view["footer"] = {"text": comp.get("text") or ""}
		elif ctype == "BUTTONS":
			for btn in comp.get("buttons") or []:
				if isinstance(btn, dict):
					view["buttons"].append(
						{k: btn.get(k) for k in ("type", "text", "url", "phone_number", "example") if btn.get(k) is not None}
					)
	return view


# --------------------------------------------------------------------- sends
def validate_param_text(field: str, value: Any, errors: list[dict[str, str]], limit: int = MAX_PARAM_LEN) -> str:
	text = str(value if value is not None else "")
	if not text.strip():
		errors.append(_e(field, "empty_param", "Template parameters cannot be empty."))
	elif len(text) > limit:
		errors.append(_e(field, "too_long", f"Parameter is longer than {limit} characters."))
	elif _BAD_PARAM_RE.search(text):
		errors.append(_e(field, "bad_param", "Template parameters cannot contain newlines, tabs or 4+ consecutive spaces."))
	return text


def normalize_header_params(header_params: Any) -> tuple[list[Any], list[dict[str, str]]]:
	"""Header parameters: one text string, or one ``{type, link, filename?}`` media dict."""
	errors: list[dict[str, str]] = []
	items = list(header_params or [])
	if len(items) > 1:
		errors.append(_e("header_params", "too_many", "A template header takes at most one parameter."))
		return [], errors
	out: list[Any] = []
	for item in items:
		if isinstance(item, dict):
			kind = str(item.get("type") or "").lower()
			link = str(item.get("link") or "").strip()
			if kind not in ("image", "document", "video"):
				errors.append(_e("header_params[0].type", "invalid_type", "Media header type must be image, document or video."))
			elif not is_http_url(link):
				errors.append(_e("header_params[0].link", "invalid_link", "Media header needs an http(s) link."))
			else:
				media: dict[str, Any] = {"type": kind, "link": link}
				if kind == "document" and item.get("filename"):
					media["filename"] = str(item["filename"])[:240]
				out.append(media)
		elif isinstance(item, str) and is_http_url(item.strip()):
			out.append({"type": "", "link": item.strip()})  # kind resolved from the template
		else:
			out.append(validate_param_text("header_params[0]", item, errors, HEADER_TEXT_MAX))
	return out, errors


def normalize_button_params(button_params: Any) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
	"""Button parameters.

	Each entry is ``{"index": 0, "sub_type": "url"|"quick_reply", "text": suffix}``
	(``payload`` for quick replies). A bare string means the URL suffix of the
	button at that list position.
	"""
	errors: list[dict[str, str]] = []
	out: list[dict[str, Any]] = []
	for i, item in enumerate(button_params or []):
		field = f"button_params[{i}]"
		if isinstance(item, dict):
			sub = str(item.get("sub_type") or item.get("type") or "url").lower()
			try:
				index = int(item.get("index", i))
			except (TypeError, ValueError):
				errors.append(_e(f"{field}.index", "invalid_index", "Button index must be an integer 0-9."))
				continue
			value = item.get("text") if item.get("text") is not None else item.get("payload")
		else:
			sub, index, value = "url", i, item
		if sub not in ("url", "quick_reply"):
			errors.append(_e(f"{field}.sub_type", "invalid_type", "Button parameter type must be url or quick_reply."))
			continue
		if not 0 <= index <= 9:
			errors.append(_e(f"{field}.index", "invalid_index", "Button index must be an integer 0-9."))
			continue
		text = validate_param_text(field, value, errors, URL_MAX if sub == "url" else 256)
		out.append({"index": index, "sub_type": sub, "text": text})
	return out, errors


def build_template_components(
	body_params: list[Any] | None = None,
	header_params: list[Any] | None = None,
	button_params: list[dict[str, Any]] | None = None,
	header_type: str | None = None,
	always_body: bool = False,
) -> list[dict[str, Any]]:
	"""Graph ``template.components`` for a send. ``header_params`` must already be normalised."""
	components: list[dict[str, Any]] = []
	for item in header_params or []:
		if isinstance(item, dict):
			kind = item.get("type") or (header_type or "").lower()
			media: dict[str, Any] = {"link": item["link"]}
			if kind == "document" and item.get("filename"):
				media["filename"] = item["filename"]
			components.append({"type": "header", "parameters": [{"type": kind, kind: media}]})
		else:
			components.append({"type": "header", "parameters": [{"type": "text", "text": str(item)}]})
	if body_params or always_body:
		components.append(
			{"type": "body", "parameters": [{"type": "text", "text": str(p)} for p in (body_params or [])]}
		)
	for bp in button_params or []:
		param = (
			{"type": "payload", "payload": bp["text"]}
			if bp["sub_type"] == "quick_reply"
			else {"type": "text", "text": bp["text"]}
		)
		components.append(
			{"type": "button", "sub_type": bp["sub_type"], "index": str(bp["index"]), "parameters": [param]}
		)
	return components


def validate_media_request(
	kind: Any, link: Any, media_id: Any, caption: Any, filename: Any
) -> tuple[dict[str, Any], list[dict[str, str]]]:
	"""Validate an outbound media send; returns the normalised request and errors."""
	errors: list[dict[str, str]] = []
	kind = str(kind or "").strip().lower()
	link = str(link or "").strip()
	media_id = str(media_id or "").strip()
	caption = str(caption or "")
	filename = str(filename or "").strip()
	if kind not in MEDIA_KINDS:
		errors.append(_e("kind", "invalid_kind", f"Media kind must be one of {', '.join(MEDIA_KINDS)}."))
	if bool(link) == bool(media_id):
		errors.append(_e("link", "link_or_id", "Provide exactly one of link or media_id."))
	elif link and not is_http_url(link):
		errors.append(_e("link", "invalid_link", "Media link must be a public http(s) URL."))
	if caption and kind == "audio":
		errors.append(_e("caption", "not_allowed", "Audio messages cannot have a caption."))
	if len(caption) > MAX_CAPTION:
		errors.append(_e("caption", "too_long", f"Caption is longer than {MAX_CAPTION} characters."))
	if filename and kind != "document":
		filename = ""  # only documents carry a filename
	return {"kind": kind, "link": link, "media_id": media_id, "caption": caption, "filename": filename}, errors


def build_media_payload(to: str, media: dict[str, Any], reply_to: str | None = None) -> dict[str, Any]:
	"""Graph ``/messages`` body for a validated media request (see :func:`validate_media_request`)."""
	kind = media["kind"]
	obj: dict[str, Any] = {"id": media["media_id"]} if media.get("media_id") else {"link": media["link"]}
	if media.get("caption") and kind != "audio":
		obj["caption"] = media["caption"]
	if media.get("filename") and kind == "document":
		obj["filename"] = media["filename"]
	data: dict[str, Any] = {
		"messaging_product": "whatsapp",
		"recipient_type": "individual",
		"to": to,
		"type": kind,
		kind: obj,
	}
	if reply_to:
		data["context"] = {"message_id": reply_to}
	return data


def validation_error(errors: list[dict[str, str]]) -> dict[str, Any]:
	"""The structured error returned for any validation failure."""
	first = errors[0]["message"] if errors else "Validation failed."
	return {"success": False, "error": "validation_failed", "message": first, "errors": errors}
