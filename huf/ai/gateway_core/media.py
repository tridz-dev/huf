"""Inbound WhatsApp media naming/saving and attachment sniffing."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import frappe

from huf.ai.gateway_core.redaction import _redact_error_text


_MEDIA_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")


_MIME_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "audio/ogg": "ogg",
    "audio/mpeg": "mp3",
    "audio/mp4": "m4a",
    "audio/aac": "aac",
    "audio/amr": "amr",
    "video/mp4": "mp4",
    "video/3gpp": "3gp",
    "application/pdf": "pdf",
    "text/plain": "txt",
    "text/csv": "csv",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-powerpoint": "ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
}


def _media_file_name(msg_type: str, media: dict, media_id: str, downloaded: dict) -> str:
    """A readable file name: the sender's own filename for documents, else ``<type>-<id>.<ext>``."""
    mime = str(downloaded.get("mime_type") or (media or {}).get("mime_type") or "").split(";")[0].strip().lower()
    ext = _MIME_EXTENSIONS.get(mime) or (mime.split("/")[-1] if "/" in mime and mime.split("/")[-1].isalnum() else "")
    original = os.path.basename(str((media or {}).get("filename") or ""))
    if not original:
        # Meta's media metadata sometimes names the file; the bridge falls back to the raw id.
        provided = os.path.basename(str(downloaded.get("filename") or ""))
        if provided and _MEDIA_SAFE_NAME.sub("_", media_id) not in (provided, provided.rsplit(".", 1)[0]):
            original = provided
    if original:
        name = original
    else:
        name = f"{msg_type}-{media_id}"
    name = _MEDIA_SAFE_NAME.sub("_", name).lstrip(".")[:100] or f"{msg_type}-{media_id}"
    if ext and "." not in os.path.basename(name):
        name = f"{name}.{ext}"[:100]
    return name


def _save_whatsapp_media(event, gateway, frappe=frappe) -> list[str]:
    """Best-effort download of inbound WhatsApp media into private Files (A9).

    Never raises: any failure is logged and the text flow continues.
    """
    saved: list[str] = []
    try:
        raw = event.raw_payload
        if isinstance(raw, str):
            raw = json.loads(raw)
        message = raw.get("message") if isinstance(raw, dict) else None
        if not isinstance(message, dict):
            return saved
        msg_type = message.get("type")
        media = message.get(msg_type) if msg_type in ("image", "document", "audio", "video", "sticker") else None
        media_id = str((media or {}).get("id") or "")
        if not media_id:
            return saved

        from huf.ai.gateway_adapters import whatsapp_bridge as bridge

        account = (getattr(gateway, "whatsapp_account", "") or "").strip() or None
        direct = None
        if not account:
            # Direct mode (no WhatsApp Account): use the gateway's own Meta credentials.
            from huf.ai.gateway_webhook import _gateway_credentials

            creds = _gateway_credentials(gateway)
            direct = {"token": creds.get("access_token"), "url": bridge.graph_base_url(creds.get("graph_api_url"))}
        downloaded = bridge.download_media(
            account, media_id, credentials=direct, kind=msg_type, filename=(media or {}).get("filename")
        )
        name = _media_file_name(msg_type, media, media_id, downloaded)
        file_doc = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": name,
                "content": downloaded["content"],
                "attached_to_doctype": "Gateway Event",
                "attached_to_name": event.name,
                "is_private": 1,
            }
        ).insert(ignore_permissions=True)
        saved.append(file_doc.file_url)
    except Exception as exc:
        frappe.logger("huf").warning(f"WhatsApp media download skipped: {_redact_error_text(str(exc))}")
    return saved


MEDIA_SAVED_TTL = 7200


