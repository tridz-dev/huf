import json
import frappe
from huf.ai.tools.credentials import require_credential, update_last_error
import requests

BASE = "https://www.googleapis.com/drive/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def _get_access_token():
	service_name = "google_drive"
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
	return {"Authorization": f"Bearer {_get_access_token()}"}


def handle_list_files(**kwargs):
	"""List files in Google Drive."""
	service_name = "google_drive"
	try:
		limit = int(kwargs.get("limit", 20))
		params = {"pageSize": limit, "fields": "files(id,name,mimeType,modifiedTime,size)"}
		if "query" in kwargs:
			params["q"] = kwargs["query"]

		resp = requests.get(f"{BASE}/files", headers=_headers(), params=params, timeout=30)
		resp.raise_for_status()
		files = resp.json().get("files", [])
		return json.dumps({
			"success": True, 
			"count": len(files), 
			"results": files
		})
	except Exception as e:
		frappe.log_error(f"Google Drive Error (List): {str(e)}", "Google Drive Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_get_file(**kwargs):
	"""Get metadata of a Google Drive file."""
	service_name = "google_drive"
	try:
		file_id = kwargs.get("file_id")
		if not file_id:
			return json.dumps({"success": False, "error": "file_id is required"})

		resp = requests.get(
			f"{BASE}/files/{file_id}",
			headers=_headers(),
			params={"fields": "id,name,mimeType,modifiedTime,size,webViewLink"},
			timeout=30,
		)
		resp.raise_for_status()
		data = resp.json()
		return json.dumps({
			"success": True, 
			"results": data
		})
	except Exception as e:
		frappe.log_error(f"Google Drive Error (Get File): {str(e)}", "Google Drive Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_search_files(**kwargs):
	"""Search for files in Google Drive."""
	service_name = "google_drive"
	try:
		query = kwargs.get("query", "").strip()
		if not query:
			return json.dumps({"success": False, "error": "query is required"})

		if query.lower().startswith("title =") or query.lower().startswith("name ="):
			query = query.split("=", 1)[1].strip()
		
		if query.startswith("'") and query.endswith("'"):
			query = query[1:-1]
		elif query.startswith('"') and query.endswith('"'):
			query = query[1:-1]

		safe_query = query.replace("'", "\\'")
		q = f"fullText contains '{safe_query}' or name contains '{safe_query}'"
		params = {"q": q, "pageSize": 20, "fields": "files(id,name,mimeType,modifiedTime)"}

		resp = requests.get(f"{BASE}/files", headers=_headers(), params=params, timeout=30)
		resp.raise_for_status()
		files = resp.json().get("files", [])
		return json.dumps({
			"success": True, 
			"count": len(files), 
			"results": files
		})
	except Exception as e:
		frappe.log_error(f"Google Drive Error (Search): {str(e)}", "Google Drive Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})
