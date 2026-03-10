import json
import frappe
from huf.ai.tools.credentials import require_credential, update_last_error
import requests

BASE = "https://sheets.googleapis.com/v4/spreadsheets"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def _get_access_token():
	service_name = "google_sheets"
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


def handle_read_sheet(**kwargs):
	"""Read data from a Google Sheets spreadsheet."""
	service_name = "google_sheets"
	try:
		sheet_id = kwargs.get("spreadsheet_id")
		if not sheet_id:
			return json.dumps({"success": False, "error": "spreadsheet_id is required"})
			
		range_name = kwargs.get("range", "Sheet1")

		resp = requests.get(
			f"{BASE}/{sheet_id}/values/{range_name}",
			headers=_headers(),
			timeout=30,
		)
		resp.raise_for_status()
		data = resp.json()
		return json.dumps({
			"success": True,
			"results": {
				"range": data.get("range", ""), 
				"values": data.get("values", [])
			}
		})
	except Exception as e:
		frappe.log_error(f"Google Sheets Error (Read): {str(e)}", "Google Sheets Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_update_sheet(**kwargs):
	"""Update data in a Google Sheets spreadsheet."""
	service_name = "google_sheets"
	try:
		sheet_id = kwargs.get("spreadsheet_id")
		range_name = kwargs.get("range")
		values = kwargs.get("data")
		if not all([sheet_id, range_name, values]):
			return json.dumps({"success": False, "error": "spreadsheet_id, range, and data are required"})

		if isinstance(values, str):
			values = json.loads(values)

		resp = requests.put(
			f"{BASE}/{sheet_id}/values/{range_name}",
			headers=_headers(),
			params={"valueInputOption": "USER_ENTERED"},
			json={"values": values},
			timeout=30,
		)
		resp.raise_for_status()
		data = resp.json()
		return json.dumps({
			"success": True,
			"results": {
				"updated_cells": data.get("updatedCells", 0), 
				"updated_range": data.get("updatedRange", "")
			}
		})
	except Exception as e:
		frappe.log_error(f"Google Sheets Error (Update): {str(e)}", "Google Sheets Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_create_sheet(**kwargs):
	"""Create a new Google Sheets spreadsheet."""
	service_name = "google_sheets"
	try:
		title = kwargs.get("title")
		if not title:
			return json.dumps({"success": False, "error": "title is required"})

		resp = requests.post(
			BASE,
			headers=_headers(),
			json={"properties": {"title": title}},
			timeout=30,
		)
		resp.raise_for_status()
		data = resp.json()
		return json.dumps({
			"success": True,
			"results": {
				"spreadsheet_id": data.get("spreadsheetId", ""),
				"url": data.get("spreadsheetUrl", ""),
				"title": title,
			}
		})
	except Exception as e:
		frappe.log_error(f"Google Sheets Error (Create): {str(e)}", "Google Sheets Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})
