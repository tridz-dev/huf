"""
Discord integration tools for sending messages and managing channels.
Uses HUF Integration Settings for credential management.
"""

import json
import frappe
import httpx
from huf.ai.tools.credentials import require_credential, get_credential, update_last_error


def _get_discord_headers():
    """Get Discord API headers with bot token."""
    service_name = "discord"
    token = get_credential(service_name, "bot_token")
    if not token:
        raise ValueError("Discord bot token not configured")
    return {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json"
    }


def handle_send_message(**kwargs) -> str:
    """Send a message to a Discord channel."""
    service_name = "discord"
    try:
        channel_id = kwargs.get("channel_id")
        message = kwargs.get("message")
        if not all([channel_id, message]):
            return json.dumps({"success": False, "error": "channel_id and message are required"}, default=str)

        headers = _get_discord_headers()
        payload = {"content": message}
        
        response = httpx.post(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        
        return json.dumps({
            "success": True, 
            "results": response.json()
        })
    except Exception as e:
        error_msg = f"Discord Send Message Error: {str(e)}"
        frappe.log_error(error_msg, "Discord Tool")
        update_last_error(service_name, error_msg)
        return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_get_channel_messages(**kwargs) -> str:
    """Get message history of a Discord channel."""
    service_name = "discord"
    try:
        channel_id = kwargs.get("channel_id")
        if not channel_id:
            return json.dumps({"success": False, "error": "channel_id is required"}, default=str)

        limit = int(kwargs.get("limit", 50))
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
        
        return json.dumps({
            "success": True, 
            "count": len(simplified), 
            "results": simplified
        })
    except Exception as e:
        error_msg = f"Discord Get Messages Error: {str(e)}"
        frappe.log_error(error_msg, "Discord Tool")
        update_last_error(service_name, error_msg)
        return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_list_channels(**kwargs) -> str:
    """List all channels in a Discord server (guild)."""
    service_name = "discord"
    try:
        guild_id = kwargs.get("guild_id")
        if not guild_id:
            return json.dumps({"success": False, "error": "guild_id is required"}, default=str)

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
        
        return json.dumps({
            "success": True, 
            "count": len(simplified), 
            "results": simplified
        })
    except Exception as e:
        error_msg = f"Discord List Channels Error: {str(e)}"
        frappe.log_error(error_msg, "Discord Tool")
        update_last_error(service_name, error_msg)
        return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_delete_message(**kwargs) -> str:
    """Delete a message from a Discord channel."""
    service_name = "discord"
    try:
        channel_id = kwargs.get("channel_id")
        message_id = kwargs.get("message_id")
        if not all([channel_id, message_id]):
            return json.dumps({"success": False, "error": "channel_id and message_id are required"}, default=str)

        headers = _get_discord_headers()
        
        response = httpx.delete(
            f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}",
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        
        return json.dumps({
            "success": True, 
            "results": {"message": f"Message {message_id} deleted successfully"}
        })
    except Exception as e:
        error_msg = f"Discord Delete Message Error: {str(e)}"
        frappe.log_error(error_msg, "Discord Tool")
        update_last_error(service_name, error_msg)
        return json.dumps({"success": False, "error": str(e)}, default=str)