def save_event_media(event, gateway, hook, frappe=frappe) -> list[str]:
    """Run the provider ``media_save`` hook once per event.

    A ``media saved`` marker is set after the hook returns. Files already attached to the event are reused only when
    that marker is set (a Flow start that falls through to the default agent asks twice). Without the marker, files
    found on the event come from an interrupted earlier try, so the hook runs again and downloads the rest."""
    key = f"huf_gw_media_saved:{getattr(event, 'name', '')}"
    try:
        saved_before = bool(frappe.cache.get_value(key))
        existing = frappe.get_all(
            "File",
            filters={"attached_to_doctype": "Gateway Event", "attached_to_name": getattr(event, "name", "")},
            pluck="file_url",
            order_by="creation asc",
        )
    except Exception:
        saved_before, existing = False, []
    if saved_before and all(isinstance(u, str) and u for u in existing):
        return list(existing)
    urls = hook(event, gateway)
    try:
        frappe.cache.set_value(key, 1, expires_in_sec=MEDIA_SAVED_TTL)
    except Exception:
        pass
    return urls


def _describe_attachments(raw_payload: Any) -> str:
    """Best-effort, provider-agnostic sniff of stored raw payload for attachments.

    GW-30 added an ``attachments`` field to ``NormalizedGatewayEvent``, but the
    ``Gateway Event`` doctype has no dedicated column for it yet (out of scope
    for this change -- see findings). Since the full (redacted) provider
    payload is already persisted on every event, this recovers "was media
    attached, and what kind" from the well-known per-provider payload shapes
    so the note can survive round-tripping through storage, rather than
    requiring attachments to be threaded through as a brand-new doctype field.
    Returns "" when nothing recognizable is found -- callers must not assume
    absence of a note means absence of media for providers not covered here.
    """
    if not isinstance(raw_payload, dict):
        return ""

    kinds: list[str] = []

    # Telegram: message/edited_message carries one of these media keys directly.
    message = raw_payload.get("message") or raw_payload.get("edited_message")
    if isinstance(message, dict):
        for key in ("photo", "document", "voice", "video", "audio", "video_note", "sticker"):
            if message.get(key):
                kinds.append(key)

    # WhatsApp Gateway Event shape ({"message": <Meta message>}), see WhatsAppGatewayAdapter.
    if isinstance(message, dict) and message.get("type") in (
        "image", "document", "audio", "video", "sticker",
    ):
        kinds.append(message["type"])

    # WhatsApp Business/Cloud API webhook shape.
    try:
        value = raw_payload["entry"][0]["changes"][0]["value"]
        msg = (value.get("messages") or [None])[0]
        if isinstance(msg, dict) and msg.get("type") in (
            "image", "document", "audio", "video", "sticker",
        ):
            kinds.append(msg["type"])
    except (KeyError, IndexError, TypeError):
        pass

    # Messenger/Instagram webhook shape.
    try:
        messaging_event = raw_payload["entry"][0]["messaging"][0]
        for attachment in (messaging_event.get("message") or {}).get("attachments") or []:
            if attachment.get("type"):
                kinds.append(str(attachment["type"]))
    except (KeyError, IndexError, TypeError):
        pass

    # MS Teams Bot Framework activity shape.
    for attachment in raw_payload.get("attachments") or []:
        if isinstance(attachment, dict) and attachment.get("contentUrl"):
            kinds.append("file")

    # Twilio-style SMS/MMS form payload (persisted as a flat dict of params).
    if raw_payload.get("NumMedia") not in (None, "0", 0):
        kinds.append("mms")

    # Slack Events API: file_share message events carry event.files[].
    slack_event = raw_payload.get("event")
    if isinstance(slack_event, dict) and isinstance(slack_event.get("files"), list):
        for slack_file in slack_event["files"]:
            if not isinstance(slack_file, dict):
                continue
            mime = str(slack_file.get("mimetype") or slack_file.get("filetype") or "").lower()
            for prefix in ("image", "video", "audio"):
                if mime.startswith(prefix):
                    kinds.append(prefix)
                    break
            else:
                kinds.append("file")

    if not kinds:
        return ""

    unique_kinds = sorted(set(kinds))
    return "[Attachment(s) present: " + ", ".join(unique_kinds) + "]"
