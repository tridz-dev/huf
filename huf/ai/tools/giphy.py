import json
import os

import requests


def handle_search_gifs(**kwargs):
	"""Search for GIFs on Giphy."""
	try:
		key = os.getenv("GIPHY_API_KEY")
		if not key:
			return json.dumps({"error": "GIPHY_API_KEY environment variable is not set"})

		limit = int(kwargs.get("limit", 10))
		resp = requests.get(
			"https://api.giphy.com/v1/gifs/search",
			params={"api_key": key, "q": kwargs["query"], "limit": limit},
			timeout=15,
		)
		resp.raise_for_status()
		gifs = [
			{
				"id": g["id"],
				"title": g.get("title", ""),
				"url": g["images"]["original"]["url"],
				"preview": g["images"]["preview_gif"]["url"] if "preview_gif" in g.get("images", {}) else "",
			}
			for g in resp.json().get("data", [])
		]
		return json.dumps({"count": len(gifs), "gifs": gifs})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_trending_gifs(**kwargs):
	"""Get trending GIFs from Giphy."""
	try:
		key = os.getenv("GIPHY_API_KEY")
		if not key:
			return json.dumps({"error": "GIPHY_API_KEY environment variable is not set"})

		limit = int(kwargs.get("limit", 10))
		resp = requests.get(
			"https://api.giphy.com/v1/gifs/trending",
			params={"api_key": key, "limit": limit},
			timeout=15,
		)
		resp.raise_for_status()
		gifs = [
			{"id": g["id"], "title": g.get("title", ""), "url": g["images"]["original"]["url"]}
			for g in resp.json().get("data", [])
		]
		return json.dumps({"count": len(gifs), "gifs": gifs})
	except Exception as e:
		return json.dumps({"error": str(e)})
