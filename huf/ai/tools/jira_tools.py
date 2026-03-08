import json
import os


def _get_client():
	try:
		from jira import JIRA
	except ImportError:
		raise ImportError("jira is required. Install with: pip install jira")

	server = os.getenv("JIRA_SERVER_URL")
	username = os.getenv("JIRA_USERNAME")
	token = os.getenv("JIRA_TOKEN") or os.getenv("JIRA_PASSWORD")

	if not server:
		raise ValueError("JIRA_SERVER_URL environment variable is not set")

	auth = (username, token) if username and token else None
	return JIRA(server=server, basic_auth=auth) if auth else JIRA(server=server), server


def handle_get_issue(**kwargs):
	"""Retrieve details of a Jira issue by its key."""
	try:
		client, _ = _get_client()
		issue = client.issue(kwargs["issue_key"])
		return json.dumps({
			"key": issue.key,
			"summary": issue.fields.summary,
			"description": issue.fields.description or "",
			"status": issue.fields.status.name,
			"assignee": issue.fields.assignee.displayName if issue.fields.assignee else "Unassigned",
			"reporter": issue.fields.reporter.displayName if issue.fields.reporter else "N/A",
			"issuetype": issue.fields.issuetype.name,
			"project": issue.fields.project.key,
		})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_create_issue(**kwargs):
	"""Create a new issue in a Jira project."""
	try:
		client, server = _get_client()
		fields = {
			"project": {"key": kwargs["project_key"]},
			"summary": kwargs["summary"],
			"description": kwargs.get("description", ""),
			"issuetype": {"name": kwargs.get("issuetype", "Task")},
		}
		issue = client.create_issue(fields=fields)
		return json.dumps({"key": issue.key, "url": f"{server}/browse/{issue.key}"})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_search_issues(**kwargs):
	"""Search Jira issues using JQL query."""
	try:
		client, _ = _get_client()
		max_results = int(kwargs.get("max_results", 50))
		issues = client.search_issues(kwargs["jql"], maxResults=max_results)
		results = [
			{
				"key": i.key,
				"summary": i.fields.summary,
				"status": i.fields.status.name,
				"assignee": i.fields.assignee.displayName if i.fields.assignee else "Unassigned",
			}
			for i in issues
		]
		return json.dumps({"count": len(results), "issues": results})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_add_comment(**kwargs):
	"""Add a comment to a Jira issue."""
	try:
		client, _ = _get_client()
		client.add_comment(kwargs["issue_key"], kwargs["comment"])
		return json.dumps({"ok": True, "issue_key": kwargs["issue_key"]})
	except Exception as e:
		return json.dumps({"error": str(e)})
