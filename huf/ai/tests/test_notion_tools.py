# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""Tests for the Notion integration tools. All HTTP calls are mocked."""

import json
import unittest
from unittest.mock import MagicMock, patch

from huf.ai.tools import notion
from huf.ai.tools._registry import ALL_INTEGRATION_TOOLS, NOTION_TOOLS

MODULE = "huf.ai.tools.notion"


def _mock_response(payload):
	resp = MagicMock()
	resp.json.return_value = payload
	resp.text = json.dumps(payload)
	resp.raise_for_status = MagicMock()
	return resp


def _result(raw):
	return json.loads(raw)


SAMPLE_PAGE = {
	"id": "page-1",
	"url": "https://notion.so/page-1",
	"created_time": "2026-01-01T00:00:00Z",
	"last_edited_time": "2026-01-02T00:00:00Z",
	"archived": False,
	"properties": {"Name": {"type": "title", "title": [{"plain_text": "Task One"}]}},
}


class TestQueryDatabase(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="secret_abc")
	@patch(f"{MODULE}.requests.request")
	def test_queries_database(self, mock_request, _cred, _err):
		mock_request.return_value = _mock_response({"results": [SAMPLE_PAGE]})

		out = _result(notion.handle_query_database(database_id="db-1"))

		self.assertTrue(out["success"])
		self.assertEqual(out["results"][0]["title"], "Task One")

		kwargs = mock_request.call_args.kwargs
		self.assertEqual(kwargs["headers"]["Authorization"], "Bearer secret_abc")
		self.assertEqual(kwargs["headers"]["Notion-Version"], "2022-06-28")

	@patch(f"{MODULE}.get_credential", return_value="db-default")
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="secret_abc")
	@patch(f"{MODULE}.requests.request")
	def test_falls_back_to_default_database_id(self, mock_request, _cred, _err, _default_db):
		mock_request.return_value = _mock_response({"results": []})

		out = _result(notion.handle_query_database())

		self.assertTrue(out["success"])
		self.assertIn("databases/db-default/query", mock_request.call_args.args[1])

	@patch(f"{MODULE}.get_credential", return_value=None)
	def test_requires_database_id(self, _default_db):
		out = _result(notion.handle_query_database())
		self.assertFalse(out["success"])
		self.assertIn("database_id", out["error"])


class TestGetPage(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="secret_abc")
	@patch(f"{MODULE}.requests.request")
	def test_get_page(self, mock_request, _cred, _err):
		mock_request.return_value = _mock_response(SAMPLE_PAGE)

		out = _result(notion.handle_get_page(page_id="page-1"))

		self.assertTrue(out["success"])
		self.assertEqual(out["results"]["title"], "Task One")

	def test_requires_page_id(self):
		out = _result(notion.handle_get_page())
		self.assertFalse(out["success"])
		self.assertIn("page_id", out["error"])


class TestCreatePage(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="secret_abc")
	@patch(f"{MODULE}.requests.request")
	def test_creates_page_with_title_property(self, mock_request, _cred, _err):
		mock_request.return_value = _mock_response({"id": "page-2", "url": "https://notion.so/page-2"})

		out = _result(notion.handle_create_page(title="New task", database_id="db-1"))

		self.assertTrue(out["success"])
		self.assertEqual(out["results"]["id"], "page-2")

		body = mock_request.call_args.kwargs["json"]
		self.assertEqual(body["parent"], {"database_id": "db-1"})
		self.assertEqual(body["properties"]["Name"]["title"][0]["text"]["content"], "New task")

	def test_requires_title(self):
		out = _result(notion.handle_create_page(database_id="db-1"))
		self.assertFalse(out["success"])
		self.assertIn("title", out["error"])


class TestRegistry(unittest.TestCase):
	def test_all_tools_registered(self):
		expected = {
			"notion_query_database": "handle_query_database",
			"notion_get_page": "handle_get_page",
			"notion_create_page": "handle_create_page",
		}
		by_name = {t["tool_name"]: t for t in NOTION_TOOLS}
		self.assertEqual(set(by_name), set(expected))
		for tool_name, handler in expected.items():
			self.assertEqual(by_name[tool_name]["function_path"], f"huf.ai.tools.notion.{handler}")
			self.assertTrue(callable(getattr(notion, handler)))

	def test_registered_in_all_integration_tools(self):
		by_name = {t["tool_name"]: t for t in ALL_INTEGRATION_TOOLS}
		for tool in NOTION_TOOLS:
			self.assertIn(tool["tool_name"], by_name)
			self.assertEqual(by_name[tool["tool_name"]]["service"], "notion")


if __name__ == "__main__":
	unittest.main()
