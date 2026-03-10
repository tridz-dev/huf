import json
import re
import frappe
from huf.ai.tools.credentials import require_credential, update_last_error
import requests


def handle_search(**kwargs):
	"""Search Zendesk Help Center articles."""
	service_name = "zendesk"
	try:
		query = kwargs.get("query")
		if not query:
			return json.dumps({"success": False, "error": "query is required"})

		username = require_credential(service_name, "email")
		password = require_credential(service_name, "api_token")
		company = require_credential(service_name, "subdomain")

		url = f"https://{company}.zendesk.com/api/v2/help_center/articles/search.json"
		resp = requests.get(url, params={"query": query}, auth=(username, password), timeout=30)
		resp.raise_for_status()

		tag_re = re.compile("<.*?>")
		articles = []
		for a in resp.json().get("results", []):
			body = re.sub(tag_re, "", a.get("body", "")) if a.get("body") else ""
			articles.append({
				"title": a.get("title", ""), 
				"body": body[:2000], 
				"url": a.get("html_url", "")
			})

		return json.dumps({
			"success": True, 
			"count": len(articles), 
			"results": articles
		})
	except Exception as e:
		frappe.log_error(f"Zendesk Error (Search): {str(e)}", "Zendesk Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})
