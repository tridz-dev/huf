"""
Telegram webhook handler for two-way agent conversations.

Receives updates from Telegram Bot API, routes user messages to a configured
HUF Agent, and sends the agent's response back to Telegram.

Security:
- The webhook URL contains only the non-secret Integration Settings docname.
- Telegram sends the configured secret token in the
  X-Telegram-Bot-Api-Secret-Token header; requests without a matching secret
  are rejected.
- Message processing happens in a background job so the HTTP response to
  Telegram is immediate and the agent has ample time to run.
"""

import json
import secrets
from typing import Optional

import frappe
from frappe.utils.background_jobs import enqueue


WEBHOOK_HEADER = "X-Telegram-Bot-Api-Secret-Token"


def _error(msg: str) -> dict:
    return {"success": False, "error": msg}


def _get_request_body() -> dict:
    """Read JSON body from the current Frappe request."""
    if not frappe.request:
        return {}

    try:
        data = frappe.request.get_data(as_text=True)
        if data:
            return json.loads(data)
    except Exception:
        pass
    return {}


def _get_request_header(name: str) -> str:
    """Read a request header in a Werkzeug/Frappe-compatible way."""
    if not frappe.request:
        return ""
    # Werkzeug headers are case-insensitive; use .headers.get directly
    return (frappe.request.headers.get(name) or "").strip()


@frappe.whitelist(allow_guest=True, methods=["POST"])
def handle_update():
    """
    Public webhook endpoint for Telegram updates.

    Query params:
        doc (str): Integration Settings document name identifying the bot.

    Headers:
        X-Telegram-Bot-Api-Secret-Token: must match the configured secret.

    Returns:
        HTTP 200 immediately; processing is enqueued as a background job.
    """
    try:
        docname = (frappe.request.args.get("doc") if frappe.request else None) or ""
        if not docname:
            return _error("Missing bot identifier")

        if not frappe.db.exists("Integration Settings", docname):
            return _error("Invalid bot identifier")

        settings = frappe.get_doc("Integration Settings", docname)
        if settings.service != "telegram" or not settings.is_active:
            return _error("Bot configuration inactive")

        # Verify secret token (constant-time compare to avoid timing attacks)
        expected_secret = settings.get_password("telegram_webhook_secret") or ""
        provided_secret = _get_request_header(WEBHOOK_HEADER)
        if expected_secret and not secrets.compare_digest(provided_secret, expected_secret):
            return _error("Invalid secret token")

        body = _get_request_body()
        if not body:
            return _error("Empty request body")

        # Enqueue actual processing so Telegram gets an immediate 200 response.
        enqueue(
            "huf.ai.tools.telegram_webhook.process_telegram_update",
            queue="default",
            settings_name=docname,
            update=body,
            timeout=300,
        )

        return {"success": True, "message": "Update accepted"}
    except Exception as e:
        frappe.log_error(f"Telegram webhook handler error: {e}", "Telegram Webhook")
        return _error(str(e))


def process_telegram_update(settings_name: str, update: dict):
    """
    Background worker: parse a Telegram update, run the configured HUF Agent,
    and send the reply back to Telegram.
    """
    try:
        frappe.set_user("Administrator")

        if not frappe.db.exists("Integration Settings", settings_name):
            frappe.log_error(f"Integration Settings {settings_name} not found", "Telegram Webhook")
            return

        settings = frappe.get_doc("Integration Settings", settings_name)
        if settings.service != "telegram" or not settings.is_active:
            return

        agent_name = settings.telegram_agent
        if not agent_name:
            frappe.log_error(
                f"No agent configured for Telegram bot {settings_name}", "Telegram Webhook"
            )
            return

        if not frappe.db.exists("Agent", agent_name):
            frappe.log_error(f"Agent {agent_name} not found", "Telegram Webhook")
            return

        message = _extract_message(update)
        if not message:
            # Nothing to reply to (e.g. callback query without text, channel post)
            return

        chat_id = message.get("chat_id")
        text = message.get("text")
        message_id = message.get("message_id")
        if not chat_id:
            frappe.log_error("Telegram update missing chat_id", "Telegram Webhook")
            return

        if not text:
            # No text to process; optionally send a hint that only text is supported
            _send_telegram_message(
                settings,
                chat_id,
                "Sorry, I can only process text messages right now.",
                reply_to_message_id=message_id,
            )
            return

        # Run the HUF agent
        try:
            from huf.ai.agent_integration import run_agent_sync

            result = run_agent_sync(
                agent_name=agent_name,
                prompt=text,
                channel_id="telegram",
                external_id=str(chat_id),
            )
            response_text = result.get("response") if isinstance(result, dict) else str(result)
        except Exception as e:
            frappe.log_error(f"Agent run failed for Telegram message: {e}", "Telegram Webhook")
            response_text = "Sorry, I couldn't process your message. Please try again later."

        if response_text:
            _send_telegram_message(
                settings,
                chat_id,
                response_text,
                reply_to_message_id=message_id,
            )

    except Exception as e:
        frappe.log_error(f"Error processing Telegram update: {e}", "Telegram Webhook")
    finally:
        frappe.db.commit()


def _extract_message(update: dict) -> Optional[dict]:
    """Extract chat_id, text and message_id from a Telegram update."""
    # Priority: edited_message -> message -> channel_post -> edited_channel_post
    msg = (
        update.get("edited_message")
        or update.get("message")
        or update.get("channel_post")
        or update.get("edited_channel_post")
    )
    if not msg:
        return None

    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    if not chat_id:
        return None

    return {
        "chat_id": chat_id,
        "text": msg.get("text") or msg.get("caption"),
        "message_id": msg.get("message_id"),
        "username": (msg.get("from") or {}).get("username"),
        "first_name": (msg.get("from") or {}).get("first_name"),
    }


def _send_telegram_message(settings, chat_id, text: str, reply_to_message_id=None):
    """Send a text reply back to Telegram using the configured bot."""
    try:
        from huf.ai.tools.telegram import handle_action

        kwargs = {
            "action": "send_message",
            "chat_id": str(chat_id),
            "text": text,
        }
        if reply_to_message_id:
            kwargs["reply_to_message_id"] = reply_to_message_id

        result = handle_action(**kwargs)
        try:
            parsed = json.loads(result) if result else {}
        except Exception:
            parsed = {}

        if not parsed.get("success"):
            error = parsed.get("error") or result or "Unknown Telegram send error"
            frappe.log_error(
                f"Telegram reply failed for {settings.name} to chat {chat_id}: {error}",
                "Telegram Webhook",
            )
    except Exception as e:
        frappe.log_error(f"Failed to send Telegram reply: {e}", "Telegram Webhook")
