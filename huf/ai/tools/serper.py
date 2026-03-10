import json
import frappe
from huf.ai.tools.credentials import require_credential, update_last_error
import requests

BASE = "https://google.serper.dev"


def _headers():
	service_name = "serper"
	key = require_credential(service_name, "api_key")
	return {"X-API-KEY": key, "Content-Type": "application/json"}


def handle_search_web(**kwargs):
	"""Search the web using Serper (Google Search API)."""
	service_name = "serper"
	try:
		query = kwargs.get("query")
		if not query:
			return json.dumps({"success": False, "error": "Query is required"})

		resp = requests.post(f"{BASE}/search", headers=_headers(), json={"q": query}, timeout=30)
		resp.raise_for_status()
		data = resp.json()
		organic = [
			{"title": r.get("title", ""), "link": r.get("link", ""), "snippet": r.get("snippet", "")}
			for r in data.get("organic", [])
		]
		return json.dumps({
			"success": True, 
			"answer_box": data.get("answerBox"), 
			"results": organic,
			"count": len(organic)
		})
	except Exception as e:
		frappe.log_error(f"Serper Search Error: {str(e)}", "Serper Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_search_news(**kwargs):
	"""Search news using Serper."""
	service_name = "serper"
	try:
		query = kwargs.get("query")
		if not query:
			return json.dumps({"success": False, "error": "Query is required"})

		resp = requests.post(f"{BASE}/news", headers=_headers(), json={"q": query}, timeout=30)
		resp.raise_for_status()
		data = resp.json()
		news = [
			{"title": r.get("title", ""), "link": r.get("link", ""), "snippet": r.get("snippet", "")}
			for r in data.get("news", [])
		]
		return json.dumps({"success": True, "count": len(news), "results": news})
	except Exception as e:
		frappe.log_error(f"Serper News Error: {str(e)}", "Serper Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_search_scholar(**kwargs):
	"""Search academic papers using Serper."""
	service_name = "serper"
	try:
		query = kwargs.get("query")
		if not query:
			return json.dumps({"success": False, "error": "Query is required"})

		resp = requests.post(f"{BASE}/scholar", headers=_headers(), json={"q": query}, timeout=30)
		resp.raise_for_status()
		data = resp.json()
		results = data.get("organic", [])
		return json.dumps({"success": True, "count": len(results), "results": results})
	except Exception as e:
		frappe.log_error(f"Serper Scholar Error: {str(e)}", "Serper Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})
