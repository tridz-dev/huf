import json
import os

import requests

BASE = "https://api.github.com"


def _headers():
	token = os.getenv("GITHUB_ACCESS_TOKEN")
	if not token:
		raise ValueError("GITHUB_ACCESS_TOKEN environment variable is not set")
	return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


def handle_list_repos(**kwargs):
	"""List repositories for the authenticated user."""
	try:
		resp = requests.get(f"{BASE}/user/repos", headers=_headers(), params={"per_page": 30, "sort": "updated"}, timeout=30)
		resp.raise_for_status()
		repos = [
			{"name": r["full_name"], "description": r.get("description", ""), "url": r["html_url"], "stars": r.get("stargazers_count", 0)}
			for r in resp.json()
		]
		return json.dumps({"count": len(repos), "repositories": repos})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_get_repo(**kwargs):
	"""Get details of a GitHub repository."""
	try:
		resp = requests.get(f"{BASE}/repos/{kwargs['repo_name']}", headers=_headers(), timeout=30)
		resp.raise_for_status()
		r = resp.json()
		return json.dumps({
			"name": r["full_name"],
			"description": r.get("description", ""),
			"language": r.get("language", ""),
			"stars": r.get("stargazers_count", 0),
			"forks": r.get("forks_count", 0),
			"open_issues": r.get("open_issues_count", 0),
			"url": r["html_url"],
		})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_create_issue(**kwargs):
	"""Create a new issue in a GitHub repository."""
	try:
		payload = {"title": kwargs["title"]}
		if "body" in kwargs:
			payload["body"] = kwargs["body"]
		resp = requests.post(f"{BASE}/repos/{kwargs['repo_name']}/issues", headers=_headers(), json=payload, timeout=30)
		resp.raise_for_status()
		issue = resp.json()
		return json.dumps({"number": issue["number"], "url": issue["html_url"], "title": issue["title"]})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_create_pull_request(**kwargs):
	"""Create a pull request in a GitHub repository."""
	try:
		payload = {
			"title": kwargs["title"],
			"body": kwargs.get("body", ""),
			"head": kwargs["head"],
			"base": kwargs["base"],
		}
		resp = requests.post(f"{BASE}/repos/{kwargs['repo_name']}/pulls", headers=_headers(), json=payload, timeout=30)
		resp.raise_for_status()
		pr = resp.json()
		return json.dumps({"number": pr["number"], "url": pr["html_url"], "title": pr["title"]})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_get_file_content(**kwargs):
	"""Get file content from a GitHub repository."""
	try:
		resp = requests.get(
			f"{BASE}/repos/{kwargs['repo_name']}/contents/{kwargs['path']}",
			headers=_headers(),
			timeout=30,
		)
		resp.raise_for_status()
		data = resp.json()
		import base64
		content = base64.b64decode(data.get("content", "")).decode("utf-8") if data.get("content") else ""
		return json.dumps({"path": data.get("path", ""), "sha": data.get("sha", ""), "content": content[:10000]})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_search_code(**kwargs):
	"""Search code across GitHub repositories."""
	try:
		resp = requests.get(f"{BASE}/search/code", headers=_headers(), params={"q": kwargs["query"]}, timeout=30)
		resp.raise_for_status()
		items = [
			{"name": i["name"], "path": i["path"], "repository": i["repository"]["full_name"], "url": i["html_url"]}
			for i in resp.json().get("items", [])[:20]
		]
		return json.dumps({"count": len(items), "results": items})
	except Exception as e:
		return json.dumps({"error": str(e)})
