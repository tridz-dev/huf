# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Pure helpers for rich WhatsApp templates and outbound media.

No database or network access lives here. The module validates template
definitions against Meta's published limits, normalises them into the shape
the ``WhatsApp Templates`` doctype (frappe_whatsapp) stores, and builds the
Graph API ``components`` / media payloads for sends. Validation problems are
returned as a list of ``{"field", "code", "message"}`` dicts so callers can
return one structured error with every problem at once.

Each Meta rule below is tagged ``# verified: <url>`` (read on the official docs
on 2026-10-14) or ``# unverified (from memory)``.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from huf.ai.gateway_adapters import whatsapp_messages as wm

# verified: https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/components/ (body 1024, header text 60 / 1 variable, footer 60)
BODY_MAX = 1024
HEADER_TEXT_MAX = 60
FOOTER_MAX = 60  # verified: .../components/
# verified: .../components/ (button label 25, phone 20, URL 2000, copy-code example 20, 10 buttons total)
BUTTON_TEXT_MAX = 25
URL_MAX = 2000
PHONE_MAX = 20
COPY_CODE_EXAMPLE_MAX = 20
MAX_BUTTONS = 10
MAX_URL_BUTTONS = 2
MAX_PHONE_BUTTONS = 1
MAX_COPY_CODE_BUTTONS = 1
# The coupon docs say the copy-code label "cannot be customized" but do not name it.
COPY_CODE_LABEL = "Copy offer code"  # unverified (from memory)
MAX_CAPTION = 1024
MAX_PARAM_LEN = 1024

# verified: https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/time-to-live (utility 30..43200 s on Cloud API; -1 = 30 days; marketing is
# 43200..2592000 but only via the Marketing Messages API, so it is not accepted here)
TTL_MIN = 30
TTL_MAX = 43200
TTL_CATEGORIES = ("UTILITY",)

# Categories a template may be created in. AUTHENTICATION is deliberately rejected for now.
CATEGORIES = ("UTILITY", "MARKETING")

HEADER_TYPES = ("TEXT", "IMAGE", "VIDEO", "DOCUMENT", "LOCATION")
MEDIA_HEADER_TYPES = ("IMAGE", "VIDEO", "DOCUMENT")
BUTTON_TYPES = ("QUICK_REPLY", "URL", "PHONE_NUMBER", "COPY_CODE")
# Outbound free-form media kinds (sticker added by T5; limits live in whatsapp_messages)
MEDIA_KINDS = wm.MEDIA_KINDS
PARAMETER_FORMATS = ("POSITIONAL", "NAMED")

# API button type -> WhatsApp Button.button_type option
DOCTYPE_BUTTON_TYPE = {
	"QUICK_REPLY": "Quick Reply",
	"URL": "Visit Website",
	"PHONE_NUMBER": "Call Phone",
	"COPY_CODE": "Copy Code",  # unverified: frappe_whatsapp has no such option today
}
_BUTTON_ALIASES = {
	"QUICK_REPLY": "QUICK_REPLY",
	"QUICK REPLY": "QUICK_REPLY",
	"URL": "URL",
	"VISIT WEBSITE": "URL",
	"PHONE_NUMBER": "PHONE_NUMBER",
	"PHONE NUMBER": "PHONE_NUMBER",
	"CALL PHONE": "PHONE_NUMBER",
	"COPY_CODE": "COPY_CODE",
	"COPY CODE": "COPY_CODE",
}

_PLACEHOLDER_RE = re.compile(r"\{\{\s*(\d+)\s*\}\}")
_VAR_RE = re.compile(r"\{\{\s*([^{}\s]*)\s*\}\}")
_ANY_BRACES_RE = re.compile(r"\{\{|\}\}")
# verified: https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/overview/ (named: unique, lowercase letters and underscores); digits and the
# leading-letter rule are unverified (from memory)
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_PHONE_CLEAN_RE = re.compile(r"[\s\-().]")
_PHONE_RE = re.compile(r"^\+[1-9]\d{4,18}$")
_BAD_PARAM_RE = re.compile(r"[\n\r\t]| {4,}")
_EMAIL_RE = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
_DIGIT_RUN_RE = re.compile(r"\d{7,}")
_SAMPLE_SEP_RE = re.compile(r"[\s\-().+]")


