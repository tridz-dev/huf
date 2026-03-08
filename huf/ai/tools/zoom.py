import json
import os

import requests


def _get_token():
	"""Get OAuth access token using Server-to-Server credentials."""
	account_id = os.getenv("ZOOM_ACCOUNT_ID")
	client_id = os.getenv("ZOOM_CLIENT_ID")
	client_secret = os.getenv("ZOOM_CLIENT_SECRET")

	if not all([account_id, client_id, client_secret]):
		raise ValueError("ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, and ZOOM_CLIENT_SECRET are required")

	resp = requests.post(
		"https://zoom.us/oauth/token",
		params={"grant_type": "account_credentials", "account_id": account_id},
		auth=(client_id, client_secret),
		timeout=30,
	)
	resp.raise_for_status()
	return resp.json()["access_token"]


def _headers():
	return {"Authorization": f"Bearer {_get_token()}", "Content-Type": "application/json"}


def handle_schedule_meeting(**kwargs):
	"""Schedule a new Zoom meeting."""
	try:
		payload = {
			"topic": kwargs["topic"],
			"type": 2,
			"start_time": kwargs["start_time"],
			"duration": int(kwargs.get("duration", 30)),
			"timezone": kwargs.get("timezone", "UTC"),
		}
		resp = requests.post("https://api.zoom.us/v2/users/me/meetings", headers=_headers(), json=payload, timeout=30)
		resp.raise_for_status()
		data = resp.json()
		return json.dumps({"id": data["id"], "join_url": data["join_url"], "topic": data["topic"]})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_list_meetings(**kwargs):
	"""List Zoom meetings for the authenticated user."""
	try:
		resp = requests.get("https://api.zoom.us/v2/users/me/meetings", headers=_headers(), timeout=30)
		resp.raise_for_status()
		meetings = resp.json().get("meetings", [])
		result = [{"id": m["id"], "topic": m["topic"], "start_time": m.get("start_time", "")} for m in meetings]
		return json.dumps({"count": len(result), "meetings": result})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_get_meeting_recordings(**kwargs):
	"""Get recordings for a Zoom meeting."""
	try:
		resp = requests.get(
			f"https://api.zoom.us/v2/meetings/{kwargs['meeting_id']}/recordings",
			headers=_headers(),
			timeout=30,
		)
		resp.raise_for_status()
		return json.dumps(resp.json())
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_delete_meeting(**kwargs):
	"""Delete a Zoom meeting."""
	try:
		resp = requests.delete(
			f"https://api.zoom.us/v2/meetings/{kwargs['meeting_id']}",
			headers=_headers(),
			timeout=30,
		)
		resp.raise_for_status()
		return json.dumps({"ok": True, "meeting_id": kwargs["meeting_id"]})
	except Exception as e:
		return json.dumps({"error": str(e)})
