# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""Tests for the Zendesk integration tools. All HTTP calls are mocked."""

import json
import unittest
from unittest.mock import MagicMock, patch

from huf.ai.tools import zendesk
from huf.ai.tools._registry import ALL_INTEGRATION_TOOLS, ZENDESK_TOOLS

MODULE = "huf.ai.tools.zendesk"


def _mock_response(payload):
	resp = MagicMock()
	resp.json.return_value = payload
	resp.text = json.dumps(payload)
	resp.raise_for_status = MagicMock()
	return resp


def _result(raw):
	return json.loads(raw)


def _fake_credential(service, key):
	return {"username": "bot@example.com", "password": "api-tok", "company_name": "acme"}[key]


class TestListTickets(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", side_effect=_fake_credential)
	@patch(f"{MODULE}.requests.request")
	def test_lists_and_filters_tickets(self, mock_request, _cred, _err):
		mock_request.return_value = _mock_response(
			{
				"tickets": [
					{"id": 1, "subject": "Open one", "status": "open", "priority": "high", "requester_id": 10, "created_at": "x"},
					{"id": 2, "subject": "Solved one", "status": "solved", "priority": "low", "requester_id": 11, "created_at": "y"},
				]
			}
		)

		out = _result(zendesk.handle_list_tickets(status="open"))

		self.assertTrue(out["success"])
		self.assertEqual(out["count"], 1)
		self.assertEqual(out["results"][0]["id"], 1)

		call_args = mock_request.call_args
		self.assertIn("acme.zendesk.com", call_args.args[1])
		self.assertEqual(call_args.kwargs["auth"], ("bot@example.com/token", "api-tok"))


class TestGetTicket(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", side_effect=_fake_credential)
	@patch(f"{MODULE}.requests.request")
	def test_get_ticket(self, mock_request, _cred, _err):
		mock_request.return_value = _mock_response(
			{
				"ticket": {
					"id": 1,
					"subject": "Help",
					"description": "Details",
					"status": "new",
					"priority": "normal",
					"requester_id": 10,
					"assignee_id": None,
					"created_at": "x",
					"updated_at": "y",
				}
			}
		)

		out = _result(zendesk.handle_get_ticket(ticket_id=1))

		self.assertTrue(out["success"])
		self.assertEqual(out["results"]["subject"], "Help")

	def test_requires_ticket_id(self):
		out = _result(zendesk.handle_get_ticket())
		self.assertFalse(out["success"])
		self.assertIn("ticket_id", out["error"])


class TestCreateTicket(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", side_effect=_fake_credential)
	@patch(f"{MODULE}.requests.request")
	def test_creates_ticket(self, mock_request, _cred, _err):
		mock_request.return_value = _mock_response({"ticket": {"id": 5, "subject": "New", "status": "new"}})

		out = _result(zendesk.handle_create_ticket(subject="New", comment="Body text", priority="high"))

		self.assertTrue(out["success"])
		self.assertEqual(out["results"]["id"], 5)

		body = mock_request.call_args.kwargs["json"]
		self.assertEqual(body["ticket"]["subject"], "New")
		self.assertEqual(body["ticket"]["comment"], {"body": "Body text"})
		self.assertEqual(body["ticket"]["priority"], "high")

	def test_requires_subject_and_comment(self):
		out = _result(zendesk.handle_create_ticket(subject="New"))
		self.assertFalse(out["success"])
		self.assertIn("comment", out["error"])


class TestRegistry(unittest.TestCase):
	def test_all_tools_registered(self):
		expected = {
			"zendesk_list_tickets": "handle_list_tickets",
			"zendesk_get_ticket": "handle_get_ticket",
			"zendesk_create_ticket": "handle_create_ticket",
		}
		by_name = {t["tool_name"]: t for t in ZENDESK_TOOLS}
		self.assertEqual(set(by_name), set(expected))
		for tool_name, handler in expected.items():
			self.assertEqual(by_name[tool_name]["function_path"], f"huf.ai.tools.zendesk.{handler}")
			self.assertTrue(callable(getattr(zendesk, handler)))

	def test_registered_in_all_integration_tools(self):
		by_name = {t["tool_name"]: t for t in ALL_INTEGRATION_TOOLS}
		for tool in ZENDESK_TOOLS:
			self.assertIn(tool["tool_name"], by_name)
			self.assertEqual(by_name[tool["tool_name"]]["service"], "zendesk")


if __name__ == "__main__":
	unittest.main()
