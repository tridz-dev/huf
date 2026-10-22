"""
Telegram integration tools for HUF agents.

Single consolidated tool that performs all Telegram Bot API actions via an
`action` parameter. Uses HUF Integration Settings for credential management
and supports Frappe File uploads, public URLs, and Telegram file_ids for
media messages.

Actions:
    send_message        Send a text message
    reply_to_message    Reply to a specific message (send_message + reply_to_message_id)
    send_photo          Send a photo (URL, file_id, or Frappe File)
    send_document       Send a document (URL, file_id, or Frappe File)
    edit_message_text   Edit a previously sent text message
    delete_message      Delete a message
    get_updates         Fetch recent incoming updates/messages
    get_chat_info       Get information about a chat
    get_me              Get information about the bot
    set_webhook         Set a webhook URL for the bot
    delete_webhook      Remove the bot webhook

Rich actions (WP-4): send_voice, send_audio, send_video, send_animation, send_sticker, send_media_group,
send_location, send_contact, set_reaction, send_chat_action, edit_message_caption,
edit_message_reply_markup, pin_message, unpin_message, forward_message, copy_message,
answer_callback_query, plus a validated ``reply_markup`` on send_message/send_photo/send_document.

Inside a run that belongs to a Telegram Gateway the recipient is the current chat by default and any
other chat is checked against the gateway's send scope and caps (``huf.ai.telegram_send_scope``).
"""

import json
import os
import re
from typing import Any, Callable, Optional

import frappe
logger = frappe.logger("huf")

from huf.ai import run_delivery
from huf.ai import telegram_send_scope as scope
from huf.ai.gateway_adapters import telegram_senders_extra as extra
from huf.ai.gateway_adapters import telegram_senders_more as more
from huf.ai.gateway_adapters.telegram_client import ALLOWED_UPDATES, TelegramApiError, TelegramBotClient
from huf.ai.gateway_adapters.telegram_keyboards import derive_callback_key, sign_callback
from huf.ai.gateway_adapters.telegram_outbound import TelegramSender
from huf.ai.tools.credentials import get_credential, update_last_error


SERVICE_NAME = "telegram"


def _error(msg: str) -> str:
    return json.dumps({"success": False, "error": msg}, default=str)


def _get_token() -> Optional[str]:
    """Fetch Telegram bot token from HUF Integration Settings or env fallback."""
    return get_credential(SERVICE_NAME, "token")


def _resolve_chat_id(kwargs: dict) -> Optional[str]:
    """Resolve chat_id from explicit value or named recipient in Integration Settings."""
    chat_id = kwargs.get("chat_id")
    if chat_id:
        return str(chat_id).strip()

    recipient_name = (kwargs.get("recipient_name") or "").strip()
    if not recipient_name:
        return None

    try:
        settings_list = frappe.get_all(
            "Integration Settings",
            filters={"service": SERVICE_NAME, "is_active": 1},
            fields=["name"],
            order_by="is_default DESC, modified DESC",
            limit=1,
        )
        if not settings_list:
            return None

        doc = frappe.get_doc("Integration Settings", settings_list[0].name)
        name_lower = recipient_name.lower()
        for row in doc.recipients:
            if (row.recipient_name or "").strip().lower() == name_lower:
                return (row.recipient_id or "").strip()
    except Exception:
        pass

    return None


def _make_client(token: str, *, timeout: int = 30) -> TelegramBotClient:
    """Bot API client for ``token``. Tests patch this to inject a fake HTTP layer."""
    return TelegramBotClient(token, timeout=timeout)


def _apply_reply(payload: dict, reply_to_message_id) -> None:
    """Reply via ``reply_parameters`` (the Bot API form the gateway sender uses)."""
    payload["reply_parameters"] = {"message_id": _coerce_int(reply_to_message_id), "allow_sending_without_reply": True}


def _close_files(files: Optional[dict]):
    """Close any open file handles in a multipart upload dict."""
    if not files:
        return
    for item in files.values():
        # files value is a tuple: (filename, file_object, mime_type)
        if isinstance(item, tuple) and len(item) >= 2:
            file_obj = item[1]
            try:
                file_obj.close()
            except Exception:
                pass


def _api_request(method: str, payload: dict, files: Optional[dict] = None, token: Optional[str] = None) -> str:
    """Call a Telegram Bot API method through ``TelegramBotClient``; return a JSON result string."""
    if token is None:
        token = _token_for_run()
    if not token:
        error_msg = "Telegram bot token not configured"
        update_last_error(SERVICE_NAME, error_msg)
        return _error(error_msg)

    client = _make_client(token, timeout=60 if files else 30)
    try:
        result = client.call(method, payload, files=files)
    except TelegramApiError as exc:
        # The client already redacts the token from description and network errors.
        detail = f"error {exc.error_code}: {exc.description}" if exc.error_code is not None else exc.description
        error_msg = f"Telegram {method} {detail}"
        logger.warning(error_msg)
        update_last_error(SERVICE_NAME, error_msg)
        return _error(error_msg)
    except Exception as exc:
        error_msg = f"Telegram {method} error: {client.redact(exc)}"
        logger.warning(error_msg)
        update_last_error(SERVICE_NAME, error_msg)
        return _error(error_msg)
    finally:
        _close_files(files)
    return json.dumps({"success": True, "results": result}, default=str)


def _coerce_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


PHOTO_MAX_BYTES = 10 * 1024 * 1024
FILE_MAX_BYTES = 50 * 1024 * 1024
_FILE_ID_RE = re.compile(r"[A-Za-z0-9_-]{20,}")
_VOICE_MIMES = ("audio/ogg", "audio/mpeg", "audio/mp4", "audio/x-m4a", "audio/m4a")
_PARSE_MODES = ("Markdown", "HTML", "MarkdownV2")


def _size_limit(kind: str) -> int:
    return PHOTO_MAX_BYTES if kind == "photo" else FILE_MAX_BYTES


def _mb(n: int) -> str:
    return f"{n // (1024 * 1024)} MB"


