"""
Notion integration tools for search, databases, pages, and blocks.
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


def _format_notion_error(response: requests.Response) -> str:
	try:
		payload = response.json()
	except ValueError:
		return response.text or f"HTTP {response.status_code}"

	if isinstance(payload, dict):
		message = payload.get("message")
		if message:
			return str(message)

	return response.text or f"HTTP {response.status_code}"


def _make_notion_request(method: str, endpoint: str, json_data=None, params=None):
	response = requests.request(
		method,
		f"{NOTION_API_BASE}/{endpoint}",
		headers=_get_notion_headers(),
		json=json_data,
		params=params,
		timeout=30,
	)
	if not response.ok:
		raise ValueError(f"Notion API error ({response.status_code}): {_format_notion_error(response)}")
	return response.json() if response.text else {}


def _parse_optional_json(value, field_name: str):
	if value in (None, ""):
		return None
	if isinstance(value, (dict, list)):
		return value
	try:
		return json.loads(value)
	except (TypeError, json.JSONDecodeError) as exc:
		raise ValueError(f"{field_name} must be valid JSON") from exc


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


def _extract_database_title(data: dict) -> str | None:
	title_parts = (data.get("title") or []) if isinstance(data.get("title"), list) else []
	if title_parts:
		return "".join(part.get("plain_text", "") for part in title_parts)
	return _extract_title(data.get("properties", {}))


def _summarize_search_result(item: dict) -> dict:
	object_type = item.get("object")
	summary = {
		"id": item.get("id"),
		"object": object_type,
		"url": item.get("url"),
		"archived": item.get("archived"),
		"last_edited_time": item.get("last_edited_time"),
	}
	if object_type == "database":
		summary["title"] = _extract_database_title(item)
	elif object_type == "page":
		summary["title"] = _extract_title(item.get("properties", {}))
	return summary


def _summarize_database_schema(data: dict) -> dict:
	properties = {}
	for name, prop in (data.get("properties") or {}).items():
		prop_type = prop.get("type")
		entry = {"type": prop_type}
		if prop_type == "select":
			entry["options"] = [opt.get("name") for opt in (prop.get("select") or {}).get("options", [])]
		elif prop_type == "multi_select":
			entry["options"] = [opt.get("name") for opt in (prop.get("multi_select") or {}).get("options", [])]
		elif prop_type == "status":
			status = prop.get("status") or {}
			entry["options"] = [opt.get("name") for opt in status.get("options", [])]
		properties[name] = entry

	return {
		"id": data.get("id"),
		"title": _extract_database_title(data),
		"url": data.get("url"),
		"properties": properties,
	}


def _extract_rich_text(rich_text: list) -> str:
	return "".join(part.get("plain_text", "") for part in rich_text or [])


def _extract_block_text(block: dict) -> str:
	block_type = block.get("type")
	if not block_type:
		return ""

	payload = block.get(block_type) or {}
	if block_type in {"paragraph", "heading_1", "heading_2", "heading_3", "quote", "callout"}:
		return _extract_rich_text(payload.get("rich_text", []))
	if block_type in {"bulleted_list_item", "numbered_list_item", "to_do"}:
		prefix = "[ ] " if block_type == "to_do" and not payload.get("checked") else ""
		if block_type == "to_do" and payload.get("checked"):
			prefix = "[x] "
		return prefix + _extract_rich_text(payload.get("rich_text", []))
	if block_type == "code":
		return _extract_rich_text(payload.get("rich_text", []))
	if block_type == "divider":
		return "---"
	return ""


def handle_search(**kwargs) -> str:
	"""Search Notion pages and databases by title."""
	try:
		payload = {"page_size": int(kwargs.get("page_size") or 20)}
		query = kwargs.get("query")
		if query:
			payload["query"] = query

		object_type = kwargs.get("object_type")
		if object_type:
			payload["filter"] = {"property": "object", "value": object_type}

		data = _make_notion_request("POST", "search", json_data=payload)
		results = [_summarize_search_result(item) for item in data.get("results", [])]

		return json.dumps(
			{
				"success": True,
				"count": len(results),
				"has_more": data.get("has_more", False),
				"next_cursor": data.get("next_cursor"),
				"results": results,
			},
			default=str,
		)
	except Exception as e:
		error_msg = f"Notion Search Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_list_databases(**kwargs) -> str:
	"""List Notion databases the integration can access."""
	try:
		payload = {
			"page_size": int(kwargs.get("page_size") or 20),
			"filter": {"property": "object", "value": "database"},
		}
		query = kwargs.get("query")
		if query:
			payload["query"] = query

		data = _make_notion_request("POST", "search", json_data=payload)
		databases = [
			{
				"id": item.get("id"),
				"title": _extract_database_title(item),
				"url": item.get("url"),
				"last_edited_time": item.get("last_edited_time"),
			}
			for item in data.get("results", [])
			if item.get("object") == "database"
		]

		return json.dumps(
			{
				"success": True,
				"count": len(databases),
				"has_more": data.get("has_more", False),
				"next_cursor": data.get("next_cursor"),
				"results": databases,
			},
			default=str,
		)
	except Exception as e:
		error_msg = f"Notion List Databases Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_get_database(**kwargs) -> str:
	"""Get a Notion database schema and property definitions."""
	try:
		database_id = _resolve_database_id(kwargs)
		if not database_id:
			return json.dumps(
				{"success": False, "error": "database_id is required (or set NOTION_DATABASE_ID)"},
				default=str,
			)

		data = _make_notion_request("GET", f"databases/{database_id}")
		return json.dumps({"success": True, "results": _summarize_database_schema(data)}, default=str)
	except Exception as e:
		error_msg = f"Notion Get Database Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_query_database(**kwargs) -> str:
	"""Query a Notion database's rows."""
	try:
		database_id = _resolve_database_id(kwargs)
		if not database_id:
			return json.dumps(
				{"success": False, "error": "database_id is required (or set NOTION_DATABASE_ID)"},
				default=str,
			)

		payload = {"page_size": int(kwargs.get("page_size") or 20)}
		filter_obj = _parse_optional_json(kwargs.get("filter"), "filter")
		if filter_obj:
			payload["filter"] = filter_obj
		sorts = _parse_optional_json(kwargs.get("sorts"), "sorts")
		if sorts:
			payload["sorts"] = sorts

		data = _make_notion_request("POST", f"databases/{database_id}/query", json_data=payload)

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

		return json.dumps(
			{
				"success": True,
				"count": len(pages),
				"has_more": data.get("has_more", False),
				"next_cursor": data.get("next_cursor"),
				"results": pages,
			},
			default=str,
		)
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
			"properties": data.get("properties", {}),
		}

		return json.dumps({"success": True, "results": page_data}, default=str)
	except Exception as e:
		error_msg = f"Notion Get Page Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_get_page_content(**kwargs) -> str:
	"""Get the block content of a Notion page as plain text."""
	try:
		page_id = kwargs.get("page_id")
		if not page_id:
			return json.dumps({"success": False, "error": "page_id is required"}, default=str)

		page_size = int(kwargs.get("page_size") or 50)
		data = _make_notion_request(
			"GET", f"blocks/{page_id}/children", params={"page_size": page_size}
		)

		lines = []
		for block in data.get("results", []):
			text = _extract_block_text(block)
			if text:
				lines.append(text)

		return json.dumps(
			{
				"success": True,
				"count": len(lines),
				"has_more": data.get("has_more", False),
				"next_cursor": data.get("next_cursor"),
				"content": "\n".join(lines),
			},
			default=str,
		)
	except Exception as e:
		error_msg = f"Notion Get Page Content Error: {e!s}"
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

		extra_properties = _parse_optional_json(kwargs.get("properties"), "properties")
		if extra_properties:
			payload["properties"].update(extra_properties)

		data = _make_notion_request("POST", "pages", json_data=payload)

		return json.dumps({"success": True, "results": {"id": data.get("id"), "url": data.get("url")}})
	except Exception as e:
		error_msg = f"Notion Create Page Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_update_page(**kwargs) -> str:
	"""Update properties on an existing Notion page."""
	try:
		page_id = kwargs.get("page_id")
		if not page_id:
			return json.dumps({"success": False, "error": "page_id is required"}, default=str)

		properties = _parse_optional_json(kwargs.get("properties"), "properties")
		if not properties:
			return json.dumps(
				{"success": False, "error": "properties is required (Notion property update JSON)"},
				default=str,
			)

		data = _make_notion_request("PATCH", f"pages/{page_id}", json_data={"properties": properties})

		return json.dumps(
			{
				"success": True,
				"results": {
					"id": data.get("id"),
					"url": data.get("url"),
					"title": _extract_title(data.get("properties", {})),
				},
			},
			default=str,
		)
	except Exception as e:
		error_msg = f"Notion Update Page Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_archive_page(**kwargs) -> str:
	"""Archive (soft-delete) a Notion page."""
	try:
		page_id = kwargs.get("page_id")
		if not page_id:
			return json.dumps({"success": False, "error": "page_id is required"}, default=str)

		data = _make_notion_request("PATCH", f"pages/{page_id}", json_data={"archived": True})

		return json.dumps(
			{
				"success": True,
				"results": {"id": data.get("id"), "archived": data.get("archived", True)},
			},
			default=str,
		)
	except Exception as e:
		error_msg = f"Notion Archive Page Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)
