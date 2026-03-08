import json

from huf.ai.tools.credentials import require_credential
import requests


def handle_search(**kwargs):
	"""Search the web using Tavily AI-optimized search."""
	try:
		api_key = require_credential("tavily", "api_key")

		payload = {
			"api_key": api_key,
			"query": kwargs["query"],
			"search_depth": kwargs.get("search_depth", "advanced"),
			"max_results": int(kwargs.get("max_results", 5)),
			"include_answer": True,
		}

		resp = requests.post("https://api.tavily.com/search", json=payload, timeout=30)
		resp.raise_for_status()
		data = resp.json()
		return json.dumps({
			"answer": data.get("answer", ""),
			"results": [
				{"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")}
				for r in data.get("results", [])
			],
		})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_extract_url(**kwargs):
	"""Extract content from URLs using Tavily."""
	try:
		api_key = require_credential("tavily", "api_key")

		urls = kwargs["urls"]
		if isinstance(urls, str):
			urls = [u.strip() for u in urls.split(",")]

		resp = requests.post(
			"https://api.tavily.com/extract",
			json={"api_key": api_key, "urls": urls},
			timeout=60,
		)
		resp.raise_for_status()
		return json.dumps(resp.json())
	except Exception as e:
		return json.dumps({"error": str(e)})
