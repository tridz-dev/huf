import json
import frappe
from huf.ai.tools.credentials import require_credential, update_last_error
import requests

BASE = "https://api.notion.com/v1"
VERSION = "2022-06-28"


def _headers():
	service_name = "notion"
	key = require_credential(service_name, "api_key")
	return {
		"Authorization": f"Bearer {key}",
		"Notion-Version": VERSION,
		"Content-Type": "application/json",
	}


def handle_create_page(**kwargs):
	"""Create a new page in a Notion database."""
	service_name = "notion"
	try:
		db_id = kwargs.get("database_id")
		title = kwargs.get("title")
		if not all([db_id, title]):
			return json.dumps({"success": False, "error": "database_id and title are required"})

		properties = {"Name": {"title": [{"text": {"content": title}}]}}
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
		return json.dumps({
			"success": True,
			"results": {
				"page_id": page["id"], 
				"url": page.get("url", ""), 
				"title": title
			}
		})
	except Exception as e:
		frappe.log_error(f"Notion Error (Create Page): {str(e)}", "Notion Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_update_page(**kwargs):
	"""Append content to an existing Notion page."""
	service_name = "notion"
	try:
		page_id = kwargs.get("page_id")
		content = kwargs.get("content")
		if not all([page_id, content]):
			return json.dumps({"success": False, "error": "page_id and content are required"})

		resp = requests.patch(
			f"{BASE}/blocks/{page_id}/children",
			headers=_headers(),
			json={
				"children": [
					{
						"object": "block",
						"type": "paragraph",
						"paragraph": {"rich_text": [{"type": "text", "text": {"content": content}}]},
					}
				]
			},
			timeout=30,
		)
		resp.raise_for_status()
		return json.dumps({
			"success": True, 
			"results": {"page_id": page_id}
		})
	except Exception as e:
		frappe.log_error(f"Notion Error (Update Page): {str(e)}", "Notion Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_search_pages(**kwargs):
	"""Search for pages in a Notion database by tag or query."""
	service_name = "notion"
	try:
		db_id = kwargs.get("database_id")
		if not db_id:
			return json.dumps({"success": False, "error": "database_id is required"})

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

		return json.dumps({
			"success": True, 
			"count": len(pages), 
			"results": pages
		})
	except Exception as e:
		frappe.log_error(f"Notion Error (Search): {str(e)}", "Notion Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})
