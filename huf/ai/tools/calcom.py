"""
Cal.com integration tools for booking listing, retrieval, and creation.
Uses HUF Integration Settings for Cal.com credentials (api_key). Cal.com's v1
REST API authenticates via an `apiKey` query parameter.
"""

import json

import frappe
import requests

from huf.ai.tools.credentials import require_credential, update_last_error

logger = frappe.logger("huf")

SERVICE_NAME = "calcom"
CALCOM_API_BASE = "https://api.cal.com/v1"


def _auth_params():
	return {"apiKey": require_credential(SERVICE_NAME, "api_key")}


def _make_calcom_request(method: str, endpoint: str, json_data=None, params=None):
	all_params = _auth_params()
	all_params.update(params or {})

	response = requests.request(
		method, f"{CALCOM_API_BASE}/{endpoint}", params=all_params, json=json_data, timeout=30
	)
	response.raise_for_status()
	return response.json() if response.text else {}


def handle_list_bookings(**kwargs) -> str:
	"""List Cal.com bookings, optionally filtered by status."""
	try:
		params = {}
		status = kwargs.get("status")
		if status:
			params["status"] = status

		data = _make_calcom_request("GET", "bookings", params=params)

		bookings = []
		for booking in data.get("bookings", []):
			bookings.append(
				{
					"uid": booking.get("uid"),
					"title": booking.get("title"),
					"start_time": booking.get("startTime"),
					"end_time": booking.get("endTime"),
					"status": booking.get("status"),
					"attendees": [a.get("email") for a in booking.get("attendees", [])],
				}
			)

		return json.dumps({"success": True, "count": len(bookings), "results": bookings})
	except Exception as e:
		error_msg = f"Cal.com List Bookings Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_get_booking(**kwargs) -> str:
	"""Get details of a Cal.com booking by UID."""
	try:
		booking_uid = kwargs.get("booking_uid")
		if not booking_uid:
			return json.dumps({"success": False, "error": "booking_uid is required"}, default=str)

		data = _make_calcom_request("GET", f"bookings/{booking_uid}")
		booking = data.get("booking", data)

		booking_data = {
			"uid": booking.get("uid"),
			"title": booking.get("title"),
			"description": booking.get("description"),
			"start_time": booking.get("startTime"),
			"end_time": booking.get("endTime"),
			"status": booking.get("status"),
			"attendees": [a.get("email") for a in booking.get("attendees", [])],
		}

		return json.dumps({"success": True, "results": booking_data})
	except Exception as e:
		error_msg = f"Cal.com Get Booking Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_create_booking(**kwargs) -> str:
	"""Create a Cal.com booking for an event type."""
	try:
		event_type_id = kwargs.get("event_type_id")
		start = kwargs.get("start")
		attendee_name = kwargs.get("attendee_name")
		attendee_email = kwargs.get("attendee_email")
		if not all([event_type_id, start, attendee_name, attendee_email]):
			return json.dumps(
				{
					"success": False,
					"error": "event_type_id, start, attendee_name, and attendee_email are required",
				},
				default=str,
			)

		payload = {
			"eventTypeId": int(event_type_id),
			"start": start,
			"responses": {"name": attendee_name, "email": attendee_email},
			"timeZone": kwargs.get("timezone") or "UTC",
			"language": "en",
			"metadata": {},
		}

		data = _make_calcom_request("POST", "bookings", json_data=payload)
		booking = data.get("booking", data)

		return json.dumps(
			{
				"success": True,
				"results": {
					"uid": booking.get("uid"),
					"title": booking.get("title"),
					"start_time": booking.get("startTime"),
					"status": booking.get("status"),
				},
			}
		)
	except Exception as e:
		error_msg = f"Cal.com Create Booking Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)
