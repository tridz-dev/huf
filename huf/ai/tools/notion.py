"""
Notion integration tools for database queries, page retrieval, and page creation.
Uses HUF Integration Settings for Notion credentials (api_key, database_id).
"""

import json

import frappe
import requests

from huf.ai.tools.credentials import get_credential, require_credential, update_last_error

logger = frappe.logger("huf")

SERVICE_NAME = "notion"
NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _get_notion_headers():
	api_key = require_credential(SERVICE_NAME, "api_key")
	return {
		"Authorization": f"Bearer {api_key}",
		"Notion-Version": NOTION_VERSION,
		"Content-Type": "application/json",
	}


def _make_notion_request(method: str, endpoint: str, json_data=None):
	response = requests.request(
		method, f"{NOTION_API_BASE}/{endpoint}", headers=_get_notion_headers(), json=json_data, timeout=30
	)
	response.raise_for_status()
	return response.json() if response.text else {}


def _resolve_database_id(kwargs: dict) -> str:
	return kwargs.get("database_id") or get_credential(SERVICE_NAME, "database_id")


def _extract_title(properties: dict) -> str | None:
	"""Best-effort extraction of a page's title from its properties dict."""
	for prop in properties.values():
		if prop.get("type") == "title":
			title_parts = prop.get("title", [])
			if title_parts:
				return "".join(part.get("plain_text", "") for part in title_parts)
	return None


def handle_query_database(**kwargs) -> str:
	"""Query a Notion database's rows."""
	try:
		database_id = _resolve_database_id(kwargs)
		if not database_id:
			return json.dumps(
				{"success": False, "error": "database_id is required (or set NOTION_DATABASE_ID)"},
				default=str,
			)

		page_size = int(kwargs.get("page_size") or 20)
		data = _make_notion_request(
			"POST", f"databases/{database_id}/query", json_data={"page_size": page_size}
		)

		pages = []
		for page in data.get("results", []):
			pages.append(
				{
					"id": page.get("id"),
					"title": _extract_title(page.get("properties", {})),
					"url": page.get("url"),
					"created_time": page.get("created_time"),
					"last_edited_time": page.get("last_edited_time"),
				}
			)

		return json.dumps({"success": True, "count": len(pages), "results": pages})
	except Exception as e:
		error_msg = f"Notion Query Database Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_get_page(**kwargs) -> str:
	"""Get a Notion page's properties by ID."""
	try:
		page_id = kwargs.get("page_id")
		if not page_id:
			return json.dumps({"success": False, "error": "page_id is required"}, default=str)

		data = _make_notion_request("GET", f"pages/{page_id}")

		page_data = {
			"id": data.get("id"),
			"title": _extract_title(data.get("properties", {})),
			"url": data.get("url"),
			"archived": data.get("archived"),
			"created_time": data.get("created_time"),
			"last_edited_time": data.get("last_edited_time"),
		}

		return json.dumps({"success": True, "results": page_data})
	except Exception as e:
		error_msg = f"Notion Get Page Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_create_page(**kwargs) -> str:
	"""Create a page (row) in a Notion database with a title property."""
	try:
		title = kwargs.get("title")
		if not title:
			return json.dumps({"success": False, "error": "title is required"}, default=str)

		database_id = _resolve_database_id(kwargs)
		if not database_id:
			return json.dumps(
				{"success": False, "error": "database_id is required (or set NOTION_DATABASE_ID)"},
				default=str,
			)

		title_property = kwargs.get("title_property") or "Name"
		payload = {
			"parent": {"database_id": database_id},
			"properties": {title_property: {"title": [{"text": {"content": title}}]}},
		}

		data = _make_notion_request("POST", "pages", json_data=payload)

		return json.dumps({"success": True, "results": {"id": data.get("id"), "url": data.get("url")}})
	except Exception as e:
		error_msg = f"Notion Create Page Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)
