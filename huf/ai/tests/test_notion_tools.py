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
	resp.ok = True
	resp.raise_for_status = MagicMock()
	return resp


def _mock_error_response(status_code, message):
	resp = MagicMock()
	resp.ok = False
	resp.status_code = status_code
	resp.text = json.dumps({"message": message})
	resp.json.return_value = {"message": message}
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

SAMPLE_DATABASE = {
	"id": "db-1",
	"object": "database",
	"url": "https://notion.so/db-1",
	"title": [{"plain_text": "Tasks"}],
	"properties": {
		"Name": {"type": "title", "title": {}},
		"Status": {
			"type": "status",
			"status": {"options": [{"name": "Not started"}, {"name": "Done"}]},
		},
	},
}


class TestSearch(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="secret_abc")
	@patch(f"{MODULE}.requests.request")
	def test_search_pages(self, mock_request, _cred, _err):
		mock_request.return_value = _mock_response(
			{"results": [{**SAMPLE_PAGE, "object": "page"}], "has_more": False}
		)

		out = _result(notion.handle_search(query="task", object_type="page"))

		self.assertTrue(out["success"])
		self.assertEqual(out["results"][0]["title"], "Task One")
		body = mock_request.call_args.kwargs["json"]
		self.assertEqual(body["query"], "task")
		self.assertEqual(body["filter"], {"property": "object", "value": "page"})


class TestListDatabases(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="secret_abc")
	@patch(f"{MODULE}.requests.request")
	def test_lists_databases(self, mock_request, _cred, _err):
		mock_request.return_value = _mock_response({"results": [SAMPLE_DATABASE], "has_more": False})

		out = _result(notion.handle_list_databases())

		self.assertTrue(out["success"])
		self.assertEqual(out["results"][0]["title"], "Tasks")
		self.assertEqual(mock_request.call_args.kwargs["json"]["filter"]["value"], "database")


class TestGetDatabase(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="secret_abc")
	@patch(f"{MODULE}.requests.request")
	def test_get_database_schema(self, mock_request, _cred, _err):
		mock_request.return_value = _mock_response(SAMPLE_DATABASE)

		out = _result(notion.handle_get_database(database_id="db-1"))

		self.assertTrue(out["success"])
		self.assertEqual(out["results"]["title"], "Tasks")
		self.assertEqual(out["results"]["properties"]["Status"]["options"], ["Not started", "Done"])


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

	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="secret_abc")
	@patch(f"{MODULE}.requests.request")
	def test_passes_filter_and_sorts(self, mock_request, _cred, _err):
		mock_request.return_value = _mock_response({"results": []})
		filter_json = '{"property":"Status","status":{"equals":"Done"}}'
		sorts_json = '[{"property":"Due","direction":"ascending"}]'

		out = _result(notion.handle_query_database(database_id="db-1", filter=filter_json, sorts=sorts_json))

		self.assertTrue(out["success"])
		body = mock_request.call_args.kwargs["json"]
		self.assertEqual(body["filter"]["property"], "Status")
		self.assertEqual(body["sorts"][0]["property"], "Due")

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


class TestGetPageContent(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="secret_abc")
	@patch(f"{MODULE}.requests.request")
	def test_get_page_content(self, mock_request, _cred, _err):
		mock_request.return_value = _mock_response(
			{
				"results": [
					{
						"type": "heading_1",
						"heading_1": {"rich_text": [{"plain_text": "Overview"}]},
					},
					{
						"type": "paragraph",
						"paragraph": {"rich_text": [{"plain_text": "Details here."}]},
					},
				],
				"has_more": False,
			}
		)

		out = _result(notion.handle_get_page_content(page_id="page-1"))

		self.assertTrue(out["success"])
		self.assertIn("Overview", out["content"])
		self.assertIn("Details here.", out["content"])


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


class TestUpdatePage(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="secret_abc")
	@patch(f"{MODULE}.requests.request")
	def test_updates_page_properties(self, mock_request, _cred, _err):
		mock_request.return_value = _mock_response(SAMPLE_PAGE)
		properties = '{"Status":{"status":{"name":"Done"}}}'

		out = _result(notion.handle_update_page(page_id="page-1", properties=properties))

		self.assertTrue(out["success"])
		body = mock_request.call_args.kwargs["json"]
		self.assertEqual(body["properties"]["Status"]["status"]["name"], "Done")

	def test_requires_properties(self):
		out = _result(notion.handle_update_page(page_id="page-1"))
		self.assertFalse(out["success"])
		self.assertIn("properties", out["error"])


class TestArchivePage(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="secret_abc")
	@patch(f"{MODULE}.requests.request")
	def test_archives_page(self, mock_request, _cred, _err):
		mock_request.return_value = _mock_response({"id": "page-1", "archived": True})

		out = _result(notion.handle_archive_page(page_id="page-1"))

		self.assertTrue(out["success"])
		self.assertTrue(out["results"]["archived"])
		self.assertEqual(mock_request.call_args.kwargs["json"], {"archived": True})


class TestErrorHandling(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="secret_abc")
	@patch(f"{MODULE}.requests.request")
	def test_surfaces_notion_api_message(self, mock_request, _cred, _err):
		mock_request.return_value = _mock_error_response(404, "Could not find page")

		out = _result(notion.handle_get_page(page_id="missing"))

		self.assertFalse(out["success"])
		self.assertIn("Could not find page", out["error"])


class TestRegistry(unittest.TestCase):
	def test_all_tools_registered(self):
		expected = {
			"notion_search": "handle_search",
			"notion_list_databases": "handle_list_databases",
			"notion_get_database": "handle_get_database",
			"notion_query_database": "handle_query_database",
			"notion_get_page": "handle_get_page",
			"notion_get_page_content": "handle_get_page_content",
			"notion_create_page": "handle_create_page",
			"notion_update_page": "handle_update_page",
			"notion_archive_page": "handle_archive_page",
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
