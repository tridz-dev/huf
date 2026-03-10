import json
import frappe
from huf.ai.tools.credentials import require_credential, update_last_error
import requests

ENDPOINT = "https://api.linear.app/graphql"


def _headers():
	service_name = "linear"
	key = require_credential(service_name, "api_key")
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
	service_name = "linear"
	try:
		data = _query("query { viewer { id name email } }")
		return json.dumps({
			"success": True, 
			"results": data.get("viewer", {})
		})
	except Exception as e:
		frappe.log_error(f"Linear Error (Get User): {str(e)}", "Linear Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_get_teams(**kwargs):
	"""Fetch all teams in the Linear workspace."""
	service_name = "linear"
	try:
		data = _query("query { teams { nodes { id name } } }")
		teams = data.get("teams", {}).get("nodes", [])
		return json.dumps({
			"success": True,
			"count": len(teams), 
			"results": teams
		})
	except Exception as e:
		frappe.log_error(f"Linear Error (Get Teams): {str(e)}", "Linear Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_get_issue(**kwargs):
	"""Retrieve details of a Linear issue by ID."""
	service_name = "linear"
	try:
		issue_id = kwargs.get("issue_id")
		if not issue_id:
			return json.dumps({"success": False, "error": "issue_id is required"})

		q = """query($id: String!) { issue(id: $id) { id title description state { name } priority assignee { name } } }"""
		data = _query(q, {"id": issue_id})
		return json.dumps({
			"success": True, 
			"results": data.get("issue", {})
		})
	except Exception as e:
		frappe.log_error(f"Linear Error (Get Issue): {str(e)}", "Linear Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_create_issue(**kwargs):
	"""Create a new issue in Linear."""
	service_name = "linear"
	try:
		title = kwargs.get("title")
		team_id = kwargs.get("team_id")
		if not all([title, team_id]):
			return json.dumps({"success": False, "error": "title and team_id are required"})

		q = """mutation($title: String!, $description: String!, $teamId: String!) {
			issueCreate(input: { title: $title, description: $description, teamId: $teamId }) {
				success issue { id title url }
			}
		}"""
		variables = {
			"title": title,
			"description": kwargs.get("description", ""),
			"teamId": team_id,
		}
		data = _query(q, variables)
		return json.dumps({
			"success": True, 
			"results": data.get("issueCreate", {}).get("issue", {})
		})
	except Exception as e:
		frappe.log_error(f"Linear Error (Create Issue): {str(e)}", "Linear Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_update_issue(**kwargs):
	"""Update a Linear issue title."""
	service_name = "linear"
	try:
		issue_id = kwargs.get("issue_id")
		title = kwargs.get("title")
		if not all([issue_id, title]):
			return json.dumps({"success": False, "error": "issue_id and title are required"})

		q = """mutation($id: String!, $title: String!) {
			issueUpdate(id: $id, input: { title: $title }) {
				success issue { id title state { name } }
			}
		}"""
		data = _query(q, {"id": issue_id, "title": title})
		return json.dumps({
			"success": True, 
			"results": data.get("issueUpdate", {}).get("issue", {})
		})
	except Exception as e:
		frappe.log_error(f"Linear Error (Update Issue): {str(e)}", "Linear Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_get_assigned_issues(**kwargs):
	"""Get issues assigned to a user."""
	service_name = "linear"
	try:
		user_id = kwargs.get("user_id")
		if not user_id:
			return json.dumps({"success": False, "error": "user_id is required"})

		q = """query($userId: String!) {
			user(id: $userId) { id name assignedIssues { nodes { id title priority } } }
		}"""
		data = _query(q, {"userId": user_id})
		user = data.get("user", {})
		issues = user.get("assignedIssues", {}).get("nodes", [])
		return json.dumps({
			"success": True,
			"results": {
				"user": user.get("name"), 
				"issues": issues,
				"count": len(issues)
			}
		})
	except Exception as e:
		frappe.log_error(f"Linear Error (Assigned Issues): {str(e)}", "Linear Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})
