# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""Tests for the Trello integration tools. All HTTP calls are mocked."""

import json
import unittest
from unittest.mock import MagicMock, patch

from huf.ai.tools import trello
from huf.ai.tools._registry import ALL_INTEGRATION_TOOLS, TRELLO_TOOLS

MODULE = "huf.ai.tools.trello"


def _mock_response(payload):
	resp = MagicMock()
	resp.json.return_value = payload
	resp.text = json.dumps(payload)
	resp.raise_for_status = MagicMock()
	return resp


def _result(raw):
	return json.loads(raw)


def _fake_credential(service, key):
	return {"api_key": "key-1", "token": "token-1"}[key]


class TestListBoards(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", side_effect=_fake_credential)
	@patch(f"{MODULE}.requests.request")
	def test_lists_boards(self, mock_request, _cred, _err):
		mock_request.return_value = _mock_response(
			[{"id": "board1", "name": "Roadmap", "url": "https://trello.com/b/board1", "closed": False}]
		)

		out = _result(trello.handle_list_boards())

		self.assertTrue(out["success"])
		self.assertEqual(out["results"][0]["name"], "Roadmap")

		params = mock_request.call_args.kwargs["params"]
		self.assertEqual(params["key"], "key-1")
		self.assertEqual(params["token"], "token-1")


class TestListCards(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", side_effect=_fake_credential)
	@patch(f"{MODULE}.requests.request")
	def test_lists_cards(self, mock_request, _cred, _err):
		mock_request.return_value = _mock_response(
			[{"id": "card1", "name": "Task 1", "idList": "list1", "due": None, "url": "https://trello.com/c/card1", "closed": False}]
		)

		out = _result(trello.handle_list_cards(board_id="board1"))

		self.assertTrue(out["success"])
		self.assertEqual(out["results"][0]["id"], "card1")

	def test_requires_board_id(self):
		out = _result(trello.handle_list_cards())
		self.assertFalse(out["success"])
		self.assertIn("board_id", out["error"])


class TestCreateCard(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", side_effect=_fake_credential)
	@patch(f"{MODULE}.requests.request")
	def test_creates_card(self, mock_request, _cred, _err):
		mock_request.return_value = _mock_response({"id": "card2", "name": "New card", "url": "https://trello.com/c/card2"})

		out = _result(trello.handle_create_card(list_id="list1", name="New card", description="desc"))

		self.assertTrue(out["success"])
		self.assertEqual(out["results"]["id"], "card2")

		params = mock_request.call_args.kwargs["params"]
		self.assertEqual(params["idList"], "list1")
		self.assertEqual(params["desc"], "desc")

	def test_requires_list_id_and_name(self):
		out = _result(trello.handle_create_card(list_id="list1"))
		self.assertFalse(out["success"])
		self.assertIn("name", out["error"])


class TestRegistry(unittest.TestCase):
	def test_all_tools_registered(self):
		expected = {
			"trello_list_boards": "handle_list_boards",
			"trello_list_cards": "handle_list_cards",
			"trello_create_card": "handle_create_card",
		}
		by_name = {t["tool_name"]: t for t in TRELLO_TOOLS}
		self.assertEqual(set(by_name), set(expected))
		for tool_name, handler in expected.items():
			self.assertEqual(by_name[tool_name]["function_path"], f"huf.ai.tools.trello.{handler}")
			self.assertTrue(callable(getattr(trello, handler)))

	def test_registered_in_all_integration_tools(self):
		by_name = {t["tool_name"]: t for t in ALL_INTEGRATION_TOOLS}
		for tool in TRELLO_TOOLS:
			self.assertIn(tool["tool_name"], by_name)
			self.assertEqual(by_name[tool["tool_name"]]["service"], "trello")


if __name__ == "__main__":
	unittest.main()
