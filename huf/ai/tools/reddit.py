import json
import frappe
from huf.ai.tools.credentials import require_credential, update_last_error
import requests

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
BASE = "https://oauth.reddit.com"


def _get_token():
	service_name = "reddit"
	client_id = require_credential(service_name, "client_id")
	client_secret = require_credential(service_name, "client_secret")

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
	service_name = "reddit"
	try:
		subreddit = kwargs.get("subreddit")
		if not subreddit:
			return json.dumps({"success": False, "error": "Subreddit is required"})
			
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
		return json.dumps({"success": True, "count": len(posts), "results": posts})
	except Exception as e:
		frappe.log_error(f"Reddit Error (Top Posts): {str(e)}", "Reddit Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_get_user_info(**kwargs):
	"""Get information about a Reddit user."""
	service_name = "reddit"
	try:
		username = kwargs.get("username")
		if not username:
			return json.dumps({"success": False, "error": "Username is required"})
			
		resp = requests.get(
			f"{BASE}/user/{username}/about",
			headers=_headers(),
			timeout=15,
		)
		resp.raise_for_status()
		d = resp.json().get("data", {})
		return json.dumps({
			"success": True,
			"results": {
				"name": d.get("name", ""),
				"comment_karma": d.get("comment_karma", 0),
				"link_karma": d.get("link_karma", 0),
				"created_utc": d.get("created_utc"),
			}
		})
	except Exception as e:
		frappe.log_error(f"Reddit Error (User Info): {str(e)}", "Reddit Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})
