import json

from huf.ai.tools.credentials import require_credential
import requests

BASE = "https://api.trello.com/1"


def _params():
	key = require_credential("trello", "api_key")
	token = require_credential("trello", "api_secret")
	return {"key": key, "token": token}


def handle_list_boards(**kwargs):
	"""List all Trello boards for the authenticated user."""
	try:
		resp = requests.get(f"{BASE}/members/me/boards", params=_params(), timeout=30)
		resp.raise_for_status()
		boards = [{"id": b["id"], "name": b["name"], "url": b["url"]} for b in resp.json()]
		return json.dumps({"count": len(boards), "boards": boards})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_get_board_lists(**kwargs):
	"""Get all lists on a Trello board."""
	try:
		resp = requests.get(f"{BASE}/boards/{kwargs['board_id']}/lists", params=_params(), timeout=30)
		resp.raise_for_status()
		lists = [{"id": l["id"], "name": l["name"]} for l in resp.json()]
		return json.dumps({"lists": lists})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_get_cards(**kwargs):
	"""Get all cards in a Trello list."""
	try:
		resp = requests.get(f"{BASE}/lists/{kwargs['list_id']}/cards", params=_params(), timeout=30)
		resp.raise_for_status()
		cards = [{"id": c["id"], "name": c["name"], "desc": c.get("desc", ""), "url": c["url"]} for c in resp.json()]
		return json.dumps({"cards": cards})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_create_card(**kwargs):
	"""Create a new card in a Trello list."""
	try:
		params = {**_params(), "idList": kwargs["list_id"], "name": kwargs["name"]}
		if "description" in kwargs:
			params["desc"] = kwargs["description"]
		resp = requests.post(f"{BASE}/cards", params=params, timeout=30)
		resp.raise_for_status()
		card = resp.json()
		return json.dumps({"id": card["id"], "name": card["name"], "url": card["url"]})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_create_board(**kwargs):
	"""Create a new Trello board."""
	try:
		params = {**_params(), "name": kwargs["name"]}
		if kwargs.get("default_lists") is not None:
			params["defaultLists"] = str(kwargs["default_lists"]).lower()
		resp = requests.post(f"{BASE}/boards", params=params, timeout=30)
		resp.raise_for_status()
		board = resp.json()
		return json.dumps({"id": board["id"], "name": board["name"], "url": board["url"]})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_move_card(**kwargs):
	"""Move a Trello card to a different list."""
	try:
		params = {**_params(), "idList": kwargs["list_id"]}
		resp = requests.put(f"{BASE}/cards/{kwargs['card_id']}", params=params, timeout=30)
		resp.raise_for_status()
		return json.dumps({"ok": True, "card_id": kwargs["card_id"], "new_list_id": kwargs["list_id"]})
	except Exception as e:
		return json.dumps({"error": str(e)})
