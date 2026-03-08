import json
import os
import re

import requests


def handle_search(**kwargs):
	"""Search Zendesk Help Center articles."""
	try:
		username = os.getenv("ZENDESK_USERNAME")
		password = os.getenv("ZENDESK_PASSWORD")
		company = os.getenv("ZENDESK_COMPANY_NAME")

		if not all([username, password, company]):
			return json.dumps({"error": "ZENDESK_USERNAME, ZENDESK_PASSWORD, and ZENDESK_COMPANY_NAME are required"})

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
