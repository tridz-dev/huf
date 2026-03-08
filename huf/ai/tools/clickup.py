import json
import os

import requests

BASE = "https://api.clickup.com/api/v2"


def _headers():
	key = os.getenv("CLICKUP_API_KEY")
	if not key:
		raise ValueError("CLICKUP_API_KEY environment variable is not set")
	return {"Authorization": key}


def _space_id():
	sid = os.getenv("CLICKUP_SPACE_ID")
	if not sid:
		raise ValueError("CLICKUP_SPACE_ID environment variable is not set")
	return sid


def _req(method, endpoint, params=None, data=None):
	resp = requests.request(method, f"{BASE}/{endpoint}", headers=_headers(), params=params, json=data, timeout=30)
	resp.raise_for_status()
	return resp.json() if resp.text else {}


def handle_list_spaces(**kwargs):
	"""List all spaces in the ClickUp workspace."""
	try:
		data = _req("GET", f"team/{_space_id()}/space")
		return json.dumps({"spaces": data.get("spaces", [])})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_list_lists(**kwargs):
	"""List all lists in a ClickUp space."""
	try:
		data = _req("GET", f"space/{kwargs['space_id']}/list")
		return json.dumps({"lists": data.get("lists", [])})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_get_task(**kwargs):
	"""Get details of a ClickUp task."""
	try:
		data = _req("GET", f"task/{kwargs['task_id']}")
		return json.dumps(data)
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_create_task(**kwargs):
	"""Create a new task in a ClickUp list."""
	try:
		payload = {"name": kwargs["task_name"], "description": kwargs.get("description", "")}
		data = _req("POST", f"list/{kwargs['list_id']}/task", data=payload)
		return json.dumps(data)
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_update_task(**kwargs):
	"""Update a ClickUp task."""
	try:
		payload = {}
		if "name" in kwargs:
			payload["name"] = kwargs["name"]
		if "description" in kwargs:
			payload["description"] = kwargs["description"]
		if "status" in kwargs:
			payload["status"] = kwargs["status"]
		data = _req("PUT", f"task/{kwargs['task_id']}", data=payload)
		return json.dumps(data)
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_delete_task(**kwargs):
	"""Delete a ClickUp task."""
	try:
		_req("DELETE", f"task/{kwargs['task_id']}")
		return json.dumps({"ok": True, "task_id": kwargs["task_id"]})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_list_tasks(**kwargs):
	"""List all tasks in a ClickUp list."""
	try:
		data = _req("GET", f"list/{kwargs['list_id']}/task")
		return json.dumps({"tasks": data.get("tasks", [])})
	except Exception as e:
		return json.dumps({"error": str(e)})
