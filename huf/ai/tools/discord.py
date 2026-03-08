"""
Discord integration tools for sending messages and managing channels.
Uses HUF Integration Settings for credential management.
"""

import json
import frappe
import httpx
from typing import Optional
from huf.ai.tools.credentials import require_credential, get_credential, update_last_error


def _get_discord_headers():
    """Get Discord API headers with bot token."""
    token = get_credential("discord", "bot_token")
    if not token:
        raise ValueError("Discord bot token not configured")
    return {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json"
    }


def handle_send_message(channel_id: str, message: str, **kwargs) -> str:
    """Send a message to a Discord channel."""
    try:
        headers = _get_discord_headers()
        payload = {"content": message}
        
        response = httpx.post(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        
        return json.dumps({"success": True, "data": response.json()})
    except Exception as e:
        error_msg = f"Discord send error: {e}"
        frappe.log_error(error_msg)
        update_last_error("discord", error_msg)
        return json.dumps({"error": str(e)})


def handle_get_channel_messages(channel_id: str, limit: int = 50, **kwargs) -> str:
    """Get message history of a Discord channel."""
    try:
        headers = _get_discord_headers()
        
        response = httpx.get(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            headers=headers,
            params={"limit": min(limit, 100)},
            timeout=30
        )
        response.raise_for_status()
        
        messages = response.json()
        simplified = [{"id": msg.get("id"), "content": msg.get("content", ""), "author": msg.get("author", {}).get("username", "unknown")}
                      for msg in messages]
        
        return json.dumps({"success": True, "messages": simplified})
    except Exception as e:
        error_msg = f"Discord get messages error: {e}"
        frappe.log_error(error_msg)
        update_last_error("discord", error_msg)
        return json.dumps({"error": str(e)})


def handle_list_channels(guild_id: str, **kwargs) -> str:
    """List all channels in a Discord server (guild)."""
    try:
        headers = _get_discord_headers()
        
        response = httpx.get(
            f"https://discord.com/api/v10/guilds/{guild_id}/channels",
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        
        channels = response.json()
        simplified = [{"id": ch.get("id"), "name": ch.get("name"), "type": ch.get("type")}
                      for ch in channels]
        
        return json.dumps({"success": True, "channels": simplified})
    except Exception as e:
        error_msg = f"Discord list channels error: {e}"
        frappe.log_error(error_msg)
        update_last_error("discord", error_msg)
        return json.dumps({"error": str(e)})


def handle_delete_message(channel_id: str, message_id: str, **kwargs) -> str:
    """Delete a message from a Discord channel."""
    try:
        headers = _get_discord_headers()
        
        response = httpx.delete(
            f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}",
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        
        return json.dumps({"success": True, "message": f"Message {message_id} deleted successfully"})
    except Exception as e:
        error_msg = f"Discord delete error: {e}"
        frappe.log_error(error_msg)
        update_last_error("discord", error_msg)
        return json.dumps({"error": str(e)})
