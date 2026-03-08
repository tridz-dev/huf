import json
import os

import requests

BASE = "https://sheets.googleapis.com/v4/spreadsheets"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def _get_access_token():
	client_id = os.getenv("GOOGLE_CLIENT_ID")
	client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
	refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")

	if not all([client_id, client_secret, refresh_token]):
		raise ValueError("GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REFRESH_TOKEN are required")

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
	try:
		sheet_id = kwargs["spreadsheet_id"]
		range_name = kwargs.get("range", "Sheet1")

		resp = requests.get(
			f"{BASE}/{sheet_id}/values/{range_name}",
			headers=_headers(),
			timeout=30,
		)
		resp.raise_for_status()
		data = resp.json()
		return json.dumps({"range": data.get("range", ""), "values": data.get("values", [])})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_update_sheet(**kwargs):
	"""Update data in a Google Sheets spreadsheet."""
	try:
		sheet_id = kwargs["spreadsheet_id"]
		range_name = kwargs["range"]
		values = kwargs["data"]
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
		return json.dumps({"updated_cells": data.get("updatedCells", 0), "updated_range": data.get("updatedRange", "")})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_create_sheet(**kwargs):
	"""Create a new Google Sheets spreadsheet."""
	try:
		resp = requests.post(
			BASE,
			headers=_headers(),
			json={"properties": {"title": kwargs["title"]}},
			timeout=30,
		)
		resp.raise_for_status()
		data = resp.json()
		return json.dumps({
			"spreadsheet_id": data.get("spreadsheetId", ""),
			"url": data.get("spreadsheetUrl", ""),
			"title": kwargs["title"],
		})
	except Exception as e:
		return json.dumps({"error": str(e)})
