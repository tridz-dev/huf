"""
ClickUp integration tools for task listing, retrieval, and creation.
Uses HUF Integration Settings for ClickUp credentials (api_key).
"""

import json

import frappe
import requests

from huf.ai.tools.credentials import require_credential, update_last_error

logger = frappe.logger("huf")

SERVICE_NAME = "clickup"
CLICKUP_API_BASE = "https://api.clickup.com/api/v2"


def _get_clickup_headers():
	api_key = require_credential(SERVICE_NAME, "api_key")
	return {"Authorization": api_key, "Content-Type": "application/json"}


def _make_clickup_request(method: str, endpoint: str, json_data=None, params=None):
	response = requests.request(
		method,
		f"{CLICKUP_API_BASE}/{endpoint}",
		headers=_get_clickup_headers(),
		json=json_data,
		params=params,
		timeout=30,
	)
	response.raise_for_status()
	return response.json() if response.text else {}


def handle_list_tasks(**kwargs) -> str:
	"""List tasks in a ClickUp list."""
	try:
		list_id = kwargs.get("list_id")
		if not list_id:
			return json.dumps({"success": False, "error": "list_id is required"}, default=str)

		include_closed = bool(kwargs.get("include_closed"))
		data = _make_clickup_request(
			"GET",
			f"list/{list_id}/task",
			params={"archived": "false", "include_closed": str(include_closed).lower()},
		)

		tasks = []
		for task in data.get("tasks", []):
			tasks.append(
				{
					"id": task.get("id"),
					"name": task.get("name"),
					"status": (task.get("status") or {}).get("status"),
					"assignees": [a.get("username") for a in task.get("assignees", [])],
					"due_date": task.get("due_date"),
					"url": task.get("url"),
				}
			)

		return json.dumps({"success": True, "count": len(tasks), "results": tasks})
	except Exception as e:
		error_msg = f"ClickUp List Tasks Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_get_task(**kwargs) -> str:
	"""Get details of a ClickUp task by ID."""
	try:
		task_id = kwargs.get("task_id")
		if not task_id:
			return json.dumps({"success": False, "error": "task_id is required"}, default=str)

		data = _make_clickup_request("GET", f"task/{task_id}")

		task_data = {
			"id": data.get("id"),
			"name": data.get("name"),
			"description": data.get("description"),
			"status": (data.get("status") or {}).get("status"),
			"assignees": [a.get("username") for a in data.get("assignees", [])],
			"priority": (data.get("priority") or {}).get("priority") if data.get("priority") else None,
			"due_date": data.get("due_date"),
			"url": data.get("url"),
		}

		return json.dumps({"success": True, "results": task_data})
	except Exception as e:
		error_msg = f"ClickUp Get Task Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_create_task(**kwargs) -> str:
	"""Create a task in a ClickUp list."""
	try:
		list_id = kwargs.get("list_id")
		name = kwargs.get("name")
		if not all([list_id, name]):
			return json.dumps({"success": False, "error": "list_id and name are required"}, default=str)

		payload = {"name": name}
		description = kwargs.get("description")
		if description:
			payload["description"] = description

		data = _make_clickup_request("POST", f"list/{list_id}/task", json_data=payload)

		return json.dumps(
			{
				"success": True,
				"results": {"id": data.get("id"), "name": data.get("name"), "url": data.get("url")},
			}
		)
	except Exception as e:
		error_msg = f"ClickUp Create Task Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)
