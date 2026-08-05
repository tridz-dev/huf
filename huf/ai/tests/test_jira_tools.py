# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""Tests for the Jira integration tools.

All HTTP calls and credential lookups are mocked — no live Jira instance is required.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from huf.ai.tools import jira
from huf.ai.tools._registry import ALL_INTEGRATION_TOOLS, JIRA_TOOLS

MODULE = "huf.ai.tools.jira"


def _mock_response(payload=None, status_code=200):
	resp = MagicMock()
	resp.status_code = status_code
	resp.json.return_value = payload if payload is not None else {}
	resp.text = json.dumps(payload or {})
	resp.raise_for_status = MagicMock()
	if status_code >= 400:
		import requests

		resp.raise_for_status.side_effect = requests.HTTPError(f"{status_code} error")
	return resp


def _result(raw):
	return json.loads(raw)


def _fake_credential(service, key):
	return {"base_url": "https://example.atlassian.net", "email": "bot@example.com", "api_token": "tok-123"}[key]


class TestSearchIssues(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", side_effect=_fake_credential)
	@patch(f"{MODULE}.requests.request")
	def test_search_returns_normalized_issues(self, mock_request, _cred, _err):
		mock_request.return_value = _mock_response(
			{
				"issues": [
					{
						"key": "ABC-1",
						"fields": {
							"summary": "Fix bug",
							"status": {"name": "In Progress"},
							"issuetype": {"name": "Bug"},
							"assignee": {"displayName": "Jane Doe"},
							"priority": {"name": "High"},
						},
					}
				]
			}
		)

		out = _result(jira.handle_search_issues(jql="project = ABC"))

		self.assertTrue(out["success"])
		self.assertEqual(out["count"], 1)
		issue = out["results"][0]
		self.assertEqual(issue["key"], "ABC-1")
		self.assertEqual(issue["status"], "In Progress")
		self.assertEqual(issue["assignee"], "Jane Doe")
		self.assertIn("ABC-1", issue["url"])

		kwargs = mock_request.call_args.kwargs
		self.assertEqual(kwargs["params"]["jql"], "project = ABC")

	def test_requires_jql(self):
		out = _result(jira.handle_search_issues())
		self.assertFalse(out["success"])
		self.assertIn("jql", out["error"])


class TestGetIssue(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", side_effect=_fake_credential)
	@patch(f"{MODULE}.requests.request")
	def test_get_issue(self, mock_request, _cred, _err):
		mock_request.return_value = _mock_response(
			{
				"key": "ABC-1",
				"fields": {
					"summary": "Fix bug",
					"status": {"name": "Open"},
					"issuetype": {"name": "Bug"},
					"assignee": None,
					"reporter": {"displayName": "John"},
					"priority": {"name": "Low"},
					"created": "2026-01-01T00:00:00Z",
					"updated": "2026-01-02T00:00:00Z",
				},
			}
		)

		out = _result(jira.handle_get_issue(issue_key="ABC-1"))

		self.assertTrue(out["success"])
		self.assertEqual(out["results"]["key"], "ABC-1")
		self.assertEqual(out["results"]["reporter"], "John")
		self.assertIsNone(out["results"]["assignee"])

	def test_requires_issue_key(self):
		out = _result(jira.handle_get_issue())
		self.assertFalse(out["success"])
		self.assertIn("issue_key", out["error"])


class TestCreateIssue(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", side_effect=_fake_credential)
	@patch(f"{MODULE}.requests.request")
	def test_create_issue_builds_adf_description(self, mock_request, _cred, _err):
		mock_request.return_value = _mock_response({"key": "ABC-2", "id": "10001"})

		out = _result(
			jira.handle_create_issue(project_key="ABC", summary="New task", description="Some details")
		)

		self.assertTrue(out["success"])
		self.assertEqual(out["results"]["key"], "ABC-2")
		self.assertIn("ABC-2", out["results"]["url"])

		body = mock_request.call_args.kwargs["json"]
		self.assertEqual(body["fields"]["project"], {"key": "ABC"})
		self.assertEqual(body["fields"]["summary"], "New task")
		self.assertEqual(body["fields"]["issuetype"], {"name": "Task"})
		self.assertEqual(body["fields"]["description"]["type"], "doc")

	def test_requires_project_key_and_summary(self):
		out = _result(jira.handle_create_issue(summary="No project"))
		self.assertFalse(out["success"])
		self.assertIn("project_key", out["error"])


class TestAddComment(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", side_effect=_fake_credential)
	@patch(f"{MODULE}.requests.request")
	def test_add_comment(self, mock_request, _cred, _err):
		mock_request.return_value = _mock_response({"id": "999", "created": "2026-01-01T00:00:00Z"})

		out = _result(jira.handle_add_comment(issue_key="ABC-1", comment="Looks good"))

		self.assertTrue(out["success"])
		self.assertEqual(out["results"]["id"], "999")

	def test_requires_comment(self):
		out = _result(jira.handle_add_comment(issue_key="ABC-1"))
		self.assertFalse(out["success"])
		self.assertIn("comment", out["error"])


class TestErrorHandling(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", side_effect=_fake_credential)
	@patch(f"{MODULE}.requests.request")
	def test_http_error_returns_envelope(self, mock_request, _cred, mock_err):
		mock_request.return_value = _mock_response({"errorMessages": ["not found"]}, status_code=404)

		out = _result(jira.handle_get_issue(issue_key="ABC-999"))

		self.assertFalse(out["success"])
		mock_err.assert_called_once()

	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", side_effect=ValueError("Credential not found"))
	def test_missing_credentials_returns_envelope(self, _cred, mock_err):
		out = _result(jira.handle_search_issues(jql="project = ABC"))
		self.assertFalse(out["success"])
		mock_err.assert_called_once()


class TestRegistry(unittest.TestCase):
	def test_all_tools_registered(self):
		expected = {
			"jira_search_issues": "handle_search_issues",
			"jira_get_issue": "handle_get_issue",
			"jira_create_issue": "handle_create_issue",
			"jira_add_comment": "handle_add_comment",
		}
		by_name = {t["tool_name"]: t for t in JIRA_TOOLS}
		self.assertEqual(set(by_name), set(expected))
		for tool_name, handler in expected.items():
			tool = by_name[tool_name]
			self.assertEqual(tool["function_path"], f"huf.ai.tools.jira.{handler}")
			self.assertTrue(callable(getattr(jira, handler)))

	def test_registered_in_all_integration_tools(self):
		by_name = {t["tool_name"]: t for t in ALL_INTEGRATION_TOOLS}
		for tool in JIRA_TOOLS:
			self.assertIn(tool["tool_name"], by_name)
			self.assertEqual(by_name[tool["tool_name"]]["service"], "jira")


if __name__ == "__main__":
	unittest.main()
