import json
import frappe
from huf.ai.tools.credentials import require_credential, update_last_error
import requests


def handle_search(**kwargs):
	"""Search the web using Brave Search."""
	service_name = "brave_search"
	try:
		key = require_credential(service_name, "api_key")

		query = kwargs.get("query")
		if not query:
			return json.dumps({"success": False, "error": "Query is required"})

		params = {
			"q": query,
			"count": int(kwargs.get("max_results", 5)),
		}
		if "country" in kwargs:
			params["country"] = kwargs["country"]

		resp = requests.get(
			"https://api.search.brave.com/res/v1/web/search",
			headers={"X-Subscription-Token": key, "Accept": "application/json"},
			params=params,
			timeout=15,
		)
		resp.raise_for_status()
		data = resp.json()
		results = [
			{"title": r.get("title", ""), "url": r.get("url", ""), "description": r.get("description", "")}
			for r in data.get("web", {}).get("results", [])
		]
		return json.dumps({"success": True, "count": len(results), "results": results})
	except Exception as e:
		frappe.log_error(f"Brave Search Error: {str(e)}", "Brave Search Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})
