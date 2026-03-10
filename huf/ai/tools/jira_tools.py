"""
Jira integration tools for issue management.
Uses HUF Integration Settings for Jira credentials.
"""

import json
import frappe
import httpx
from huf.ai.tools.credentials import require_credential, get_credential, update_last_error


def _get_jira_config():
    """Get Jira configuration from Integration Settings."""
    service_name = "jira"
    server_url = get_credential(service_name, "server_url")
    username = get_credential(service_name, "username")
    token = get_credential(service_name, "token")
    
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


def handle_get_issue(**kwargs) -> str:
    """Retrieve details of a Jira issue."""
    service_name = "jira"
    try:
        issue_key = kwargs.get("issue_key")
        if not issue_key:
            return json.dumps({"success": False, "error": "issue_key is required"})

        data = _make_jira_request("GET", f"issue/{issue_key}")
        
        server_url = _get_jira_config()[0]
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
            "url": f"{server_url}/browse/{issue_key}"
        }
        
        return json.dumps({"success": True, "results": issue_data})
    except Exception as e:
        frappe.log_error(f"Jira Get Issue Error: {str(e)}", "Jira Tool")
        update_last_error(service_name, str(e))
        return json.dumps({"success": False, "error": str(e)})


def handle_create_issue(**kwargs) -> str:
    """Create a new Jira issue."""
    service_name = "jira"
    try:
        project_key = kwargs.get("project_key")
        summary = kwargs.get("summary")
        if not all([project_key, summary]):
            return json.dumps({"success": False, "error": "project_key and summary are required"})

        description = kwargs.get("description")
        issuetype = kwargs.get("issuetype", "Task")

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
        
        server_url = _get_jira_config()[0]
        issue_key = data.get("key")
        return json.dumps({
            "success": True, 
            "results": {
                "key": issue_key,
                "id": data.get("id"),
                "url": f"{server_url}/browse/{issue_key}"
            }
        })
    except Exception as e:
        frappe.log_error(f"Jira Create Issue Error: {str(e)}", "Jira Tool")
        update_last_error(service_name, str(e))
        return json.dumps({"success": False, "error": str(e)})


def handle_search_issues(**kwargs) -> str:
    """Search Jira issues using JQL query."""
    service_name = "jira"
    try:
        jql = kwargs.get("jql")
        if not jql:
            return json.dumps({"success": False, "error": "jql is required"})

        max_results = int(kwargs.get("max_results", 50))
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
            "results": {
                "total": data.get("total"),
                "count": len(issues),
                "issues": issues
            }
        })
    except Exception as e:
        frappe.log_error(f"Jira Search Error: {str(e)}", "Jira Tool")
        update_last_error(service_name, str(e))
        return json.dumps({"success": False, "error": str(e)})


def handle_add_comment(**kwargs) -> str:
    """Add a comment to a Jira issue."""
    service_name = "jira"
    try:
        issue_key = kwargs.get("issue_key")
        comment = kwargs.get("comment")
        if not all([issue_key, comment]):
            return json.dumps({"success": False, "error": "issue_key and comment are required"})

        payload = {"body": comment}
        data = _make_jira_request("POST", f"issue/{issue_key}/comment", json_data=payload)
        
        return json.dumps({
            "success": True,
            "results": {
                "comment_id": data.get("id"),
                "created": data.get("created"),
                "author": data.get("author", {}).get("displayName")
            }
        })
    except Exception as e:
        frappe.log_error(f"Jira Add Comment Error: {str(e)}", "Jira Tool")
        update_last_error(service_name, str(e))
        return json.dumps({"success": False, "error": str(e)})
