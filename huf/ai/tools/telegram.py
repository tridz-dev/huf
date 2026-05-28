"""
Telegram integration tools for sending messages via Telegram bot.
Uses HUF Integration Settings for credential management.
"""

import json
import frappe
import httpx
from huf.ai.tools.credentials import require_credential, get_credential, update_last_error


def _handle_send_message(**kwargs) -> str:
    """Send a message via Telegram bot."""
    service_name = "telegram"
    try:
        chat_id = kwargs.get("chat_id")
        message = kwargs.get("message")
        if not all([chat_id, message]):
            return json.dumps({"success": False, "error": "chat_id and message are required"})

        # Get token from Integration Settings
        token = get_credential(service_name, "token")
        if not token:
            error_msg = "Telegram bot token not configured"
            update_last_error(service_name, error_msg)
            return json.dumps({"success": False, "error": error_msg})
        
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        
        response = httpx.post(url, json=payload, timeout=30)
        response.raise_for_status()
        
        return json.dumps({
            "success": True,
            "results": response.json()
        })
    except Exception as e:
        error_msg = f"Telegram Send Message Error: {str(e)}"
        frappe.log_error(error_msg, "Telegram Tool")
        update_last_error(service_name, error_msg)
        return json.dumps({"success": False, "error": str(e)})


def handle_action(**kwargs) -> str:
    action = kwargs.get("action", "").strip().lower()
    dispatch = {
        "send_message": _handle_send_message,
    }
    handler = dispatch.get(action)
    if not handler:
        valid = ", ".join(sorted(dispatch.keys()))
        return json.dumps({"success": False, "error": f"Unknown action '{action}'. Valid: {valid}"})
    return handler(**kwargs)
