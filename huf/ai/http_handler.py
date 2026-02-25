import frappe
import requests
from requests.exceptions import RequestException
import json
from urllib.parse import urlparse


def validate_url(url, tool_name=None):
    """
    Validate URL to prevent SSRF and other attacks
    """
    from urllib.parse import urlparse
    import re
    
    # Parse the URL
    parsed = urlparse(url)
    
    # If tool has a base URL, validate against it
    if tool_name:
        tool_doc = frappe.get_doc("Agent Tool Function", tool_name)
        if tool_doc.base_url:
            tool_parsed = urlparse(tool_doc.base_url)
            if parsed.netloc != tool_parsed.netloc:
                return False
    
    # Block private IP addresses
    if parsed.hostname:
        # Regex to match private IPs
        private_ip_pattern = re.compile(
            r'^(127\.|10\.|172\.1[6-9]\.|172\.2[0-9]\.|172\.3[0-1]\.|192\.168\.)'
        )
        
        if private_ip_pattern.match(parsed.hostname):
            return False
            
        if parsed.hostname in ['localhost', '127.0.0.1', '::1']:
            return False
    
    # Allow only HTTP and HTTPS
    if parsed.scheme not in ['http', 'https']:
        return False
        
    
    return True


@frappe.whitelist(allow_guest=True)
def handle_http_request(method, url, headers=None, params=None, data=None, json_data=None, tool_name=None):
    """
    Generic HTTP request handler with support for tool-defined headers
    """
    try:
        tool_info = {}
        tool_allowed_for_guest = False
        
        if tool_name:
            try:
                tool_doc = frappe.get_doc("Agent Tool Function", tool_name)
                # Extract headers from tool's http_headers child table
                tool_headers = {}
                if hasattr(tool_doc, 'http_headers') and tool_doc.http_headers:
                    for header in tool_doc.http_headers:
                        if header.key and header.value:
                            tool_headers[header.key] = header.value
                
                tool_info = {
                    "base_url": tool_doc.base_url,
                    "headers": tool_headers
                }
                tool_allowed_for_guest = bool(tool_doc.allowed_for_guest)
            except frappe.DoesNotExistError:
                return {
                    "success": False,
                    "error": f"Tool '{tool_name}' not found"
                }
        
        # Check if guest user is trying to use a tool that doesn't allow guest access
        if frappe.session.user == "Guest" and not tool_allowed_for_guest:
            return {
                "success": False,
                "error": "This tool does not allow guest access. Please log in or enable 'Allowed for Guest' on the tool.",
                "status_code": 403
            }
        
        # Apply base URL if specified in tool
        final_url = url
        if tool_info.get("base_url"):
            # If the provided URL is relative, combine with base URL
            if not url.startswith(('http://', 'https://')):
                final_url = tool_info["base_url"].rstrip('/') + '/' + url.lstrip('/')
        
        # Merge tool headers with request headers
        # Tool headers come first, then request headers can override them
        tool_headers = tool_info.get("headers", {}) or {}
        request_headers = headers or {}
        final_headers = {**tool_headers, **request_headers}
        
        # Prepare request parameters
        request_kwargs = {
            'headers': final_headers,
            'params': params or {},
            'timeout': 30
        }
        
        # Add data or json based on what's provided
        if data is not None:
            request_kwargs['data'] = data
        if json_data is not None:
            request_kwargs['json'] = json_data
            
        # Make the request
        response = requests.request(method, final_url, **request_kwargs)
        
        # Try to parse JSON response, fall back to text
        try:
            response_data = response.json()
        except ValueError:
            response_data = response.text
            
        # Return standardized response
        result = {
            "success": True,
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "data": response_data,
            "final_url": final_url
        }
        
        # Add guidance for the AI if it's an error
        if response.status_code >= 400:
            result["suggestion"] = "Check if the URL is correct and if you need to include authentication headers."
            
        return result
        
    except RequestException as e:
        frappe.log_error(f"HTTP Request Error: {str(e)}", "HTTP Handler")
        return {
            "success": False,
            "error": str(e),
            "suggestion": "Check the URL and network connection.",
            "status_code": getattr(e.response, 'status_code', None) if hasattr(e, 'response') else None
        }

@frappe.whitelist(allow_guest=True)
def handle_get_request(url, headers=None, params=None, tool_name=None):
    """
    Handle GET requests with tool-defined headers
    """
    return handle_http_request('GET', url, headers=headers, params=params, tool_name=tool_name)


@frappe.whitelist(allow_guest=True)
def handle_post_request(url, headers=None, data=None, json_data=None, tool_name=None):
    """
    Handle POST requests with JSON data support
    """
    # Convert string JSON to dict if needed
    if isinstance(json_data, str):
        try:
            json_data = json.loads(json_data)
        except json.JSONDecodeError:
            return {
                "success": False,
                "error": "Invalid JSON data provided"
            }
    
    # If data is provided but json_data is not, try to parse data as JSON
    if data is not None and json_data is None:
        if isinstance(data, str):
            try:
                json_data = json.loads(data)
                data = None  # Clear data since we're using json_data now
            except json.JSONDecodeError:
                # If it's not JSON, keep it as form data
                pass
    
    return handle_http_request('POST', url, headers=headers, data=data, json_data=json_data, tool_name=tool_name)