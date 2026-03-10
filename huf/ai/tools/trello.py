import json
import frappe
from huf.ai.tools.credentials import require_credential, update_last_error
import requests

BASE = "https://api.trello.com/1"


def _params():
	service_name = "trello"
	key = require_credential(service_name, "api_key")
	token = require_credential(service_name, "api_secret")
	return {"key": key, "token": token}


def handle_list_boards(**kwargs):
	"""List all Trello boards for the authenticated user."""
	service_name = "trello"
	try:
		resp = requests.get(f"{BASE}/members/me/boards", params=_params(), timeout=30)
		resp.raise_for_status()
		boards = [{"id": b["id"], "name": b["name"], "url": b["url"]} for b in resp.json()]
		return json.dumps({
			"success": True, 
			"count": len(boards), 
			"results": boards
		})
	except Exception as e:
		frappe.log_error(f"Trello Error (List Boards): {str(e)}", "Trello Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_get_board_lists(**kwargs):
	"""Get all lists on a Trello board."""
	service_name = "trello"
	try:
		board_id = kwargs.get("board_id")
		if not board_id:
			return json.dumps({"success": False, "error": "board_id is required"})

		resp = requests.get(f"{BASE}/boards/{board_id}/lists", params=_params(), timeout=30)
		resp.raise_for_status()
		lists = [{"id": l["id"], "name": l["name"]} for l in resp.json()]
		return json.dumps({
			"success": True, 
			"results": lists
		})
	except Exception as e:
		frappe.log_error(f"Trello Error (Get Board Lists): {str(e)}", "Trello Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_get_cards(**kwargs):
	"""Get all cards in a Trello list."""
	service_name = "trello"
	try:
		list_id = kwargs.get("list_id")
		if not list_id:
			return json.dumps({"success": False, "error": "list_id is required"})

		resp = requests.get(f"{BASE}/lists/{list_id}/cards", params=_params(), timeout=30)
		resp.raise_for_status()
		cards = [{"id": c["id"], "name": c["name"], "desc": c.get("desc", ""), "url": c["url"]} for c in resp.json()]
		return json.dumps({
			"success": True, 
			"results": cards
		})
	except Exception as e:
		frappe.log_error(f"Trello Error (Get Cards): {str(e)}", "Trello Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_create_card(**kwargs):
	"""Create a new card in a Trello list."""
	service_name = "trello"
	try:
		list_id = kwargs.get("list_id")
		name = kwargs.get("name")
		if not all([list_id, name]):
			return json.dumps({"success": False, "error": "list_id and name are required"})

		params = {**_params(), "idList": list_id, "name": name}
		if "description" in kwargs:
			params["desc"] = kwargs["description"]
		resp = requests.post(f"{BASE}/cards", params=params, timeout=30)
		resp.raise_for_status()
		card = resp.json()
		return json.dumps({
			"success": True, 
			"results": {"id": card["id"], "name": card["name"], "url": card["url"]}
		})
	except Exception as e:
		frappe.log_error(f"Trello Error (Create Card): {str(e)}", "Trello Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_create_board(**kwargs):
	"""Create a new Trello board."""
	service_name = "trello"
	try:
		name = kwargs.get("name")
		if not name:
			return json.dumps({"success": False, "error": "name is required"})

		params = {**_params(), "name": name}
		if kwargs.get("default_lists") is not None:
			params["defaultLists"] = str(kwargs["default_lists"]).lower()
		resp = requests.post(f"{BASE}/boards", params=params, timeout=30)
		resp.raise_for_status()
		board = resp.json()
		return json.dumps({
			"success": True, 
			"results": {"id": board["id"], "name": board["name"], "url": board["url"]}
		})
	except Exception as e:
		frappe.log_error(f"Trello Error (Create Board): {str(e)}", "Trello Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_move_card(**kwargs):
	"""Move a Trello card to a different list."""
	service_name = "trello"
	try:
		card_id = kwargs.get("card_id")
		list_id = kwargs.get("list_id")
		if not all([card_id, list_id]):
			return json.dumps({"success": False, "error": "card_id and list_id are required"})

		params = {**_params(), "idList": list_id}
		resp = requests.put(f"{BASE}/cards/{card_id}", params=params, timeout=30)
		resp.raise_for_status()
		return json.dumps({
			"success": True, 
			"results": {"card_id": card_id, "new_list_id": list_id}
		})
	except Exception as e:
		frappe.log_error(f"Trello Error (Move Card): {str(e)}", "Trello Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})
