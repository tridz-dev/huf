import json

from huf.ai.tools.credentials import require_credential
import requests

BASE = "https://www.googleapis.com/drive/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def _get_access_token():
	client_id = require_credential("google", "client_id")
	client_secret = require_credential("google", "client_secret")
	refresh_token = require_credential("google", "refresh_token")

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
	try:
		limit = int(kwargs.get("limit", 20))
		params = {"pageSize": limit, "fields": "files(id,name,mimeType,modifiedTime,size)"}
		if "query" in kwargs:
			params["q"] = kwargs["query"]

		resp = requests.get(f"{BASE}/files", headers=_headers(), params=params, timeout=30)
		resp.raise_for_status()
		files = resp.json().get("files", [])
		return json.dumps({"count": len(files), "files": files})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_get_file(**kwargs):
	"""Get metadata of a Google Drive file."""
	try:
		resp = requests.get(
			f"{BASE}/files/{kwargs['file_id']}",
			headers=_headers(),
			params={"fields": "id,name,mimeType,modifiedTime,size,webViewLink"},
			timeout=30,
		)
		resp.raise_for_status()
		return json.dumps(resp.json())
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_search_files(**kwargs):
	"""Search for files in Google Drive."""
	try:
		query = kwargs["query"]
		q = f"fullText contains '{query}' or name contains '{query}'"
		params = {"q": q, "pageSize": 20, "fields": "files(id,name,mimeType,modifiedTime)"}

		resp = requests.get(f"{BASE}/files", headers=_headers(), params=params, timeout=30)
		resp.raise_for_status()
		files = resp.json().get("files", [])
		return json.dumps({"count": len(files), "files": files})
	except Exception as e:
		return json.dumps({"error": str(e)})
