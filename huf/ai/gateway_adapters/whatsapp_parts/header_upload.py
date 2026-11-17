# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Header / carousel-card sample reading and Meta resumable upload, split out of ``whatsapp_bridge``."""

from __future__ import annotations

import mimetypes
import os
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import frappe

from huf.ai.gateway_adapters import whatsapp_bridge as wb
from huf.ai.gateway_adapters import whatsapp_templates as wt


_MB = 1024 * 1024
_MEDIA_MIME_PREFIXES = {"IMAGE": ("image/",), "VIDEO": ("video/",), "DOCUMENT": ("application/", "text/")}
_HEADER_SAMPLE_LIMITS = {"IMAGE": 5 * _MB, "VIDEO": 16 * _MB, "DOCUMENT": 100 * _MB}


def _read_header_sample(
	sample: str, header_type: str, http_get: Callable[..., Any] | None = None
) -> tuple[bytes, str]:
	"""Bytes and MIME type of a media header sample: a public URL or an uploaded Frappe File."""
	import mimetypes

	if wt.is_http_url(sample):
		resp = wb._fetch_sample(sample, http_get or wb._default_get)
		content = resp.content
		mime = str((getattr(resp, "headers", None) or {}).get("Content-Type") or "").split(";")[0].strip().lower()
		mime = mime or (mimetypes.guess_type(urlparse(sample).path)[0] or "")
	else:
		name = frappe.db.get_value("File", {"file_url": sample}, "name")
		if not name:
			raise wb._sample_problem("sample_not_found", "No uploaded file matches this sample path.")
		content = frappe.get_doc("File", name).get_content()
		if isinstance(content, str):
			content = content.encode()
		mime = mimetypes.guess_type(sample)[0] or ""
	if not mime.startswith(_MEDIA_MIME_PREFIXES[header_type]):
		raise wb._sample_problem("invalid_sample", f"The sample is {mime or 'of unknown type'}, not an {header_type} file.")
	if not content:
		raise wb._sample_problem("invalid_sample", "The sample file is empty.")
	if len(content) > _HEADER_SAMPLE_LIMITS[header_type]:
		raise wb._sample_problem("sample_too_large", f"The {header_type} sample is larger than {_HEADER_SAMPLE_LIMITS[header_type] // _MB} MB.")
	return content, mime


def _upload_file_name(sample: str, mime: str) -> str:
	"""``file_name`` query param of the upload session (documented as required)."""
	base = os.path.basename(urlparse(sample).path) if wt.is_http_url(sample) else os.path.basename(sample)
	base = re.sub(r"[^A-Za-z0-9._-]", "_", base)[:100]
	return base or "sample" + (mimetypes.guess_extension(mime) or "")


def upload_header_handle(
	acct: dict[str, Any],
	header_type: str,
	sample: str,
	http_post: Callable[..., Any] | None = None,
	http_get: Callable[..., Any] | None = None,
) -> str:
	"""Meta resumable upload of a header sample; returns the ``header_handle`` (``h``).

	Two calls, as in Meta's Resumable Upload API: ``POST /{app_id}/uploads`` opens a session
	(file length and type), ``POST /{session id}`` with the raw bytes returns the handle. Raises
	:class:`wb.BridgeError` (validation error for a bad sample, ``upload_failed`` for a Meta refusal).
	"""
	if not acct.get("app_id"):
		raise wb._sample_problem("app_id_missing", "Set the App ID on the WhatsApp Account to upload header samples.")
	content, mime = _read_header_sample(sample, header_type, http_get)
	http_post = http_post or wb._default_post
	base = f"{acct['url']}/{acct['version']}"
	try:
		opened = http_post(
			f"{base}/{acct['app_id']}/uploads",
			params={"file_length": len(content), "file_type": mime, "file_name": _upload_file_name(sample, mime)},
			headers={"Authorization": f"Bearer {acct['token']}"},
			timeout=wb._HTTP_TIMEOUT,
		)
		code = getattr(opened, "status_code", 200)
		if isinstance(code, int) and code >= 400:
			raise wb.BridgeError(wb._graph_err("upload_failed", opened))
		session = str(opened.json()["id"])
		sent = http_post(
			f"{base}/{session}",
			data=content,
			headers={"Authorization": f"OAuth {acct['token']}", "file_offset": "0"},
			timeout=60,
		)
		code = getattr(sent, "status_code", 200)
		if isinstance(code, int) and code >= 400:
			raise wb.BridgeError(wb._graph_err("upload_failed", sent))
		return str(sent.json()["h"])
	except wb.BridgeError:
		raise
	except Exception as exc:
		raise wb.BridgeError(wb._graph_err("upload_failed", exc)) from exc


def upload_card_handles(
	acct: dict[str, Any], spec: dict[str, Any], http_post: Callable[..., Any] | None = None,
	http_get: Callable[..., Any] | None = None,
) -> None:
	"""Upload every carousel card header sample (same resumable upload as header media) and set its ``header_handle``."""
	for i, card in enumerate(spec.get("cards") or []):
		if card["header_handle"]:
			continue
		try:
			card["header_handle"] = upload_header_handle(acct, card["header_type"], card["header_sample"], http_post, http_get)
		except wb.BridgeError as exc:
			errs = exc.payload.get("errors")
			if isinstance(errs, list):
				for e in errs:
					if isinstance(e, dict):
						e["field"] = f"cards[{i}].sample"
			raise
