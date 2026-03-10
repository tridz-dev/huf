import json
import frappe
from huf.ai.tools.credentials import require_credential, update_last_error
import requests

BASE = "https://api.clickup.com/api/v2"


def _headers():
	service_name = "clickup"
	key = require_credential(service_name, "api_key")
	return {"Authorization": key}


def _space_id():
	service_name = "clickup"
	return require_credential(service_name, "space_id")


def _req(method, endpoint, params=None, data=None):
	resp = requests.request(method, f"{BASE}/{endpoint}", headers=_headers(), params=params, json=data, timeout=30)
	resp.raise_for_status()
	return resp.json() if resp.text else {}


def handle_list_spaces(**kwargs):
	"""List all spaces in the ClickUp workspace."""
	service_name = "clickup"
	try:
		data = _req("GET", f"team/{_space_id()}/space")
		spaces = data.get("spaces", [])
		return json.dumps({
			"success": True, 
			"count": len(spaces), 
			"results": spaces
		})
	except Exception as e:
		frappe.log_error(f"ClickUp Error (List Spaces): {str(e)}", "ClickUp Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_list_lists(**kwargs):
	"""List all lists in a ClickUp space."""
	service_name = "clickup"
	try:
		space_id = kwargs.get("space_id")
		if not space_id:
			return json.dumps({"success": False, "error": "space_id is required"})

		data = _req("GET", f"space/{space_id}/list")
		lists = data.get("lists", [])
		return json.dumps({
			"success": True, 
			"count": len(lists), 
			"results": lists
		})
	except Exception as e:
		frappe.log_error(f"ClickUp Error (List Lists): {str(e)}", "ClickUp Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_get_task(**kwargs):
	"""Get details of a ClickUp task."""
	service_name = "clickup"
	try:
		task_id = kwargs.get("task_id")
		if not task_id:
			return json.dumps({"success": False, "error": "task_id is required"})

		data = _req("GET", f"task/{task_id}")
		return json.dumps({
			"success": True, 
			"results": data
		})
	except Exception as e:
		frappe.log_error(f"ClickUp Error (Get Task): {str(e)}", "ClickUp Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_create_task(**kwargs):
	"""Create a new task in a ClickUp list."""
	service_name = "clickup"
	try:
		list_id = kwargs.get("list_id")
		task_name = kwargs.get("task_name")
		if not all([list_id, task_name]):
			return json.dumps({"success": False, "error": "list_id and task_name are required"})

		payload = {"name": task_name, "description": kwargs.get("description", "")}
		data = _req("POST", f"list/{list_id}/task", data=payload)
		return json.dumps({
			"success": True, 
			"results": data
		})
	except Exception as e:
		frappe.log_error(f"ClickUp Error (Create Task): {str(e)}", "ClickUp Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_update_task(**kwargs):
	"""Update a ClickUp task."""
	service_name = "clickup"
	try:
		task_id = kwargs.get("task_id")
		if not task_id:
			return json.dumps({"success": False, "error": "task_id is required"})

		payload = {}
		if "name" in kwargs:
			payload["name"] = kwargs["name"]
		if "description" in kwargs:
			payload["description"] = kwargs["description"]
		if "status" in kwargs:
			payload["status"] = kwargs["status"]
		
		data = _req("PUT", f"task/{task_id}", data=payload)
		return json.dumps({
			"success": True, 
			"results": data
		})
	except Exception as e:
		frappe.log_error(f"ClickUp Error (Update Task): {str(e)}", "ClickUp Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_delete_task(**kwargs):
	"""Delete a ClickUp task."""
	service_name = "clickup"
	try:
		task_id = kwargs.get("task_id")
		if not task_id:
			return json.dumps({"success": False, "error": "task_id is required"})

		_req("DELETE", f"task/{task_id}")
		return json.dumps({"success": True, "results": {"task_id": task_id}})
	except Exception as e:
		frappe.log_error(f"ClickUp Error (Delete Task): {str(e)}", "ClickUp Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_list_tasks(**kwargs):
	"""List all tasks in a ClickUp list."""
	service_name = "clickup"
	try:
		list_id = kwargs.get("list_id")
		if not list_id:
			return json.dumps({"success": False, "error": "list_id is required"})

		data = _req("GET", f"list/{list_id}/task")
		tasks = data.get("tasks", [])
		return json.dumps({
			"success": True, 
			"count": len(tasks), 
			"results": tasks
		})
	except Exception as e:
		frappe.log_error(f"ClickUp Error (List Tasks): {str(e)}", "ClickUp Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})
