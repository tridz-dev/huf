import json
import socket  # noqa: F401  (tests patch http_handler.socket.getaddrinfo)

import frappe
import requests
from requests.exceptions import RequestException
from frappe.rate_limiter import rate_limit

from frappe import _
from huf.ai.outbound.ssrf import (  # noqa: F401
	PinnedDNSAdapter,
	_close_response,
	_is_public_ip,
	_make_pinned_connection,
	_send,
	extract_origin,
	resolve_public_ips,
	validate_url,
)
from huf.permissions import has_capability

ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}
MAX_RESPONSE_SIZE = 10 * 1024 * 1024  # 10MB
DEFAULT_TIMEOUT = 30


def _http_request(method, url, **kwargs):
    """
    Internal HTTP request helper for non-whitelisted Huf code.

    Applies SSRF validation and a default timeout. Prefer this over raw
    requests/httpx calls so security policy is applied consistently.
    """
    if method.upper() not in ALLOWED_METHODS:
        raise ValueError(f"HTTP method '{method}' is not allowed")

    ips, error_msg = resolve_public_ips(url)
    if error_msg:
        raise ValueError(error_msg)

    request_kwargs = {"timeout": kwargs.get("timeout", DEFAULT_TIMEOUT)}
    request_kwargs.update(kwargs)

    # allow_redirects is forced off by _send's callers; this helper never follows redirects blindly.
    return _send(method, url, ips, **request_kwargs)

MAX_TIMEOUT = 600


def _clamp_timeout(value):
	"""Seconds in [1, 600]; None, non-numeric, NaN and inf fall back to the 30 s default."""
	try:
		seconds = float(value)
	except (TypeError, ValueError):
		return DEFAULT_TIMEOUT
	if seconds != seconds or seconds in (float("inf"), float("-inf")):
		return DEFAULT_TIMEOUT
	return min(max(seconds, 1), MAX_TIMEOUT)


@rate_limit(key="tool_name", limit=100, seconds=60)
@frappe.whitelist(allow_guest=True)
def handle_http_request(method, url, headers=None, params=None, data=None, json_data=None, tool_name=None):
	"""
	Generic HTTP request handler with support for tool-defined headers.

	No timeout parameter here: this endpoint is reachable by guests, so the limit is
	not caller-controlled. Server-side code passes one through ``_run_http_request``.
	"""
	return _run_http_request(method, url, headers, params, data, json_data, tool_name)


