import json
import frappe
logger = frappe.logger("huf")
from huf.ai.tools.credentials import get_credential, update_last_error
from huf.ai.tools.integration.provider_errors import ProviderCredentialError, check_google_response, mint_google_access_token, not_connected_message
import requests

BASE = "https://sheets.googleapis.com/v4/spreadsheets"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def _get_access_token():
	service_name = "google_sheets"
	client_id = get_credential(service_name, "client_id")
	client_secret = get_credential(service_name, "client_secret")
	refresh_token = get_credential(service_name, "refresh_token")
	if not (client_id and client_secret and refresh_token):
		raise ProviderCredentialError(not_connected_message("Google Sheets", "the client ID, client secret and refresh token"), kind="missing")
	return mint_google_access_token("Google Sheets", client_id, client_secret, refresh_token)["access_token"]


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
		check_google_response(resp, "Google Sheets", "spreadsheets", not_found="spreadsheet")
		data = resp.json()
		return json.dumps({
			"success": True,
			"results": {
				"range": data.get("range", ""), 
				"values": data.get("values", [])
			}
		})
	except Exception as e:
		logger.warning(f"Google Sheets Error (Read): {str(e)}")
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
		check_google_response(resp, "Google Sheets", "spreadsheets", not_found="spreadsheet")
		data = resp.json()
		return json.dumps({
			"success": True,
			"results": {
				"updated_cells": data.get("updatedCells", 0), 
				"updated_range": data.get("updatedRange", "")
			}
		})
	except Exception as e:
		logger.warning(f"Google Sheets Error (Update): {str(e)}")
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
		check_google_response(resp, "Google Sheets", "spreadsheets", not_found="spreadsheet")
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
		logger.warning(f"Google Sheets Error (Create): {str(e)}")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})
