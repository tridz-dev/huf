import json
import frappe
import requests


def handle_search(**kwargs):
	"""Search Wikipedia and return a summary."""
	try:
		query = kwargs.get("query")
		if not query:
			return json.dumps({"success": False, "error": "Query is required"})
			
		resp = requests.get(
			"https://en.wikipedia.org/api/rest_v1/page/summary/" + requests.utils.quote(query),
			headers={"User-Agent": "huf-agent/1.0"},
			timeout=15,
		)

		if resp.status_code == 404:
			search_resp = requests.get(
				"https://en.wikipedia.org/w/api.php",
				params={"action": "opensearch", "search": query, "limit": 5, "format": "json"},
				timeout=15,
			)
			search_resp.raise_for_status()
			data = search_resp.json()
			suggestions = data[1] if len(data) > 1 else []
			return json.dumps({
				"success": True, 
				"results": {
					"found": False, 
					"suggestions": suggestions
				}
			})

		resp.raise_for_status()
		data = resp.json()
		return json.dumps({
			"success": True,
			"results": {
				"title": data.get("title", ""),
				"extract": data.get("extract", ""),
				"url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
				"description": data.get("description", ""),
			}
		})
	except Exception as e:
		frappe.log_error(f"Wikipedia Error: {str(e)}", "Wikipedia Tool")
		return json.dumps({"success": False, "error": str(e)})
