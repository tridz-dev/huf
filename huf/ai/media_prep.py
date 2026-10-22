"""Prepare inbound media (images, documents, voice notes) for an agent run.

Shared by the web chat path (``agent_chat``) and the gateway path (``gateway_service``) so both
treat attachments the same way:

- images      -> passed to the model as image input (``files=[{..., is_image: 1}]``)
- documents   -> OCR / extracted text appended to the prompt, labelled and size-capped
- audio       -> transcript prepended to the prompt, labelled; the original file is kept
- unsupported or failed preparation -> a short labelled note, never an exception

Every external call (OCR, STT) goes through ``_ocr_document`` / ``_transcribe_audio`` so tests can
fake them without network access.
"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass, field

import frappe

# Budget: ~4 chars per token, so 12k chars is about 3k tokens per document and 24k about 6k tokens
# for all documents of one message.
MAX_DOC_TEXT_CHARS = 12000
MAX_TOTAL_TEXT_CHARS = 24000
MAX_TRANSCRIPT_CHARS = 8000

_DOCUMENT_MIME_PREFIXES = (
	"application/pdf",
	"application/msword",
	"application/vnd.",
	"application/json",
	"application/rtf",
	"text/",
)
_DOCUMENT_EXTENSIONS = {
	".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".rtf",
	".txt", ".md", ".csv", ".json", ".html", ".htm", ".xml",
}  # fmt: skip


@dataclass
class PreparedMedia:
	files: list = field(default_factory=list)
	prefix: str = ""
	suffix: str = ""


def classify_media(filename: str, mime_type: str | None = None) -> str:
	"""Return ``image``, ``audio``, ``document`` or ``unsupported``."""
	mime = (mime_type or mimetypes.guess_type(filename or "")[0] or "").lower()
	if mime.startswith("image/"):
		return "image"
	from huf.ai import audio_service

	if audio_service.is_audio_file(filename or "", mime or None):
		return "audio"
	ext = "." + (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""
	if ext in _DOCUMENT_EXTENSIONS or mime.startswith(_DOCUMENT_MIME_PREFIXES):
		return "document"
	return "unsupported"


def _ocr_document(file_id: str, agent_name: str) -> dict:
	from huf.ai import sdk_tools
	from huf.ai.agent_integration import _run_async_safely

	return _run_async_safely(
		sdk_tools.handle_ocr_document(file_id=file_id, agent_name=agent_name, create_message=False)
	)


def _transcribe_audio(file_id: str, agent_name: str) -> dict:
	from huf.ai import audio_service

	return audio_service.transcribe_audio_file(file_id=file_id, agent_name=agent_name)


def cap_text(text: str, limit: int) -> tuple[str, bool]:
	text = text or ""
	if len(text) <= limit:
		return text, False
	return text[: max(limit, 0)], True


def format_document_block(filename: str, text: str, file_hash: str = "n/a") -> str:
	return (
		"Attached File Content (OCR Extracted):\n"
		"The following text was extracted from an attached file. Use this as context:\n\n"
		f"--- File: {filename} (hash: {file_hash}) ---\n{text}\n"
	)


def _log_stt_failure(name, exc_type, message) -> None:
	"""Warn (never raise) about a failed voice-note transcription; redacts secrets."""
	try:
		import re

		msg = re.sub(r"(sk-[A-Za-z0-9_\-]{6,}|(?i:bearer)\s+\S+|(?i:api[_-]?key)[\"'=: ]+\S+)", "[redacted]", str(message or ""))[:300]
		frappe.logger("huf").warning("Voice note transcription failed (%s): %s: %s", name, exc_type, msg)
	except Exception:
		pass


def prepare_media_for_agent(entries, agent_name: str) -> PreparedMedia:
	"""Build files + prompt additions for already-resolved File entries.

	Each entry is a dict with ``file_id``, ``file_url``, ``filename`` and ``mime_type``.
	Never raises.
	"""
	prep = PreparedMedia()
	prefixes: list[str] = []
	suffixes: list[str] = []
	remaining = MAX_TOTAL_TEXT_CHARS
	for entry in entries or []:
		name = entry.get("filename") or entry.get("file_url") or "file"
		kind = classify_media(name, entry.get("mime_type"))
		file_id = entry.get("file_id")
		base = {
			"file_id": file_id,
			"file_url": entry.get("file_url"),
			"filename": name,
		}
		if kind == "image":
			prep.files.append({**base, "is_image": 1})
		elif kind == "audio":
			prep.files.append({**base, "is_audio": 1})
			try:
				res = _transcribe_audio(file_id, agent_name) or {}
				text = (res.get("transcript") or res.get("text") or "").strip() if res.get("success") else ""
				if not text:
					_log_stt_failure(name, "ProviderError", res.get("error"))
			except Exception as exc:
				_log_stt_failure(name, type(exc).__name__, str(exc))
				text = ""
			if text:
				text, cut = cap_text(text, MAX_TRANSCRIPT_CHARS)
				prefixes.append(f"[Voice note transcript ({name})]: {text}" + (" [transcript truncated]" if cut else ""))
			else:
				prefixes.append(f"[Voice note ({name}) could not be transcribed]")
		elif kind == "document":
			prep.files.append({**base, "is_document": 1})
			try:
				res = _ocr_document(file_id, agent_name) or {}
				text = (res.get("text") or "").strip() if res.get("success") else ""
				file_hash = res.get("file_hash", "n/a")
			except Exception:
				text, file_hash = "", "n/a"
			if not text:
				suffixes.append(f"[Document ({name}) could not be read]")
			elif remaining <= 0:
				suffixes.append(f"[Document ({name}) text omitted: size budget reached]")
			else:
				text, cut = cap_text(text, min(MAX_DOC_TEXT_CHARS, remaining))
				remaining -= len(text)
				block = format_document_block(name, text, file_hash)
				if cut:
					block += "[document text truncated]\n"
				suffixes.append(block)
		else:
			prep.files.append(base)
			suffixes.append(f"[Attachment ({name}) has an unsupported type and was not read]")
	prep.prefix = "\n".join(prefixes)
	prep.suffix = "\n".join(suffixes)
	return prep


def resolve_event_files(event_name: str, file_urls) -> list[dict]:
	"""File entries for URLs saved for this Gateway Event only (no cross-event/gateway access)."""
	urls = [u for u in (file_urls or []) if u]
	if not urls:
		return []
	rows = frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": "Gateway Event",
			"attached_to_name": event_name,
			"file_url": ["in", urls],
		},
		fields=["name", "file_url", "file_name"],
	)
	return [
		{
			"file_id": r.get("name"),
			"file_url": r.get("file_url"),
			"filename": r.get("file_name"),
			"mime_type": mimetypes.guess_type(r.get("file_name") or "")[0],
		}
		for r in rows
	]


def build_prompt(note: str, text: str, prep: PreparedMedia) -> str:
	parts = [prep.prefix, note, text, prep.suffix]
	return "\n".join(p for p in parts if p)
