"""
GitHub integration tools for repository and issue management.
Uses HUF Integration Settings for GitHub credentials.
"""

import json
import frappe
import httpx
from huf.ai.tools.credentials import require_credential, get_credential, update_last_error


GITHUB_API_BASE = "https://api.github.com"


def _get_github_headers():
    """Get GitHub API headers with token."""
    service_name = "github"
    token = get_credential(service_name, "access_token")
    if not token:
        raise ValueError("GitHub access token not configured")
    
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json"
    }


def _make_github_request(method: str, endpoint: str, json_data=None, params=None):
    """Make authenticated request to GitHub API."""
    headers = _get_github_headers()
    url = f"{GITHUB_API_BASE}/{endpoint}"
    
    response = httpx.request(
        method,
        url,
        headers=headers,
        json=json_data,
        params=params,
        timeout=30
    )
    response.raise_for_status()
    
    return response.json() if response.text else {}


def handle_list_repos(**kwargs) -> str:
    """List GitHub repositories for the authenticated user."""
    service_name = "github"
    try:
        data = _make_github_request("GET", "user/repos", params={"sort": "updated", "per_page": 30})
        
        repos = []
        for repo in data:
            repos.append({
                "name": repo.get("name"),
                "full_name": repo.get("full_name"),
                "description": repo.get("description"),
                "url": repo.get("html_url"),
                "stars": repo.get("stargazers_count"),
                "forks": repo.get("forks_count"),
                "language": repo.get("language"),
                "private": repo.get("private"),
                "updated_at": repo.get("updated_at")
            })
        
        return json.dumps({
            "success": True, 
            "count": len(repos), 
            "results": repos
        })
    except Exception as e:
        error_msg = f"GitHub List Repos Error: {str(e)}"
        frappe.log_error(error_msg, "GitHub Tool")
        update_last_error(service_name, error_msg)
        return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_get_repo(**kwargs) -> str:
    """Get details of a GitHub repository."""
    service_name = "github"
    try:
        repo_name = kwargs.get("repo_name")
        if not repo_name:
            return json.dumps({"success": False, "error": "repo_name is required"}, default=str)

        data = _make_github_request("GET", f"repos/{repo_name}")
        
        repo_data = {
            "name": data.get("name"),
            "full_name": data.get("full_name"),
            "description": data.get("description"),
            "url": data.get("html_url"),
            "stars": data.get("stargazers_count"),
            "forks": data.get("forks_count"),
            "open_issues": data.get("open_issues_count"),
            "language": data.get("language"),
            "private": data.get("private"),
            "default_branch": data.get("default_branch"),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
            "owner": data.get("owner", {}).get("login")
        }
        
        return json.dumps({
            "success": True, 
            "results": repo_data
        })
    except Exception as e:
        error_msg = f"GitHub Get Repo Error: {str(e)}"
        frappe.log_error(error_msg, "GitHub Tool")
        update_last_error(service_name, error_msg)
        return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_create_issue(**kwargs) -> str:
    """Create a GitHub issue."""
    service_name = "github"
    try:
        repo_name = kwargs.get("repo_name")
        title = kwargs.get("title")
        if not all([repo_name, title]):
            return json.dumps({"success": False, "error": "repo_name and title are required"}, default=str)

        body = kwargs.get("body")
        payload = {"title": title}
        if body:
            payload["body"] = body
        
        data = _make_github_request("POST", f"repos/{repo_name}/issues", json_data=payload)
        
        issue_data = {
            "number": data.get("number"),
            "title": data.get("title"),
            "url": data.get("html_url"),
            "state": data.get("state"),
            "created_at": data.get("created_at"),
            "author": data.get("user", {}).get("login")
        }
        
        return json.dumps({
            "success": True, 
            "results": issue_data
        })
    except Exception as e:
        error_msg = f"GitHub Create Issue Error: {str(e)}"
        frappe.log_error(error_msg, "GitHub Tool")
        update_last_error(service_name, error_msg)
        return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_create_pull_request(**kwargs) -> str:
    """Create a GitHub pull request."""
    service_name = "github"
    try:
        repo_name = kwargs.get("repo_name")
        title = kwargs.get("title")
        body = kwargs.get("body")
        head = kwargs.get("head")
        base = kwargs.get("base")
        if not all([repo_name, title, body, head, base]):
            return json.dumps({"success": False, "error": "repo_name, title, body, head, and base are required"}, default=str)

        payload = {
            "title": title,
            "body": body,
            "head": head,
            "base": base
        }
        
        data = _make_github_request("POST", f"repos/{repo_name}/pulls", json_data=payload)
        
        pr_data = {
            "number": data.get("number"),
            "title": data.get("title"),
            "url": data.get("html_url"),
            "state": data.get("state"),
            "head": data.get("head", {}).get("ref"),
            "base": data.get("base", {}).get("ref"),
            "created_at": data.get("created_at"),
            "author": data.get("user", {}).get("login")
        }
        
        return json.dumps({
            "success": True, 
            "results": pr_data
        })
    except Exception as e:
        error_msg = f"GitHub Create PR Error: {str(e)}"
        frappe.log_error(error_msg, "GitHub Tool")
        update_last_error(service_name, error_msg)
        return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_get_file_content(**kwargs) -> str:
    """Get file content from a GitHub repository."""
    service_name = "github"
    try:
        repo_name = kwargs.get("repo_name")
        path = kwargs.get("path")
        if not all([repo_name, path]):
            return json.dumps({"success": False, "error": "repo_name and path are required"}, default=str)

        data = _make_github_request("GET", f"repos/{repo_name}/contents/{path}")
        
        import base64
        content = base64.b64decode(data.get("content", "")).decode("utf-8") if data.get("content") else ""
        
        file_data = {
            "name": data.get("name"),
            "path": data.get("path"),
            "sha": data.get("sha"),
            "size": data.get("size"),
            "url": data.get("html_url"),
            "content": content,
            "encoding": data.get("encoding")
        }
        
        return json.dumps({
            "success": True, 
            "results": file_data
        })
    except Exception as e:
        error_msg = f"GitHub Get File Content Error: {str(e)}"
        frappe.log_error(error_msg, "GitHub Tool")
        update_last_error(service_name, error_msg)
        return json.dumps({"success": False, "error": str(e)}, default=str)


def handle_search_code(**kwargs) -> str:
    """Search code across GitHub."""
    service_name = "github"
    try:
        query = kwargs.get("query")
        if not query:
            return json.dumps({"success": False, "error": "query is required"}, default=str)

        data = _make_github_request("GET", "search/code", params={"q": query, "per_page": 30})
        
        items = []
        for item in data.get("items", []):
            items.append({
                "name": item.get("name"),
                "path": item.get("path"),
                "repository": item.get("repository", {}).get("full_name"),
                "url": item.get("html_url"),
                "score": item.get("score")
            })
        
        return json.dumps({
            "success": True,
            "total_count": data.get("total_count"),
            "count": len(items),
            "results": items
        })
    except Exception as e:
        error_msg = f"GitHub Search Code Error: {str(e)}"
        frappe.log_error(error_msg, "GitHub Tool")
        update_last_error(service_name, error_msg)
        return json.dumps({"success": False, "error": str(e)}, default=str)
