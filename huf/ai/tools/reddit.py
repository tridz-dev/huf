import json

from huf.ai.tools.credentials import require_credential
import requests

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
BASE = "https://oauth.reddit.com"


def _get_token():
	client_id = require_credential("reddit", "client_id")
	client_secret = require_credential("reddit", "client_secret")

	resp = requests.post(
		TOKEN_URL,
		auth=(client_id, client_secret),
		data={"grant_type": "client_credentials"},
		headers={"User-Agent": "huf-agent/1.0"},
		timeout=15,
	)
	resp.raise_for_status()
	return resp.json()["access_token"]


def _headers():
	return {"Authorization": f"Bearer {_get_token()}", "User-Agent": "huf-agent/1.0"}


def handle_get_top_posts(**kwargs):
	"""Get top posts from a subreddit."""
	try:
		subreddit = kwargs["subreddit"]
		time_filter = kwargs.get("time_filter", "week")
		limit = int(kwargs.get("limit", 10))

		resp = requests.get(
			f"{BASE}/r/{subreddit}/top",
			headers=_headers(),
			params={"t": time_filter, "limit": limit},
			timeout=15,
		)
		resp.raise_for_status()
		posts = []
		for child in resp.json().get("data", {}).get("children", []):
			d = child.get("data", {})
			posts.append({
				"title": d.get("title", ""),
				"score": d.get("score", 0),
				"url": d.get("url", ""),
				"author": d.get("author", ""),
				"num_comments": d.get("num_comments", 0),
			})
		return json.dumps({"count": len(posts), "posts": posts})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_get_user_info(**kwargs):
	"""Get information about a Reddit user."""
	try:
		resp = requests.get(
			f"{BASE}/user/{kwargs['username']}/about",
			headers=_headers(),
			timeout=15,
		)
		resp.raise_for_status()
		d = resp.json().get("data", {})
		return json.dumps({
			"name": d.get("name", ""),
			"comment_karma": d.get("comment_karma", 0),
			"link_karma": d.get("link_karma", 0),
			"created_utc": d.get("created_utc"),
		})
	except Exception as e:
		return json.dumps({"error": str(e)})
