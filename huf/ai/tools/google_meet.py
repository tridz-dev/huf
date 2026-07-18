import json
import frappe
import requests
from huf.ai.tools.credentials import require_credential, update_last_error

MEET_BASE = "https://meet.googleapis.com/v2"
CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def _get_access_token():
	service_name = "google_meet"
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


def handle_create_meet_space(**kwargs):
	"""Create a Google Meet meeting space and return a joinable link."""
	service_name = "google_meet"
	try:
		access_type = kwargs.get("access_type", "OPEN")
		if access_type not in ("OPEN", "TRUSTED", "RESTRICTED"):
			return json.dumps({"success": False, "error": "access_type must be OPEN, TRUSTED, or RESTRICTED"})

		body = {
			"config": {
				"accessType": access_type,
			}
		}

		resp = requests.post(
			f"{MEET_BASE}/spaces",
			headers=_headers(),
			json=body,
			timeout=30,
		)
		try:
			resp.raise_for_status()
		except requests.exceptions.HTTPError as e:
			error_details = resp.text
			frappe.log_error(title="Google Meet Tool API Error", message=f"Status: {e}, Details: {error_details}")
			raise Exception(f"Google API Error: {resp.status_code} - {error_details}")

		data = resp.json()

		return json.dumps({
			"success": True,
			"results": {
				"space_name": data.get("name"),
				"meeting_code": data.get("meetingCode"),
				"meet_url": data.get("meetingUri"),
				"access_type": data.get("config", {}).get("accessType"),
			}
		})
	except Exception as e:
		frappe.log_error(title="Google Meet Tool", message=f"Google Meet Error (Create Space): {str(e)}")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_create_meet_event(**kwargs):
	"""Create a Google Calendar event with an auto-generated Google Meet conference."""
	service_name = "google_meet"
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
			"conferenceData": {
				"createRequest": {
					"requestId": frappe.generate_hash(length=12),
					"conferenceSolutionKey": {"type": "hangoutsMeet"},
				}
			},
		}
		if "description" in kwargs:
			event["description"] = kwargs["description"]

		resp = requests.post(
			f"{CALENDAR_BASE}/calendars/primary/events?conferenceDataVersion=1",
			headers=_headers(),
			json=event,
			timeout=30,
		)
		try:
			resp.raise_for_status()
		except requests.exceptions.HTTPError as e:
			error_details = resp.text
			frappe.log_error(title="Google Meet Tool API Error", message=f"Status: {e}, Details: {error_details}")
			raise Exception(f"Google API Error: {resp.status_code} - {error_details}")

		data = resp.json()

		meet_url = None
		for ep in data.get("conferenceData", {}).get("entryPoints", []):
			if ep.get("entryPointType") == "video":
				meet_url = ep.get("uri")
				break

		return json.dumps({
			"success": True,
			"results": {
				"event_id": data.get("id"),
				"summary": data.get("summary"),
				"html_link": data.get("htmlLink"),
				"meet_url": meet_url,
			}
		})
	except Exception as e:
		frappe.log_error(title="Google Meet Tool", message=f"Google Meet Error (Create Event): {str(e)}")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})
