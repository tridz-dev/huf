import json
import os

import requests


def handle_search_google(**kwargs):
	"""Search Google using SerpApi."""
	try:
		key = os.getenv("SERP_API_KEY")
		if not key:
			return json.dumps({"error": "SERP_API_KEY environment variable is not set"})

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
		key = os.getenv("SERP_API_KEY")
		if not key:
			return json.dumps({"error": "SERP_API_KEY environment variable is not set"})

		params = {"api_key": key, "search_query": kwargs["query"], "engine": "youtube"}
		resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
		resp.raise_for_status()
		data = resp.json()
		return json.dumps({"results": data.get("video_results", [])})
	except Exception as e:
		return json.dumps({"error": str(e)})