def _e(field: str, code: str, message: str) -> dict[str, str]:
	return {"field": field, "code": code, "message": message}


def placeholders(text: str) -> list[int]:
	"""Numbered placeholders in order of first appearance (named ones are ignored)."""
	seen: list[int] = []
	for m in _PLACEHOLDER_RE.finditer(text or ""):
		n = int(m.group(1))
		if n not in seen:
			seen.append(n)
	return seen


def variables(text: str) -> list[str]:
	"""All variable tokens (``"1"`` or ``"first_name"``) in order of first appearance."""
	seen: list[str] = []
	for m in _VAR_RE.finditer(text or ""):
		if m.group(1) and m.group(1) not in seen:
			seen.append(m.group(1))
	return seen


def _check_variables(field: str, text: str, errors: list[dict[str, str]]) -> tuple[list[str], list[str]]:
	"""Validate the variables of one text; return ``(positional, named)`` tokens."""
	positional: list[str] = []
	named: list[str] = []
	if _ANY_BRACES_RE.search(_VAR_RE.sub("", text or "")) or "{{}}" in (text or ""):
		errors.append(_e(field, "bad_placeholder", "Variables must look like {{1}} or {{first_name}}."))
	for token in variables(text):
		if token.isdigit():
			positional.append(token)
		elif _NAME_RE.match(token):
			named.append(token)
		else:
			errors.append(
				_e(field, "invalid_variable_name", f"Variable name {token!r} must match ^[a-z][a-z0-9_]*$.")
			)
	if positional and named:
		errors.append(_e(field, "mixed_parameter_format", "Do not mix {{1}} and {{name}} variables in one template."))
	elif positional and sorted(int(p) for p in positional) != list(range(1, len(positional) + 1)):
		errors.append(_e(field, "placeholder_sequence", "Placeholders must be numbered {{1}}, {{2}}, ... without gaps."))
	return positional, named


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


def _parse_named_samples(field: str, raw: Any, errors: list[dict[str, str]]) -> dict[str, str] | None:
	"""``{name: example}`` dict, or list of ``{name, example}`` -> ordered dict; None when absent."""
	if raw in (None, "", [], {}):
		return None
	out: dict[str, str] = {}
	if isinstance(raw, dict):
		items = [{"name": k, "example": v} for k, v in raw.items()]
	elif isinstance(raw, (list, tuple)):
		items = list(raw)
	else:
		errors.append(_e(field, "invalid", "Named samples must be a list of {name, example} or a name->example map."))
		return None
	for i, item in enumerate(items):
		if not isinstance(item, dict):
			errors.append(_e(f"{field}[{i}]", "invalid", "Each named sample must be {name, example}."))
			continue
		name = str(item.get("name") or item.get("param_name") or "").strip()
		example = item.get("example") if item.get("example") is not None else item.get("value")
		if not name:
			errors.append(_e(f"{field}[{i}].name", "required", "Named sample needs a name."))
			continue
		out[name] = str(example if example is not None else "").strip()
	return out


def _personal_data(field: str, value: str, errors: list[dict[str, str]]) -> None:
	# Meta asks for examples without real customer data. The exact detector is ours.  # unverified (from memory)
	if _EMAIL_RE.search(value) or _DIGIT_RUN_RE.search(_SAMPLE_SEP_RE.sub("", value)):
		errors.append(
			_e(field, "sample_looks_like_personal_data", "Samples must not look like a phone number or email address.")
		)


def _ttl_value(payload: dict[str, Any]) -> Any:
	for key in ("ttl_seconds", "message_send_ttl_seconds"):
		if payload.get(key) is not None:
			return payload[key]
	return None


