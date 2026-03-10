import json
import frappe
from huf.ai.tools.credentials import require_credential, update_last_error
import requests

BASE = "https://api.unsplash.com"


def _headers():
	service_name = "unsplash"
	key = require_credential(service_name, "access_key")
	return {"Authorization": f"Client-ID {key}"}


def handle_search_photos(**kwargs):
	"""Search for photos on Unsplash."""
	service_name = "unsplash"
	try:
		query = kwargs.get("query")
		if not query:
			return json.dumps({"success": False, "error": "query is required"})

		per_page = int(kwargs.get("per_page", 10))
		resp = requests.get(
			f"{BASE}/search/photos",
			headers=_headers(),
			params={"query": query, "per_page": per_page},
			timeout=15,
		)
		resp.raise_for_status()
		results = [
			{
				"id": p["id"],
				"description": p.get("description") or p.get("alt_description", ""),
				"url": p["urls"]["regular"],
				"thumb": p["urls"]["thumb"],
				"photographer": p["user"]["name"],
			}
			for p in resp.json().get("results", [])
		]
		return json.dumps({
			"success": True, 
			"count": len(results), 
			"results": results
		})
	except Exception as e:
		frappe.log_error(f"Unsplash Error (Search): {str(e)}", "Unsplash Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_get_random_photo(**kwargs):
	"""Get a random photo from Unsplash."""
	service_name = "unsplash"
	try:
		params = {}
		if "query" in kwargs:
			params["query"] = kwargs["query"]
		resp = requests.get(f"{BASE}/photos/random", headers=_headers(), params=params, timeout=15)
		resp.raise_for_status()
		p = resp.json()
		return json.dumps({
			"success": True,
			"results": {
				"id": p["id"],
				"description": p.get("description") or p.get("alt_description", ""),
				"url": p["urls"]["regular"],
				"photographer": p["user"]["name"],
			}
		})
	except Exception as e:
		frappe.log_error(f"Unsplash Error (Random): {str(e)}", "Unsplash Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})
