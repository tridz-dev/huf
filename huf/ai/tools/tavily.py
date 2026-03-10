import json
import frappe
from huf.ai.tools.credentials import require_credential, update_last_error
import requests


def handle_search(**kwargs):
	"""Search the web using Tavily AI-optimized search."""
	service_name = "tavily"
	try:
		api_key = require_credential(service_name, "api_key")

		query = kwargs.get("query")
		if not query:
			return json.dumps({"success": False, "error": "Query is required"})

		payload = {
			"api_key": api_key,
			"query": query,
			"search_depth": kwargs.get("search_depth", "advanced"),
			"max_results": int(kwargs.get("max_results", 5)),
			"include_answer": True,
		}

		resp = requests.post("https://api.tavily.com/search", json=payload, timeout=30)
		resp.raise_for_status()
		data = resp.json()
		results = [
			{"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")}
			for r in data.get("results", [])
		]
		return json.dumps({
			"success": True,
			"answer": data.get("answer", ""),
			"results": results,
			"count": len(results)
		})
	except Exception as e:
		frappe.log_error(f"Tavily Search Error: {str(e)}", "Tavily Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_extract_url(**kwargs):
	"""Extract content from URLs using Tavily."""
	service_name = "tavily"
	try:
		api_key = require_credential(service_name, "api_key")

		urls = kwargs.get("urls")
		if not urls:
			return json.dumps({"success": False, "error": "URLs are required"})
			
		if isinstance(urls, str):
			urls = [u.strip() for u in urls.split(",")]

		resp = requests.post(
			"https://api.tavily.com/extract",
			json={"api_key": api_key, "urls": urls},
			timeout=60,
		)
		resp.raise_for_status()
		data = resp.json()
		return json.dumps({"success": True, "data": data})
	except Exception as e:
		frappe.log_error(f"Tavily Extract Error: {str(e)}", "Tavily Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})
