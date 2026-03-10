import json
import frappe
from huf.ai.tools.credentials import require_credential, update_last_error
import requests


def handle_search_google(**kwargs):
	"""Search Google using SerpApi."""
	service_name = "serpapi"
	try:
		key = require_credential(service_name, "api_key")

		query = kwargs.get("query")
		if not query:
			return json.dumps({"success": False, "error": "Query is required"})

		params = {"api_key": key, "q": query, "engine": "google"}
		resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
		resp.raise_for_status()
		data = resp.json()
		organic = [
			{"title": r.get("title", ""), "link": r.get("link", ""), "snippet": r.get("snippet", "")}
			for r in data.get("organic_results", [])
		]
		return json.dumps({"success": True, "count": len(organic), "results": organic})
	except Exception as e:
		frappe.log_error(f"SerpApi Google Error: {str(e)}", "SerpApi Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_search_youtube(**kwargs):
	"""Search YouTube using SerpApi."""
	service_name = "serpapi"
	try:
		key = require_credential(service_name, "api_key")

		query = kwargs.get("query")
		if not query:
			return json.dumps({"success": False, "error": "Query is required"})

		params = {"api_key": key, "search_query": query, "engine": "youtube"}
		resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
		resp.raise_for_status()
		data = resp.json()
		results = data.get("video_results", [])
		return json.dumps({"success": True, "count": len(results), "results": results})
	except Exception as e:
		frappe.log_error(f"SerpApi YouTube Error: {str(e)}", "SerpApi Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})
