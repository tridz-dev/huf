"""
Slack integration tools for sending messages and managing channels.
Uses HUF Integration Settings for credential management.
"""

import json
import frappe
import httpx
from huf.ai.tools.credentials import require_credential, get_credential, update_last_error


def _get_slack_headers():
    """Get Slack API headers with token."""
    service_name = "slack"
    token = get_credential(service_name, "token")
    if not token:
        raise ValueError("Slack token not configured")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }


def _handle_send_message(**kwargs) -> str:
    """Send a message to a Slack channel."""
    service_name = "slack"
    try:
        channel = kwargs.get("channel")
        text = kwargs.get("text")
        if not all([channel, text]):
            return json.dumps({"success": False, "error": "channel and text are required"})

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
            error_msg = data.get("error", "Unknown error")
            update_last_error(service_name, error_msg)
            return json.dumps({"success": False, "error": error_msg})
        
        return json.dumps({"success": True, "results": data})
    except Exception as e:
        error_msg = f"Slack Send Message Error: {str(e)}"
        frappe.log_error(error_msg, "Slack Tool")
        update_last_error(service_name, error_msg)
        return json.dumps({"success": False, "error": str(e)})


def _handle_send_message_thread(**kwargs) -> str:
    """Reply to a message thread in a Slack channel."""
    service_name = "slack"
    try:
        channel = kwargs.get("channel")
        text = kwargs.get("text")
        thread_ts = kwargs.get("thread_ts")
        if not all([channel, text, thread_ts]):
            return json.dumps({"success": False, "error": "channel, text, and thread_ts are required"})

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
            error_msg = data.get("error", "Unknown error")
            update_last_error(service_name, error_msg)
            return json.dumps({"success": False, "error": error_msg})
        
        return json.dumps({"success": True, "results": data})
    except Exception as e:
        error_msg = f"Slack Thread Reply Error: {str(e)}"
        frappe.log_error(error_msg, "Slack Tool")
        update_last_error(service_name, error_msg)
        return json.dumps({"success": False, "error": str(e)})


def _handle_list_channels(**kwargs) -> str:
    """List all channels in the Slack workspace."""
    service_name = "slack"
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
            error_msg = data.get("error", "Unknown error")
            update_last_error(service_name, error_msg)
            return json.dumps({"success": False, "error": error_msg})
        
        channels = [{"id": ch.get("id"), "name": ch.get("name"), "is_private": ch.get("is_private", False)}
                    for ch in data.get("channels", [])]
        
        return json.dumps({
            "success": True, 
            "count": len(channels), 
            "results": channels
        })
    except Exception as e:
        error_msg = f"Slack List Channels Error: {str(e)}"
        frappe.log_error(error_msg, "Slack Tool")
        update_last_error(service_name, error_msg)
        return json.dumps({"success": False, "error": str(e)})


def _handle_get_channel_history(**kwargs) -> str:
    """Get message history of a Slack channel."""
    service_name = "slack"
    try:
        channel = kwargs.get("channel")
        if not channel:
            return json.dumps({"success": False, "error": "channel is required"})

        limit = int(kwargs.get("limit", 100))
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
            error_msg = data.get("error", "Unknown error")
            update_last_error(service_name, error_msg)
            return json.dumps({"success": False, "error": error_msg})
        
        messages = [{"ts": msg.get("ts"), "text": msg.get("text", ""), "user": msg.get("user", "bot" if msg.get("bot_id") else "unknown")}
                    for msg in data.get("messages", [])]
        
        return json.dumps({
            "success": True, 
            "count": len(messages), 
            "results": messages
        })
    except Exception as e:
        error_msg = f"Slack Get History Error: {str(e)}"
        frappe.log_error(error_msg, "Slack Tool")
        update_last_error(service_name, error_msg)
        return json.dumps({"success": False, "error": str(e)})


def _handle_search_messages(**kwargs) -> str:
    """Search messages across the Slack workspace."""
    service_name = "slack"
    try:
        query = kwargs.get("query")
        if not query:
            return json.dumps({"success": False, "error": "query is required"})

        limit = int(kwargs.get("limit", 20))
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
            error_msg = data.get("error", "Unknown error")
            update_last_error(service_name, error_msg)
            return json.dumps({"success": False, "error": error_msg})
        
        matches = data.get("messages", {}).get("matches", [])
        results = [{"text": msg.get("text", ""), "user": msg.get("username", msg.get("user", "unknown")), "channel": msg.get("channel", {}).get("name", "unknown"), "permalink": msg.get("permalink")}
                   for msg in matches]
        
        return json.dumps({
            "success": True, 
            "count": len(results), 
            "results": results
        })
    except Exception as e:
        error_msg = f"Slack Search Error: {str(e)}"
        frappe.log_error(error_msg, "Slack Tool")
        update_last_error(service_name, error_msg)
        return json.dumps({"success": False, "error": str(e)})


def _handle_list_users(**kwargs) -> str:
    """List all users in the Slack workspace."""
    service_name = "slack"
    try:
        limit = int(kwargs.get("limit", 100))
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
            error_msg = data.get("error", "Unknown error")
            update_last_error(service_name, error_msg)
            return json.dumps({"success": False, "error": error_msg})
        
        users = [{"id": user.get("id"), "name": user.get("name"), "real_name": user.get("real_name", ""), "is_bot": user.get("is_bot", False)}
                 for user in data.get("members", [])
                 if not user.get("deleted", False)]
        
        return json.dumps({
            "success": True, 
            "count": len(users), 
            "results": users
        })
    except Exception as e:
        error_msg = f"Slack List Users Error: {str(e)}"
        frappe.log_error(error_msg, "Slack Tool")
        update_last_error(service_name, error_msg)
        return json.dumps({"success": False, "error": str(e)})


def handle_action(**kwargs) -> str:
    action = kwargs.get("action", "").strip().lower()
    dispatch = {
        "send_message": _handle_send_message,
        "reply_thread": _handle_send_message_thread,
        "list_channels": _handle_list_channels,
        "get_history": _handle_get_channel_history,
        "search_messages": _handle_search_messages,
        "list_users": _handle_list_users,
    }
    handler = dispatch.get(action)
    if not handler:
        valid = ", ".join(sorted(dispatch.keys()))
        return json.dumps({"success": False, "error": f"Unknown action '{action}'. Valid: {valid}"})
    return handler(**kwargs)
