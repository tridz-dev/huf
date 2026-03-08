"""
Slack integration tools for sending messages and managing channels.
Uses HUF Integration Settings for credential management.
"""

import json
import frappe
import httpx
from typing import List, Optional, Dict, Any
from huf.ai.tools.credentials import require_credential, get_credential, update_last_error


def _get_slack_headers():
    """Get Slack API headers with token."""
    token = get_credential("slack", "token")
    if not token:
        raise ValueError("Slack token not configured")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }


def handle_send_message(channel: str, text: str, **kwargs) -> str:
    """Send a message to a Slack channel."""
    try:
        headers = _get_slack_headers()
        payload = {"channel": channel, "text": text, "mrkdwn": True}
        
        response = httpx.post(
            "https://slack.com/api/chat.postMessage",
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        if not data.get("ok"):
            return json.dumps({"error": data.get("error", "Unknown error")})
        
        return json.dumps({"success": True, "data": data})
    except Exception as e:
        error_msg = f"Slack send error: {e}"
        frappe.log_error(error_msg)
        update_last_error("slack", error_msg)
        return json.dumps({"error": str(e)})


def handle_send_message_thread(channel: str, text: str, thread_ts: str, **kwargs) -> str:
    """Reply to a message thread in a Slack channel."""
    try:
        headers = _get_slack_headers()
        payload = {"channel": channel, "text": text, "thread_ts": thread_ts, "mrkdwn": True}
        
        response = httpx.post(
            "https://slack.com/api/chat.postMessage",
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        if not data.get("ok"):
            return json.dumps({"error": data.get("error", "Unknown error")})
        
        return json.dumps({"success": True, "data": data})
    except Exception as e:
        error_msg = f"Slack thread reply error: {e}"
        frappe.log_error(error_msg)
        update_last_error("slack", error_msg)
        return json.dumps({"error": str(e)})


def handle_list_channels(**kwargs) -> str:
    """List all channels in the Slack workspace."""
    try:
        headers = _get_slack_headers()
        
        response = httpx.get(
            "https://slack.com/api/conversations.list",
            headers=headers,
            params={"types": "public_channel,private_channel"},
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        if not data.get("ok"):
            return json.dumps({"error": data.get("error", "Unknown error")})
        
        channels = [{"id": ch.get("id"), "name": ch.get("name"), "is_private": ch.get("is_private", False)}
                    for ch in data.get("channels", [])]
        
        return json.dumps({"success": True, "channels": channels})
    except Exception as e:
        error_msg = f"Slack list channels error: {e}"
        frappe.log_error(error_msg)
        update_last_error("slack", error_msg)
        return json.dumps({"error": str(e)})


def handle_get_channel_history(channel: str, limit: int = 100, **kwargs) -> str:
    """Get message history of a Slack channel."""
    try:
        headers = _get_slack_headers()
        
        response = httpx.get(
            "https://slack.com/api/conversations.history",
            headers=headers,
            params={"channel": channel, "limit": min(limit, 200)},
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        if not data.get("ok"):
            return json.dumps({"error": data.get("error", "Unknown error")})
        
        messages = [{"ts": msg.get("ts"), "text": msg.get("text", ""), "user": msg.get("user", "bot" if msg.get("bot_id") else "unknown")}
                    for msg in data.get("messages", [])]
        
        return json.dumps({"success": True, "messages": messages})
    except Exception as e:
        error_msg = f"Slack get history error: {e}"
        frappe.log_error(error_msg)
        update_last_error("slack", error_msg)
        return json.dumps({"error": str(e)})


def handle_search_messages(query: str, limit: int = 20, **kwargs) -> str:
    """Search messages across the Slack workspace."""
    try:
        headers = _get_slack_headers()
        
        response = httpx.get(
            "https://slack.com/api/search.messages",
            headers=headers,
            params={"query": query, "count": min(limit, 100)},
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        if not data.get("ok"):
            return json.dumps({"error": data.get("error", "Unknown error")})
        
        matches = data.get("messages", {}).get("matches", [])
        results = [{"text": msg.get("text", ""), "user": msg.get("username", msg.get("user", "unknown")), "channel": msg.get("channel", {}).get("name", "unknown"), "permalink": msg.get("permalink")}
                   for msg in matches]
        
        return json.dumps({"success": True, "count": len(results), "results": results})
    except Exception as e:
        error_msg = f"Slack search error: {e}"
        frappe.log_error(error_msg)
        update_last_error("slack", error_msg)
        return json.dumps({"error": str(e)})


def handle_list_users(limit: int = 100, **kwargs) -> str:
    """List all users in the Slack workspace."""
    try:
        headers = _get_slack_headers()
        
        response = httpx.get(
            "https://slack.com/api/users.list",
            headers=headers,
            params={"limit": min(limit, 200)},
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        if not data.get("ok"):
            return json.dumps({"error": data.get("error", "Unknown error")})
        
        users = [{"id": user.get("id"), "name": user.get("name"), "real_name": user.get("real_name", ""), "is_bot": user.get("is_bot", False)}
                 for user in data.get("members", [])
                 if not user.get("deleted", False)]
        
        return json.dumps({"success": True, "count": len(users), "users": users})
    except Exception as e:
        error_msg = f"Slack list users error: {e}"
        frappe.log_error(error_msg)
        update_last_error("slack", error_msg)
        return json.dumps({"error": str(e)})
