import json
import frappe
import requests

BASE = "https://hacker-news.firebaseio.com/v0"


def handle_get_top_stories(**kwargs):
	"""Get top stories from Hacker News."""
	try:
		num = int(kwargs.get("num_stories", 10))
		resp = requests.get(f"{BASE}/topstories.json", timeout=15)
		resp.raise_for_status()
		ids = resp.json()[:num]

		stories = []
		for sid in ids:
			sr = requests.get(f"{BASE}/item/{sid}.json", timeout=10)
			if sr.ok:
				s = sr.json()
				if s:
					stories.append({
						"id": s.get("id"),
						"title": s.get("title", ""),
						"url": s.get("url", ""),
						"score": s.get("score", 0),
						"by": s.get("by", ""),
					})
		return json.dumps({
			"success": True,
			"count": len(stories),
			"results": stories
		})
	except Exception as e:
		frappe.log_error(f"Hacker News Error (Top Stories): {str(e)}", "HackerNews Tool")
		return json.dumps({"success": False, "error": str(e)})


def handle_get_user(**kwargs):
	"""Get details of a Hacker News user."""
	try:
		username = kwargs.get("username")
		if not username:
			return json.dumps({"success": False, "error": "Username is required"})
			
		resp = requests.get(f"{BASE}/user/{username}.json", timeout=15)
		resp.raise_for_status()
		user = resp.json()
		if not user:
			return json.dumps({"success": False, "error": "User not found"})
			
		return json.dumps({
			"success": True,
			"results": {
				"id": user.get("id"),
				"karma": user.get("karma", 0),
				"about": user.get("about", ""),
				"created": user.get("created"),
			}
		})
	except Exception as e:
		frappe.log_error(f"Hacker News Error (Get User): {str(e)}", "HackerNews Tool")
		return json.dumps({"success": False, "error": str(e)})
