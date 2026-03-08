import json
import os

import requests

BASE = "https://api.notion.com/v1"
VERSION = "2022-06-28"


def _headers():
	key = os.getenv("NOTION_API_KEY")
	if not key:
		raise ValueError("NOTION_API_KEY environment variable is not set")
	return {
		"Authorization": f"Bearer {key}",
		"Notion-Version": VERSION,
		"Content-Type": "application/json",
	}


def handle_create_page(**kwargs):
	"""Create a new page in a Notion database."""
	try:
		db_id = kwargs.get("database_id") or os.getenv("NOTION_DATABASE_ID")
		if not db_id:
			return json.dumps({"error": "database_id is required"})

		properties = {"Name": {"title": [{"text": {"content": kwargs["title"]}}]}}
		if "tag" in kwargs:
			properties["Tag"] = {"select": {"name": kwargs["tag"]}}

		children = []
		if "content" in kwargs:
			children.append({
				"object": "block",
				"type": "paragraph",
				"paragraph": {"rich_text": [{"type": "text", "text": {"content": kwargs["content"]}}]},
			})

		resp = requests.post(
			f"{BASE}/pages",
			headers=_headers(),
			json={"parent": {"database_id": db_id}, "properties": properties, "children": children},
			timeout=30,
		)
		resp.raise_for_status()
		page = resp.json()
		return json.dumps({"page_id": page["id"], "url": page.get("url", ""), "title": kwargs["title"]})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_update_page(**kwargs):
	"""Append content to an existing Notion page."""
	try:
		resp = requests.patch(
			f"{BASE}/blocks/{kwargs['page_id']}/children",
			headers=_headers(),
			json={
				"children": [
					{
						"object": "block",
						"type": "paragraph",
						"paragraph": {"rich_text": [{"type": "text", "text": {"content": kwargs["content"]}}]},
					}
				]
			},
			timeout=30,
		)
		resp.raise_for_status()
		return json.dumps({"ok": True, "page_id": kwargs["page_id"]})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_search_pages(**kwargs):
	"""Search for pages in a Notion database by tag or query."""
	try:
		db_id = kwargs.get("database_id") or os.getenv("NOTION_DATABASE_ID")
		if not db_id:
			return json.dumps({"error": "database_id is required"})

		payload = {}
		if "tag" in kwargs:
			payload["filter"] = {"property": "Tag", "select": {"equals": kwargs["tag"]}}

		resp = requests.post(f"{BASE}/databases/{db_id}/query", headers=_headers(), json=payload, timeout=30)
		resp.raise_for_status()
		data = resp.json()

		pages = []
		for p in data.get("results", []):
			title = "Untitled"
			title_prop = p.get("properties", {}).get("Name", {}).get("title", [])
			if title_prop:
				title = title_prop[0].get("text", {}).get("content", "Untitled")
			pages.append({"page_id": p["id"], "title": title, "url": p.get("url", "")})

		return json.dumps({"count": len(pages), "pages": pages})
	except Exception as e:
		return json.dumps({"error": str(e)})
