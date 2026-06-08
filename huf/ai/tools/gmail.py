import json
import base64
from email.mime.text import MIMEText
import frappe
import httpx
from huf.ai.tools.credentials import require_credential, get_credential, update_last_error


def _get_gmail_access_token() -> str:
    """Get Gmail OAuth2 access token by refreshing if possible."""
    service_name = "gmail"
    # Try to get existing access token first
    access_token = get_credential(service_name, "access_token")
    if access_token:
        # Check if it's still valid (in a real flow you'd check expiry, but for now we try to refresh if missing)
        return access_token
    
    # Try to refresh using client_id, client_secret, refresh_token
    try:
        client_id = require_credential(service_name, "client_id")
        client_secret = require_credential(service_name, "client_secret")
        refresh_token = require_credential(service_name, "refresh_token")
        
        response = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=15
        )
        response.raise_for_status()
        data = response.json()
        new_token = data.get("access_token")
        # In a real app, you might want to save this back to credentials
        return new_token
    except Exception as e:
        frappe.log_error(f"Gmail token refresh error: {e}", "Gmail Tool")
        return None


def _get_gmail_headers():
    """Get Gmail API headers."""
    token = _get_gmail_access_token()
    if not token:
        raise ValueError("Gmail access token or refresh token not configured/valid")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }


def handle_get_emails(**kwargs) -> str:
    """Get latest emails from Gmail."""
    service_name = "gmail"
    try:
        count = int(kwargs.get("count", 10))
        query = kwargs.get("query", "")
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
        
        return json.dumps({
            "success": True, 
            "count": len(detailed_messages), 
            "results": detailed_messages
        })
    except Exception as e:
        frappe.log_error(f"Gmail Get Emails Error: {str(e)}", "Gmail Tool")
        update_last_error(service_name, str(e))
        return json.dumps({"success": False, "error": str(e)})


def handle_send_email(**kwargs) -> str:
    """Send an email via Gmail."""
    service_name = "gmail"
    try:
        to = kwargs.get("to")
        subject = kwargs.get("subject")
        body = kwargs.get("body")
        if not all([to, subject, body]):
            return json.dumps({"success": False, "error": "to, subject, and body are required"})

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
        
        return json.dumps({"success": True, "results": response.json()})
    except Exception as e:
        frappe.log_error(f"Gmail Send Email Error: {str(e)}", "Gmail Tool")
        update_last_error(service_name, str(e))
        return json.dumps({"success": False, "error": str(e)})


def handle_create_draft(**kwargs) -> str:
    """Create a draft email in Gmail."""
    service_name = "gmail"
    try:
        to = kwargs.get("to")
        subject = kwargs.get("subject")
        body = kwargs.get("body")
        if not all([to, subject, body]):
            return json.dumps({"success": False, "error": "to, subject, and body are required"})

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
        
        return json.dumps({"success": True, "results": response.json()})
    except Exception as e:
        frappe.log_error(f"Gmail Create Draft Error: {str(e)}", "Gmail Tool")
        update_last_error(service_name, str(e))
        return json.dumps({"success": False, "error": str(e)})


def handle_mark_as_read(**kwargs) -> str:
    """Mark an email as read in Gmail."""
    service_name = "gmail"
    try:
        message_id = kwargs.get("message_id")
        if not message_id:
            return json.dumps({"success": False, "error": "message_id is required"})

        headers = _get_gmail_headers()
        payload = {"removeLabelIds": ["UNREAD"]}
        
        response = httpx.post(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}/modify",
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        
        return json.dumps({"success": True, "results": response.json()})
    except Exception as e:
        frappe.log_error(f"Gmail Mark As Read Error: {str(e)}", "Gmail Tool")
        update_last_error(service_name, str(e))
        return json.dumps({"success": False, "error": str(e)})
