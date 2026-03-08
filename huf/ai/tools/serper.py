import json

from huf.ai.tools.credentials import require_credential
import requests

BASE = "https://google.serper.dev"


def _headers():
	key = require_credential("serper", "api_key")
	return {"X-API-KEY": key, "Content-Type": "application/json"}


def handle_search_web(**kwargs):
	"""Search the web using Serper (Google Search API)."""
	try:
		resp = requests.post(f"{BASE}/search", headers=_headers(), json={"q": kwargs["query"]}, timeout=30)
		resp.raise_for_status()
		data = resp.json()
		organic = [
			{"title": r.get("title", ""), "link": r.get("link", ""), "snippet": r.get("snippet", "")}
			for r in data.get("organic", [])
		]
		return json.dumps({"answer_box": data.get("answerBox"), "results": organic})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_search_news(**kwargs):
	"""Search news using Serper."""
	try:
		resp = requests.post(f"{BASE}/news", headers=_headers(), json={"q": kwargs["query"]}, timeout=30)
		resp.raise_for_status()
		data = resp.json()
		news = [
			{"title": r.get("title", ""), "link": r.get("link", ""), "snippet": r.get("snippet", "")}
			for r in data.get("news", [])
		]
		return json.dumps({"count": len(news), "news": news})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_search_scholar(**kwargs):
	"""Search academic papers using Serper."""
	try:
		resp = requests.post(f"{BASE}/scholar", headers=_headers(), json={"q": kwargs["query"]}, timeout=30)
		resp.raise_for_status()
		data = resp.json()
		return json.dumps({"results": data.get("organic", [])})
	except Exception as e:
		return json.dumps({"error": str(e)})
