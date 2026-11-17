# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Template send-parameter normalisers. Split from whatsapp_templates."""

from __future__ import annotations

import re
from typing import Any

from huf.ai.gateway_adapters import whatsapp_templates as wt


def validate_param_text(field: str, value: Any, errors: list[dict[str, str]], limit: int = wt.MAX_PARAM_LEN) -> str:
	text = str(value if value is not None else "")
	if not text.strip():
		errors.append(wt._e(field, "empty_param", "Template parameters cannot be empty."))
	elif len(text) > limit:
		errors.append(wt._e(field, "too_long", f"Parameter is longer than {limit} characters."))
	elif wt._BAD_PARAM_RE.search(text):
		errors.append(wt._e(field, "bad_param", "Template parameters cannot contain newlines, tabs or 4+ consecutive spaces."))
	return text


def normalize_header_params(header_params: Any) -> tuple[list[Any], list[dict[str, str]]]:
	"""Header parameters: one text string, or one ``{type, link, filename?}`` media dict
	(or ``{type: "location", latitude, longitude, name?, address?}`` for LOCATION headers)."""
	errors: list[dict[str, str]] = []
	items = list(header_params or [])
	if len(items) > 1:
		errors.append(wt._e("header_params", "too_many", "A template header takes at most one parameter."))
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
					errors.append(wt._e("header_params[0]", "invalid_location", "A location header needs numeric latitude and longitude."))
					continue
				for key in ("name", "address"):
					if item.get(key):
						loc[key] = str(item[key])
				out.append({"type": "location", "location": loc})
			elif kind not in ("image", "document", "video"):
				errors.append(wt._e("header_params[0].type", "invalid_type", "Media header type must be image, document or video."))
			elif kind == "document" and str(item.get("file") or "").strip() and not link:
				# private Frappe File: uploaded to Meta media at send time and sent by id
				doc_file: dict[str, Any] = {"type": "document", "file": str(item["file"]).strip()}
				if item.get("filename"):
					doc_file["filename"] = str(item["filename"])[:240]
				out.append(doc_file)
			elif not wt.is_http_url(link):
				errors.append(wt._e("header_params[0].link", "invalid_link", "Media header needs an http(s) link."))
			else:
				media: dict[str, Any] = {"type": kind, "link": link}
				if kind == "document" and item.get("filename"):
					media["filename"] = str(item["filename"])[:240]
				out.append(media)
		elif isinstance(item, str) and wt.is_http_url(item.strip()):
			out.append({"type": "", "link": item.strip()})  # kind resolved from the template
		else:
			out.append(validate_param_text("header_params[0]", item, errors, wt.HEADER_TEXT_MAX))
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
				errors.append(wt._e(f"{field}.index", "invalid_index", "Button index must be an integer 0-9."))
				continue
			value = item.get("text") if item.get("text") is not None else item.get("payload")
		else:
			sub, index, value = "url", i, item
		if sub not in ("url", "quick_reply"):
			errors.append(wt._e(f"{field}.sub_type", "invalid_type", "Button parameter type must be url or quick_reply."))
			continue
		if not 0 <= index <= 9:
			errors.append(wt._e(f"{field}.index", "invalid_index", "Button index must be an integer 0-9."))
			continue
		text = validate_param_text(field, value, errors, wt.URL_MAX if sub == "url" else 256)
		out.append({"index": index, "sub_type": sub, "text": text})
	return out, errors
