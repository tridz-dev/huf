"""
Trello integration tools for board/card listing and card creation.
Uses HUF Integration Settings for Trello credentials (api_key, token).
"""

import json

import frappe
import requests

from huf.ai.tools.credentials import require_credential, update_last_error

logger = frappe.logger("huf")

SERVICE_NAME = "trello"
TRELLO_API_BASE = "https://api.trello.com/1"


def _auth_params():
	return {
		"key": require_credential(SERVICE_NAME, "api_key"),
		"token": require_credential(SERVICE_NAME, "token"),
	}


def _make_trello_request(method: str, endpoint: str, params=None):
	all_params = _auth_params()
	all_params.update(params or {})

	response = requests.request(method, f"{TRELLO_API_BASE}/{endpoint}", params=all_params, timeout=30)
	response.raise_for_status()
	return response.json() if response.text else {}


def handle_list_boards(**kwargs) -> str:
	"""List Trello boards for the authenticated user."""
	try:
		data = _make_trello_request("GET", "members/me/boards", params={"fields": "name,url,closed"})

		boards = [
			{
				"id": board.get("id"),
				"name": board.get("name"),
				"url": board.get("url"),
				"closed": board.get("closed"),
			}
			for board in data
		]

		return json.dumps({"success": True, "count": len(boards), "results": boards})
	except Exception as e:
		error_msg = f"Trello List Boards Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_list_cards(**kwargs) -> str:
	"""List cards on a Trello board."""
	try:
		board_id = kwargs.get("board_id")
		if not board_id:
			return json.dumps({"success": False, "error": "board_id is required"}, default=str)

		data = _make_trello_request(
			"GET", f"boards/{board_id}/cards", params={"fields": "name,url,due,idList,closed"}
		)

		cards = [
			{
				"id": card.get("id"),
				"name": card.get("name"),
				"list_id": card.get("idList"),
				"due": card.get("due"),
				"url": card.get("url"),
				"closed": card.get("closed"),
			}
			for card in data
		]

		return json.dumps({"success": True, "count": len(cards), "results": cards})
	except Exception as e:
		error_msg = f"Trello List Cards Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_create_card(**kwargs) -> str:
	"""Create a card on a Trello list."""
	try:
		list_id = kwargs.get("list_id")
		name = kwargs.get("name")
		if not all([list_id, name]):
			return json.dumps({"success": False, "error": "list_id and name are required"}, default=str)

		params = {"idList": list_id, "name": name}
		description = kwargs.get("description")
		if description:
			params["desc"] = description

		data = _make_trello_request("POST", "cards", params=params)

		return json.dumps(
			{
				"success": True,
				"results": {"id": data.get("id"), "name": data.get("name"), "url": data.get("url")},
			}
		)
	except Exception as e:
		error_msg = f"Trello Create Card Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)
