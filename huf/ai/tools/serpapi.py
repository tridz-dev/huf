import json

from huf.ai.tools.credentials import require_credential
import requests


def handle_search_google(**kwargs):
	"""Search Google using SerpApi."""
	try:
		key = require_credential("serpapi", "api_key")

		params = {"api_key": key, "q": kwargs["query"], "engine": "google"}
		resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
		resp.raise_for_status()
		data = resp.json()
		organic = [
			{"title": r.get("title", ""), "link": r.get("link", ""), "snippet": r.get("snippet", "")}
			for r in data.get("organic_results", [])
		]
		return json.dumps({"count": len(organic), "results": organic})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_search_youtube(**kwargs):
	"""Search YouTube using SerpApi."""
	try:
		key = require_credential("serpapi", "api_key")

		params = {"api_key": key, "search_query": kwargs["query"], "engine": "youtube"}
		resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
		resp.raise_for_status()
		data = resp.json()
		return json.dumps({"results": data.get("video_results", [])})
	except Exception as e:
		return json.dumps({"error": str(e)})
