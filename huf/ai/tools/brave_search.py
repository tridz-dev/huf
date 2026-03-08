import json

from huf.ai.tools.credentials import require_credential
import requests


def handle_search(**kwargs):
	"""Search the web using Brave Search."""
	try:
		key = require_credential("brave", "api_key")

		params = {
			"q": kwargs["query"],
			"count": int(kwargs.get("max_results", 5)),
		}
		if "country" in kwargs:
			params["country"] = kwargs["country"]

		resp = requests.get(
			"https://api.search.brave.com/res/v1/web/search",
			headers={"X-Subscription-Token": key, "Accept": "application/json"},
			params=params,
			timeout=30,
		)
		resp.raise_for_status()
		data = resp.json()
		results = [
			{"title": r.get("title", ""), "url": r.get("url", ""), "description": r.get("description", "")}
			for r in data.get("web", {}).get("results", [])
		]
		return json.dumps({"count": len(results), "results": results})
	except Exception as e:
		return json.dumps({"error": str(e)})
