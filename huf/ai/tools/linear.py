"""
Linear integration tools for issue listing, retrieval, and creation.
Uses HUF Integration Settings for Linear credentials (api_key). Linear's API is GraphQL-only.
"""

import json

import frappe
import requests

from huf.ai.tools.credentials import require_credential, update_last_error

logger = frappe.logger("huf")

SERVICE_NAME = "linear"
LINEAR_API_URL = "https://api.linear.app/graphql"


def _make_linear_request(query: str, variables: dict | None = None) -> dict:
	api_key = require_credential(SERVICE_NAME, "api_key")

	response = requests.post(
		LINEAR_API_URL,
		headers={"Authorization": api_key, "Content-Type": "application/json"},
		json={"query": query, "variables": variables or {}},
		timeout=30,
	)
	response.raise_for_status()
	data = response.json()
	if data.get("errors"):
		raise ValueError("; ".join(err.get("message", "unknown error") for err in data["errors"]))
	return data.get("data", {})


def handle_list_issues(**kwargs) -> str:
	"""List Linear issues, optionally filtered by team key."""
	try:
		team_key = kwargs.get("team_key")
		limit = int(kwargs.get("limit") or 20)

		filter_clause = ""
		variables = {}
		if team_key:
			filter_clause = ", filter: { team: { key: { eq: $teamKey } } }"
			variables["teamKey"] = team_key

		query = f"""
		query Issues($teamKey: String) {{
			issues(first: {limit}{filter_clause}) {{
				nodes {{
					identifier
					title
					state {{ name }}
					assignee {{ name }}
					priority
					url
				}}
			}}
		}}
		"""
		data = _make_linear_request(query, variables)

		issues = [
			{
				"identifier": node.get("identifier"),
				"title": node.get("title"),
				"status": (node.get("state") or {}).get("name"),
				"assignee": (node.get("assignee") or {}).get("name"),
				"priority": node.get("priority"),
				"url": node.get("url"),
			}
			for node in data.get("issues", {}).get("nodes", [])
		]

		return json.dumps({"success": True, "count": len(issues), "results": issues})
	except Exception as e:
		error_msg = f"Linear List Issues Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_get_issue(**kwargs) -> str:
	"""Get details of a Linear issue by its human-readable identifier (e.g. 'ENG-123')."""
	try:
		issue_id = kwargs.get("issue_id")
		if not issue_id:
			return json.dumps({"success": False, "error": "issue_id is required"}, default=str)

		query = """
		query Issue($id: String!) {
			issue(id: $id) {
				identifier
				title
				description
				state { name }
				assignee { name }
				priority
				url
				createdAt
				updatedAt
			}
		}
		"""
		data = _make_linear_request(query, {"id": issue_id})
		issue = data.get("issue")
		if not issue:
			return json.dumps({"success": False, "error": f"Issue '{issue_id}' not found"}, default=str)

		issue_data = {
			"identifier": issue.get("identifier"),
			"title": issue.get("title"),
			"description": issue.get("description"),
			"status": (issue.get("state") or {}).get("name"),
			"assignee": (issue.get("assignee") or {}).get("name"),
			"priority": issue.get("priority"),
			"url": issue.get("url"),
			"created_at": issue.get("createdAt"),
			"updated_at": issue.get("updatedAt"),
		}
		return json.dumps({"success": True, "results": issue_data})
	except Exception as e:
		error_msg = f"Linear Get Issue Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_create_issue(**kwargs) -> str:
	"""Create a Linear issue in a team, given the team's key."""
	try:
		team_key = kwargs.get("team_key")
		title = kwargs.get("title")
		if not all([team_key, title]):
			return json.dumps({"success": False, "error": "team_key and title are required"}, default=str)

		team_query = "query Team($key: String!) { teams(filter: { key: { eq: $key } }) { nodes { id } } }"
		team_data = _make_linear_request(team_query, {"key": team_key})
		team_nodes = team_data.get("teams", {}).get("nodes", [])
		if not team_nodes:
			return json.dumps({"success": False, "error": f"Team '{team_key}' not found"}, default=str)
		team_id = team_nodes[0]["id"]

		mutation = """
		mutation CreateIssue($input: IssueCreateInput!) {
			issueCreate(input: $input) {
				success
				issue { identifier title url }
			}
		}
		"""
		issue_input = {"teamId": team_id, "title": title}
		description = kwargs.get("description")
		if description:
			issue_input["description"] = description

		data = _make_linear_request(mutation, {"input": issue_input})
		result = data.get("issueCreate", {})
		if not result.get("success"):
			return json.dumps({"success": False, "error": "Linear rejected the issue creation"}, default=str)

		issue = result.get("issue", {})
		return json.dumps(
			{
				"success": True,
				"results": {
					"identifier": issue.get("identifier"),
					"title": issue.get("title"),
					"url": issue.get("url"),
				},
			}
		)
	except Exception as e:
		error_msg = f"Linear Create Issue Error: {e!s}"
		logger.warning(error_msg)
		update_last_error(SERVICE_NAME, error_msg)
		return json.dumps({"success": False, "error": str(e)}, default=str)