def _resolve_media(kind: str, source) -> Any:
    """Resolve a media source for ``TelegramSender``: URL / file_id string, or ``(name, bytes, mime)``.

    Public URLs go through the same SSRF guard as ``http_handler``; Frappe Files (docname or file_url)
    are permission-checked and size-limited per Bot API (50 MB uploads, 10 MB photos). Raises ValueError
    with a clear message otherwise.
    """
    source = str(source or "").strip()
    if not source:
        raise ValueError(f"{kind} source is required")
    if source.lower().startswith(("http://", "https://")):
        from huf.ai.http_handler import validate_url

        ok, err = validate_url(source)
        if not ok:
            raise ValueError(f"URL rejected: {err}")
        return source

    file_doc = None
    try:
        if frappe.db.exists("File", source):
            file_doc = frappe.get_doc("File", source)
        else:
            name = frappe.db.get_value("File", {"file_url": source}, "name")
            file_doc = frappe.get_doc("File", name) if name else None
    except Exception:
        file_doc = None
    if file_doc is not None:
        if not frappe.has_permission("File", "read", doc=file_doc):
            raise ValueError("You do not have permission to read that file")
        path = file_doc.get_full_path()
        if not os.path.exists(path):
            raise ValueError("The file is missing on the server")
        limit = _size_limit(kind)
        size = os.path.getsize(path)
        if size > limit:
            raise ValueError(f"File is {_mb(size)}; Telegram allows at most {_mb(limit)} for a {kind}")
        mime = file_doc.content_type or "application/octet-stream"
        if kind == "voice" and mime not in _VOICE_MIMES:
            raise ValueError("A voice message must be OGG/Opus (audio/ogg), MP3 or M4A; use send_audio or send_document")
        with open(path, "rb") as fh:
            return (os.path.basename(path), fh.read(), mime)
    if _FILE_ID_RE.fullmatch(source):
        return source  # a Telegram file_id
    raise ValueError("File source not recognised: use a public https URL, a Telegram file_id, or a Frappe File name/file_url")


def _parse_mode(kwargs: dict) -> Optional[str]:
    mode = kwargs.get("parse_mode")
    return mode if mode in _PARSE_MODES else None


def _markup(kwargs: dict, chat_id=None) -> Optional[dict]:
    """Validated ``reply_markup`` (None when absent); raises ValueError. Callback buttons are signed."""
    raw = kwargs.get("reply_markup")
    sign = None
    gateway = scope.run_gateway()
    if gateway:
        secret = _gateway_values(gateway).get("webhook_secret", "")
        if secret:
            key = derive_callback_key(secret)
            sign = lambda payload: sign_callback(key, payload, context=str(chat_id or ""))  # noqa: E731
    return extra.normalize_reply_markup(raw, sign=sign)


def _gateway_values(gateway: str) -> dict:
    try:
        settings_name = frappe.db.get_value("Gateway", gateway, "integration_settings")
        if not settings_name:
            return {}
        doc = frappe.get_doc("Integration Settings", settings_name)
        return {row.key: str(row.get_password("value") or "") for row in doc.credentials or [] if row.key}
    except Exception:
        return {}


def _token_for_run() -> Optional[str]:
    gateway = scope.run_gateway()
    if gateway:
        token = _gateway_values(gateway).get("token")
        if token:
            return token
    return _get_token()


def _run_sender(label: str, fn: Callable[[TelegramSender], Any], *, upload: bool = False) -> str:
    """Run ``fn(sender)`` on a Bot API client; map failures to a redacted JSON error."""
    token = _token_for_run()
    if not token:
        error_msg = "Telegram bot token not configured"
        update_last_error(SERVICE_NAME, error_msg)
        return _error(error_msg)
    client = _make_client(token, timeout=60 if upload else 30)
    try:
        result = fn(TelegramSender(client))
    except TelegramApiError as exc:
        detail = f"error {exc.error_code}: {exc.description}" if exc.error_code is not None else exc.description
        error_msg = f"Telegram {label} {detail}"
        logger.warning(error_msg)
        update_last_error(SERVICE_NAME, error_msg)
        return _error(error_msg)
    except ValueError as exc:
        return _error(client.redact(exc))
    except Exception as exc:
        error_msg = f"Telegram {label} error: {client.redact(exc)}"
        logger.warning(error_msg)
        update_last_error(SERVICE_NAME, error_msg)
        return _error(error_msg)
    return json.dumps({"success": True, "results": result}, default=str)


def _chat_or_error(kwargs: dict):
    chat_id = _resolve_chat_id(kwargs)
    return chat_id, (None if chat_id else _error("chat_id or recipient_name is required"))


def _common_kw(kwargs: dict, chat_id) -> dict:
    """Sender keyword arguments shared by the send_* actions."""
    kw: dict = {}
    if kwargs.get("reply_to_message_id"):
        kw["reply_to"] = _coerce_int(kwargs["reply_to_message_id"])
    if kwargs.get("message_thread_id") or kwargs.get("thread_id"):
        kw["thread_id"] = _coerce_int(kwargs.get("message_thread_id") or kwargs.get("thread_id"))
    if _truthy(kwargs.get("disable_notification")):
        kw["silent"] = True
    if _truthy(kwargs.get("protect_content")):
        kw["protect"] = True
    markup = _markup(kwargs, chat_id)
    if markup:
        kw["markup"] = markup
    return kw


