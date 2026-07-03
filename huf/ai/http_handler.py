import ipaddress
import json
import socket
from urllib.parse import urlparse

import frappe
import requests
from requests.exceptions import RequestException

ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}
MAX_RESPONSE_SIZE = 10 * 1024 * 1024  # 10MB

def _is_public_ip(ip_str: str) -> bool:
	"""Return True only if ip_str is a routable public address.

	Unwraps IPv4-mapped IPv6 (e.g. ::ffff:127.0.0.1) before classifying,
	and rejects loopback/private/link-local/reserved/multicast/unspecified
	for both IPv4 and IPv6.
	"""
	try:
		addr = ipaddress.ip_address(ip_str)
	except ValueError:
		# Not a parseable IP — fail closed.
		return False

	# Unwrap IPv4-mapped IPv6 so ::ffff:127.0.0.1 is judged as 127.0.0.1.
	mapped = getattr(addr, "ipv4_mapped", None)
	if mapped is not None:
		addr = mapped

	if (
		addr.is_private
		or addr.is_loopback
		or addr.is_link_local
		or addr.is_reserved
		or addr.is_multicast
		or addr.is_unspecified
	):
		return False
	return True


def validate_url(url):
	"""
	Validate URL to prevent SSRF and other attacks.

	Returns a tuple (is_valid, error_message).
	"""
	parsed = urlparse(url)

	# Allow only HTTP and HTTPS
	if parsed.scheme not in ("http", "https"):
		return False, "Only HTTP and HTTPS schemes are allowed"

	if not parsed.hostname:
		return False, "Invalid URL: no hostname"

	# Resolve hostname and reject if any resolved IP is private/internal.
	# NOTE: this does not prevent DNS rebinding — the request below re-resolves
	# independently. Rebinding mitigation is a known follow-up (see plan 002 notes).
	try:
		addr_info = socket.getaddrinfo(parsed.hostname, None)
		ips = {info[4][0] for info in addr_info}
	except socket.gaierror:
		return False, f"Cannot resolve hostname: {parsed.hostname}"

	for ip in ips:
		if not _is_public_ip(ip):
			return False, "Requests to private/internal addresses are not allowed"

	return True, None


@frappe.whitelist(allow_guest=True)
def handle_http_request(method, url, headers=None, params=None, data=None, json_data=None, tool_name=None):
	"""
	Generic HTTP request handler with support for tool-defined headers
	"""
	# Validate HTTP method
	if method.upper() not in ALLOWED_METHODS:
		return {
			"success": False,
			"error": f"HTTP method '{method}' is not allowed. Allowed methods: {', '.join(sorted(ALLOWED_METHODS))}",
		}

	try:
		tool_info = {}
		tool_allowed_for_guest = False

		if tool_name:
			try:
				tool_doc = frappe.get_doc("Agent Tool Function", tool_name)
				# Extract headers from tool's http_headers child table
				tool_headers = {}
				if hasattr(tool_doc, "http_headers") and tool_doc.http_headers:
					for header in tool_doc.http_headers:
						if header.key and header.value:
							tool_headers[header.key] = header.value

				tool_info = {
					"base_url": tool_doc.base_url,
					"headers": tool_headers,
				}
				tool_allowed_for_guest = bool(tool_doc.allowed_for_guest)
			except frappe.DoesNotExistError:
				return {
					"success": False,
					"error": f"Tool '{tool_name}' not found",
				}

		# Check if guest user is trying to use a tool that doesn't allow guest access
		if frappe.session.user == "Guest" and not tool_allowed_for_guest:
			return {
				"success": False,
				"error": "This tool does not allow guest access. Please log in or enable 'Allowed for Guest' on the tool.",
				"status_code": 403,
			}

		# Apply base URL if specified in tool
		final_url = url
		if tool_info.get("base_url"):
			# If the provided URL is relative, combine with base URL
			if not url.startswith(("http://", "https://")):
				final_url = tool_info["base_url"].rstrip("/") + "/" + url.lstrip("/")

		# Validate URL to prevent SSRF
		is_valid, error_msg = validate_url(final_url)
		if not is_valid:
			return {
				"success": False,
				"error": error_msg,
				"suggestion": "Ensure the URL points to a public, external service.",
			}

		# Merge tool headers with request headers
		# Tool headers come first, then request headers can override them
		tool_headers = tool_info.get("headers", {}) or {}
		request_headers = headers or {}
		final_headers = {**tool_headers, **request_headers}

		# Prepare request parameters
		request_kwargs = {
			"headers": final_headers,
			"params": params or {},
			"timeout": 30,
		}

		# Add data or json based on what's provided
		if data is not None:
			request_kwargs["data"] = data
		if json_data is not None:
			request_kwargs["json"] = json_data

		# Make the request, following redirects manually so each hop is
		# re-validated against the SSRF guard (allow_redirects=False).
		request_kwargs["allow_redirects"] = False
		current_url = final_url
		max_redirects = 5
		for _hop in range(max_redirects + 1):
			response = requests.request(method, current_url, **request_kwargs)
			if response.status_code not in (301, 302, 303, 307, 308):
				break
			location = response.headers.get("Location")
			if not location:
				break
			# Resolve relative redirects against the current URL.
			next_url = requests.compat.urljoin(current_url, location)
			is_valid, error_msg = validate_url(next_url)
			if not is_valid:
				return {
					"success": False,
					"error": f"Redirect blocked: {error_msg}",
					"suggestion": "The server attempted to redirect to a private/internal address.",
				}
			current_url = next_url
		else:
			# Loop exhausted without breaking — too many redirects.
			return {
				"success": False,
				"error": "Too many redirects (max 5)",
				"suggestion": "The URL redirects in a loop or exceeds the redirect limit.",
			}

		# Check response size — pre-check via Content-Length header, then verify actual content
		content_length = response.headers.get("Content-Length")
		if content_length and content_length.isdigit() and int(content_length) > MAX_RESPONSE_SIZE:
			return {
				"success": False,
				"error": "Response too large (Content-Length exceeds 10MB limit)",
				"status_code": response.status_code,
				"suggestion": "The API indicates a response larger than 10MB. Try requesting less data.",
			}

		if len(response.content) > MAX_RESPONSE_SIZE:
			return {
				"success": False,
				"error": "Response too large",
				"status_code": response.status_code,
				"suggestion": "The API response exceeds the 10MB size limit. Try requesting less data.",
			}

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
			"final_url": current_url,
		}

		# Add guidance for the AI if it's an error
		if response.status_code >= 400:
			result["suggestion"] = (
				"Check if the URL is correct and if you need to include authentication headers."
			)

		return result

	except RequestException as e:
		frappe.log_error(f"HTTP Request Error: {e!s}", "HTTP Handler")
		return {
			"success": False,
			"error": str(e),
			"suggestion": "Check the URL and network connection.",
			"status_code": getattr(e.response, "status_code", None) if hasattr(e, "response") else None,
		}


@frappe.whitelist(allow_guest=True)
def handle_get_request(url, headers=None, params=None, tool_name=None):
	"""
	Handle GET requests with tool-defined headers
	"""
	return handle_http_request("GET", url, headers=headers, params=params, tool_name=tool_name)


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
				"error": "Invalid JSON data provided",
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

	return handle_http_request(
		"POST", url, headers=headers, data=data, json_data=json_data, tool_name=tool_name
	)
