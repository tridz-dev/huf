"""
Cal.com integration tools for booking listing, retrieval, and creation.
Uses HUF Integration Settings for Cal.com credentials (api_key). Cal.com API v2
authenticates with a Bearer token and requires a cal-api-version header.
"""

import json

import frappe
import requests

from huf.ai.tools.credentials import require_credential, update_last_error

logger = frappe.logger("huf")

SERVICE_NAME = "calcom"
CALCOM_API_BASE = "https://api.cal.com/v2"
LIST_BOOKINGS_API_VERSION = "2026-05-01"
BOOKING_API_VERSION = "2026-02-25"
EVENT_TYPES_API_VERSION = "2024-06-14"
VALID_LIST_STATUSES = {"upcoming", "recurring", "past", "cancelled", "unconfirmed"}


def _headers(api_version: str) -> dict:
	return {
		"Authorization": f"Bearer {require_credential(SERVICE_NAME, 'api_key')}",
		"Content-Type": "application/json",
		"cal-api-version": api_version,
	}


def _unwrap_response(payload: dict) -> dict | list:
	if not isinstance(payload, dict):
		return payload

	if payload.get("status") == "error":
		error = payload.get("error") or payload.get("message") or "Cal.com API error"
		if isinstance(error, dict):
			error = error.get("message") or json.dumps(error)
		raise ValueError(str(error))

	if "data" in payload:
		return payload["data"]
	return payload


def _booking_items(payload: dict) -> list:
	data = _unwrap_response(payload)
	if isinstance(data, list):
		return data
	if isinstance(data, dict):
		return data.get("items") or data.get("bookings") or []
	return []


def _normalize_booking(booking: dict) -> dict:
	return {
		"uid": booking.get("uid"),
		"title": booking.get("title"),
		"start_time": booking.get("startTime") or booking.get("start"),
		"end_time": booking.get("endTime") or booking.get("end"),
		"status": booking.get("status"),
		"attendees": [a.get("email") for a in (booking.get("attendees") or []) if a.get("email")],
	}


def _normalize_event_type(event_type: dict) -> dict:
	return {
		"id": event_type.get("id"),
		"title": event_type.get("title"),
		"slug": event_type.get("slug"),
		"description": event_type.get("description"),
		"duration_minutes": event_type.get("lengthInMinutes") or event_type.get("duration"),
		"booking_url": event_type.get("bookingUrl"),
		"hidden": event_type.get("hidden"),
	}


def _parse_event_type_id(value) -> int:
	raw = str(value or "").strip()
	if not raw.isdigit():
		raise ValueError(
			"event_type_id must be a numeric Cal.com event type ID. "
			"Ask the user for the ID from Cal.com → Event Types → event settings."
		)
	return int(raw)


def _make_calcom_request(
	method: str,
	endpoint: str,
	api_version: str,
	json_data=None,
	params=None,
):
	response = requests.request(
		method,
		f"{CALCOM_API_BASE}/{endpoint}",
		headers=_headers(api_version),
		params=params or None,
		json=json_data,
		timeout=30,
	)
	if not response.ok:
		message = response.text
		try:
			payload = response.json()
			if isinstance(payload, dict):
				error = payload.get("error") or payload.get("message")
				if isinstance(error, dict):
					error = error.get("message") or json.dumps(error)
				if error:
					message = str(error)
		except ValueError:
			pass
		raise ValueError(f"Cal.com API error ({response.status_code}): {message}")

	return response.json() if response.text else {}


def handle_list_bookings(**kwargs) -> str:
	"""List Cal.com bookings, optionally filtered by status."""
	try:
		params = {}
		status = kwargs.get("status")
		if status:
			status = str(status).strip().lower()
			if status not in VALID_LIST_STATUSES:
				return json.dumps(
					{
						"success": False,
						"error": (
							f"status must be one of: {', '.join(sorted(VALID_LIST_STATUSES))}"
						),
					},
					default=str,
				)
			params["status"] = status

		data = _make_calcom_request("GET", "bookings", LIST_BOOKINGS_API_VERSION, params=params)
		bookings = [_normalize_booking(booking) for booking in _booking_items(data)]

		return json.dumps({"success": True, "count": len(bookings), "results": bookings})
	except Exception as e:
		error_msg = f"Cal.com List Bookings Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_list_event_types(**kwargs) -> str:
	"""List Cal.com event types for the authenticated account."""
	try:
		params = {}
		username = kwargs.get("username")
		if username:
			params["username"] = username

		data = _make_calcom_request("GET", "event-types", EVENT_TYPES_API_VERSION, params=params)
		event_types = _unwrap_response(data)
		if not isinstance(event_types, list):
			event_types = []

		results = [_normalize_event_type(event_type) for event_type in event_types]
		return json.dumps({"success": True, "count": len(results), "results": results})
	except Exception as e:
		error_msg = f"Cal.com List Event Types Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_get_booking(**kwargs) -> str:
	"""Get details of a Cal.com booking by UID."""
	try:
		booking_uid = kwargs.get("booking_uid")
		if not booking_uid:
			return json.dumps({"success": False, "error": "booking_uid is required"}, default=str)

		data = _make_calcom_request("GET", f"bookings/{booking_uid}", BOOKING_API_VERSION)
		booking = _unwrap_response(data)
		if isinstance(booking, list):
			booking = booking[0] if booking else {}
		if not isinstance(booking, dict) or not booking.get("uid"):
			return json.dumps(
				{"success": False, "error": f"Booking '{booking_uid}' not found"},
				default=str,
			)

		booking_data = _normalize_booking(booking)
		booking_data["description"] = booking.get("description")

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

		parsed_event_type_id = _parse_event_type_id(event_type_id)
		payload = {
			"eventTypeId": parsed_event_type_id,
			"start": start,
			"attendee": {
				"name": attendee_name,
				"email": attendee_email,
				"timeZone": kwargs.get("timezone") or "UTC",
				"language": "en",
			},
		}

		data = _make_calcom_request("POST", "bookings", BOOKING_API_VERSION, json_data=payload)
		booking = _unwrap_response(data)
		if isinstance(booking, list):
			booking = booking[0] if booking else {}
		if not isinstance(booking, dict):
			booking = {}

		return json.dumps(
			{
				"success": True,
				"results": {
					"uid": booking.get("uid"),
					"title": booking.get("title"),
					"start_time": booking.get("startTime") or booking.get("start"),
					"status": booking.get("status"),
				},
			}
		)
	except Exception as e:
		error_msg = f"Cal.com Create Booking Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)