def _truthy(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _build_message_payload(kwargs: dict) -> tuple:
    """Build common payload for send/edit operations. Returns (payload, files)."""
    chat_id = _resolve_chat_id(kwargs)
    if not chat_id:
        return _error("chat_id or recipient_name is required"), None

    text = kwargs.get("text") or kwargs.get("message")
    if not text:
        return _error("text (or message) is required"), None

    payload = {"chat_id": chat_id, "text": text}
    parse_mode = _parse_mode(kwargs)
    if parse_mode:
        payload["parse_mode"] = parse_mode

    disable_notification = kwargs.get("disable_notification")
    if disable_notification is not None:
        payload["disable_notification"] = _truthy(disable_notification)
    if _truthy(kwargs.get("protect_content")):
        payload["protect_content"] = True
    if kwargs.get("message_effect_id"):
        payload["message_effect_id"] = str(kwargs["message_effect_id"])

    reply_to_message_id = kwargs.get("reply_to_message_id")
    if reply_to_message_id:
        _apply_reply(payload, reply_to_message_id)

    thread = kwargs.get("message_thread_id") or kwargs.get("thread_id")
    if thread:
        payload["message_thread_id"] = _coerce_int(thread)
    try:
        markup = _markup(kwargs, chat_id)
    except ValueError as exc:
        return _error(str(exc)), None
    if markup:
        payload["reply_markup"] = markup

    return payload, None


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


def _handle_send_message(**kwargs) -> str:
    """Send a text message to a chat."""
    payload, files = _build_message_payload(kwargs)
    if isinstance(payload, str):
        return payload
    return _api_request("sendMessage", payload, files)


def _handle_reply_to_message(**kwargs) -> str:
    """Reply to a specific message in a chat."""
    if not kwargs.get("reply_to_message_id"):
        return _error("reply_to_message_id is required for reply_to_message")
    return _handle_send_message(**kwargs)


def _send_media_action(kind: str, kwargs: dict, source_keys: tuple) -> str:
    chat_id, err = _chat_or_error(kwargs)
    if err:
        return err
    source = next((kwargs.get(k) for k in source_keys if kwargs.get(k)), None)
    if not source:
        return _error(f"{source_keys[0]} (or file/file_url) is required")
    try:
        media = _resolve_media(kind, source)
        kw = _common_kw(kwargs, chat_id)
    except ValueError as exc:
        return _error(str(exc))
    if kwargs.get("caption"):
        kw["caption"] = str(kwargs["caption"])
    extra_fields = {}
    if _parse_mode(kwargs) and kw.get("caption"):
        extra_fields["parse_mode"] = _parse_mode(kwargs)
    for key in ("duration", "width", "height", "length"):
        if kwargs.get(key):
            extra_fields[key] = _coerce_int(kwargs[key])
    if kind == "video" and _truthy(kwargs.get("supports_streaming")):
        extra_fields["supports_streaming"] = True
    if kind in ("photo", "video", "animation") and _truthy(kwargs.get("has_spoiler")):
        extra_fields["has_spoiler"] = True
    for key in ("title", "performer"):
        if kind == "audio" and kwargs.get(key):
            extra_fields[key] = str(kwargs[key])
    if kwargs.get("message_effect_id"):
        extra_fields["message_effect_id"] = str(kwargs["message_effect_id"])
    if extra_fields:
        kw["extra"] = extra_fields
    return _run_sender(
        f"send{kind.capitalize()}", lambda sender: sender.send_media(kind, chat_id, media, **kw), upload=isinstance(media, tuple)
    )


def _handle_send_photo(**kwargs) -> str:
    """Send a photo. Accepts URL (SSRF-guarded), Telegram file_id, or Frappe File (<= 10 MB)."""
    return _send_media_action("photo", kwargs, ("photo", "file", "file_url"))


def _handle_send_document(**kwargs) -> str:
    """Send a document. Accepts URL (SSRF-guarded), Telegram file_id, or Frappe File (<= 50 MB)."""
    return _send_media_action("document", kwargs, ("document", "file", "file_url"))


def _handle_send_voice(**kwargs) -> str:
    return _send_media_action("voice", kwargs, ("voice", "audio", "file", "file_url"))


def _handle_send_audio(**kwargs) -> str:
    return _send_media_action("audio", kwargs, ("audio", "file", "file_url"))


def _handle_send_video(**kwargs) -> str:
    return _send_media_action("video", kwargs, ("video", "file", "file_url"))


def _handle_send_animation(**kwargs) -> str:
    return _send_media_action("animation", kwargs, ("animation", "file", "file_url"))


def _handle_send_video_note(**kwargs) -> str:
    return _send_media_action("video_note", kwargs, ("video_note", "video", "file", "file_url"))


def _handle_send_sticker(**kwargs) -> str:
    return _send_media_action("sticker", kwargs, ("sticker", "file", "file_url"))


def _handle_send_media_group(**kwargs) -> str:
    """Send an album of 2-10 photos/videos/audios/documents: ``items`` = [{type, media, caption}]."""
    chat_id, err = _chat_or_error(kwargs)
    if err:
        return err
    items = kwargs.get("items")
    try:
        if isinstance(items, str):
            items = json.loads(items)
        if not isinstance(items, list) or not 2 <= len(items) <= 10:
            return _error("items must be a list of 2-10 {type, media, caption} objects")
        built = []
        for item in items:
            if not isinstance(item, dict) or not item.get("media"):
                return _error("each item needs a media source")
            kind = item.get("type") or "photo"
            if kind not in ("photo", "video", "audio", "document"):
                return _error("item type must be photo, video, audio or document")
            built.append({"type": kind, "media": _resolve_media(kind, item["media"]), "caption": item.get("caption") or ""})
        kw = _common_kw({k: v for k, v in kwargs.items() if k != "reply_markup"}, chat_id)
        kw.pop("markup", None)
        kw.pop("protect", None)
    except ValueError as exc:
        return _error(str(exc))
    return _run_sender(
        "sendMediaGroup", lambda sender: sender.send_media_group(chat_id, built, **kw),
        upload=any(isinstance(i["media"], tuple) for i in built),
    )


def _handle_send_location(**kwargs) -> str:
    chat_id, err = _chat_or_error(kwargs)
    if err:
        return err
    try:
        lat, lon = float(kwargs.get("latitude")), float(kwargs.get("longitude"))
    except (TypeError, ValueError):
        return _error("latitude and longitude are required numbers")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return _error("latitude must be -90..90 and longitude -180..180")
    try:
        kw = _common_kw(kwargs, chat_id)
    except ValueError as exc:
        return _error(str(exc))
    kw.pop("protect", None)
    return _run_sender("sendLocation", lambda sender: sender.send_location(chat_id, lat, lon, **kw))


def _handle_send_contact(**kwargs) -> str:
    chat_id, err = _chat_or_error(kwargs)
    if err:
        return err
    phone = str(kwargs.get("phone_number") or kwargs.get("contact_phone") or "").strip()
    first = str(kwargs.get("first_name") or kwargs.get("contact_name") or "").strip()
    if not phone or not first:
        return _error("phone_number and first_name are required")
    try:
        kw = _common_kw(kwargs, chat_id)
    except ValueError as exc:
        return _error(str(exc))
    kw.pop("protect", None)
    last = str(kwargs.get("last_name") or "")
    return _run_sender("sendContact", lambda sender: sender.send_contact(chat_id, phone, first, last_name=last, **kw))


def _need_message(kwargs: dict):
    chat_id, err = _chat_or_error(kwargs)
    if err:
        return None, None, err
    if not kwargs.get("message_id"):
        return None, None, _error("message_id is required")
    return chat_id, _coerce_int(kwargs["message_id"]), None


def _handle_set_reaction(**kwargs) -> str:
    chat_id, message_id, err = _need_message(kwargs)
    if err:
        return err
    emoji = None if _truthy(kwargs.get("remove")) else (str(kwargs.get("emoji") or "").strip() or None)
    return _run_sender(
        "setMessageReaction", lambda s: s.set_reaction(chat_id, message_id, emoji, big=_truthy(kwargs.get("big")))
    )


def _handle_send_chat_action(**kwargs) -> str:
    chat_id, err = _chat_or_error(kwargs)
    if err:
        return err
    chat_action = str(kwargs.get("chat_action") or "typing")
    thread = kwargs.get("message_thread_id") or kwargs.get("thread_id")
    return _run_sender(
        "sendChatAction", lambda s: s.send_chat_action(chat_id, chat_action, thread_id=_coerce_int(thread) if thread else None)
    )


def _handle_edit_message_caption(**kwargs) -> str:
    chat_id, message_id, err = _need_message(kwargs)
    if err:
        return err
    caption = kwargs.get("caption")
    if not caption:
        return _error("caption is required")
    try:
        markup = _markup(kwargs, chat_id)
    except ValueError as exc:
        return _error(str(exc))
    return _run_sender(
        "editMessageCaption", lambda s: s.edit_message_caption(chat_id, message_id, str(caption), markup=markup)
    )


def _handle_edit_message_reply_markup(**kwargs) -> str:
    """Replace the inline keyboard; omit reply_markup to remove it."""
    chat_id, message_id, err = _need_message(kwargs)
    if err:
        return err
    try:
        markup = _markup(kwargs, chat_id)
    except ValueError as exc:
        return _error(str(exc))
    if markup and "inline_keyboard" not in markup:
        return _error("only an inline_keyboard can be edited onto an existing message")
    return _run_sender("editMessageReplyMarkup", lambda s: s.edit_message_reply_markup(chat_id, message_id, markup))


def _handle_pin_message(**kwargs) -> str:
    chat_id, message_id, err = _need_message(kwargs)
    if err:
        return err
    silent = not _truthy(kwargs.get("notify"))
    return _run_sender("pinChatMessage", lambda s: s.pin_message(chat_id, message_id, silent=silent))


def _handle_unpin_message(**kwargs) -> str:
    chat_id, err = _chat_or_error(kwargs)
    if err:
        return err
    mid = _coerce_int(kwargs["message_id"]) if kwargs.get("message_id") else None
    return _run_sender("unpinChatMessage", lambda s: s.unpin_message(chat_id, mid))


def _handle_forward_message(**kwargs) -> str:
    return _forward_or_copy("forward", kwargs)


def _handle_copy_message(**kwargs) -> str:
    return _forward_or_copy("copy", kwargs)


def _forward_or_copy(mode: str, kwargs: dict) -> str:
    chat_id, err = _chat_or_error(kwargs)
    if err:
        return err
    from_chat = str(kwargs.get("from_chat_id") or "").strip()
    if not from_chat or not kwargs.get("message_id"):
        return _error("from_chat_id and message_id are required")
    message_id = _coerce_int(kwargs["message_id"])
    thread = kwargs.get("message_thread_id") or kwargs.get("thread_id")
    common = {
        "thread_id": _coerce_int(thread) if thread else None,
        "silent": _truthy(kwargs.get("disable_notification")),
        "protect": _truthy(kwargs.get("protect_content")),
    }
    if mode == "forward":
        return _run_sender(
            "forwardMessage", lambda s: extra.forward_message(s.client, chat_id, from_chat, message_id, **common)
        )
    try:
        markup = _markup(kwargs, chat_id)
    except ValueError as exc:
        return _error(str(exc))
    return _run_sender(
        "copyMessage",
        lambda s: extra.copy_message(
            s.client, chat_id, from_chat, message_id, caption=kwargs.get("caption"),
            parse_mode=_parse_mode(kwargs), markup=markup, **common,
        ),
    )


def _handle_answer_callback_query(**kwargs) -> str:
    query_id = str(kwargs.get("callback_query_id") or "").strip()
    if not query_id:
        return _error("callback_query_id is required")
    return _run_sender(
        "answerCallbackQuery",
        lambda s: s.answer_callback_query(
            query_id, str(kwargs.get("text") or ""), show_alert=_truthy(kwargs.get("show_alert"))
        ),
    )


def _handle_edit_message_text(**kwargs) -> str:
    """Edit the text of a previously sent message."""
    chat_id = _resolve_chat_id(kwargs)
    message_id = kwargs.get("message_id")
    if not chat_id:
        return _error("chat_id or recipient_name is required")
    if not message_id:
        return _error("message_id is required")

    text = kwargs.get("text") or kwargs.get("message")
    if not text:
        return _error("text (or message) is required")

    payload = {
        "chat_id": chat_id,
        "message_id": _coerce_int(message_id),
        "text": text,
    }

    parse_mode = kwargs.get("parse_mode")
    if parse_mode in ("Markdown", "HTML", "MarkdownV2"):
        payload["parse_mode"] = parse_mode

    return _api_request("editMessageText", payload)


def _handle_delete_message(**kwargs) -> str:
    """Delete a message from a chat."""
    chat_id = _resolve_chat_id(kwargs)
    message_id = kwargs.get("message_id")
    if not chat_id:
        return _error("chat_id or recipient_name is required")
    if not message_id:
        return _error("message_id is required")

    payload = {
        "chat_id": chat_id,
        "message_id": _coerce_int(message_id),
    }
    return _api_request("deleteMessage", payload)


def _handle_get_updates(**kwargs) -> str:
    """Fetch recent updates/messages received by the bot."""
    payload = {}
    offset = kwargs.get("offset")
    if offset:
        payload["offset"] = _coerce_int(offset)
    limit = kwargs.get("limit")
    if limit:
        payload["limit"] = min(_coerce_int(limit, 100), 100)
    return _api_request("getUpdates", payload)


def _handle_get_chat_info(**kwargs) -> str:
    """Get information about a chat."""
    chat_id = _resolve_chat_id(kwargs)
    if not chat_id:
        return _error("chat_id or recipient_name is required")
    return _api_request("getChat", {"chat_id": chat_id})


def _handle_get_me(**kwargs) -> str:
    """Get information about the bot itself."""
    return _api_request("getMe", {})


def _handle_set_webhook(**kwargs) -> str:
    """Set a webhook URL for the bot."""
    url = kwargs.get("url")
    if not url:
        return _error("url is required")
    payload = {"url": url, "allowed_updates": list(ALLOWED_UPDATES)}
    secret_token = kwargs.get("secret_token")
    if secret_token:
        payload["secret_token"] = secret_token
    return _api_request("setWebhook", payload)


def _handle_delete_webhook(**kwargs) -> str:
    """Remove the bot webhook."""
    return _api_request("deleteWebhook", {})


def setup_webhook(token: str, webhook_url: str, secret_token: Optional[str] = None) -> dict:
    """
    Configure Telegram webhook for a specific bot token.

    Returns the raw Telegram API result dict (not a JSON string).
    """
    payload = {"url": webhook_url, "allowed_updates": list(ALLOWED_UPDATES)}
    if secret_token:
        payload["secret_token"] = secret_token

    result = _api_request("setWebhook", payload, token=token)
    try:
        parsed = json.loads(result)
    except Exception:
        return {"ok": False, "description": result}
    return parsed


def delete_webhook(token: str) -> dict:
    """Remove Telegram webhook for a specific bot token."""
    result = _api_request("deleteWebhook", {}, token=token)
    try:
        parsed = json.loads(result)
    except Exception:
        return {"ok": False, "description": result}
    return parsed


def get_webhook_info(token: str) -> dict:
    """Get current webhook status from Telegram for a specific bot token."""
    result = _api_request("getWebhookInfo", {}, token=token)
    try:
        parsed = json.loads(result)
    except Exception:
        return {"ok": False, "description": result}
    return parsed


# ---------------------------------------------------------------------------
# WP-X actions: venue, dice, poll, checklist, templates, topics, reads, files
# ---------------------------------------------------------------------------


def _more_kw(kwargs: dict, chat_id) -> dict:
    """Sender options for the ``telegram_senders_more`` functions (reply/thread/silent/protect/markup/effect)."""
    kw = _common_kw(kwargs, chat_id)
    if kwargs.get("message_effect_id"):
        kw["effect_id"] = str(kwargs["message_effect_id"])
    return kw


def _ok(result) -> str:
    return json.dumps({"success": True, "results": result}, default=str)


def _run_client(label: str, fn: Callable[[TelegramBotClient], Any]) -> str:
    """Like ``_run_sender`` for functions that take the raw client."""
    return _run_sender(label, lambda sender: fn(sender.client))


def _need_thread(kwargs: dict):
    chat_id, err = _chat_or_error(kwargs)
    thread = kwargs.get("message_thread_id") or kwargs.get("thread_id")
    if not err and not thread:
        err = _error("message_thread_id (the forum topic id) is required")
    return chat_id, (_coerce_int(thread) if thread else None), err


def _handle_send_venue(**kwargs) -> str:
    chat_id, err = _chat_or_error(kwargs)
    if err:
        return err
    try:
        lat, lon = float(kwargs.get("latitude")), float(kwargs.get("longitude"))
    except (TypeError, ValueError):
        return _error("latitude and longitude are required numbers")
    try:
        kw = _more_kw(kwargs, chat_id)
    except ValueError as exc:
        return _error(str(exc))
    return _run_client(
        "sendVenue",
        lambda c: more.send_venue(
            c, chat_id, lat, lon, kwargs.get("title"), kwargs.get("address"),
            foursquare_id=kwargs.get("foursquare_id") or "", google_place_id=kwargs.get("google_place_id") or "", **kw,
        ),
    )


def _handle_send_dice(**kwargs) -> str:
    chat_id, err = _chat_or_error(kwargs)
    if err:
        return err
    try:
        kw = _more_kw(kwargs, chat_id)
    except ValueError as exc:
        return _error(str(exc))
    return _run_client("sendDice", lambda c: more.send_dice(c, chat_id, str(kwargs.get("emoji") or ""), **kw))


def _handle_send_poll(**kwargs) -> str:
    chat_id, err = _chat_or_error(kwargs)
    if err:
        return err
    try:
        anon = kwargs.get("is_anonymous", kwargs.get("anonymous"))
        poll = more.build_poll(
            kwargs.get("question"), kwargs.get("options"),
            is_anonymous=None if anon is None else _truthy(anon),
            poll_type=str(kwargs.get("poll_type") or ("quiz" if _truthy(kwargs.get("quiz")) else "regular")),
            allows_multiple_answers=_truthy(kwargs.get("allows_multiple_answers")),
            correct_option_id=kwargs.get("correct_option_id"), correct_option_ids=kwargs.get("correct_option_ids"),
            explanation=str(kwargs.get("explanation") or ""), parse_mode=_parse_mode(kwargs),
            open_period=kwargs.get("open_period"),
        )
        kw = _more_kw(kwargs, chat_id)
    except (ValueError, TypeError) as exc:
        return _error(str(exc))
    return _run_client("sendPoll", lambda c: more.send_poll(c, chat_id, poll, **kw))


def _handle_stop_poll(**kwargs) -> str:
    chat_id, message_id, err = _need_message(kwargs)
    if err:
        return err
    return _run_client("stopPoll", lambda c: more.stop_poll(c, chat_id, message_id))


def _handle_send_checklist(**kwargs) -> str:
    """Business-only (Bot API sendChecklist): sent on behalf of a connected business account."""
    chat_id, err = _chat_or_error(kwargs)
    if err:
        return err
    try:
        checklist = more.build_checklist(
            kwargs.get("title"), kwargs.get("tasks"), parse_mode=_parse_mode(kwargs),
            others_can_add=_truthy(kwargs.get("others_can_add_tasks")),
            others_can_mark=_truthy(kwargs.get("others_can_mark_tasks_as_done")),
        )
        kw = _more_kw(kwargs, chat_id)
    except (ValueError, TypeError) as exc:
        return _error(str(exc))
    kw.pop("thread_id", None)
    return _run_client(
        "sendChecklist",
        lambda c: more.send_checklist(c, chat_id, str(kwargs.get("business_connection_id") or ""), checklist, **kw),
    )


# -- templates (huf.ai.telegram_templates, imported lazily) ---------------------------------------


def _templates():
    from huf.ai import telegram_templates

    return telegram_templates


def _variables(kwargs: dict) -> dict:
    raw = kwargs.get("variables")
    if raw in (None, ""):
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raise ValueError("variables must be a JSON object") from None
    if not isinstance(raw, dict):
        raise ValueError("variables must be an object of {name: value}")
    return raw


def _template_gateway(kwargs: dict) -> Optional[str]:
    return scope.run_gateway() or str(kwargs.get("gateway") or "").strip() or None


def _template_name(kwargs: dict):
    name = str(kwargs.get("template_name") or kwargs.get("name") or "").strip()
    return name, (None if name else _error("template_name is required"))


def _plain(value):
    if isinstance(value, dict):
        return value
    if hasattr(value, "_asdict"):
        return dict(value._asdict())
    if hasattr(value, "__dict__"):
        return {k: v for k, v in vars(value).items() if not k.startswith("_")}
    return value


def _handle_list_templates(**kwargs) -> str:
    try:
        return _ok(_templates().list_templates(_template_gateway(kwargs)))
    except Exception as exc:
        return _error(f"Could not list templates: {exc}")


def _handle_preview_template(**kwargs) -> str:
    name, err = _template_name(kwargs)
    if err:
        return err
    try:
        rendered = _templates().render_template(name, _variables(kwargs), _template_gateway(kwargs))
    except Exception as exc:
        return _error(f"Could not render template: {exc}")
    return _ok(_plain(rendered))


def _handle_send_template(**kwargs) -> str:
    chat_id, err = _chat_or_error(kwargs)
    if err:
        return err
    name, err = _template_name(kwargs)
    if err:
        return err
    gateway = _template_gateway(kwargs)
    if not gateway:
        return _error("gateway is required outside a Telegram gateway conversation")
    token = _token_for_run()
    if not token:
        update_last_error(SERVICE_NAME, "Telegram bot token not configured")
        return _error("Telegram bot token not configured")
    client = _make_client(token)
    thread = kwargs.get("message_thread_id") or kwargs.get("thread_id")
    reply = kwargs.get("reply_to_message_id")
    try:
        result = _templates().send_template(
            gateway, chat_id, name, _variables(kwargs) or None, thread_id=_coerce_int(thread) if thread else None,
            reply_to=_coerce_int(reply) if reply else None, sender=TelegramSender(client),
        )
    except TelegramApiError as exc:
        return _error(f"Telegram sendTemplate {client.redact(exc.description)}")
    except Exception as exc:
        return _error(f"Could not send template: {client.redact(exc)}")
    return _ok(_plain(result))


# -- forum topics ---------------------------------------------------------------------------------


def _topic_action(
        label: str, kwargs: dict, call: Callable[[TelegramBotClient, Any, Any], Any], *, deleting=False, needs_thread=True
) -> str:
    if needs_thread:
        chat_id, thread, err = _need_thread(kwargs)
    else:
        (chat_id, err), thread = _chat_or_error(kwargs), None
    if err:
        return err

    def run(client: TelegramBotClient):
        reason = more.bot_can_manage_topics(client, chat_id, deleting=deleting)
        if reason:
            raise ValueError(f"Cannot manage forum topics: {reason}.")
        return call(client, chat_id, thread)

    return _run_client(label, run)


def _handle_create_forum_topic(**kwargs) -> str:
    return _topic_action(
        "createForumTopic", kwargs,
        lambda c, chat, _t: more.create_forum_topic(
            c, chat, kwargs.get("name"), icon_color=kwargs.get("icon_color"),
            icon_custom_emoji_id=str(kwargs.get("icon_custom_emoji_id") or ""),
        ),
        needs_thread=False,
    )


def _handle_edit_forum_topic(**kwargs) -> str:
    icon = kwargs.get("icon_custom_emoji_id")
    return _topic_action(
        "editForumTopic", kwargs,
        lambda c, chat, t: more.edit_forum_topic(
            c, chat, t, name=kwargs.get("name") or "", icon_custom_emoji_id=None if icon is None else str(icon)
        ),
    )


def _handle_close_forum_topic(**kwargs) -> str:
    return _topic_action("closeForumTopic", kwargs, lambda c, chat, t: more.topic_call(c, "closeForumTopic", chat, t))


def _handle_reopen_forum_topic(**kwargs) -> str:
    return _topic_action("reopenForumTopic", kwargs, lambda c, chat, t: more.topic_call(c, "reopenForumTopic", chat, t))


def _handle_delete_forum_topic(**kwargs) -> str:
    return _topic_action(
        "deleteForumTopic", kwargs, lambda c, chat, t: more.topic_call(c, "deleteForumTopic", chat, t), deleting=True
    )


# -- read-only chat info ----------------------------------------------------------------------------


def _handle_get_chat_member(**kwargs) -> str:
    chat_id, err = _chat_or_error(kwargs)
    if err:
        return err
    if not kwargs.get("user_id"):
        return _error("user_id is required")
    return _run_client("getChatMember", lambda c: more.get_chat_member(c, chat_id, kwargs["user_id"]))


def _handle_get_chat_administrators(**kwargs) -> str:
    chat_id, err = _chat_or_error(kwargs)
    if err:
        return err
    return _run_client("getChatAdministrators", lambda c: more.get_chat_administrators(c, chat_id))


def _handle_get_chat_member_count(**kwargs) -> str:
    chat_id, err = _chat_or_error(kwargs)
    if err:
        return err
    return _run_client("getChatMemberCount", lambda c: more.get_chat_member_count(c, chat_id))


# -- get_file ---------------------------------------------------------------------------------------


def _handle_get_file(**kwargs) -> str:
    """Download a Telegram file_id (<= 20 MB, the Bot API limit) into a private Frappe File."""
    file_id = str(kwargs.get("file_id") or "").strip()
    if not _FILE_ID_RE.fullmatch(file_id):
        return _error("file_id (a Telegram file_id) is required")

    def run(sender: TelegramSender):
        client = sender.client
        info = client.call("getFile", {"file_id": file_id}) or {}
        size = _coerce_int(info.get("file_size"))
        if size > more.MAX_GET_FILE_BYTES:
            raise ValueError(f"File is {_mb(size)}; the Bot API allows downloads up to {_mb(more.MAX_GET_FILE_BYTES)}")
        content, file_path = client.download_file(file_id)
        if len(content) > more.MAX_GET_FILE_BYTES:
            raise ValueError(f"File is {_mb(len(content))}; the Bot API allows downloads up to {_mb(more.MAX_GET_FILE_BYTES)}")
        name = os.path.basename(str(file_path)) or "telegram_file"
        doc = frappe.get_doc({"doctype": "File", "file_name": name, "content": content, "is_private": 1})
        doc.insert()
        return {"file_url": doc.file_url, "file_name": name, "size": len(content), "file_path": file_path}

    return _run_sender("getFile", run, upload=True)


# -- list_messages / get_account_info -----------------------------------------------------------------

_LIST_DEFAULT, _LIST_MAX, _TEXT_MAX = 20, 50, 500
_SECRET_RE = re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b")


def _redact_text(text) -> str:
    return _SECRET_RE.sub("[redacted]", str(text or ""))[:_TEXT_MAX]


def _merge_outbound(gateway: str, chat: str, items: list, limit: int) -> list:
    """Add the bot's own recorded messages (direction outbound) to the inbound items, newest first."""
    from huf.ai.gateway_adapters import telegram_messages

    for it in items:
        it["direction"] = "inbound"
    out = [
        {"id": str(r["message_id"]), "time": str(r.get("time") or ""), "sender": "bot", "kind": r.get("kind") or "text",
         "text": _redact_text(r.get("text_preview")), "direction": "outbound"}
        for r in telegram_messages.outbound_for_chat(gateway, chat)
    ]
    return sorted(items + out, key=lambda r: r.get("time") or "", reverse=True)[:limit]


def _handle_list_messages(**kwargs) -> str:
    """Recent Gateway Events for this gateway and ONE chat (newest first, redacted, max 50)."""
    gateway = _template_gateway(kwargs)
    if not gateway:
        return _error("gateway is required outside a Telegram gateway conversation")
    chat = scope.normalize_chat(_resolve_chat_id(kwargs))
    if not chat:
        return _error("chat_id is required")
    try:
        limit = max(1, min(_coerce_int(kwargs.get("limit"), _LIST_DEFAULT), _LIST_MAX))
    except Exception:
        limit = _LIST_DEFAULT
    in_run = bool(scope.run_gateway())
    if in_run and chat != scope.current_chat(scope.effective_run_id()):
        return _refused("action_not_permitted", "list_messages only reads the current chat.")
    filters = {"gateway": gateway, "conversation_id": ["like", f"{chat}%"]}
    order = "received_at desc"
    try:
        if in_run:
            # Controlled read for the gateway execution user: current gateway + current chat only, redacted fields.
            rows = frappe.get_all(
                "Gateway Event", filters=filters,
                fields=["provider_event_id", "sender_id", "message_text", "status", "received_at"],
                order_by=order, limit_page_length=limit, ignore_permissions=True,
            )
            items = [
                {
                    "id": r.get("provider_event_id"), "time": str(r.get("received_at") or ""),
                    "sender": str(r.get("sender_id") or ""), "kind": "inbound",
                    "text": _redact_text(r.get("message_text")), "status": r.get("status"),
                }
                for r in rows
            ]
            items = _merge_outbound(gateway, chat, items, limit)
            return _ok({"items": items, "count": len(items)})
        if not frappe.has_permission("Gateway Event", "read"):
            return _refused("permission_denied", "Not permitted to read Gateway Events.")
        rows = frappe.get_list(
            "Gateway Event",
            filters=filters,
            fields=["name", "provider_event_id", "sender_id", "message_text", "status", "received_at", "reply_status"],
            order_by=order,
            limit_page_length=limit,
        )
    except frappe.PermissionError:
        return _refused("permission_denied", "Not permitted to read Gateway Events.")
    except Exception as exc:
        return _error(f"Could not list messages: {exc}")
    items = [{**r, "message_text": _redact_text(r.get("message_text"))} for r in rows]
    return _ok({"items": items, "count": len(items)})


def _handle_get_account_info(**kwargs) -> str:
    """Bot identity, capability flags and webhook health (no secrets, no URLs)."""
    from huf.ai.gateway_adapters import telegram_health as health

    gateway = _template_gateway(kwargs)

    def run(sender: TelegramSender):
        client = sender.client
        info = {"bot": health.check_bot(client)}
        wh = health.check_webhook(client, "")
        info["webhook"] = {
            "registered": bool(wh["url"]), "pending_update_count": wh["pending_update_count"],
            "last_error_date": wh["last_error_date"], "last_error_message": client.redact(wh["last_error_message"]),
            "allowed_updates_ok": wh["allowed_updates_ok"],
        }
        if gateway:
            try:
                fields = ["telegram_parse_mode", "telegram_business_policy", "telegram_join_policy", "direct_policy",
                    "room_policy", "voice_reply_mode", "telegram_streaming", "telegram_inline_enabled"]
                row = frappe.db.get_value("Gateway", gateway, fields, as_dict=True) or {}
                info["gateway"] = {"name": gateway, **{k: v for k, v in row.items() if v not in (None, "")}}
            except Exception:
                info["gateway"] = {"name": gateway}
        return info

    return _run_sender("getAccountInfo", run)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def handle_action(**kwargs) -> str:
    """
    Dispatch Telegram actions.

    Args:
        action (str): The action to perform.
        chat_id (str|int): Target Telegram chat/channel ID.
        recipient_name (str): Optional named recipient from Integration Settings.
        text / message (str): Message text.
        parse_mode (str): "Markdown" (default), "HTML", "MarkdownV2", or omitted.
        reply_to_message_id (int): Message ID to reply to.
        photo / file / file_url (str): Media source for send_photo.
        document / file / file_url (str): Document source for send_document.
        caption (str): Caption for media messages.
        message_id (int): Message ID for edit/delete.
        url (str): Webhook URL for set_webhook.
        secret_token (str): Secret token for webhook.
        offset / limit (int): Pagination for get_updates.
        disable_notification (bool): Send silently.

    Returns:
        JSON string with success flag and Telegram API result.
    """
    action = (kwargs.get("action") or "").strip().lower()

    dispatch = {
        "send_message": _handle_send_message,
        "reply_to_message": _handle_reply_to_message,
        "send_photo": _handle_send_photo,
        "send_document": _handle_send_document,
        "send_voice": _handle_send_voice,
        "send_audio": _handle_send_audio,
        "send_video": _handle_send_video,
        "send_animation": _handle_send_animation,
        "send_sticker": _handle_send_sticker,
        "send_media_group": _handle_send_media_group,
        "send_location": _handle_send_location,
        "send_contact": _handle_send_contact,
        "send_video_note": _handle_send_video_note,
        "send_venue": _handle_send_venue,
        "send_dice": _handle_send_dice,
        "send_poll": _handle_send_poll,
        "stop_poll": _handle_stop_poll,
        "send_checklist": _handle_send_checklist,
        "send_template": _handle_send_template,
        "list_templates": _handle_list_templates,
        "preview_template": _handle_preview_template,
        "create_forum_topic": _handle_create_forum_topic,
        "edit_forum_topic": _handle_edit_forum_topic,
        "close_forum_topic": _handle_close_forum_topic,
        "reopen_forum_topic": _handle_reopen_forum_topic,
        "delete_forum_topic": _handle_delete_forum_topic,
        "get_chat_member": _handle_get_chat_member,
        "get_chat_administrators": _handle_get_chat_administrators,
        "get_chat_member_count": _handle_get_chat_member_count,
        "get_file": _handle_get_file,
        "list_messages": _handle_list_messages,
        "get_account_info": _handle_get_account_info,
        "set_reaction": _handle_set_reaction,
        "send_chat_action": _handle_send_chat_action,
        "edit_message_text": _handle_edit_message_text,
        "edit_message_caption": _handle_edit_message_caption,
        "edit_message_reply_markup": _handle_edit_message_reply_markup,
        "delete_message": _handle_delete_message,
        "pin_message": _handle_pin_message,
        "unpin_message": _handle_unpin_message,
        "forward_message": _handle_forward_message,
        "copy_message": _handle_copy_message,
        "answer_callback_query": _handle_answer_callback_query,
        "get_updates": _handle_get_updates,
        "get_chat_info": _handle_get_chat_info,
        "get_me": _handle_get_me,
        "set_webhook": _handle_set_webhook,
        "delete_webhook": _handle_delete_webhook,
    }

    handler = dispatch.get(action)
    if not handler:
        valid = ", ".join(sorted(dispatch.keys()))
        return _error(f"Unknown action '{action}'. Valid actions: {valid}")

    key = _idempotency_key(action, kwargs)
    if isinstance(key, tuple):  # (error JSON,)
        return key[0]
    if key:
        refusal = _scope_refusal(action, kwargs)  # scope BEFORE any cached result is returned
        if refusal:
            return refusal
        existing = _idem_claim(key)
        if existing is not None:
            return existing
        raw = _scoped_dispatch(action, handler, kwargs)
        _idem_finish(key, raw)
        return raw
    return _scoped_dispatch(action, handler, kwargs)


def _scope_refusal(action: str, kwargs: dict) -> Optional[str]:
    """Refusal JSON when this call is not allowed inside the run's gateway scope (no mutation), else None."""
    gateway = scope.run_gateway()
    if not gateway:
        state, _ = scope.gateway_state()
        if state == "invalid":
            return _refused(
                "action_not_permitted",
                "This run's gateway is disabled, missing or not a Telegram gateway; Telegram tools are unavailable.",
            )
        return None
    if action in GATEWAY_BLOCKED_ACTIONS:
        return _refused("action_not_permitted", f"{action} is not available to agents running inside a gateway.")
    if action in CHAT_ACTIONS:
        run_id = scope.effective_run_id()
        if scope.is_inline_run(run_id):
            return _refused("action_not_permitted", "Inline-mode runs have no chat; Telegram chat actions are not available.")
        chat = _resolve_chat_id(kwargs) or scope.current_chat(run_id)
        if not chat:
            return _error("chat_id or recipient_name is required")
        refusal = scope.check_recipient(gateway, run_id, chat)
        if not refusal and action in ("forward_message", "copy_message"):
            refusal = scope.check_recipient(gateway, run_id, kwargs.get("from_chat_id"))
        if refusal:
            return refusal
        if action in OUTBOUND_ONLY_ACTIONS:
            from huf.ai.gateway_adapters import telegram_messages

            if not telegram_messages.is_outbound(gateway, scope.normalize_chat(chat), kwargs.get("message_id")):
                return _refused(
                    "action_not_permitted",
                    f"{action} only works on messages the bot sent in this chat; get ids from list_messages.",
                )
        gate = GATEWAY_FLAG_GATES.get(action)
        if gate and not _gateway_flag(gateway, gate[0]):
            return _refused("action_not_permitted", f"{action} needs the gateway's {gate[1]} access for agents to be enabled.")
    return None


def _scoped_dispatch(action: str, handler: Callable[..., str], kwargs: dict) -> str:
    refusal = _scope_refusal(action, kwargs)
    if refusal:
        return refusal
    gateway = scope.run_gateway()
    if not gateway:
        return handler(**kwargs)  # not inside a gateway run: explicit chat ids / Integration Settings recipients

    # Inside a Telegram gateway run the model is not trusted (checked above); pin the target chat.
    kwargs.pop("gateway_name", None)
    if action in CHAT_ACTIONS:
        run_id = scope.effective_run_id()
        kwargs["chat_id"] = _resolve_chat_id(kwargs) or scope.current_chat(run_id)
        kwargs.pop("recipient_name", None)
        if action in SEND_ACTIONS:
            refusal = scope.claim_send(gateway, run_id)
            if refusal:
                return refusal
            try:
                raw = handler(**kwargs)
            except Exception:
                scope.release_send(gateway, run_id)
                raise
            if not _succeeded(raw):
                scope.release_send(gateway, run_id)
            else:
                if action in SEND_ACTIONS and scope.normalize_chat(kwargs["chat_id"]) == scope.current_chat(run_id):
                    run_delivery.mark(run_id)
                    scope.note_current_chat_text(
                        gateway, run_id, kwargs.get("text") or kwargs.get("message") or kwargs.get("caption") or f"[{action}]")
                _record_tool_send(gateway, kwargs["chat_id"], action, kwargs, raw)
            return raw
    return handler(**kwargs)


OUTBOUND_ONLY_ACTIONS = frozenset({"edit_message_text", "delete_message"})


def _message_ids(node) -> list:
    if isinstance(node, dict):
        if node.get("message_id") is not None:
            return [node["message_id"]]
        return [i for v in node.values() for i in _message_ids(v)]
    if isinstance(node, list):
        return [i for v in node for i in _message_ids(v)]
    return []


def _record_tool_send(gateway: str, chat, action: str, kwargs: dict, raw: str) -> None:
    """Remember message ids a tool send created in the current chat (best effort)."""
    try:
        from huf.ai.gateway_adapters import telegram_messages

        ids = _message_ids(json.loads(raw).get("results"))
        text = kwargs.get("text") or kwargs.get("message") or kwargs.get("caption") or ""
        kind = "text" if action in ("send_message", "reply_to_message") else action.replace("send_", "")
        telegram_messages.record_outbound(gateway, scope.normalize_chat(chat), ids, kind=kind, text=text)
    except Exception:
        pass


GATEWAY_BLOCKED_ACTIONS = frozenset({"set_webhook", "delete_webhook", "get_updates"})
# Actions that take a target chat (checked against the gateway scope).
CHAT_ACTIONS = frozenset({
    "send_message", "reply_to_message", "send_photo", "send_document", "send_voice", "send_audio", "send_video",
    "send_animation", "send_sticker", "send_media_group", "send_location", "send_contact", "set_reaction",
    "send_chat_action", "edit_message_text", "edit_message_caption", "edit_message_reply_markup",
    "delete_message", "pin_message", "unpin_message", "forward_message", "copy_message", "get_chat_info",
    "send_video_note", "send_venue", "send_dice", "send_poll", "stop_poll", "send_checklist", "send_template",
    "create_forum_topic", "edit_forum_topic", "close_forum_topic", "reopen_forum_topic", "delete_forum_topic",
    "get_chat_member", "get_chat_administrators", "get_chat_member_count", "list_messages",
})
# Actions that create a new message (counted against the per-run / per-day caps).
SEND_ACTIONS = frozenset({
    "send_message", "reply_to_message", "send_photo", "send_document", "send_voice", "send_audio", "send_video",
    "send_animation", "send_sticker", "send_media_group", "send_location", "send_contact", "forward_message",
    "copy_message", "send_video_note", "send_venue", "send_dice", "send_poll", "send_checklist", "send_template",
})
# Extra gateway-flag gates: sendChecklist acts as the connected business account owner.
GATEWAY_FLAG_GATES = {"send_checklist": ("telegram_agent_allow_business", "business account")}


# -- idempotency (optional ``idempotency_key``; like whatsapp_send_keys but cache-backed) ---------------

IDEM_TTL = 24 * 3600
_IDEM_KEY_RE = re.compile(r"[A-Za-z0-9._:-]{1,120}")


def _gateway_flag(gateway: str, field: str) -> bool:
    try:
        return bool(frappe.db.get_value("Gateway", gateway, field))
    except Exception:
        return False


def _idem_cache():
    return frappe.cache()


def _idempotency_key(action: str, kwargs: dict):
    """Cache key for a send with an ``idempotency_key`` (None when absent / not a send); ``(error,)`` if invalid."""
    raw = kwargs.pop("idempotency_key", None)
    if raw in (None, "") or action not in SEND_ACTIONS:
        return None
    raw = str(raw).strip()
    if not _IDEM_KEY_RE.fullmatch(raw):
        return (_refused("invalid_idempotency_key", "idempotency_key must be 1-120 chars of letters, digits, . _ : -"),)
    chat = scope.normalize_chat(_resolve_chat_id(kwargs)) or scope.current_chat(scope.effective_run_id())
    return f"huf_tg_idem:{scope.run_gateway() or '-'}:{scope.effective_run_id() or '-'}:{chat or '-'}:{action}:{raw}"


def _idem_claim(key: str) -> Optional[str]:
    """Previous result (or an in-flight refusal) for ``key``; None after claiming it for this call."""
    try:
        prior = _idem_cache().get_value(key)
    except Exception:
        prior = None
    if isinstance(prior, dict):
        if prior.get("state") == "done":
            return prior.get("result")
        return _refused("duplicate_in_flight", "A send with this idempotency_key is already in progress.")
    try:
        _idem_cache().set_value(key, {"state": "pending"}, expires_in_sec=IDEM_TTL)
    except Exception:
        pass
    return None


def _idem_finish(key: str, raw: str) -> None:
    try:
        if _succeeded(raw):
            _idem_cache().set_value(key, {"state": "done", "result": raw}, expires_in_sec=IDEM_TTL)
        else:
            _idem_cache().delete_value(key)  # a failed send may be retried with the same key
    except Exception:
        pass


def _refused(code: str, message: str) -> str:
    return json.dumps({"success": False, "error": code, "message": message})


def _succeeded(raw: str) -> bool:
    try:
        return bool(json.loads(raw).get("success"))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Backward-compatible wrapper for the old single-action function path.
# ---------------------------------------------------------------------------


def handle_send_message(**kwargs) -> str:
    """Backward-compatible wrapper around telegram action."""
    kwargs["action"] = "send_message"
    if "message" in kwargs and "text" not in kwargs:
        kwargs["text"] = kwargs["message"]
    return handle_action(**kwargs)
