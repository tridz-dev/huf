import json
import os

import requests

BASE = "https://api.unsplash.com"


def _headers():
	key = os.getenv("UNSPLASH_ACCESS_KEY")
	if not key:
		raise ValueError("UNSPLASH_ACCESS_KEY environment variable is not set")
	return {"Authorization": f"Client-ID {key}"}


def handle_search_photos(**kwargs):
	"""Search for photos on Unsplash."""
	try:
		per_page = int(kwargs.get("per_page", 10))
		resp = requests.get(
			f"{BASE}/search/photos",
			headers=_headers(),
			params={"query": kwargs["query"], "per_page": per_page},
			timeout=15,
		)
		resp.raise_for_status()
		results = [
			{
				"id": p["id"],
				"description": p.get("description") or p.get("alt_description", ""),
				"url": p["urls"]["regular"],
				"thumb": p["urls"]["thumb"],
				"photographer": p["user"]["name"],
			}
			for p in resp.json().get("results", [])
		]
		return json.dumps({"count": len(results), "photos": results})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_get_random_photo(**kwargs):
	"""Get a random photo from Unsplash."""
	try:
		params = {}
		if "query" in kwargs:
			params["query"] = kwargs["query"]
		resp = requests.get(f"{BASE}/photos/random", headers=_headers(), params=params, timeout=15)
		resp.raise_for_status()
		p = resp.json()
		return json.dumps({
			"id": p["id"],
			"description": p.get("description") or p.get("alt_description", ""),
			"url": p["urls"]["regular"],
			"photographer": p["user"]["name"],
		})
	except Exception as e:
		return json.dumps({"error": str(e)})
