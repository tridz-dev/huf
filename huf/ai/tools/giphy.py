import json
import frappe
from huf.ai.tools.credentials import require_credential, update_last_error
import requests


def handle_search_gifs(**kwargs):
	"""Search for GIFs on Giphy."""
	service_name = "giphy"
	try:
		query = kwargs.get("query")
		if not query:
			return json.dumps({"success": False, "error": "query is required"})

		key = require_credential(service_name, "api_key")
		limit = int(kwargs.get("limit", 10))
		resp = requests.get(
			"https://api.giphy.com/v1/gifs/search",
			params={"api_key": key, "q": query, "limit": limit},
			timeout=15,
		)
		resp.raise_for_status()
		gifs = [
			{
				"id": g["id"],
				"title": g.get("title", ""),
				"url": g["images"]["original"]["url"],
				"preview": g["images"]["preview_gif"]["url"] if "preview_gif" in g.get("images", {}) else "",
			}
			for g in resp.json().get("data", [])
		]
		return json.dumps({
			"success": True, 
			"count": len(gifs), 
			"results": gifs
		})
	except Exception as e:
		frappe.log_error(f"Giphy Error (Search): {str(e)}", "Giphy Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_trending_gifs(**kwargs):
	"""Get trending GIFs from Giphy."""
	service_name = "giphy"
	try:
		key = require_credential(service_name, "api_key")
		limit = int(kwargs.get("limit", 10))
		resp = requests.get(
			"https://api.giphy.com/v1/gifs/trending",
			params={"api_key": key, "limit": limit},
			timeout=15,
		)
		resp.raise_for_status()
		gifs = [
			{
				"id": g["id"], 
				"title": g.get("title", ""), 
				"url": g["images"]["original"]["url"]
			}
			for g in resp.json().get("data", [])
		]
		return json.dumps({
			"success": True, 
			"count": len(gifs), 
			"results": gifs
		})
	except Exception as e:
		frappe.log_error(f"Giphy Error (Trending): {str(e)}", "Giphy Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})
