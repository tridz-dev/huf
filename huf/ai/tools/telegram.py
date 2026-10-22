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
"""

import json
import os
from typing import Optional

import frappe
logger = frappe.logger("huf")

from huf.ai.gateway_adapters.telegram_client import ALLOWED_UPDATES, TelegramApiError, TelegramBotClient
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
        token = _get_token()
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


def _resolve_file_payload(param_name: str, file_source):
    """
    Resolve a media parameter for Telegram API.

    Returns (payload_value, files_dict). If a local Frappe file is found, the
    file is opened for multipart upload and payload_value is omitted (Telegram
    reads it from the form part). Otherwise the value is sent as a string
    (URL or Telegram file_id).
    """
    if not file_source:
        return None, None

    source = str(file_source).strip()

    # Public URL
    if source.startswith("http://") or source.startswith("https://"):
        return source, None

    # Try resolving as a Frappe file first (by docname or file_url)
    file_doc = None
    try:
        if frappe.db.exists("File", source):
            file_doc = frappe.get_doc("File", source)
        else:
            file_name = frappe.db.get_value("File", {"file_url": source}, "name")
            if file_name:
                file_doc = frappe.get_doc("File", file_name)
    except Exception:
        file_doc = None

    if file_doc:
        file_path = file_doc.get_full_path()
        if os.path.exists(file_path):
            filename = os.path.basename(file_path)
            mime_type = file_doc.content_type or "application/octet-stream"
            return None, {param_name: (filename, open(file_path, "rb"), mime_type)}

    # Fallback: treat as Telegram file_id
    return source, None


def _build_message_payload(kwargs: dict) -> tuple:
    """Build common payload for send/edit operations. Returns (payload, files)."""
    chat_id = _resolve_chat_id(kwargs)
    if not chat_id:
        return _error("chat_id or recipient_name is required"), None

    text = kwargs.get("text") or kwargs.get("message")
    if not text:
        return _error("text (or message) is required"), None

    payload = {}
    if chat_id:
        payload["chat_id"] = chat_id
    if text:
        payload["text"] = text

    parse_mode = kwargs.get("parse_mode")
    if parse_mode in ("Markdown", "HTML", "MarkdownV2"):
        payload["parse_mode"] = parse_mode

    disable_notification = kwargs.get("disable_notification")
    if disable_notification is not None:
        payload["disable_notification"] = bool(int(disable_notification))

    reply_to_message_id = kwargs.get("reply_to_message_id")
    if reply_to_message_id:
        _apply_reply(payload, reply_to_message_id)

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


def _handle_send_photo(**kwargs) -> str:
    """Send a photo to a chat. Accepts URL, Telegram file_id, or Frappe File."""
    chat_id = _resolve_chat_id(kwargs)
    if not chat_id:
        return _error("chat_id or recipient_name is required")

    photo_source = kwargs.get("photo") or kwargs.get("file") or kwargs.get("file_url")
    if not photo_source:
        return _error("photo (or file/file_url) is required")

    payload = {"chat_id": chat_id}
    photo_value, files = _resolve_file_payload("photo", photo_source)
    if photo_value:
        payload["photo"] = photo_value

    caption = kwargs.get("caption")
    if caption:
        payload["caption"] = caption

    parse_mode = kwargs.get("parse_mode")
    if parse_mode in ("Markdown", "HTML", "MarkdownV2"):
        payload["parse_mode"] = parse_mode

    disable_notification = kwargs.get("disable_notification")
    if disable_notification is not None:
        payload["disable_notification"] = bool(int(disable_notification))

    reply_to_message_id = kwargs.get("reply_to_message_id")
    if reply_to_message_id:
        _apply_reply(payload, reply_to_message_id)

    return _api_request("sendPhoto", payload, files)


def _handle_send_document(**kwargs) -> str:
    """Send a document to a chat. Accepts URL, Telegram file_id, or Frappe File."""
    chat_id = _resolve_chat_id(kwargs)
    if not chat_id:
        return _error("chat_id or recipient_name is required")

    document_source = kwargs.get("document") or kwargs.get("file") or kwargs.get("file_url")
    if not document_source:
        return _error("document (or file/file_url) is required")

    payload = {"chat_id": chat_id}
    document_value, files = _resolve_file_payload("document", document_source)
    if document_value:
        payload["document"] = document_value

    caption = kwargs.get("caption")
    if caption:
        payload["caption"] = caption

    parse_mode = kwargs.get("parse_mode")
    if parse_mode in ("Markdown", "HTML", "MarkdownV2"):
        payload["parse_mode"] = parse_mode

    disable_notification = kwargs.get("disable_notification")
    if disable_notification is not None:
        payload["disable_notification"] = bool(int(disable_notification))

    reply_to_message_id = kwargs.get("reply_to_message_id")
    if reply_to_message_id:
        _apply_reply(payload, reply_to_message_id)

    return _api_request("sendDocument", payload, files)


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
        "edit_message_text": _handle_edit_message_text,
        "delete_message": _handle_delete_message,
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

    return handler(**kwargs)


# ---------------------------------------------------------------------------
# Backward-compatible wrapper for the old single-action function path.
# ---------------------------------------------------------------------------


def handle_send_message(**kwargs) -> str:
    """Backward-compatible wrapper around telegram action."""
    kwargs["action"] = "send_message"
    if "message" in kwargs and "text" not in kwargs:
        kwargs["text"] = kwargs["message"]
    return handle_action(**kwargs)