def _run_http_request(method, url, headers=None, params=None, data=None, json_data=None, tool_name=None, timeout=None):
	# Check agent.use capability (guest sessions are exempt)
	if frappe.session.user != "Guest" and not has_capability(frappe.session.user, "agent.use"):
		frappe.throw(
			_("You are not authorized to use HTTP tools."),
			frappe.PermissionError
		)

	# Validate HTTP method
	if method.upper() not in ALLOWED_METHODS:
		return {
			"success": False,
			"error": f"HTTP method '{method}' is not allowed. Allowed methods: {', '.join(sorted(ALLOWED_METHODS))}",
		}

	sessions = []
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
						header_value = header.get_password("value")
						if header.key and header_value:
							tool_headers[header.key] = header_value

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

		# Validate URL to prevent SSRF. The host is resolved once here; the request connects to these addresses.
		pinned_ips, error_msg = resolve_public_ips(final_url)
		if error_msg:
			return {
				"success": False,
				"error": error_msg,
				"suggestion": "Ensure the URL points to a public, external service.",
			}

		# Merge tool headers with request headers, checking origin binding
		tool_headers = tool_info.get("headers", {}) or {}
		request_headers = headers or {}

		# Only attach tool headers if the final URL's origin matches the tool's base_url origin
		base_url = tool_info.get("base_url", "")
		if base_url:
			base_url_origin = extract_origin(base_url)
			final_url_origin = extract_origin(final_url)
			if base_url_origin != final_url_origin:
				# Cross-origin: do not attach tool headers and strip Authorization-class headers
				tool_headers = {}
				auth_headers = {
					"authorization", "proxy-authorization", "x-api-key",
					"x-auth-token", "authorization-signature"
				}
				request_headers = {
					k: v for k, v in request_headers.items()
					if k.lower() not in auth_headers
				}

		final_headers = {**tool_headers, **request_headers}

		# Prepare request parameters
		request_kwargs = {
			"headers": final_headers,
			"params": params or {},
			"timeout": _clamp_timeout(timeout),
			"stream": True,  # Stream response body to enforce size cap during read
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
		base_url_origin = extract_origin(base_url) if base_url else None
		auth_headers = {
			"authorization", "proxy-authorization", "x-api-key",
			"x-auth-token", "authorization-signature"
		}
		for _hop in range(max_redirects + 1):
			response = _send(method, current_url, pinned_ips, **request_kwargs)
			sessions.append(response)
			if response.status_code not in (301, 302, 303, 307, 308):
				break
			location = response.headers.get("Location")
			if not location:
				break
			# Resolve relative redirects against the current URL.
			next_url = requests.compat.urljoin(current_url, location)
			# Every hop is resolved and checked once, and connected to at the checked addresses.
			pinned_ips, error_msg = resolve_public_ips(next_url)
			if error_msg:
				return {
					"success": False,
					"error": f"Redirect blocked: {error_msg}",
					"suggestion": "The server attempted to redirect to a private/internal address.",
				}
			# Check if redirect changes origin; strip auth headers if so
			if base_url_origin:
				next_url_origin = extract_origin(next_url)
				if next_url_origin != base_url_origin:
					# Cross-origin redirect: strip Authorization-class headers
					request_kwargs["headers"] = {
						k: v for k, v in request_kwargs["headers"].items()
						if k.lower() not in auth_headers
					}
			current_url = next_url
		else:
			# Loop exhausted without breaking — too many redirects.
			return {
				"success": False,
				"error": "Too many redirects (max 5)",
				"suggestion": "The URL redirects in a loop or exceeds the redirect limit.",
			}

		# Check response size — pre-check via Content-Length header (fast-path)
		content_length = response.headers.get("Content-Length")
		if content_length and content_length.isdigit() and int(content_length) > MAX_RESPONSE_SIZE:
			return {
				"success": False,
				"error": "Response too large (Content-Length exceeds 10MB limit)",
				"status_code": response.status_code,
				"suggestion": "The API indicates a response larger than 10MB. Try requesting less data.",
			}

		# Stream response body and enforce size cap during read
		total_read = 0
		chunks = []
		for chunk in response.iter_content(chunk_size=8192):
			if not chunk:
				continue
			total_read += len(chunk)
			if total_read > MAX_RESPONSE_SIZE:
				return {
					"success": False,
					"error": "Response too large",
					"status_code": response.status_code,
					"suggestion": "The API response exceeds the 10MB size limit. Try requesting less data.",
				}
			chunks.append(chunk)

		response_body = b"".join(chunks)

		# Parse JSON response from accumulated body, fall back to text
		try:
			response_data = json.loads(response_body)
		except (json.JSONDecodeError, ValueError):
			try:
				response_data = response_body.decode(errors="replace")
			except Exception:
				response_data = str(response_body)

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
		frappe.log_error(title="HTTP Handler", message=f"HTTP Request Error: {e!s}")
		return {
			"success": False,
			"error": str(e),
			"suggestion": "Check the URL and network connection.",
			"status_code": getattr(e.response, "status_code", None) if hasattr(e, "response") else None,
		}
	finally:
		for _response in sessions:
			_close_response(_response)


@rate_limit(key="tool_name", limit=100, seconds=60)
@frappe.whitelist(allow_guest=True)
def handle_get_request(url, headers=None, params=None, tool_name=None):
	"""
	Handle GET requests with tool-defined headers
	"""
	# Check agent.use capability (guest sessions are exempt)
	if frappe.session.user != "Guest" and not has_capability(frappe.session.user, "agent.use"):
		frappe.throw(
			_("You are not authorized to use HTTP tools."),
			frappe.PermissionError
		)

	return handle_http_request("GET", url, headers=headers, params=params, tool_name=tool_name)


@rate_limit(key="tool_name", limit=100, seconds=60)
@frappe.whitelist(allow_guest=True)
def handle_post_request(url, headers=None, data=None, json_data=None, tool_name=None):
	"""
	Handle POST requests with JSON data support
	"""
	# Check agent.use capability (guest sessions are exempt)
	if frappe.session.user != "Guest" and not has_capability(frappe.session.user, "agent.use"):
		frappe.throw(
			_("You are not authorized to use HTTP tools."),
			frappe.PermissionError
		)

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


HTTP_TOOL_NAME = "http_request"
MAX_TOOL_BODY_CHARS = 64 * 1024  # 64KB returned to the Flow / agent
_TOOL_HEADER_ALLOWLIST = {
	"content-type", "content-length", "content-encoding", "location", "etag",
	"last-modified", "cache-control", "retry-after", "date", "link",
}


def _coerce_mapping(value, label):
	"""Accept a dict or a JSON-object string (Flow templates often yield strings)."""
	if value in (None, ""):
		return None, None
	if isinstance(value, dict):
		return value, None
	if isinstance(value, str):
		try:
			parsed = json.loads(value)
		except (json.JSONDecodeError, ValueError):
			return None, f"{label} must be a JSON object"
		if isinstance(parsed, dict):
			return parsed, None
	return None, f"{label} must be a JSON object"


def _timeout_value(seconds):
	"""A flow step's "Stop waiting after" limit in seconds, or None for the 30 s default."""
	try:
		value = float(seconds)
	except (TypeError, ValueError):
		return None
	return min(value, 600.0) if value > 0 else None


def http_request(url, method="GET", headers=None, body=None, timeout_seconds=None):
	"""Built-in ``http_request`` tool: thin, safe wrapper over ``handle_http_request``.

	Reuses its SSRF guard (public IPs only, http/https only), manual redirect
	handling with per-hop re-validation, method allow-list, ``agent.use``
	capability check and the 10MB streaming cap. The tool row has
	``allowed_for_guest=0`` and the wrapper blocks Guest outright.

	Returns a JSON string: ``success`` is True only for 2xx. Non-2xx and any
	guard/transport failure yield ``success: false`` (with ``status_code`` /
	``error``) so the Flow engine can mark the node failed.
	"""
	if frappe.session.user == "Guest":
		return json.dumps({"success": False, "error": "Guest users cannot use http_request.", "status_code": 403})

	if not url or not isinstance(url, str):
		return json.dumps({"success": False, "error": "url is required"})

	method = str(method or "GET").upper()
	req_headers, err = _coerce_mapping(headers, "headers")
	if err:
		return json.dumps({"success": False, "error": err})

	data = json_data = None
	if body not in (None, ""):
		if isinstance(body, (dict, list)):
			json_data = body
		elif isinstance(body, str):
			try:
				parsed = json.loads(body)
			except (json.JSONDecodeError, ValueError):
				parsed = None
			if isinstance(parsed, (dict, list)):
				json_data = parsed
			else:
				data = body
		else:
			data = str(body)

	# Call the undecorated function: the rate limiter is keyed to web requests and
	# this runs inside a worker. Guard behaviour is unchanged.
	result = _run_http_request(
		method,
		url,
		headers=req_headers,
		data=data,
		json_data=json_data,
		tool_name=HTTP_TOOL_NAME,
		timeout=_timeout_value(timeout_seconds),
	)

	if not isinstance(result, dict):
		return json.dumps({"success": False, "error": "Unexpected response from HTTP handler"})

	status = result.get("status_code")
	if not result.get("success"):
		out = {"success": False, "error": result.get("error") or "Request failed"}
		if status is not None:
			out["status_code"] = status
		return json.dumps(out, default=str)

	payload = result.get("data")
	body_text = payload if isinstance(payload, str) else json.dumps(payload, default=str)
	truncated = len(body_text) > MAX_TOOL_BODY_CHARS
	if truncated:
		body_text = body_text[:MAX_TOOL_BODY_CHARS]

	resp_headers = {
		k: v for k, v in (result.get("headers") or {}).items() if str(k).lower() in _TOOL_HEADER_ALLOWLIST
	}
	ok = isinstance(status, int) and 200 <= status < 300
	out = {
		"success": ok,
		"status_code": status,
		"headers": resp_headers,
		"body": body_text,
		"truncated": truncated,
		"final_url": result.get("final_url"),
	}
	if not ok:
		out["error"] = f"HTTP {status}"
	return json.dumps(out, default=str)
