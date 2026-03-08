import base64
import json
import os
from email.mime.text import MIMEText

import requests

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
TOKEN_URL = "https://oauth2.googleapis.com/token"
BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


def _get_access_token():
	"""Exchange refresh token for access token."""
	client_id = os.getenv("GOOGLE_CLIENT_ID")
	client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
	refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")

	if not all([client_id, client_secret, refresh_token]):
		raise ValueError("GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REFRESH_TOKEN are required")

	resp = requests.post(TOKEN_URL, data={
		"client_id": client_id,
		"client_secret": client_secret,
		"refresh_token": refresh_token,
		"grant_type": "refresh_token",
	}, timeout=15)
	resp.raise_for_status()
	return resp.json()["access_token"]


def _headers():
	return {"Authorization": f"Bearer {_get_access_token()}", "Content-Type": "application/json"}


def handle_get_emails(**kwargs):
	"""Get latest emails from Gmail."""
	try:
		count = int(kwargs.get("count", 10))
		query = kwargs.get("query", "")
		params = {"maxResults": count}
		if query:
			params["q"] = query

		resp = requests.get(f"{BASE}/messages", headers=_headers(), params=params, timeout=30)
		resp.raise_for_status()
		messages = resp.json().get("messages", [])

		emails = []
		for msg in messages[:count]:
			detail = requests.get(f"{BASE}/messages/{msg['id']}", headers=_headers(), params={"format": "metadata"}, timeout=15)
			if detail.ok:
				headers_list = detail.json().get("payload", {}).get("headers", [])
				email_data = {"id": msg["id"]}
				for h in headers_list:
					if h["name"] == "Subject":
						email_data["subject"] = h["value"]
					elif h["name"] == "From":
						email_data["from"] = h["value"]
					elif h["name"] == "Date":
						email_data["date"] = h["value"]
				emails.append(email_data)

		return json.dumps({"count": len(emails), "emails": emails})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_send_email(**kwargs):
	"""Send an email via Gmail."""
	try:
		msg = MIMEText(kwargs["body"])
		msg["to"] = kwargs["to"]
		msg["subject"] = kwargs["subject"]
		raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

		resp = requests.post(
			f"{BASE}/messages/send",
			headers=_headers(),
			json={"raw": raw},
			timeout=30,
		)
		resp.raise_for_status()
		data = resp.json()
		return json.dumps({"ok": True, "message_id": data.get("id", "")})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_create_draft(**kwargs):
	"""Create a draft email in Gmail."""
	try:
		msg = MIMEText(kwargs["body"])
		msg["to"] = kwargs["to"]
		msg["subject"] = kwargs["subject"]
		raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

		resp = requests.post(
			f"{BASE}/drafts",
			headers=_headers(),
			json={"message": {"raw": raw}},
			timeout=30,
		)
		resp.raise_for_status()
		data = resp.json()
		return json.dumps({"ok": True, "draft_id": data.get("id", "")})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_mark_as_read(**kwargs):
	"""Mark an email as read in Gmail."""
	try:
		resp = requests.post(
			f"{BASE}/messages/{kwargs['message_id']}/modify",
			headers=_headers(),
			json={"removeLabelIds": ["UNREAD"]},
			timeout=15,
		)
		resp.raise_for_status()
		return json.dumps({"ok": True, "message_id": kwargs["message_id"]})
	except Exception as e:
		return json.dumps({"error": str(e)})
