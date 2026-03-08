"""
Telegram integration tools for sending messages via Telegram bot.
Uses HUF Integration Settings for credential management.
"""

import json
import frappe
import httpx
from typing import Optional
from huf.ai.tools.credentials import require_credential, get_credential, update_last_error


def handle_send_message(chat_id: str, message: str, **kwargs) -> str:
    """
    Send a message via Telegram bot.
    
    Args:
        chat_id: Telegram chat ID to send to
        message: Message text
    
    Returns:
        JSON string with the response from Telegram API
    """
    try:
        # Get token from Integration Settings
        token = get_credential("telegram", "token")
        if not token:
            return json.dumps({"error": "Telegram bot token not configured. Please set up Integration Settings for telegram service with 'token' credential."})
        
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
            "data": response.json()
        })
    except httpx.HTTPError as e:
        error_msg = f"Telegram API error: {e}"
        frappe.log_error(error_msg)
        update_last_error("telegram", error_msg)
        return json.dumps({"error": f"HTTP error: {str(e)}"})
    except Exception as e:
        error_msg = f"Telegram send error: {e}"
        frappe.log_error(error_msg)
        update_last_error("telegram", error_msg)
        return json.dumps({"error": str(e)})
