"""Secure download of Slack ``event.files[]`` attachments into private File docs.

Requirements: the Slack app needs the ``files:read`` scope, and the bot token
is read from the gateway credential key ``token``.

NOT called from the webhook: Slack requires an ack within 3 seconds, so
wiring this into the queued gateway job is a follow-up needing an owner
decision.

Security rules: only ``https://files.slack.com`` (hostname matched exactly
after URL parsing); redirects are never followed (a redirect would forward
the Authorization header elsewhere); a hard 20 MB byte cap is enforced while
streaming regardless of the declared size; HTML responses (Slack's login page
for a missing scope) and non-allow-listed mime types are rejected; and the
bot token never appears in logs or exception text.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Callable
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 20 * 1024 * 1024
ALLOWED_HOST = "files.slack.com"
CONNECT_TIMEOUT = 5
READ_TIMEOUT = 20
MAX_FILENAME_LEN = 120

ALLOWED_MIME_PREFIXES = ("image/", "audio/", "video/")
ALLOWED_MIMES = {
    "application/pdf",
    "text/plain",
    "text/csv",
    "application/msword",
    "application/vnd.ms-excel",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.oasis.opendocument.text",
    "application/vnd.oasis.opendocument.spreadsheet",
    "application/vnd.oasis.opendocument.presentation",
}

_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def sanitize_filename(name: Any, fallback: str = "slack-file") -> str:
    text = _CONTROL_RE.sub("", str(name or ""))
    text = text.replace("\\", "/").rsplit("/", 1)[-1]
    text = text.strip().lstrip(".")
    if len(text) > MAX_FILENAME_LEN:
        root, ext = os.path.splitext(text)
        ext = ext[:16]
        text = root[: MAX_FILENAME_LEN - len(ext)] + ext
    return text or fallback


_MIME_RE = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$")


def _mime_allowed(mime: str) -> bool:
    if not _MIME_RE.match(mime):
        return False
    return mime in ALLOWED_MIMES or mime.startswith(ALLOWED_MIME_PREFIXES)


def _url_allowed(url: Any) -> bool:
    if not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url)
        return parsed.scheme == "https" and parsed.hostname == ALLOWED_HOST
    except Exception:
        return False


def _default_http_get(url: str, *, headers: dict, timeout: tuple, stream: bool, allow_redirects: bool):
    import requests

    return requests.get(url, headers=headers, timeout=timeout, stream=stream, allow_redirects=allow_redirects)


def _default_save_file(filename: str, content: bytes, *, is_private: bool = True) -> str | None:
    from frappe.utils.file_manager import save_file

    saved = save_file(filename, content, None, None, is_private=is_private)
    return getattr(saved, "name", None)


def download_slack_file(
    file_info: Any,
    bot_token: str,
    *,
    http_get: Callable[..., Any] = _default_http_get,
    save_file: Callable[..., Any] = _default_save_file,
) -> dict | None:
    """Download one Slack file; return metadata dict or None on any refusal/failure."""
    file_id = "unknown"
    response = None
    try:
        if not isinstance(file_info, dict) or not bot_token:
            return None
        file_id = str(file_info.get("id") or "unknown")

        declared = file_info.get("size")
        if isinstance(declared, (int, float)) and declared > MAX_FILE_BYTES:
            logger.warning("slack file %s skipped: declared size too large", file_id)
            return None

        url = file_info.get("url_private_download") or file_info.get("url_private")
        if not _url_allowed(url):
            logger.warning("slack file %s skipped: url not allowed", file_id)
            return None

        response = http_get(
            url,
            headers={"Authorization": f"Bearer {bot_token}"},
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            stream=True,
            allow_redirects=False,
        )
        status = getattr(response, "status_code", None)
        if status != 200:
            logger.warning("slack file %s download failed: status %s", file_id, status)
            return None

        headers = getattr(response, "headers", None) or {}
        content_type = str(headers.get("Content-Type") or headers.get("content-type") or "")
        mime = content_type.split(";", 1)[0].strip().lower()
        if mime == "text/html":
            logger.warning("slack file %s rejected: html response (missing files:read?)", file_id)
            return None
        if not mime:
            mime = str(file_info.get("mimetype") or "").split(";", 1)[0].strip().lower()
        if not _mime_allowed(mime):
            logger.warning("slack file %s rejected: mime not allowed", file_id)
            return None

        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                logger.warning("slack file %s aborted: exceeded byte cap", file_id)
                return None
            chunks.append(chunk)
        if not total:
            return None

        filename = sanitize_filename(file_info.get("name") or file_info.get("title"), f"slack-{file_id}")
        file_doc = save_file(filename, b"".join(chunks), is_private=True)
        if not file_doc:
            return None
        kind = mime.split("/", 1)[0] if mime.split("/", 1)[0] in ("image", "audio", "video") else "file"
        return {"file_doc": file_doc, "filename": filename, "mime_type": mime, "size": total, "kind": kind, "file_id": file_id}
    except Exception:
        # Deliberately no exc text/traceback: it could echo request headers.
        logger.warning("slack file %s download failed", file_id)
        return None
    finally:
        try:
            if response is not None and hasattr(response, "close"):
                response.close()
        except Exception:
            pass
