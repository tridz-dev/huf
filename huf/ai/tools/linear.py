import json

from huf.ai.tools.credentials import require_credential
import requests

ENDPOINT = "https://api.linear.app/graphql"


def _headers():
	key = require_credential("linear", "api_key")
	return {"Authorization": key, "Content-Type": "application/json"}


def _query(q, variables=None):
	resp = requests.post(ENDPOINT, json={"query": q, "variables": variables}, headers=_headers(), timeout=30)
	resp.raise_for_status()
	data = resp.json()
	if "errors" in data:
		raise Exception(f"GraphQL Error: {data['errors']}")
	return data.get("data")


def handle_get_user_details(**kwargs):
	"""Fetch authenticated Linear user details."""
	try:
		data = _query("query { viewer { id name email } }")
		return json.dumps(data.get("viewer", {}))
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_get_teams(**kwargs):
	"""Fetch all teams in the Linear workspace."""
	try:
		data = _query("query { teams { nodes { id name } } }")
		return json.dumps({"teams": data.get("teams", {}).get("nodes", [])})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_get_issue(**kwargs):
	"""Retrieve details of a Linear issue by ID."""
	try:
		q = """query($id: String!) { issue(id: $id) { id title description state { name } priority assignee { name } } }"""
		data = _query(q, {"id": kwargs["issue_id"]})
		return json.dumps(data.get("issue", {}))
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_create_issue(**kwargs):
	"""Create a new issue in Linear."""
	try:
		q = """mutation($title: String!, $description: String!, $teamId: String!) {
			issueCreate(input: { title: $title, description: $description, teamId: $teamId }) {
				success issue { id title url }
			}
		}"""
		variables = {
			"title": kwargs["title"],
			"description": kwargs.get("description", ""),
			"teamId": kwargs["team_id"],
		}
		data = _query(q, variables)
		return json.dumps(data.get("issueCreate", {}).get("issue", {}))
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_update_issue(**kwargs):
	"""Update a Linear issue title."""
	try:
		q = """mutation($id: String!, $title: String!) {
			issueUpdate(id: $id, input: { title: $title }) {
				success issue { id title state { name } }
			}
		}"""
		data = _query(q, {"id": kwargs["issue_id"], "title": kwargs["title"]})
		return json.dumps(data.get("issueUpdate", {}).get("issue", {}))
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_get_assigned_issues(**kwargs):
	"""Get issues assigned to a user."""
	try:
		q = """query($userId: String!) {
			user(id: $userId) { id name assignedIssues { nodes { id title priority } } }
		}"""
		data = _query(q, {"userId": kwargs["user_id"]})
		user = data.get("user", {})
		return json.dumps({"user": user.get("name"), "issues": user.get("assignedIssues", {}).get("nodes", [])})
	except Exception as e:
		return json.dumps({"error": str(e)})
