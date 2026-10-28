import json
import base64
import time
from email.mime.text import MIMEText
import frappe
logger = frappe.logger("huf")
import httpx
from huf.ai.tools.credentials import get_credential, update_last_error, set_credential
from huf.ai.tools.provider_errors import (
    ProviderCredentialError,
    check_google_response,
    invalid_recipients,
    normalize_recipients,
    mint_google_access_token,
    not_connected_message,
)

GMAIL_SEND_SCOPE = "gmail.send"


def _resolve_gmail_access_token() -> str:
    """Return a valid Gmail access token, refreshing and persisting it when needed.

    Raises ProviderCredentialError with plain copy when credentials are missing or Google rejects them.
    """
    service_name = "gmail"

    access_token = get_credential(service_name, "access_token")
    access_token_expiry_str = get_credential(service_name, "access_token_expiry")

    if access_token and access_token_expiry_str:
        try:
            expiry_time = float(access_token_expiry_str)
            # If token expires in more than 60 seconds, use it
            if time.time() < expiry_time - 60:
                return access_token
        except (ValueError, TypeError):
            # If expiry time is malformed, proceed to refresh
            pass

    client_id = get_credential(service_name, "client_id")
    client_secret = get_credential(service_name, "client_secret")
    refresh_token = get_credential(service_name, "refresh_token")
    if not (client_id and client_secret and refresh_token):
        raise ProviderCredentialError(not_connected_message("Gmail", "the client ID, client secret and refresh token"), kind="missing")

    data = mint_google_access_token("Gmail", client_id, client_secret, refresh_token)
    new_token = data["access_token"]
    expiry_time = time.time() + data.get("expires_in", 3600)
    set_credential(service_name, "access_token", new_token)
    set_credential(service_name, "access_token_expiry", str(expiry_time))
    return new_token


def _get_gmail_access_token():
    """Like _resolve_gmail_access_token but returns None instead of raising."""
    try:
        return _resolve_gmail_access_token()
    except Exception as e:
        logger.warning(f"Gmail token refresh error: {e}")
        return None


def _get_gmail_headers():
    """Get Gmail API headers. Raises ProviderCredentialError with the specific reason."""
    token = _resolve_gmail_access_token()
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
        check_google_response(response, "Gmail", "gmail.readonly")
        
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
                check_google_response(msg_resp, "Gmail", "gmail.readonly")
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
                logger.warning(f"Gmail fetch email details error for {msg['id']}: {e}")
        
        return json.dumps({
            "success": True, 
            "count": len(detailed_messages), 
            "results": detailed_messages
        })
    except Exception as e:
        logger.warning(f"Gmail Get Emails Error: {str(e)}")
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

        bad = invalid_recipients(to)
        if bad:
            return json.dumps({"success": False, "error": "Enter a valid email address for To (not: " + ", ".join(bad)[:120] + ")."})
        to = normalize_recipients(to)

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
        check_google_response(response, "Gmail", "gmail.send")
        
        return json.dumps({"success": True, "results": response.json()})
    except Exception as e:
        logger.warning(f"Gmail Send Email Error: {str(e)}")
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

        bad = invalid_recipients(to)
        if bad:
            return json.dumps({"success": False, "error": "Enter a valid email address for To (not: " + ", ".join(bad)[:120] + ")."})
        to = normalize_recipients(to)

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
        check_google_response(response, "Gmail", "gmail.compose")
        
        return json.dumps({"success": True, "results": response.json()})
    except Exception as e:
        logger.warning(f"Gmail Create Draft Error: {str(e)}")
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
        check_google_response(response, "Gmail", "gmail.modify")
        
        return json.dumps({"success": True, "results": response.json()})
    except Exception as e:
        logger.warning(f"Gmail Mark As Read Error: {str(e)}")
        update_last_error(service_name, str(e))
        return json.dumps({"success": False, "error": str(e)})
