"""
Jira integration tools for issue management.
Uses HUF Integration Settings for Jira credentials.
"""

import json
import frappe
import httpx
from typing import Optional, Dict, Any
from huf.ai.tools.credentials import require_credential, get_credential, update_last_error


def _get_jira_config():
    """Get Jira configuration from Integration Settings."""
    server_url = get_credential("jira", "server_url")
    username = get_credential("jira", "username")
    token = get_credential("jira", "token")
    
    if not all([server_url, username, token]):
        raise ValueError("Jira credentials not fully configured (server_url, username, token required)")
    
    return server_url.rstrip("/"), username, token


def _make_jira_request(method: str, endpoint: str, json_data=None, params=None):
    """Make authenticated request to Jira API."""
    server_url, username, token = _get_jira_config()
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    auth = (username, token)
    url = f"{server_url}/rest/api/2/{endpoint}"
    
    response = httpx.request(
        method,
        url,
        headers=headers,
        auth=auth,
        json=json_data,
        params=params,
        timeout=30
    )
    response.raise_for_status()
    
    return response.json() if response.text else {}


def handle_get_issue(issue_key: str, **kwargs) -> str:
    """
    Retrieve details of a Jira issue.
    
    Args:
        issue_key: Jira issue key (e.g. PROJ-123)
    
    Returns:
        JSON string with issue details
    """
    try:
        data = _make_jira_request("GET", f"issue/{issue_key}")
        
        # Extract key fields
        issue_data = {
            "key": data.get("key"),
            "summary": data.get("fields", {}).get("summary"),
            "description": data.get("fields", {}).get("description"),
            "status": data.get("fields", {}).get("status", {}).get("name"),
            "priority": data.get("fields", {}).get("priority", {}).get("name"),
            "assignee": data.get("fields", {}).get("assignee", {}).get("displayName") if data.get("fields", {}).get("assignee") else None,
            "reporter": data.get("fields", {}).get("reporter", {}).get("displayName"),
            "created": data.get("fields", {}).get("created"),
            "updated": data.get("fields", {}).get("updated"),
            "issue_type": data.get("fields", {}).get("issuetype", {}).get("name"),
            "url": f"{_get_jira_config()[0]}/browse/{issue_key}"
        }
        
        return json.dumps({"success": True, "issue": issue_data})
    except Exception as e:
        error_msg = f"Jira get issue error: {e}"
        frappe.log_error(error_msg)
        update_last_error("jira", error_msg)
        return json.dumps({"error": str(e)})


def handle_create_issue(project_key: str, summary: str, description: str = None, issuetype: str = "Task", **kwargs) -> str:
    """
    Create a new Jira issue.
    
    Args:
        project_key: Jira project key (e.g. PROJ)
        summary: Issue summary/title
        description: Issue description
        issuetype: Issue type (default: Task)
    
    Returns:
        JSON string with created issue details
    """
    try:
        payload = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "issuetype": {"name": issuetype}
            }
        }
        
        if description:
            payload["fields"]["description"] = description
        
        data = _make_jira_request("POST", "issue", json_data=payload)
        
        issue_key = data.get("key")
        issue_data = {
            "key": issue_key,
            "id": data.get("id"),
            "self": data.get("self"),
            "url": f"{_get_jira_config()[0]}/browse/{issue_key}"
        }
        
        return json.dumps({"success": True, "issue": issue_data})
    except Exception as e:
        error_msg = f"Jira create issue error: {e}"
        frappe.log_error(error_msg)
        update_last_error("jira", error_msg)
        return json.dumps({"error": str(e)})


def handle_search_issues(jql: str, max_results: int = 50, **kwargs) -> str:
    """
    Search Jira issues using JQL query.
    
    Args:
        jql: JQL query string
        max_results: Max results (default 50)
    
    Returns:
        JSON string with search results
    """
    try:
        params = {
            "jql": jql,
            "maxResults": max_results,
            "fields": "summary,status,assignee,priority,created,updated,issuetype"
        }
        
        data = _make_jira_request("GET", "search", params=params)
        
        issues = []
        for issue in data.get("issues", []):
            fields = issue.get("fields", {})
            issues.append({
                "key": issue.get("key"),
                "summary": fields.get("summary"),
                "status": fields.get("status", {}).get("name"),
                "priority": fields.get("priority", {}).get("name"),
                "assignee": fields.get("assignee", {}).get("displayName") if fields.get("assignee") else None,
                "created": fields.get("created"),
                "updated": fields.get("updated"),
                "issue_type": fields.get("issuetype", {}).get("name")
            })
        
        return json.dumps({
            "success": True,
            "total": data.get("total"),
            "count": len(issues),
            "issues": issues
        })
    except Exception as e:
        error_msg = f"Jira search error: {e}"
        frappe.log_error(error_msg)
        update_last_error("jira", error_msg)
        return json.dumps({"error": str(e)})


def handle_add_comment(issue_key: str, comment: str, **kwargs) -> str:
    """
    Add a comment to a Jira issue.
    
    Args:
        issue_key: Jira issue key
        comment: Comment text
    
    Returns:
        JSON string with result
    """
    try:
        payload = {
            "body": comment
        }
        
        data = _make_jira_request("POST", f"issue/{issue_key}/comment", json_data=payload)
        
        return json.dumps({
            "success": True,
            "comment_id": data.get("id"),
            "created": data.get("created"),
            "author": data.get("author", {}).get("displayName")
        })
    except Exception as e:
        error_msg = f"Jira add comment error: {e}"
        frappe.log_error(error_msg)
        update_last_error("jira", error_msg)
        return json.dumps({"error": str(e)})
