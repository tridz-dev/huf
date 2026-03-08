import json
import os
from datetime import datetime, timedelta

import requests

BASE = "https://www.googleapis.com/calendar/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def _get_access_token():
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


def handle_list_events(**kwargs):
	"""List upcoming events from Google Calendar."""
	try:
		limit = int(kwargs.get("limit", 10))
		now = datetime.utcnow().isoformat() + "Z"
		params = {"maxResults": limit, "timeMin": now, "orderBy": "startTime", "singleEvents": True}
		if "start_date" in kwargs:
			params["timeMin"] = kwargs["start_date"]

		resp = requests.get(f"{BASE}/calendars/primary/events", headers=_headers(), params=params, timeout=30)
		resp.raise_for_status()
		events = [
			{
				"id": e["id"],
				"summary": e.get("summary", ""),
				"start": e.get("start", {}).get("dateTime", e.get("start", {}).get("date", "")),
				"end": e.get("end", {}).get("dateTime", e.get("end", {}).get("date", "")),
			}
			for e in resp.json().get("items", [])
		]
		return json.dumps({"count": len(events), "events": events})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_create_event(**kwargs):
	"""Create a new event in Google Calendar."""
	try:
		event = {
			"summary": kwargs["title"],
			"start": {"dateTime": kwargs["start_date"], "timeZone": kwargs.get("timezone", "UTC")},
			"end": {"dateTime": kwargs["end_date"], "timeZone": kwargs.get("timezone", "UTC")},
		}
		if "description" in kwargs:
			event["description"] = kwargs["description"]

		resp = requests.post(f"{BASE}/calendars/primary/events", headers=_headers(), json=event, timeout=30)
		resp.raise_for_status()
		data = resp.json()
		return json.dumps({"id": data["id"], "summary": data.get("summary", ""), "htmlLink": data.get("htmlLink", "")})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_update_event(**kwargs):
	"""Update an existing Google Calendar event."""
	try:
		patch = {}
		if "title" in kwargs:
			patch["summary"] = kwargs["title"]
		if "description" in kwargs:
			patch["description"] = kwargs["description"]

		resp = requests.patch(
			f"{BASE}/calendars/primary/events/{kwargs['event_id']}",
			headers=_headers(),
			json=patch,
			timeout=30,
		)
		resp.raise_for_status()
		return json.dumps({"ok": True, "event_id": kwargs["event_id"]})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_delete_event(**kwargs):
	"""Delete a Google Calendar event."""
	try:
		resp = requests.delete(
			f"{BASE}/calendars/primary/events/{kwargs['event_id']}",
			headers=_headers(),
			timeout=30,
		)
		resp.raise_for_status()
		return json.dumps({"ok": True, "event_id": kwargs["event_id"]})
	except Exception as e:
		return json.dumps({"error": str(e)})
