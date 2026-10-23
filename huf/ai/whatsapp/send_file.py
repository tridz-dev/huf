# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Resolve a Huf File for a WhatsApp media send (MM-D).

The agent may name a File by ``file_id`` or ``file_url``. A file is only readable when it belongs to the
current run: attached to the run's conversation (directly, as an Agent Message attachment, or as the
inbound Gateway Event media), or an unattached upload owned by the run's user. Anything else (other
private files, traversal, non-File urls) is refused. Voice notes are converted to Ogg/Opus with ffmpeg
(argument list, no shell, audio piped through stdin/stdout so no path or text from the model is used).
"""

from __future__ import annotations

import mimetypes
import re
import shutil
import subprocess
import time
from typing import Any
from urllib.parse import unquote

import frappe

from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.gateway_adapters import whatsapp_messages as wm

_URL_PREFIXES = ("/private/files/", "/files/")
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,139}$")
_FFMPEG_TIMEOUT = 60
_STATUS_TIMEOUT = 5
_STATUS_TTL = 300
_status_cache: dict[str, Any] = {"at": 0.0, "value": None}
OGG_OPUS_MIME = "audio/ogg; codecs=opus"
_RUN_PARENTS = ("Agent Conversation", "Agent Message", "Gateway Event")


class FileSendError(Exception):
	def __init__(self, code: str, message: str):
		super().__init__(message)
		self.code = code
		self.message = message


# ------------------------------------------------------------------ seams (mocked in tests)
def _file_row(key: str) -> dict | None:
	"""File row by name or by file_url (``None`` when no such File)."""
	fields = ["name", "file_url", "file_name", "is_private", "is_folder", "attached_to_doctype", "attached_to_name", "owner", "file_size"]
	filters = {"file_url": key} if key.startswith("/") else {"name": key}
	return frappe.db.get_value("File", filters, fields, as_dict=True)


def _run_conversation(run_id: str | None) -> str:
	if not run_id:
		return ""
	try:
		return str(frappe.db.get_value("Agent Run", run_id, "conversation") or "")
	except Exception:
		return ""


def _parent_conversation(doctype: str, name: str) -> str:
	"""The Agent Conversation a message / gateway event belongs to ('' when unknown)."""
	try:
		field = "conversation_id" if doctype == "Gateway Event" else "conversation"
		return str(frappe.db.get_value(doctype, name, field) or "")
	except Exception:
		return ""


def _session_user() -> str:
	return str(getattr(frappe.session, "user", "") or "")


def _read_content(row: dict) -> bytes:
	return frappe.get_doc("File", row["name"]).get_content()


# ------------------------------------------------------------------ resolution
def _clean_reference(file_url: str | None, file_id: str | None) -> str:
	"""The lookup key, after rejecting anything that is not a plain Huf File reference."""
	file_url, file_id = (file_url or "").strip(), (file_id or "").strip()
	if bool(file_url) == bool(file_id):
		raise FileSendError("invalid_file_reference", "Provide exactly one of file_url or file_id.")
	if file_id:
		if not _NAME_RE.match(file_id) or ".." in file_id:
			raise FileSendError("invalid_file_reference", "file_id is not a valid File name.")
		return file_id
	decoded = unquote(unquote(file_url))
	bad = (
		"\\" in decoded or ".." in decoded or "?" in decoded or "#" in decoded or "//" in decoded
		or any(ord(c) < 32 for c in decoded) or not decoded.startswith(_URL_PREFIXES)
		or file_url != decoded
	)
	if bad or not _NAME_RE.match(decoded.rsplit("/", 1)[-1]):
		raise FileSendError("invalid_file_reference", "file_url must be a /private/files/ or /files/ path of a Huf File.")
	return file_url


def _may_use(row: dict, run_id: str | None) -> bool:
	conversation = _run_conversation(run_id)
	if not conversation:
		return False
	doctype, parent = row.get("attached_to_doctype") or "", row.get("attached_to_name") or ""
	if doctype == "Agent Conversation":
		return parent == conversation
	if doctype in _RUN_PARENTS:
		return bool(parent) and _parent_conversation(doctype, parent) == conversation
	if doctype:
		return False  # attached to some other record: not ours
	user = _session_user()
	return bool(user) and user != "Guest" and row.get("owner") == user


def resolve_file(file_url: str | None, file_id: str | None, run_id: str | None) -> dict[str, Any]:
	"""``{content, filename, mime}`` of a File the run may send, or raise :class:`FileSendError`."""
	key = _clean_reference(file_url, file_id)
	row = _file_row(key)
	if not row or row.get("is_folder"):
		raise FileSendError("file_not_found", "No such file.")
	if not _may_use(row, run_id):
		raise FileSendError("file_not_permitted", "This file is not available to this conversation.")
	size = int(row.get("file_size") or 0)
	if size > bridge.DEFAULT_MAX_MEDIA_BYTES:
		raise FileSendError("too_large", "The file is larger than WhatsApp allows.")
	name = row.get("file_name") or str(row.get("file_url") or "").rsplit("/", 1)[-1]
	mime = mimetypes.guess_type(name)[0] or ""
	return {"row": row, "filename": name, "mime": mime, "size": size}


def load_content(resolved: dict[str, Any]) -> bytes:
	return _read_content(resolved["row"]) or b""


# ------------------------------------------------------------------ audio
def is_ogg_opus(content: bytes) -> bool:
	return content[:4] == b"OggS" and b"OpusHead" in content[:256]


def _ffmpeg_cache_clear() -> None:
	_status_cache.update({"at": 0.0, "value": None})


def ffmpeg_status() -> dict[str, Any]:
	"""{available, has_libopus, version} for this host's ffmpeg, cached for a few minutes."""
	now = time.monotonic()
	cached = _status_cache["value"]
	if cached is not None and now - _status_cache["at"] < _STATUS_TTL:
		return dict(cached)
	status: dict[str, Any] = {"available": False, "has_libopus": False, "version": ""}
	ffmpeg = shutil.which("ffmpeg")
	if ffmpeg:
		def _out(args: list[str]) -> str | None:
			try:
				proc = subprocess.run(
					[ffmpeg, *args], capture_output=True, timeout=_STATUS_TIMEOUT, shell=False, check=False
				)
			except (subprocess.SubprocessError, OSError):
				return None
			return proc.stdout.decode("utf-8", "replace") if proc.returncode == 0 else None

		version_out = _out(["-version"])
		if version_out is not None:
			match = re.search(r"version\s+(\S+)", version_out)
			status["available"] = True
			status["version"] = match.group(1) if match else ""
			encoders = _out(["-hide_banner", "-encoders"]) or ""
			status["has_libopus"] = bool(re.search(r"\blibopus\b", encoders))
	_status_cache.update({"at": now, "value": status})
	return dict(status)


