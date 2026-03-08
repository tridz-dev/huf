"""
GitHub integration tools for repository and issue management.
Uses HUF Integration Settings for GitHub credentials.
"""

import json
import frappe
import httpx
from typing import Optional, Dict, Any
from huf.ai.tools.credentials import require_credential, get_credential, update_last_error


GITHUB_API_BASE = "https://api.github.com"


def _get_github_headers():
    """Get GitHub API headers with token."""
    token = get_credential("github", "access_token")
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
    """
    List GitHub repositories for the authenticated user.
    
    Returns:
        JSON string with list of repositories
    """
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
        
        return json.dumps({"success": True, "count": len(repos), "repositories": repos})
    except Exception as e:
        error_msg = f"GitHub list repos error: {e}"
        frappe.log_error(error_msg)
        update_last_error("github", error_msg)
        return json.dumps({"error": str(e)})


def handle_get_repo(repo_name: str, **kwargs) -> str:
    """
    Get details of a GitHub repository.
    
    Args:
        repo_name: Repository full name (owner/repo)
    
    Returns:
        JSON string with repository details
    """
    try:
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
        
        return json.dumps({"success": True, "repository": repo_data})
    except Exception as e:
        error_msg = f"GitHub get repo error: {e}"
        frappe.log_error(error_msg)
        update_last_error("github", error_msg)
        return json.dumps({"error": str(e)})


def handle_create_issue(repo_name: str, title: str, body: str = None, **kwargs) -> str:
    """
    Create a GitHub issue.
    
    Args:
        repo_name: Repository full name (owner/repo)
        title: Issue title
        body: Issue body
    
    Returns:
        JSON string with created issue details
    """
    try:
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
        
        return json.dumps({"success": True, "issue": issue_data})
    except Exception as e:
        error_msg = f"GitHub create issue error: {e}"
        frappe.log_error(error_msg)
        update_last_error("github", error_msg)
        return json.dumps({"error": str(e)})


def handle_create_pull_request(repo_name: str, title: str, body: str, head: str, base: str, **kwargs) -> str:
    """
    Create a GitHub pull request.
    
    Args:
        repo_name: Repository full name (owner/repo)
        title: PR title
        body: PR description
        head: Head branch
        base: Base branch
    
    Returns:
        JSON string with created PR details
    """
    try:
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
        
        return json.dumps({"success": True, "pull_request": pr_data})
    except Exception as e:
        error_msg = f"GitHub create PR error: {e}"
        frappe.log_error(error_msg)
        update_last_error("github", error_msg)
        return json.dumps({"error": str(e)})


def handle_get_file_content(repo_name: str, path: str, **kwargs) -> str:
    """
    Get file content from a GitHub repository.
    
    Args:
        repo_name: Repository full name (owner/repo)
        path: File path in repository
    
    Returns:
        JSON string with file content
    """
    try:
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
        
        return json.dumps({"success": True, "file": file_data})
    except Exception as e:
        error_msg = f"GitHub get file error: {e}"
        frappe.log_error(error_msg)
        update_last_error("github", error_msg)
        return json.dumps({"error": str(e)})


def handle_search_code(query: str, **kwargs) -> str:
    """
    Search code across GitHub.
    
    Args:
        query: Code search query
    
    Returns:
        JSON string with search results
    """
    try:
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
        error_msg = f"GitHub search code error: {e}"
        frappe.log_error(error_msg)
        update_last_error("github", error_msg)
        return json.dumps({"error": str(e)})
