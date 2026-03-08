import json
import os
from datetime import datetime, timedelta

import requests

BASE = "https://api.cal.com/v2"


def _headers():
	key = os.getenv("CALCOM_API_KEY")
	if not key:
		raise ValueError("CALCOM_API_KEY environment variable is not set")
	return {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "cal-api-version": "2024-08-13"}


def handle_get_available_slots(**kwargs):
	"""Get available booking slots from Cal.com."""
	try:
		event_type_id = kwargs.get("event_type_id") or os.getenv("CALCOM_EVENT_TYPE_ID")
		start = kwargs.get("start_date", datetime.utcnow().strftime("%Y-%m-%d"))
		end = kwargs.get("end_date", (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d"))

		resp = requests.get(
			f"{BASE}/slots",
			headers=_headers(),
			params={"eventTypeId": event_type_id, "startDate": start, "endDate": end},
			timeout=30,
		)
		resp.raise_for_status()
		return json.dumps(resp.json())
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_create_booking(**kwargs):
	"""Create a new booking on Cal.com."""
	try:
		event_type_id = kwargs.get("event_type_id") or os.getenv("CALCOM_EVENT_TYPE_ID")
		payload = {
			"eventTypeId": int(event_type_id),
			"start": kwargs["start_time"],
			"attendee": {"name": kwargs["attendee_name"], "email": kwargs["attendee_email"]},
		}
		if "timezone" in kwargs:
			payload["attendee"]["timeZone"] = kwargs["timezone"]

		resp = requests.post(f"{BASE}/bookings", headers=_headers(), json=payload, timeout=30)
		resp.raise_for_status()
		return json.dumps(resp.json())
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_list_bookings(**kwargs):
	"""List upcoming bookings from Cal.com."""
	try:
		resp = requests.get(f"{BASE}/bookings", headers=_headers(), params={"status": "upcoming"}, timeout=30)
		resp.raise_for_status()
		return json.dumps(resp.json())
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_cancel_booking(**kwargs):
	"""Cancel a Cal.com booking."""
	try:
		payload = {}
		if "reason" in kwargs:
			payload["cancellationReason"] = kwargs["reason"]
		resp = requests.delete(f"{BASE}/bookings/{kwargs['booking_id']}", headers=_headers(), json=payload, timeout=30)
		resp.raise_for_status()
		return json.dumps({"ok": True, "booking_id": kwargs["booking_id"]})
	except Exception as e:
		return json.dumps({"error": str(e)})
