"""
Jira Cloud integration tools for issue search, retrieval, and creation.
Uses HUF Integration Settings for Jira credentials (base_url, email, api_token).
"""

import json

import frappe
import requests

from huf.ai.tools.credentials import get_credential, require_credential, update_last_error

logger = frappe.logger("huf")

SERVICE_NAME = "jira"


def _get_jira_config():
	"""Return (base_url, auth) for authenticated Jira REST API requests."""
	base_url = require_credential(SERVICE_NAME, "base_url").rstrip("/")
	email = require_credential(SERVICE_NAME, "email")
	api_token = require_credential(SERVICE_NAME, "api_token")
	return base_url, (email, api_token)


def _make_jira_request(method: str, path: str, json_data=None, params=None):
	base_url, auth = _get_jira_config()
	url = f"{base_url}/rest/api/3/{path}"

	response = requests.request(
		method,
		url,
		auth=auth,
		headers={"Accept": "application/json", "Content-Type": "application/json"},
		json=json_data,
		params=params,
		timeout=30,
	)
	response.raise_for_status()
	return response.json() if response.text else {}


def _adf_text(text: str) -> dict:
	"""Wrap plain text in Jira's Atlassian Document Format, required by the v3 API."""
	return {
		"type": "doc",
		"version": 1,
		"content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
	}


def handle_search_issues(**kwargs) -> str:
	"""Search Jira issues using JQL."""
	try:
		jql = kwargs.get("jql")
		if not jql:
			return json.dumps({"success": False, "error": "jql is required"}, default=str)

		max_results = int(kwargs.get("max_results") or 20)
		data = _make_jira_request(
			"GET",
			"search",
			params={
				"jql": jql,
				"maxResults": max_results,
				"fields": "summary,status,issuetype,assignee,priority",
			},
		)

		issues = []
		for issue in data.get("issues", []):
			fields = issue.get("fields", {})
			issues.append(
				{
					"key": issue.get("key"),
					"summary": fields.get("summary"),
					"status": (fields.get("status") or {}).get("name"),
					"issue_type": (fields.get("issuetype") or {}).get("name"),
					"assignee": ((fields.get("assignee") or {}).get("displayName")),
					"priority": (fields.get("priority") or {}).get("name"),
					"url": f"{require_credential(SERVICE_NAME, 'base_url').rstrip('/')}/browse/{issue.get('key')}",
				}
			)

		return json.dumps({"success": True, "count": len(issues), "results": issues})
	except Exception as e:
		error_msg = f"Jira Search Issues Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_get_issue(**kwargs) -> str:
	"""Get details of a Jira issue by key."""
	try:
		issue_key = kwargs.get("issue_key")
		if not issue_key:
			return json.dumps({"success": False, "error": "issue_key is required"}, default=str)

		data = _make_jira_request("GET", f"issue/{issue_key}")
		fields = data.get("fields", {})

		issue_data = {
			"key": data.get("key"),
			"summary": fields.get("summary"),
			"description": fields.get("description"),
			"status": (fields.get("status") or {}).get("name"),
			"issue_type": (fields.get("issuetype") or {}).get("name"),
			"assignee": (fields.get("assignee") or {}).get("displayName"),
			"reporter": (fields.get("reporter") or {}).get("displayName"),
			"priority": (fields.get("priority") or {}).get("name"),
			"created": fields.get("created"),
			"updated": fields.get("updated"),
			"url": f"{require_credential(SERVICE_NAME, 'base_url').rstrip('/')}/browse/{data.get('key')}",
		}

		return json.dumps({"success": True, "results": issue_data})
	except Exception as e:
		error_msg = f"Jira Get Issue Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_create_issue(**kwargs) -> str:
	"""Create a Jira issue."""
	try:
		project_key = kwargs.get("project_key")
		summary = kwargs.get("summary")
		issue_type = kwargs.get("issue_type") or "Task"
		if not all([project_key, summary]):
			return json.dumps(
				{"success": False, "error": "project_key and summary are required"}, default=str
			)

		fields = {
			"project": {"key": project_key},
			"summary": summary,
			"issuetype": {"name": issue_type},
		}
		description = kwargs.get("description")
		if description:
			fields["description"] = _adf_text(description)

		data = _make_jira_request("POST", "issue", json_data={"fields": fields})
		base_url = require_credential(SERVICE_NAME, "base_url").rstrip("/")

		return json.dumps(
			{
				"success": True,
				"results": {
					"key": data.get("key"),
					"id": data.get("id"),
					"url": f"{base_url}/browse/{data.get('key')}",
				},
			}
		)
	except Exception as e:
		error_msg = f"Jira Create Issue Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_add_comment(**kwargs) -> str:
	"""Add a comment to a Jira issue."""
	try:
		issue_key = kwargs.get("issue_key")
		comment = kwargs.get("comment")
		if not all([issue_key, comment]):
			return json.dumps({"success": False, "error": "issue_key and comment are required"}, default=str)

		data = _make_jira_request(
			"POST", f"issue/{issue_key}/comment", json_data={"body": _adf_text(comment)}
		)

		return json.dumps(
			{"success": True, "results": {"id": data.get("id"), "created": data.get("created")}}
		)
	except Exception as e:
		error_msg = f"Jira Add Comment Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)