def validate_template_spec(payload: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
	"""Validate a template definition; return ``(normalised_spec, errors)``.

	``errors`` is a list of ``{field, code, message}``; wrap with :func:`validation_error`
	for the one-shot summary (``message`` = first error, ``errors`` = the full list).

	Accepted keys: ``template``/``body``; ``parameter_format`` (POSITIONAL|NAMED, inferred
	when omitted); ``sample_values`` (positional: comma string or list) or ``named_samples``
	(``[{name, example}]`` or ``{name: example}``); ``header`` (text, or a dict with
	``type``/``text``/``example``), ``header_type`` (TEXT|IMAGE|VIDEO|DOCUMENT|LOCATION),
	``sample`` (header variable example for TEXT; file reference for media), ``header_handle``
	(Meta upload handle for media), ``footer``, ``buttons`` (list of ``{type, text, url,
	phone_number, example}``), ``category`` (UTILITY|MARKETING) and ``ttl_seconds`` (UTILITY only).
	"""
	errors: list[dict[str, str]] = []
	payload = payload if isinstance(payload, dict) else {}

	# ---- category / ttl
	category = str(payload.get("category") or "").strip().upper()
	if category == "AUTHENTICATION":
		errors.append(_e("category", "category_not_supported", "Authentication templates are not supported yet."))
	elif category and category not in CATEGORIES:
		errors.append(_e("category", "invalid_category", f"Category must be one of {', '.join(CATEGORIES)}."))
	ttl = _ttl_value(payload)
	if ttl is not None:
		if isinstance(ttl, bool) or not isinstance(ttl, int):
			errors.append(_e("ttl_seconds", "invalid_ttl", "ttl_seconds must be an integer."))
		elif category not in TTL_CATEGORIES:
			errors.append(_e("ttl_seconds", "ttl_not_allowed", "ttl_seconds can only be set on UTILITY templates."))
		elif ttl != -1 and not TTL_MIN <= ttl <= TTL_MAX:
			errors.append(
				_e("ttl_seconds", "ttl_out_of_range", f"ttl_seconds must be {TTL_MIN}-{TTL_MAX} (or -1 for 30 days).")
			)

	# ---- body
	body = str(payload.get("template") if payload.get("template") is not None else payload.get("body") or "")
	if not body.strip():
		errors.append(_e("body", "required", "Body is required."))
	elif len(body) > BODY_MAX:
		errors.append(_e("body", "too_long", f"Body is {len(body)} characters; the limit is {BODY_MAX}."))
	body_pos, body_named = _check_variables("body", body, errors) if body else ([], [])
	body_vars = body_pos or body_named
	stripped_body = body.strip()
	# unverified (from memory): Meta rejects templates whose body starts or ends with a variable
	if body_vars and re.match(r"^\{\{[^{}]*\}\}", stripped_body):
		errors.append(_e("body", "body_starts_with_variable", "The body cannot start with a variable."))
	if body_vars and re.search(r"\{\{[^{}]*\}\}$", stripped_body):
		errors.append(_e("body", "body_ends_with_variable", "The body cannot end with a variable."))

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
	header_handle = str(payload.get("header_handle") or "").strip()
	header_pos: list[str] = []
	header_named: list[str] = []
	header_named_samples = _parse_named_samples("header_named_samples", payload.get("header_named_samples"), errors)
	if header_type and header_type not in HEADER_TYPES:
		errors.append(
			_e("header_type", "unsupported_header_type", f"Header type must be one of {', '.join(HEADER_TYPES)}.")
		)
	elif header_type == "TEXT":
		if not header_text.strip():
			errors.append(_e("header", "required", "A TEXT header needs header text."))
		else:
			if len(header_text) > HEADER_TEXT_MAX:
				errors.append(
					_e("header", "too_long", f"Header text is {len(header_text)} characters; the limit is {HEADER_TEXT_MAX}.")
				)
			header_pos, header_named = _check_variables("header", header_text, errors)
			hvars = header_pos or header_named
			if len(hvars) > 1:
				errors.append(_e("header", "too_many_variables", "A text header allows at most one variable."))
			elif len(hvars) == 1:
				if not header_sample and header_named_samples:
					header_sample = header_named_samples.get(hvars[0], "")
				if not header_sample:
					errors.append(_e("sample", "required", "A header with a variable needs one example value in 'sample'."))
				elif "," in header_sample and not header_named:
					errors.append(_e("sample", "sample_comma", "The header example must be a single value without commas."))
				else:
					_personal_data("sample", header_sample, errors)
			else:
				header_sample = ""
	elif header_type in MEDIA_HEADER_TYPES:
		if header_text.strip():
			errors.append(_e("header", "not_allowed", f"An {header_type} header carries media, not text."))
			header_text = ""
		if header_handle:
			pass  # an already-uploaded Meta handle satisfies the sample requirement
		elif not header_sample:
			errors.append(_e("sample", "required", f"An {header_type} header needs a sample file (URL or uploaded file path)."))
		elif not (is_http_url(header_sample) or header_sample.startswith(("/files/", "/private/files/"))):
			errors.append(_e("sample", "invalid_sample", "Sample must be an http(s) URL or an uploaded file path such as /files/x.png."))
	elif header_type == "LOCATION":
		# verified: https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/components/ (no creation parameters; coordinates are supplied at send time)
		if header_text.strip():
			errors.append(_e("header", "not_allowed", "A LOCATION header carries no text."))
		header_text = ""
		header_sample = ""
	else:
		header_text = ""
		header_sample = ""
	if header_type not in MEDIA_HEADER_TYPES:
		header_handle = ""

	# ---- parameter format
	declared = str(payload.get("parameter_format") or "").strip().upper()
	if declared and declared not in PARAMETER_FORMATS:
		errors.append(_e("parameter_format", "invalid_parameter_format", "parameter_format must be POSITIONAL or NAMED."))
		declared = ""
	has_named = bool(body_named or header_named)
	has_pos = bool(body_pos or header_pos)
	if has_named and has_pos and not any(e["code"] == "mixed_parameter_format" for e in errors):
		errors.append(_e("body", "mixed_parameter_format", "Do not mix {{1}} and {{name}} variables in one template."))
	parameter_format = declared or ("NAMED" if has_named else "POSITIONAL")
	if declared == "NAMED" and has_pos:
		errors.append(_e("parameter_format", "parameter_format_mismatch", "NAMED templates must use {{name}} variables."))
	elif declared == "POSITIONAL" and has_named:
		errors.append(_e("parameter_format", "parameter_format_mismatch", "POSITIONAL templates must use {{1}} variables."))

	# ---- body samples (every variable needs one)
	samples: list[str] = []
	named_samples: list[dict[str, str]] = []
	if body_vars:
		if body_named:
			provided = _parse_named_samples("named_samples", payload.get("named_samples"), errors)
			if provided is None:
				ordered = _split_samples(payload.get("sample_values"))
				if ordered and len(ordered) == len(body_named):
					provided = dict(zip(body_named, ordered))
			provided = provided or {}
			for name in provided:
				if name not in body_named:
					errors.append(_e(f"named_samples.{name}", "sample_unknown_variable", f"No variable {{{{{name}}}}} in the body."))
			for name in body_named:
				value = provided.get(name)
				if value is None:
					errors.append(_e(f"named_samples.{name}", "sample_missing", f"Variable {{{{{name}}}}} needs a sample value."))
				elif not value:
					errors.append(_e(f"named_samples.{name}", "sample_empty", f"Sample for {{{{{name}}}}} cannot be empty."))
				else:
					_personal_data(f"named_samples.{name}", value, errors)
					named_samples.append({"name": name, "example": value})
			samples = [s["example"] for s in named_samples]
		else:
			samples = _split_samples(payload.get("sample_values"))
			if len(samples) != len(body_pos):
				errors.append(
					_e("sample_values", "sample_count", f"Provide exactly {len(body_pos)} sample value(s) for the body placeholders.")
				)
			elif any(not s for s in samples):
				errors.append(_e("sample_values", "sample_empty", "Every body placeholder needs a non-empty sample value."))
			else:
				for i, s in enumerate(samples):
					_personal_data(f"sample_values[{i}]", s, errors)
			if isinstance(payload.get("sample_values"), (list, tuple)) and any(
				"," in str(s) for s in payload["sample_values"]
			):
				errors.append(_e("sample_values", "sample_comma", "Sample values cannot contain commas."))

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

	hvar = (header_pos or header_named or [""])[0] if header_type == "TEXT" else ""
	spec = {
		"body": body,
		"parameter_format": parameter_format,
		"sample_values": samples,
		"named_samples": named_samples,
		"header_type": header_type if header_type in HEADER_TYPES else "",
		"header_text": header_text,
		"header_sample": header_sample,
		"header_variable": hvar,
		"header_handle": header_handle,
		"footer": footer,
		"buttons": buttons,
		"category": category if category in CATEGORIES else "",
		"ttl_seconds": ttl if ttl is not None and not isinstance(ttl, bool) and isinstance(ttl, int) else None,
		"notes": [b["note"] for b in buttons if b.get("note")],
	}
	return spec, errors


def expand_url_example(prefix: str, example: str) -> tuple[str, str]:
	"""Full example URL for a dynamic URL button, plus a note when a bare suffix was expanded.

	``prefix`` is the button URL up to the variable. An example that is already absolute (has a
	scheme) is returned unchanged; a bare value (``abc123``) is appended to the prefix.
	"""
	example = (example or "").strip()
	if not example or "://" in example or not prefix:
		return example, ""
	full = prefix + (example[1:] if prefix.endswith("/") and example.startswith("/") else example)
	return full, f"The example '{example}' was expanded to the full URL {full} (Meta needs the whole URL)."


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
			errors.append(_e(f"{field}.type", "invalid_type", f"Button type must be one of {', '.join(BUTTON_TYPES)}."))
			continue
		text = str(item.get("text") or item.get("button_label") or "").strip()
		if btype == "COPY_CODE":
			text = COPY_CODE_LABEL  # label is fixed by Meta
		btn: dict[str, Any] = {"type": btype, "text": text}
		if not text:
			errors.append(_e(f"{field}.text", "required", "Button text is required."))
		elif len(text) > BUTTON_TEXT_MAX:
			errors.append(_e(f"{field}.text", "too_long", f"Button text is {len(text)} characters; the limit is {BUTTON_TEXT_MAX}."))
		if btype == "URL":
			url = str(item.get("url") or item.get("website_url") or "").strip()
			btn["url"] = url
			match = re.search(r"\{\{\s*([^{}\s]*)\s*\}\}$", url)
			prefix = url[: match.start()] if match else url
			tokens = variables(url)
			if not is_http_url(_VAR_RE.sub("", url)) and not is_http_url(url):
				errors.append(_e(f"{field}.url", "invalid_url", "URL must start with http:// or https://."))
			elif len(url) > URL_MAX:
				errors.append(_e(f"{field}.url", "too_long", f"URL is longer than {URL_MAX} characters."))
			dynamic = bool(tokens) or "{{" in url
			if dynamic:
				# verified: https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/components/ (one variable, appended at the end of the URL)
				token = match.group(1) if match else ""
				var_ok = bool(token) and (token == "1" or bool(_NAME_RE.match(token)))
				if not match or len(_VAR_RE.findall(url)) != 1 or _ANY_BRACES_RE.search(prefix) or not var_ok:
					errors.append(_e(f"{field}.url", "bad_placeholder", "A URL button allows a single {{1}} or {{name}} variable, at the very end."))
				example = str(item.get("example") or item.get("example_url") or "").strip()
				btn["example"] = example
				if not example:
					errors.append(_e(f"{field}.example", "required", "A dynamic URL needs an example full URL."))
				elif len(example) > URL_MAX:
					errors.append(_e(f"{field}.example", "too_long", f"The example URL is longer than {URL_MAX} characters."))
				elif "," in example:
					errors.append(_e(f"{field}.example", "sample_comma", "The example URL cannot contain commas."))
				else:
					full, note = expand_url_example(prefix, example)
					if note:
						btn["note"] = f"{field}: {note}"
					btn["example"] = full
					if not full.startswith("https://"):
						errors.append(_e(f"{field}.example", "invalid_example", "The example must be an absolute https URL, e.g. " + prefix + "abc123."))
					elif not full.startswith(prefix) or full == prefix:
						errors.append(_e(f"{field}.example", "invalid_example", f"The example must start with {prefix} and add a value for the variable."))
			btn["dynamic"] = dynamic
		elif btype == "PHONE_NUMBER":
			phone = _PHONE_CLEAN_RE.sub("", str(item.get("phone_number") or item.get("phone") or ""))
			if phone and not phone.startswith("+") and phone.isdigit():
				phone = "+" + phone
			btn["phone_number"] = phone
			if not _PHONE_RE.match(phone) or len(phone) > PHONE_MAX:
				errors.append(_e(f"{field}.phone_number", "invalid_phone", "Phone number must be in international format, e.g. +15551234567."))
		elif btype == "COPY_CODE":
			example = str(item.get("example") or item.get("code") or "").strip()
			btn["example"] = example
			if not example:
				errors.append(_e(f"{field}.example", "required", "A copy-code button needs an example code."))
			elif len(example) > COPY_CODE_EXAMPLE_MAX:  # verified: .../marketing-templates/coupon-templates
				errors.append(_e(f"{field}.example", "too_long", f"The example code is longer than {COPY_CODE_EXAMPLE_MAX} characters."))
		out.append(btn)

	count = lambda t: sum(1 for b in out if b["type"] == t)  # noqa: E731
	if len(out) > MAX_BUTTONS:
		errors.append(_e("buttons", "too_many_buttons", f"At most {MAX_BUTTONS} buttons are allowed."))
	if count("URL") > MAX_URL_BUTTONS:
		errors.append(_e("buttons", "too_many_url_buttons", f"At most {MAX_URL_BUTTONS} URL buttons are allowed."))
	if count("PHONE_NUMBER") > MAX_PHONE_BUTTONS:
		errors.append(_e("buttons", "too_many_phone_buttons", "Only one phone-number button is allowed."))
	if count("COPY_CODE") > MAX_COPY_CODE_BUTTONS:
		errors.append(_e("buttons", "too_many_copy_code_buttons", "Only one copy-code button is allowed."))
	kinds = [b["type"] == "QUICK_REPLY" for b in out]
	switches = sum(1 for a, b in zip(kinds, kinds[1:]) if a != b)
	if switches > 1:  # verified: .../components/ (quick replies grouped, other buttons grouped)
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
		elif b["type"] == "COPY_CODE":
			row["example_url"] = b.get("example") or ""
		rows.append(row)
	return rows


def build_meta_payload(spec: dict[str, Any], media_header: dict[str, Any] | None = None) -> dict[str, Any]:
	"""Create/edit body extras for a validated spec: ``components`` + top-level keys.

	``parameter_format`` is always set; ``message_send_ttl_seconds`` only when a TTL is
	set. ``media_header`` is a ready-made media HEADER component to reuse (an edit with an
	unchanged media header); otherwise ``spec["header_handle"]`` is used to build one.
	"""
	out: dict[str, Any] = {
		"parameter_format": spec.get("parameter_format") or "POSITIONAL",
		"components": build_meta_components(spec, media_header),
	}
	if spec.get("ttl_seconds") is not None:
		out["message_send_ttl_seconds"] = spec["ttl_seconds"]
	return out


def build_meta_components(spec: dict[str, Any], media_header: dict[str, Any] | None = None) -> list[dict[str, Any]]:
	"""FULL Graph ``components`` array for a validated spec (create or edit)."""
	named = spec.get("parameter_format") == "NAMED"
	body: dict[str, Any] = {"type": "BODY", "text": spec["body"]}
	if named and spec.get("named_samples"):
		body["example"] = {
			"body_text_named_params": [
				{"param_name": s["name"], "example": s["example"]} for s in spec["named_samples"]
			]
		}
	elif spec.get("sample_values"):
		body["example"] = {"body_text": [list(spec["sample_values"])]}
	components: list[dict[str, Any]] = []
	htype = spec.get("header_type")
	if htype == "TEXT":
		header: dict[str, Any] = {"type": "HEADER", "format": "TEXT", "text": spec["header_text"]}
		if spec.get("header_sample"):
			if named:
				header["example"] = {
					"header_text_named_params": [
						{"param_name": spec.get("header_variable") or "", "example": spec["header_sample"]}
					]
				}
			else:
				header["example"] = {"header_text": [spec["header_sample"]]}
		components.append(header)
	elif htype in MEDIA_HEADER_TYPES:
		if media_header:
			components.append(media_header)
		elif spec.get("header_handle"):
			components.append(
				{"type": "HEADER", "format": htype, "example": {"header_handle": [spec["header_handle"]]}}
			)
	elif htype == "LOCATION":
		components.append({"type": "HEADER", "format": "LOCATION"})
	components.append(body)
	if spec.get("footer"):
		components.append({"type": "FOOTER", "text": spec["footer"]})
	if spec.get("buttons"):
		buttons: list[dict[str, Any]] = []
		for b in spec["buttons"]:
			if b["type"] == "COPY_CODE":
				buttons.append({"type": "COPY_CODE", "example": b["example"]})  # no text: label is fixed
				continue
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
	"""Header parameters: one text string, or one ``{type, link, filename?}`` media dict
	(or ``{type: "location", latitude, longitude, name?, address?}`` for LOCATION headers)."""
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
			if kind == "location":
				try:
					loc: dict[str, Any] = {"latitude": float(item["latitude"]), "longitude": float(item["longitude"])}
				except (KeyError, TypeError, ValueError):
					errors.append(_e("header_params[0]", "invalid_location", "A location header needs numeric latitude and longitude."))
					continue
				for key in ("name", "address"):
					if item.get(key):
						loc[key] = str(item[key])
				out.append({"type": "location", "location": loc})
			elif kind not in ("image", "document", "video"):
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
			if kind == "location":
				components.append({"type": "header", "parameters": [{"type": "location", "location": item["location"]}]})
				continue
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


def _template_view(template: Any) -> dict[str, Any]:
	"""``{fmt, body_vars, header_vars, header_type}`` from a spec dict or a Meta components list."""
	body = header = htype = ""
	fmt = ""
	if isinstance(template, dict):
		body = str(template.get("body") or template.get("template") or "")
		header = str(template.get("header_text") or "")
		htype = str(template.get("header_type") or "").upper()
		fmt = str(template.get("parameter_format") or "").upper()
	else:
		for comp in template if isinstance(template, list) else []:
			if not isinstance(comp, dict):
				continue
			ctype = str(comp.get("type") or "").upper()
			if ctype == "BODY":
				body = str(comp.get("text") or "")
			elif ctype == "HEADER":
				htype = str(comp.get("format") or "TEXT").upper()
				header = str(comp.get("text") or "")
	body_vars, header_vars = variables(body), variables(header) if htype in ("", "TEXT") else []
	if fmt not in PARAMETER_FORMATS:
		fmt = "NAMED" if any(not v.isdigit() for v in body_vars + header_vars) else "POSITIONAL"
	return {"fmt": fmt, "body_vars": body_vars, "header_vars": header_vars, "header_type": htype}


def _named_values(field: str, raw: Any, names: list[str], errors: list[dict[str, str]]) -> list[tuple[str, Any]]:
	"""Resolve send values for ``names``: a dict / list of ``{name, value}`` / plain ordered list."""
	if isinstance(raw, dict):
		pairs = dict(raw)
	elif isinstance(raw, (list, tuple)) and raw and all(isinstance(x, dict) for x in raw):
		pairs = {
			str(x.get("name") or x.get("parameter_name") or ""): (x["value"] if "value" in x else x.get("text"))
			for x in raw
		}
	else:
		values = list(raw or [])
		if len(values) != len(names):
			errors.append(_e(field, "param_count_mismatch", f"This template takes {len(names)} named parameter(s); got {len(values)}."))
			return []
		return list(zip(names, values))
	for name in pairs:
		if name not in names:
			errors.append(_e(f"{field}.{name}", "param_unknown", f"No variable {{{{{name}}}}} in this template."))
	out = []
	for name in names:
		if name not in pairs:
			errors.append(_e(f"{field}.{name}", "param_missing", f"Variable {{{{{name}}}}} needs a value."))
		else:
			out.append((name, pairs[name]))
	return out


def build_send_components(
	template: Any,
	body_params: Any = None,
	header_params: Any = None,
	button_params: Any = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
	"""Graph ``template.components`` for a send, validating the raw parameters.

	``template`` is a validated spec or a Meta ``components`` list (``parameter_format`` is
	read from the spec, else inferred from the variables). For NAMED templates every body /
	text-header parameter carries ``parameter_name``; give ``body_params`` / ``header_params``
	as ``{name: value}``, ``[{name, value}]`` or an ordered list. Returns ``(components, errors)``.
	"""
	errors: list[dict[str, str]] = []
	view = _template_view(template)
	named = view["fmt"] == "NAMED"
	components: list[dict[str, Any]] = []

	# header
	if isinstance(header_params, dict) and "type" not in header_params:
		header_raw = [v for _, v in _named_values("header_params", header_params, view["header_vars"], errors)]
	else:
		header_raw = [header_params] if isinstance(header_params, dict) else list(header_params or [])
	if named and len(view["header_vars"]) == 1 and header_raw and not isinstance(header_raw[0], dict):
		text = validate_param_text("header_params[0]", header_raw[0], errors, HEADER_TEXT_MAX)
		components.append({
			"type": "header",
			"parameters": [{"type": "text", "parameter_name": view["header_vars"][0], "text": text}],
		})
	else:
		headers_n, herr = normalize_header_params(header_raw)
		errors += herr
		components += build_template_components(None, headers_n, None, view["header_type"].lower())

	# body
	if named and view["body_vars"]:
		params = []
		for name, value in _named_values("body_params", body_params, view["body_vars"], errors):
			text = validate_param_text(f"body_params.{name}", value, errors)
			params.append({"type": "text", "parameter_name": name, "text": text})
		components.append({"type": "body", "parameters": params})
	else:
		items = list(body_params.values()) if isinstance(body_params, dict) else list(body_params or [])
		texts = [validate_param_text(f"body_params[{i}]", v, errors) for i, v in enumerate(items)]
		if texts:
			components.append({"type": "body", "parameters": [{"type": "text", "text": t} for t in texts]})

	# buttons
	buttons_n, berr = normalize_button_params(button_params)
	errors += berr
	components += build_template_components(None, None, buttons_n)
	return components, errors


def validate_media_request(
	kind: Any, link: Any, media_id: Any, caption: Any, filename: Any, voice: Any = None
) -> tuple[dict[str, Any], list[dict[str, str]]]:
	"""Validate an outbound media send; returns the normalised request and errors (see whatsapp_messages)."""
	return wm.validate_media_message(kind, link, media_id, caption, filename, voice)


def build_media_payload(to: str, media: dict[str, Any], reply_to: str | None = None) -> dict[str, Any]:
	"""Graph ``/messages`` body for a validated media request (see :func:`validate_media_request`)."""
	return wm.build_media_message_payload(to, media, reply_to)


# Payload builders for the other outbound types: ``(payload, errors)``; implemented in whatsapp_messages.
build_sticker_payload = wm.build_sticker_payload
build_location_payload = wm.build_location_payload
build_contacts_payload = wm.build_contacts_payload
build_reaction_payload = wm.build_reaction_payload
build_reply_buttons_payload = wm.build_reply_buttons_payload
build_list_payload = wm.build_list_payload
build_cta_url_payload = wm.build_cta_url_payload
build_location_request_payload = wm.build_location_request_payload
build_flow_payload = wm.build_flow_payload
build_interactive_payload = wm.build_interactive_payload


def validation_error(errors: list[dict[str, str]]) -> dict[str, Any]:
	"""The structured error returned for any validation failure."""
	first = errors[0]["message"] if errors else "Validation failed."
	return {"success": False, "error": "validation_failed", "message": first, "errors": errors}
