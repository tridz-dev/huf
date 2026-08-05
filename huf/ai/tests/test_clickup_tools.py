# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""Tests for the ClickUp integration tools. All HTTP calls are mocked."""

import json
import unittest
from unittest.mock import MagicMock, patch

from huf.ai.tools import clickup
from huf.ai.tools._registry import ALL_INTEGRATION_TOOLS, CLICKUP_TOOLS

MODULE = "huf.ai.tools.clickup"


def _mock_response(payload):
	resp = MagicMock()
	resp.json.return_value = payload
	resp.text = json.dumps(payload)
	resp.raise_for_status = MagicMock()
	return resp


def _result(raw):
	return json.loads(raw)


class TestListTasks(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="pk_token")
	@patch(f"{MODULE}.requests.request")
	def test_lists_tasks(self, mock_request, _cred, _err):
		mock_request.return_value = _mock_response(
			{
				"tasks": [
					{
						"id": "abc123",
						"name": "Ship feature",
						"status": {"status": "in progress"},
						"assignees": [{"username": "jane"}],
						"due_date": None,
						"url": "https://app.clickup.com/t/abc123",
					}
				]
			}
		)

		out = _result(clickup.handle_list_tasks(list_id="list-1"))

		self.assertTrue(out["success"])
		self.assertEqual(out["results"][0]["id"], "abc123")
		self.assertEqual(out["results"][0]["status"], "in progress")
		self.assertEqual(out["results"][0]["assignees"], ["jane"])

		kwargs = mock_request.call_args.kwargs
		self.assertEqual(kwargs["headers"]["Authorization"], "pk_token")

	def test_requires_list_id(self):
		out = _result(clickup.handle_list_tasks())
		self.assertFalse(out["success"])
		self.assertIn("list_id", out["error"])


class TestGetTask(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="pk_token")
	@patch(f"{MODULE}.requests.request")
	def test_get_task(self, mock_request, _cred, _err):
		mock_request.return_value = _mock_response(
			{
				"id": "abc123",
				"name": "Ship feature",
				"description": "Details",
				"status": {"status": "open"},
				"assignees": [],
				"priority": {"priority": "high"},
				"due_date": "1700000000000",
				"url": "https://app.clickup.com/t/abc123",
			}
		)

		out = _result(clickup.handle_get_task(task_id="abc123"))

		self.assertTrue(out["success"])
		self.assertEqual(out["results"]["priority"], "high")

	def test_requires_task_id(self):
		out = _result(clickup.handle_get_task())
		self.assertFalse(out["success"])
		self.assertIn("task_id", out["error"])


class TestCreateTask(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="pk_token")
	@patch(f"{MODULE}.requests.request")
	def test_create_task(self, mock_request, _cred, _err):
		mock_request.return_value = _mock_response(
			{"id": "abc999", "name": "New task", "url": "https://app.clickup.com/t/abc999"}
		)

		out = _result(clickup.handle_create_task(list_id="list-1", name="New task", description="desc"))

		self.assertTrue(out["success"])
		self.assertEqual(out["results"]["id"], "abc999")

		body = mock_request.call_args.kwargs["json"]
		self.assertEqual(body["name"], "New task")
		self.assertEqual(body["description"], "desc")

	def test_requires_name(self):
		out = _result(clickup.handle_create_task(list_id="list-1"))
		self.assertFalse(out["success"])
		self.assertIn("name", out["error"])


class TestErrorHandling(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", side_effect=ValueError("Credential not found"))
	def test_missing_credentials_returns_envelope(self, _cred, mock_err):
		out = _result(clickup.handle_list_tasks(list_id="list-1"))
		self.assertFalse(out["success"])
		mock_err.assert_called_once()


class TestRegistry(unittest.TestCase):
	def test_all_tools_registered(self):
		expected = {
			"clickup_list_tasks": "handle_list_tasks",
			"clickup_get_task": "handle_get_task",
			"clickup_create_task": "handle_create_task",
		}
		by_name = {t["tool_name"]: t for t in CLICKUP_TOOLS}
		self.assertEqual(set(by_name), set(expected))
		for tool_name, handler in expected.items():
			self.assertEqual(by_name[tool_name]["function_path"], f"huf.ai.tools.clickup.{handler}")
			self.assertTrue(callable(getattr(clickup, handler)))

	def test_registered_in_all_integration_tools(self):
		by_name = {t["tool_name"]: t for t in ALL_INTEGRATION_TOOLS}
		for tool in CLICKUP_TOOLS:
			self.assertIn(tool["tool_name"], by_name)
			self.assertEqual(by_name[tool["tool_name"]]["service"], "clickup")


if __name__ == "__main__":
	unittest.main()
