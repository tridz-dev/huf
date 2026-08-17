"""
Zoom integration tools for meeting listing, retrieval, and creation.
Uses HUF Integration Settings for Zoom Server-to-Server OAuth credentials
(account_id, client_id, client_secret). Access tokens are cached in the
Frappe cache until shortly before they expire.
"""

import json

import frappe
import requests

from huf.ai.tools.credentials import require_credential, update_last_error

logger = frappe.logger("huf")

SERVICE_NAME = "zoom"
ZOOM_OAUTH_URL = "https://zoom.us/oauth/token"
ZOOM_API_BASE = "https://api.zoom.us/v2"
_TOKEN_CACHE_KEY = "zoom_s2s_access_token"


def _get_access_token() -> str:
	cached = frappe.cache().get_value(_TOKEN_CACHE_KEY)
	if cached:
		return cached

	account_id = require_credential(SERVICE_NAME, "account_id")
	client_id = require_credential(SERVICE_NAME, "client_id")
	client_secret = require_credential(SERVICE_NAME, "client_secret")

	response = requests.post(
		ZOOM_OAUTH_URL,
		params={"grant_type": "account_credentials", "account_id": account_id},
		auth=(client_id, client_secret),
		timeout=30,
	)
	response.raise_for_status()
	data = response.json()

	access_token = data.get("access_token")
	if not access_token:
		raise ValueError("Zoom OAuth response did not include an access_token")

	expires_in = int(data.get("expires_in") or 3600)
	frappe.cache().set_value(_TOKEN_CACHE_KEY, access_token, expires_in_sec=max(expires_in - 60, 60))
	return access_token


def _make_zoom_request(method: str, endpoint: str, json_data=None, params=None):
	headers = {"Authorization": f"Bearer {_get_access_token()}", "Content-Type": "application/json"}

	response = requests.request(
		method, f"{ZOOM_API_BASE}/{endpoint}", headers=headers, json=json_data, params=params, timeout=30
	)
	response.raise_for_status()
	return response.json() if response.text else {}


def handle_list_meetings(**kwargs) -> str:
	"""List scheduled Zoom meetings for the authenticated user."""
	try:
		data = _make_zoom_request("GET", "users/me/meetings", params={"type": "scheduled"})

		meetings = []
		for meeting in data.get("meetings", []):
			meetings.append(
				{
					"id": meeting.get("id"),
					"topic": meeting.get("topic"),
					"start_time": meeting.get("start_time"),
					"duration": meeting.get("duration"),
					"join_url": meeting.get("join_url"),
				}
			)

		return json.dumps({"success": True, "count": len(meetings), "results": meetings})
	except Exception as e:
		error_msg = f"Zoom List Meetings Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_get_meeting(**kwargs) -> str:
	"""Get details of a Zoom meeting by ID."""
	try:
		meeting_id = kwargs.get("meeting_id")
		if not meeting_id:
			return json.dumps({"success": False, "error": "meeting_id is required"}, default=str)

		data = _make_zoom_request("GET", f"meetings/{meeting_id}")

		meeting_data = {
			"id": data.get("id"),
			"topic": data.get("topic"),
			"agenda": data.get("agenda"),
			"start_time": data.get("start_time"),
			"duration": data.get("duration"),
			"timezone": data.get("timezone"),
			"join_url": data.get("join_url"),
			"host_email": data.get("host_email"),
		}

		return json.dumps({"success": True, "results": meeting_data})
	except Exception as e:
		error_msg = f"Zoom Get Meeting Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_create_meeting(**kwargs) -> str:
	"""Create a scheduled (or instant) Zoom meeting."""
	try:
		topic = kwargs.get("topic")
		if not topic:
			return json.dumps({"success": False, "error": "topic is required"}, default=str)

		start_time = kwargs.get("start_time")
		payload = {
			"topic": topic,
			"type": 2 if start_time else 1,  # 2 = scheduled, 1 = instant
			"duration": int(kwargs.get("duration") or 30),
		}
		if start_time:
			payload["start_time"] = start_time

		data = _make_zoom_request("POST", "users/me/meetings", json_data=payload)

		return json.dumps(
			{
				"success": True,
				"results": {
					"id": data.get("id"),
					"topic": data.get("topic"),
					"join_url": data.get("join_url"),
					"start_url": data.get("start_url"),
				},
			}
		)
	except Exception as e:
		error_msg = f"Zoom Create Meeting Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)
