import json
import frappe
from datetime import datetime
from huf.ai.tools.credentials import require_credential, update_last_error
import requests

BASE = "https://www.googleapis.com/calendar/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def _get_access_token():
	service_name = "google_calendar"
	client_id = require_credential(service_name, "client_id")
	client_secret = require_credential(service_name, "client_secret")
	refresh_token = require_credential(service_name, "refresh_token")

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
	service_name = "google_calendar"
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
		return json.dumps({
			"success": True, 
			"count": len(events), 
			"results": events
		})
	except Exception as e:
		frappe.log_error(f"Google Calendar Error (List): {str(e)}", "Google Calendar Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_create_event(**kwargs):
	"""Create a new event in Google Calendar."""
	service_name = "google_calendar"
	try:
		title = kwargs.get("title")
		start_date = kwargs.get("start_date")
		end_date = kwargs.get("end_date")
		if not all([title, start_date, end_date]):
			return json.dumps({"success": False, "error": "title, start_date, and end_date are required"})

		event = {
			"summary": title,
			"start": {"dateTime": start_date, "timeZone": kwargs.get("timezone", "UTC")},
			"end": {"dateTime": end_date, "timeZone": kwargs.get("timezone", "UTC")},
		}
		if "description" in kwargs:
			event["description"] = kwargs["description"]

		resp = requests.post(f"{BASE}/calendars/primary/events", headers=_headers(), json=event, timeout=30)
		resp.raise_for_status()
		data = resp.json()
		return json.dumps({
			"success": True, 
			"results": {
				"id": data["id"], 
				"summary": data.get("summary", ""), 
				"htmlLink": data.get("htmlLink", "")
			}
		})
	except Exception as e:
		frappe.log_error(f"Google Calendar Error (Create): {str(e)}", "Google Calendar Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_update_event(**kwargs):
	"""Update an existing Google Calendar event."""
	service_name = "google_calendar"
	try:
		event_id = kwargs.get("event_id")
		if not event_id:
			return json.dumps({"success": False, "error": "event_id is required"})

		patch = {}
		if "title" in kwargs:
			patch["summary"] = kwargs["title"]
		if "description" in kwargs:
			patch["description"] = kwargs["description"]

		resp = requests.patch(
			f"{BASE}/calendars/primary/events/{event_id}",
			headers=_headers(),
			json=patch,
			timeout=30,
		)
		resp.raise_for_status()
		return json.dumps({"success": True, "results": {"event_id": event_id}})
	except Exception as e:
		frappe.log_error(f"Google Calendar Error (Update): {str(e)}", "Google Calendar Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_delete_event(**kwargs):
	"""Delete a Google Calendar event."""
	service_name = "google_calendar"
	try:
		event_id = kwargs.get("event_id")
		if not event_id:
			return json.dumps({"success": False, "error": "event_id is required"})

		resp = requests.delete(
			f"{BASE}/calendars/primary/events/{event_id}",
			headers=_headers(),
			timeout=30,
		)
		resp.raise_for_status()
		return json.dumps({"success": True, "results": {"event_id": event_id}})
	except Exception as e:
		frappe.log_error(f"Google Calendar Error (Delete): {str(e)}", "Google Calendar Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})
