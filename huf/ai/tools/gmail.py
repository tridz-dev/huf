"""
Gmail integration tools for email management.
Uses HUF Integration Settings with OAuth2 credentials.
"""

import json
import base64
from email.mime.text import MIMEText
import frappe
import httpx
from typing import Optional, List
from huf.ai.tools.credentials import require_credential, get_credential, update_last_error


def _get_gmail_access_token() -> str:
    """Get or refresh Gmail OAuth2 access token."""
    # This is a simplified version - in production, you'd implement proper OAuth2 refresh flow
    # For now, we expect the access token to be stored in credentials
    return get_credential("gmail", "access_token")


def _get_gmail_headers():
    """Get Gmail API headers."""
    token = _get_gmail_access_token()
    if not token:
        raise ValueError("Gmail access token not configured")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }


def _encode_message(message_text: str) -> str:
    """Encode message for Gmail API."""
    message = MIMEText(message_text)
    return base64.urlsafe_b64encode(message.as_bytes()).decode()


def handle_get_emails(count: int = 10, query: str = "", **kwargs) -> str:
    """Get latest emails from Gmail."""
    try:
        headers = _get_gmail_headers()
        
        params = {"maxResults": count}
        if query:
            params["q"] = query
        
        response = httpx.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            headers=headers,
            params=params,
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        messages = data.get("messages", [])
        
        # Get full message details for each
        detailed_messages = []
        for msg in messages[:count]:
            try:
                msg_resp = httpx.get(
                    f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg['id']}",
                    headers=headers,
                    params={"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]},
                    timeout=30
                )
                msg_resp.raise_for_status()
                msg_data = msg_resp.json()
                
                headers_dict = {h["name"]: h["value"] for h in msg_data.get("payload", {}).get("headers", [])}
                detailed_messages.append({
                    "id": msg["id"],
                    "threadId": msg["threadId"],
                    "subject": headers_dict.get("Subject", ""),
                    "from": headers_dict.get("From", ""),
                    "date": headers_dict.get("Date", ""),
                    "snippet": msg_data.get("snippet", "")
                })
            except Exception as e:
                frappe.log_error(f"Gmail fetch email details error for {msg['id']}: {e}")
                detailed_messages.append({"id": msg["id"], "error": "Failed to fetch details"})
        
        return json.dumps({"success": True, "count": len(detailed_messages), "emails": detailed_messages})
    except Exception as e:
        error_msg = f"Gmail get emails error: {e}"
        frappe.log_error(error_msg)
        update_last_error("gmail", error_msg)
        return json.dumps({"error": str(e)})


def handle_send_email(to: str, subject: str, body: str, **kwargs) -> str:
    """Send an email via Gmail."""
    try:
        headers = _get_gmail_headers()
        
        # Create email message
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        
        payload = {"raw": raw_message}
        
        response = httpx.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        
        return json.dumps({"success": True, "data": response.json()})
    except Exception as e:
        error_msg = f"Gmail send error: {e}"
        frappe.log_error(error_msg)
        update_last_error("gmail", error_msg)
        return json.dumps({"error": str(e)})


def handle_create_draft(to: str, subject: str, body: str, **kwargs) -> str:
    """Create a draft email in Gmail."""
    try:
        headers = _get_gmail_headers()
        
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        
        payload = {"message": {"raw": raw_message}}
        
        response = httpx.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/drafts",
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        
        return json.dumps({"success": True, "data": response.json()})
    except Exception as e:
        error_msg = f"Gmail create draft error: {e}"
        frappe.log_error(error_msg)
        update_last_error("gmail", error_msg)
        return json.dumps({"error": str(e)})


def handle_mark_as_read(message_id: str, **kwargs) -> str:
    """Mark an email as read in Gmail."""
    try:
        headers = _get_gmail_headers()
        
        # Remove UNREAD label
        payload = {
            "removeLabelIds": ["UNREAD"]
        }
        
        response = httpx.post(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}/modify",
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        
        return json.dumps({"success": True, "data": response.json()})
    except Exception as e:
        error_msg = f"Gmail mark as read error: {e}"
        frappe.log_error(error_msg)
        update_last_error("gmail", error_msg)
        return json.dumps({"error": str(e)})
