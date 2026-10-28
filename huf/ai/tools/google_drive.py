import json
import frappe
logger = frappe.logger("huf")
from huf.ai.tools.credentials import get_credential, update_last_error
from huf.ai.tools.provider_errors import ProviderCredentialError, check_google_response, mint_google_access_token, not_connected_message
import requests

BASE = "https://www.googleapis.com/drive/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def _get_access_token():
	service_name = "google_drive"
	client_id = get_credential(service_name, "client_id")
	client_secret = get_credential(service_name, "client_secret")
	refresh_token = get_credential(service_name, "refresh_token")
	if not (client_id and client_secret and refresh_token):
		raise ProviderCredentialError(not_connected_message("Google Drive", "the client ID, client secret and refresh token"), kind="missing")
	return mint_google_access_token("Google Drive", client_id, client_secret, refresh_token)["access_token"]


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
		check_google_response(resp, "Google Drive", "drive.readonly", not_found="file")
		files = resp.json().get("files", [])
		return json.dumps({
			"success": True, 
			"count": len(files), 
			"results": files
		})
	except Exception as e:
		logger.warning(f"Google Drive Error (List): {str(e)}")
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
		check_google_response(resp, "Google Drive", "drive.readonly", not_found="file")
		data = resp.json()
		return json.dumps({
			"success": True, 
			"results": data
		})
	except Exception as e:
		logger.warning(f"Google Drive Error (Get File): {str(e)}")
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
		check_google_response(resp, "Google Drive", "drive.readonly", not_found="file")
		files = resp.json().get("files", [])
		return json.dumps({
			"success": True, 
			"count": len(files), 
			"results": files
		})
	except Exception as e:
		logger.warning(f"Google Drive Error (Search): {str(e)}")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})