def to_ogg_opus(content: bytes) -> bytes:
	"""Convert any audio ffmpeg can read to mono Ogg/Opus (WhatsApp voice-note format)."""
	ffmpeg = shutil.which("ffmpeg")
	if not ffmpeg:
		raise FileSendError("ffmpeg_unavailable", "ffmpeg is not installed on this server, so this audio cannot be converted to a voice note. Send an .ogg (Opus) file instead.")
	cmd = [
		ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-vn",
		"-ac", "1", "-c:a", "libopus", "-b:a", "32k", "-f", "ogg", "pipe:1",
	]
	try:
		proc = subprocess.run(cmd, input=content, capture_output=True, timeout=_FFMPEG_TIMEOUT, shell=False, check=False)
	except subprocess.TimeoutExpired as exc:
		raise FileSendError("audio_conversion_failed", "Converting the audio timed out.") from exc
	except OSError as exc:
		raise FileSendError("audio_conversion_failed", "Could not run ffmpeg.") from exc
	if proc.returncode != 0 or not proc.stdout:
		raise FileSendError("audio_conversion_failed", "The file could not be converted to Ogg/Opus; it may not be valid audio.")
	return proc.stdout


def prepare_upload(resolved: dict[str, Any], kind: str | None, voice: bool) -> dict[str, Any]:
	"""Read the bytes and return ``{content, mime, filename, kind, voice}`` ready for upload (limits checked, no network)."""
	mime, filename = resolved["mime"], resolved["filename"]
	kind = (kind or "").strip().lower() or wm.kind_for_mime(mime)
	if voice and kind and kind != "audio":
		raise FileSendError("invalid_kind", "Only audio can be sent as a voice note.")
	if voice and not kind:
		kind = "audio" if wm.normalize_mime(mime).startswith("audio/") else ""
	if not kind:
		raise FileSendError("unsupported_mime", f"WhatsApp does not accept {wm.normalize_mime(mime) or 'this file type'} media.")
	if wm.kind_for_mime(mime) != kind and not (kind == "audio" and voice and wm.normalize_mime(mime).startswith("audio/")):
		raise FileSendError("kind_mismatch", f"This file is {wm.normalize_mime(mime) or 'an unknown type'}, which cannot be sent as {kind}.")
	cap = bridge.MEDIA_LIMITS_BY_KIND.get(kind)
	if cap and resolved.get("size", 0) > cap:
		raise FileSendError("too_large", f"{kind} files are at most {cap // (1024 * 1024) or 1} MB.")
	content = load_content(resolved)
	if voice:
		if not (wm.normalize_mime(mime) == "audio/ogg" and is_ogg_opus(content)):
			content = to_ogg_opus(content)
			stem = filename.rsplit(".", 1)[0] or "voice"
			filename = f"{stem}.ogg"
		mime = OGG_OPUS_MIME
	_, errors = wm.validate_upload(mime, content, kind, voice)
	if errors:
		raise _validation(errors)
	return {"content": content, "mime": mime, "filename": filename, "kind": kind, "voice": voice}


def _validation(errors: list[dict[str, str]]) -> FileSendError:
	first = errors[0]
	return FileSendError(first.get("code") or "invalid_file", first.get("message") or "The file cannot be sent.")


def split_caption(caption: str, limit: int = wm.MAX_CAPTION) -> tuple[str, str]:
	"""``(first, rest)``: the first part fits a media caption (split at whitespace), the rest goes as text."""
	caption = (caption or "").strip()
	if len(caption) <= limit:
		return caption, ""
	cut = caption.rfind(" ", 0, limit)
	cut = cut if cut > 0 else limit
	return caption[:cut].rstrip(), caption[cut:].strip()
