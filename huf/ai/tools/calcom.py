import json
from datetime import datetime, timedelta
import frappe
from huf.ai.tools.credentials import require_credential, update_last_error
import requests

BASE = "https://api.cal.com/v2"


def _headers():
	service_name = "calcom"
	key = require_credential(service_name, "api_key")
	return {
		"Authorization": f"Bearer {key}", 
		"Content-Type": "application/json", 
		"cal-api-version": "2024-08-13"
	}


def handle_get_available_slots(**kwargs):
	"""Get available booking slots from Cal.com."""
	service_name = "calcom"
	try:
		event_type_id = kwargs.get("event_type_id")
		if not event_type_id:
			return json.dumps({"success": False, "error": "event_type_id is required"})

		start = kwargs.get("start_date", datetime.utcnow().strftime("%Y-%m-%d"))
		end = kwargs.get("end_date", (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d"))

		resp = requests.get(
			f"{BASE}/slots",
			headers=_headers(),
			params={"eventTypeId": event_type_id, "startDate": start, "endDate": end},
			timeout=30,
		)
		resp.raise_for_status()
		return json.dumps({
			"success": True, 
			"results": resp.json()
		})
	except Exception as e:
		frappe.log_error(f"Cal.com Error (Slots): {str(e)}", "Cal.com Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_create_booking(**kwargs):
	"""Create a new booking on Cal.com."""
	service_name = "calcom"
	try:
		event_type_id = kwargs.get("event_type_id")
		start_time = kwargs.get("start_time")
		attendee_name = kwargs.get("attendee_name")
		attendee_email = kwargs.get("attendee_email")
		
		if not all([event_type_id, start_time, attendee_name, attendee_email]):
			return json.dumps({"success": False, "error": "event_type_id, start_time, attendee_name, and attendee_email are required"})

		payload = {
			"eventTypeId": int(event_type_id),
			"start": start_time,
			"attendee": {"name": attendee_name, "email": attendee_email},
		}
		if "timezone" in kwargs:
			payload["attendee"]["timeZone"] = kwargs["timezone"]

		resp = requests.post(f"{BASE}/bookings", headers=_headers(), json=payload, timeout=30)
		resp.raise_for_status()
		return json.dumps({
			"success": True, 
			"results": resp.json()
		})
	except Exception as e:
		frappe.log_error(f"Cal.com Error (Create Booking): {str(e)}", "Cal.com Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_list_bookings(**kwargs):
	"""List upcoming bookings from Cal.com."""
	service_name = "calcom"
	try:
		resp = requests.get(f"{BASE}/bookings", headers=_headers(), params={"status": "upcoming"}, timeout=30)
		resp.raise_for_status()
		data = resp.json()
		return json.dumps({
			"success": True, 
			"results": data
		})
	except Exception as e:
		frappe.log_error(f"Cal.com Error (List Bookings): {str(e)}", "Cal.com Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_cancel_booking(**kwargs):
	"""Cancel a Cal.com booking."""
	service_name = "calcom"
	try:
		booking_id = kwargs.get("booking_id")
		if not booking_id:
			return json.dumps({"success": False, "error": "booking_id is required"})

		payload = {}
		if "reason" in kwargs:
			payload["cancellationReason"] = kwargs["reason"]
		
		resp = requests.delete(f"{BASE}/bookings/{booking_id}", headers=_headers(), json=payload, timeout=30)
		resp.raise_for_status()
		return json.dumps({
			"success": True, 
			"results": {"booking_id": booking_id}
		})
	except Exception as e:
		frappe.log_error(f"Cal.com Error (Cancel Booking): {str(e)}", "Cal.com Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})
