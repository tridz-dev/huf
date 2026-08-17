# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""Tests for the Linear integration tools (GraphQL). All HTTP calls are mocked."""

import json
import unittest
from unittest.mock import MagicMock, patch

from huf.ai.tools import linear
from huf.ai.tools._registry import ALL_INTEGRATION_TOOLS, LINEAR_TOOLS

MODULE = "huf.ai.tools.linear"


def _mock_response(payload):
	resp = MagicMock()
	resp.json.return_value = payload
	resp.raise_for_status = MagicMock()
	return resp


def _result(raw):
	return json.loads(raw)


class TestListIssues(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="lin_api_key")
	@patch(f"{MODULE}.requests.post")
	def test_lists_issues_with_team_filter(self, mock_post, _cred, _err):
		mock_post.return_value = _mock_response(
			{
				"data": {
					"issues": {
						"nodes": [
							{
								"identifier": "ENG-1",
								"title": "Fix crash",
								"state": {"name": "In Progress"},
								"assignee": {"name": "Jane"},
								"priority": 2,
								"url": "https://linear.app/eng-1",
							}
						]
					}
				}
			}
		)

		out = _result(linear.handle_list_issues(team_key="ENG"))

		self.assertTrue(out["success"])
		self.assertEqual(out["results"][0]["identifier"], "ENG-1")
		self.assertEqual(out["results"][0]["status"], "In Progress")

		kwargs = mock_post.call_args.kwargs
		self.assertEqual(kwargs["headers"]["Authorization"], "lin_api_key")
		self.assertEqual(kwargs["json"]["variables"]["teamKey"], "ENG")

	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="lin_api_key")
	@patch(f"{MODULE}.requests.post")
	def test_graphql_errors_surface_as_failure(self, mock_post, _cred, mock_err):
		mock_post.return_value = _mock_response({"errors": [{"message": "Invalid token"}]})

		out = _result(linear.handle_list_issues())

		self.assertFalse(out["success"])
		self.assertIn("Invalid token", out["error"])
		mock_err.assert_called_once()


class TestGetIssue(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="lin_api_key")
	@patch(f"{MODULE}.requests.post")
	def test_get_issue(self, mock_post, _cred, _err):
		mock_post.return_value = _mock_response(
			{
				"data": {
					"issue": {
						"identifier": "ENG-1",
						"title": "Fix crash",
						"description": "Details",
						"state": {"name": "Done"},
						"assignee": None,
						"priority": 1,
						"url": "https://linear.app/eng-1",
						"createdAt": "2026-01-01T00:00:00Z",
						"updatedAt": "2026-01-02T00:00:00Z",
					}
				}
			}
		)

		out = _result(linear.handle_get_issue(issue_id="ENG-1"))

		self.assertTrue(out["success"])
		self.assertEqual(out["results"]["identifier"], "ENG-1")
		self.assertIsNone(out["results"]["assignee"])

	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="lin_api_key")
	@patch(f"{MODULE}.requests.post")
	def test_not_found(self, mock_post, _cred, _err):
		mock_post.return_value = _mock_response({"data": {"issue": None}})

		out = _result(linear.handle_get_issue(issue_id="ENG-999"))

		self.assertFalse(out["success"])
		self.assertIn("not found", out["error"])

	def test_requires_issue_id(self):
		out = _result(linear.handle_get_issue())
		self.assertFalse(out["success"])
		self.assertIn("issue_id", out["error"])


class TestCreateIssue(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="lin_api_key")
	@patch(f"{MODULE}.requests.post")
	def test_resolves_team_then_creates(self, mock_post, _cred, _err):
		mock_post.side_effect = [
			_mock_response({"data": {"teams": {"nodes": [{"id": "team-uuid"}]}}}),
			_mock_response(
				{
					"data": {
						"issueCreate": {
							"success": True,
							"issue": {"identifier": "ENG-2", "title": "New issue", "url": "https://linear.app/eng-2"},
						}
					}
				}
			),
		]

		out = _result(linear.handle_create_issue(team_key="ENG", title="New issue"))

		self.assertTrue(out["success"])
		self.assertEqual(out["results"]["identifier"], "ENG-2")
		self.assertEqual(mock_post.call_count, 2)
		second_call_vars = mock_post.call_args_list[1].kwargs["json"]["variables"]
		self.assertEqual(second_call_vars["input"]["teamId"], "team-uuid")

	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="lin_api_key")
	@patch(f"{MODULE}.requests.post")
	def test_unknown_team_key(self, mock_post, _cred, _err):
		mock_post.return_value = _mock_response({"data": {"teams": {"nodes": []}}})

		out = _result(linear.handle_create_issue(team_key="MISSING", title="x"))

		self.assertFalse(out["success"])
		self.assertIn("MISSING", out["error"])

	def test_requires_team_key_and_title(self):
		out = _result(linear.handle_create_issue(title="x"))
		self.assertFalse(out["success"])
		self.assertIn("team_key", out["error"])


class TestRegistry(unittest.TestCase):
	def test_all_tools_registered(self):
		expected = {
			"linear_list_issues": "handle_list_issues",
			"linear_get_issue": "handle_get_issue",
			"linear_create_issue": "handle_create_issue",
		}
		by_name = {t["tool_name"]: t for t in LINEAR_TOOLS}
		self.assertEqual(set(by_name), set(expected))
		for tool_name, handler in expected.items():
			self.assertEqual(by_name[tool_name]["function_path"], f"huf.ai.tools.linear.{handler}")
			self.assertTrue(callable(getattr(linear, handler)))

	def test_registered_in_all_integration_tools(self):
		by_name = {t["tool_name"]: t for t in ALL_INTEGRATION_TOOLS}
		for tool in LINEAR_TOOLS:
			self.assertIn(tool["tool_name"], by_name)
			self.assertEqual(by_name[tool["tool_name"]]["service"], "linear")


if __name__ == "__main__":
	unittest.main()
