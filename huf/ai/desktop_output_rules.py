# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Pure rules for files a Huf Desktop uploads as Artifacts (no frappe import, so they unit-test without a bench)
and the ranking used by the skill/agent search endpoint."""

import base64
import binascii
import os
import re

MAX_UPLOAD_BYTES = 25 * 1024 * 1024

# extension -> (content type, Artifact.artifact_type, magic prefix or None, stored inline as text)
ALLOWED = {
	"pdf": ("application/pdf", "document", b"%PDF-", False),
	"docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "document", b"PK\x03\x04", False),
	"xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "document", b"PK\x03\x04", False),
	"pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", "document", b"PK\x03\x04", False),
	"png": ("image/png", "image", b"\x89PNG\r\n\x1a\n", False),
	"jpg": ("image/jpeg", "image", b"\xff\xd8\xff", False),
	"jpeg": ("image/jpeg", "image", b"\xff\xd8\xff", False),
	"csv": ("text/csv", "text", None, True),
	"txt": ("text/plain", "text", None, True),
	"md": ("text/markdown", "markdown", None, True),
	"html": ("text/html", "html", None, True),
	"json": ("application/json", "text", None, True),
}
SECRET_NAME = re.compile(r"(^|[._-])(id_rsa|id_ed25519|credentials?|secrets?|passwd|netrc|npmrc|token|apikey|api_key)([._-]|$)", re.I)
SECRET_EXT = {"pem", "key", "p12", "pfx", "env", "kdbx", "gpg", "asc"}


class UploadRejected(ValueError):
	def __init__(self, code, message):
		super().__init__(message)
		self.code = code


def clean_filename(filename):
	"""A bare file name: no directories, no hidden names, length-capped. Raises UploadRejected."""
	name = os.path.basename(str(filename or "").replace("\\", "/")).strip()
	if not name or name.startswith(".") or "\x00" in name or len(name) > 180:
		raise UploadRejected("bad_filename", "invalid file name")
	return name


def validate_upload(filename, content_b64):
	"""Return ``(name, ext, content_type, artifact_type, data, inline_text_or_None)`` or raise UploadRejected.

	Checks the name, the extension allowlist, secret-looking names, the size cap (before decoding fully
	where possible) and, for binary types, the magic bytes so the declared type matches the content."""
	name = clean_filename(filename)
	ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
	if ext in SECRET_EXT or SECRET_NAME.search(name):
		raise UploadRejected("secret_name", "the file name looks like a secret or key")
	if ext not in ALLOWED:
		raise UploadRejected("type_not_allowed", f".{ext or '(none)'} files are not accepted")
	if not isinstance(content_b64, str) or not content_b64:
		raise UploadRejected("empty", "no content")
	if len(content_b64) > (MAX_UPLOAD_BYTES * 4) // 3 + 8:
		raise UploadRejected("too_large", "file exceeds the size cap")
	try:
		data = base64.b64decode(content_b64, validate=True)
	except (binascii.Error, ValueError):
		raise UploadRejected("bad_encoding", "content is not valid base64") from None
	if not data:
		raise UploadRejected("empty", "no content")
	if len(data) > MAX_UPLOAD_BYTES:
		raise UploadRejected("too_large", "file exceeds the size cap")
	content_type, artifact_type, magic, inline = ALLOWED[ext]
	if magic and not data.startswith(magic):
		raise UploadRejected("type_mismatch", "content does not match the file extension")
	text = None
	if inline:
		try:
			text = data.decode("utf-8")
		except UnicodeDecodeError:
			raise UploadRejected("type_mismatch", "text file is not valid UTF-8") from None
	return name, ext, content_type, artifact_type, data, text


def rank_catalog(items, query, kind="all", limit=50):
	"""Rank ``[{kind, name, description, ...}]`` by query: name 3x, description 1x, every term must match.
	Empty query keeps the order. ``kind`` filters to ``skill`` or ``agent``."""
	terms = [t for t in str(query or "").lower().split() if t]
	out = []
	for i, it in enumerate(items):
		if kind in ("skill", "agent") and it.get("kind") != kind:
			continue
		name = str(it.get("name") or "").lower()
		desc = str(it.get("description") or "").lower()
		total = 0
		for t in terms:
			s = 0
			if t in name:
				s = 300 if name.startswith(t) else 200
			elif t in desc:
				s = 100
			if not s:
				total = None
				break
			total += s
		if total is None:
			continue
		out.append((-total, i, it))
	out.sort(key=lambda r: (r[0], r[1]))
	return [r[2] for r in out[: max(1, min(int(limit or 50), 200))]]
