import json
import re

from huf.ai.tools.credentials import require_credential
import requests


def handle_search(**kwargs):
	"""Search Zendesk Help Center articles."""
	try:
		username = require_credential("zendesk", "email")
		password = require_credential("zendesk", "api_token")
		company = require_credential("zendesk", "subdomain")

		url = f"https://{company}.zendesk.com/api/v2/help_center/articles/search.json"
		resp = requests.get(url, params={"query": kwargs["query"]}, auth=(username, password), timeout=30)
		resp.raise_for_status()

		tag_re = re.compile("<.*?>")
		articles = []
		for a in resp.json().get("results", []):
			body = re.sub(tag_re, "", a.get("body", "")) if a.get("body") else ""
			articles.append({"title": a.get("title", ""), "body": body[:2000], "url": a.get("html_url", "")})

		return json.dumps({"count": len(articles), "articles": articles})
	except Exception as e:
		return json.dumps({"error": str(e)})
