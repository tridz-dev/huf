"""Upload a private Frappe File (PDF) to Meta WhatsApp media and return the media id.

The file is read as the requesting user, never made public and never linked: the template
DOCUMENT header is sent by media ``id``. Neither the access token nor file bytes are logged.
"""

from __future__ import annotations

import hashlib
import time
import re
from typing import Any, Callable

import frappe

MAX_PDF_BYTES = 16 * 1024 * 1024  # HUF cap; Meta allows up to 100 MB for documents
META_DOC_LIMIT = 100 * 1024 * 1024
CACHE_TTL_SECONDS = 7 * 24 * 3600  # Meta media ids live ~30 days
_CACHE_KEY = "huf_wa_media_id"
# Meta reports a missing/expired media id on SEND as 131009 (parameter invalid) or 100 (invalid
# parameter); both are generic, so they only count when the message also mentions media.
# 131052 (inbound download) and 131053 (upload) are NOT expired-media errors.
_MEDIA_PARAM_CODES = {131009, 100}
_EXPIRED_RE = re.compile(r"media.*(not found|expired|does not exist|invalid)|(not found|expired).*media", re.I)


class MediaUploadError(Exception):
	"""``code`` is one of file_not_found, file_forbidden, not_pdf, file_too_large, upload_failed."""

	def __init__(self, code: str, message: str = ""):
		super().__init__(message or code)
		self.code = code
		self.message = message or code

	def payload(self) -> dict[str, Any]:
		return {"success": False, "error": self.code, "message": self.message}


def max_bytes() -> int:
	try:
		configured = int(frappe.conf.get("huf_whatsapp_max_pdf_bytes") or MAX_PDF_BYTES)
	except (TypeError, ValueError):
		configured = MAX_PDF_BYTES
	return max(1, min(configured, META_DOC_LIMIT))


def _find_file(ref: str) -> Any:
	ref = str(ref or "").strip()
	name = None
	if ref and frappe.db.exists("File", ref):
		name = ref
	elif ref:
		name = frappe.db.get_value("File", {"file_url": ref}, "name")
	if not name:
		raise MediaUploadError("file_not_found", "File not found.")
	return frappe.get_doc("File", name)


def load_pdf(file_ref: Any, requesting_user: str | None = None) -> tuple[bytes, str]:
	"""Permission-checked, validated PDF bytes and a default filename."""
	user = requesting_user or frappe.session.user
	doc = _find_file(str(file_ref or ""))
	if doc.is_folder or not frappe.has_permission("File", "read", doc=doc, user=user):
		raise MediaUploadError("file_forbidden", "You are not permitted to read this file.")
	fname = str(doc.file_name or doc.name)
	if not fname.lower().endswith(".pdf"):
		raise MediaUploadError("not_pdf", "Only PDF files can be attached.")
	cap = max_bytes()
	if int(doc.file_size or 0) > cap:
		raise MediaUploadError("file_too_large", f"PDF is larger than {cap // (1024 * 1024)} MB.")
	try:
		data = doc.get_content()
	except Exception:
		raise MediaUploadError("file_not_found", "File content could not be read.") from None
	if isinstance(data, str):
		data = data.encode("latin-1", "ignore")
	if len(data) > cap:
		raise MediaUploadError("file_too_large", f"PDF is larger than {cap // (1024 * 1024)} MB.")
	if not data.startswith(b"%PDF-"):
		raise MediaUploadError("not_pdf", "File is not a valid PDF.")
	return data, fname


def _cache_key(digest: str, phone_id: str) -> str:
	return f"{digest}:{phone_id}"


def invalidate(digest: str, phone_id: str) -> None:
	frappe.cache().hdel(_CACHE_KEY, _cache_key(digest, phone_id))


def _post(acct: dict[str, Any], data: bytes, filename: str, http_post: Callable[..., Any] | None) -> str:
	if http_post is None:
		import requests

		http_post = requests.post
	url = f"{acct['url']}/{acct['version']}/{acct['phone_id']}/media"
	try:
		resp = http_post(
			url,
			headers={"Authorization": f"Bearer {acct['token']}"},
			data={"messaging_product": "whatsapp", "type": "application/pdf"},
			files={"file": (filename, data, "application/pdf")},
			timeout=60,
		)
		status = getattr(resp, "status_code", 200)
		if isinstance(status, int) and status >= 400:
			raise ValueError("http_error")
		media_id = str(resp.json()["id"])
	except Exception:
		raise MediaUploadError("upload_failed", "WhatsApp media upload failed.") from None
	return media_id


def upload_private_pdf(
	gateway_or_acct: Any,
	file_name_or_url: Any,
	requesting_user: str | None = None,
	http_post: Callable[..., Any] | None = None,
	force: bool = False,
) -> str:
	"""Meta media id for a private PDF File. ``gateway_or_acct`` is a Gateway name or a resolved
	bridge account dict (``url``, ``version``, ``phone_id``, ``token``)."""
	if isinstance(gateway_or_acct, dict):
		acct = gateway_or_acct
	else:
		from huf.ai.gateway_adapters import whatsapp_bridge as bridge

		acct = bridge.resolve_account(bridge.gateway_account(str(gateway_or_acct)))
		if not acct:
			raise MediaUploadError("upload_failed", "WhatsApp account not available.")
	data, filename = load_pdf(file_name_or_url, requesting_user)
	digest = hashlib.sha256(data).hexdigest()
	phone_id = str(acct["phone_id"])
	if not force:
		cached = frappe.cache().hget(_CACHE_KEY, _cache_key(digest, phone_id))
		if cached:
			cached = cached.decode() if isinstance(cached, bytes) else str(cached)
			media_id, _, expiry = cached.partition("|")
			if expiry.isdigit() and int(expiry) > time.time():
				return media_id
			frappe.cache().hdel(_CACHE_KEY, _cache_key(digest, phone_id))
	media_id = _post(acct, data, filename, http_post)
	frappe.cache().hset(_CACHE_KEY, _cache_key(digest, phone_id), f"{media_id}|{int(time.time()) + CACHE_TTL_SECONDS}")
	return media_id


def is_expired_media_error(detail: dict[str, Any]) -> bool:
	try:
		if int(detail.get("graph_code")) in _MEDIA_PARAM_CODES and "media" in str(detail.get("message") or "").lower():
			return True
	except (TypeError, ValueError):
		pass
	return bool(_EXPIRED_RE.search(str(detail.get("message") or "")))


def file_header_param(components: list[dict[str, Any]]) -> dict[str, Any] | None:
	for comp in components:
		if comp.get("type") == "header":
			for p in comp.get("parameters") or []:
				if p.get("type") == "document" and "file" in (p.get("document") or {}):
					return p
	return None


def resolve_file_headers(
	acct: dict[str, Any],
	components: list[dict[str, Any]],
	requesting_user: str | None = None,
	http_post: Callable[..., Any] | None = None,
	force: bool = False,
) -> bool:
	"""Replace a ``{"file": ref}`` DOCUMENT header by ``{"id": media_id}`` in place. True if one was resolved."""
	param = file_header_param(components)
	if not param:
		return False
	doc = param["document"]
	ref = doc.pop("file")
	media_id = upload_private_pdf(acct, ref, requesting_user, http_post, force)
	if not doc.get("filename"):
		doc["filename"] = _find_file(ref).file_name
	doc["id"] = media_id
	return True


def source_file(components: list[dict[str, Any]]) -> Any:
	param = file_header_param(components)
	return param["document"]["file"] if param else None
