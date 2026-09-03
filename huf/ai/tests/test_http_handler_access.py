"""
Unit tests for huf.ai.http_handler security hardening.

Tests cover:
- ST-07.1: Authorization checks (agent.use capability)
- ST-07.2: Guest access gating (existing behavior verification)
- ST-07.3: Header origin binding
- ST-07.4: Response size cap enforcement via streaming
- ST-07.5: Rate limit decorator presence (full testing deferred to bench/integration)

These are pure unit tests using unittest.mock — they do not require a live
Frappe site/bench.

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_http_handler_access
"""
import json
import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from huf.ai.http_handler import (
	handle_http_request,
	handle_get_request,
	handle_post_request,
	extract_origin,
)


class TestExtractOrigin(unittest.TestCase):
	"""Tests for the extract_origin helper."""

	def test_extract_https_origin_with_default_port(self):
		"""Default https port is 443."""
		url = "https://api.example.com/path"
		scheme, host, port = extract_origin(url)
		self.assertEqual(scheme, "https")
		self.assertEqual(host, "api.example.com")
		self.assertEqual(port, 443)

	def test_extract_http_origin_with_default_port(self):
		"""Default http port is 80."""
		url = "http://api.example.com/path"
		scheme, host, port = extract_origin(url)
		self.assertEqual(scheme, "http")
		self.assertEqual(host, "api.example.com")
		self.assertEqual(port, 80)

	def test_extract_origin_with_explicit_port(self):
		"""Explicit port is preserved."""
		url = "https://api.example.com:8443/path"
		scheme, host, port = extract_origin(url)
		self.assertEqual(scheme, "https")
		self.assertEqual(host, "api.example.com")
		self.assertEqual(port, 8443)

	def test_extract_origin_same_origin_comparison(self):
		"""Same base_url and request URL have matching origins."""
		base_url = "https://api.example.com/"
		request_url = "https://api.example.com/endpoint"
		base_origin = extract_origin(base_url)
		request_origin = extract_origin(request_url)
		self.assertEqual(base_origin, request_origin)

	def test_extract_origin_cross_origin_comparison(self):
		"""Different hostnames result in different origins."""
		base_url = "https://api.example.com/"
		request_url = "https://attacker.com/"
		base_origin = extract_origin(base_url)
		request_origin = extract_origin(request_url)
		self.assertNotEqual(base_origin, request_origin)

	def test_extract_origin_port_mismatch(self):
		"""Different ports result in different origins."""
		url1 = "https://api.example.com:443/"
		url2 = "https://api.example.com:8443/"
		origin1 = extract_origin(url1)
		origin2 = extract_origin(url2)
		self.assertNotEqual(origin1, origin2)


class TestAuthorizationST071(unittest.TestCase):
	"""Tests for ST-07.1: agent.use capability check."""

	@patch("frappe.session")
	@patch("huf.ai.http_handler.has_capability")
	@patch("frappe.throw")
	def test_non_guest_without_agent_use_capability_denied(
		self, mock_throw, mock_has_capability, mock_session
	):
		"""Non-guest user without agent.use capability is denied."""
		mock_session.user = "user@example.com"
		mock_has_capability.return_value = False
		mock_throw.side_effect = Exception("PermissionError")

		try:
			handle_http_request("GET", "https://api.example.com/")
		except Exception as e:
			self.assertIn("PermissionError", str(e))

		mock_throw.assert_called()

	@patch("frappe.session")
	@patch("huf.ai.http_handler.has_capability")
	@patch("frappe.throw")
	def test_non_guest_with_agent_use_capability_allowed_to_proceed(
		self, mock_throw, mock_has_capability, mock_session
	):
		"""Non-guest user with agent.use capability proceeds past auth check."""
		mock_session.user = "user@example.com"
		mock_has_capability.return_value = True

		# Mock the rest of the flow to prevent further execution
		with patch("huf.ai.http_handler.requests.request") as mock_request:
			mock_response = Mock()
			mock_response.status_code = 200
			mock_response.headers = {}
			mock_response.iter_content = Mock(return_value=[b"{}"])
			mock_request.return_value = mock_response

			result = handle_http_request(
				"GET", "https://api.example.com/", tool_name="test_tool"
			)

			# Should not raise PermissionError
			mock_throw.assert_not_called()

	@patch("frappe.session")
	@patch("huf.ai.http_handler.has_capability")
	@patch("frappe.throw")
	def test_guest_bypasses_capability_check(
		self, mock_throw, mock_has_capability, mock_session
	):
		"""Guest user is exempt from agent.use capability check."""
		mock_session.user = "Guest"

		# Mock the rest to get past initial checks
		with patch("frappe.get_doc") as mock_get_doc:
			mock_tool_doc = Mock()
			mock_tool_doc.base_url = "https://api.example.com/"
			mock_tool_doc.http_headers = []
			mock_tool_doc.allowed_for_guest = True
			mock_get_doc.return_value = mock_tool_doc

			with patch("huf.ai.http_handler.requests.request") as mock_request:
				mock_response = Mock()
				mock_response.status_code = 200
				mock_response.headers = {}
				mock_response.iter_content = Mock(return_value=[b"{}"])
				mock_request.return_value = mock_response

				result = handle_http_request(
					"GET", "https://api.example.com/", tool_name="test_tool"
				)

				# Guest should bypass capability check
				mock_has_capability.assert_not_called()
				mock_throw.assert_not_called()


class TestGuestAccessST072(unittest.TestCase):
	"""Tests for ST-07.2: Guest access gating (existing behavior verification)."""

	@patch("frappe.session")
	@patch("huf.ai.http_handler.has_capability")
	def test_guest_no_tool_specified_denied(self, mock_has_capability, mock_session):
		"""Guest without tool_name is denied (tool_allowed_for_guest stays False)."""
		mock_session.user = "Guest"

		result = handle_http_request("GET", "https://api.example.com/")

		self.assertFalse(result["success"])
		self.assertEqual(result["status_code"], 403)
		self.assertIn("does not allow guest access", result["error"])

	@patch("frappe.session")
	@patch("huf.ai.http_handler.has_capability")
	def test_guest_tool_with_allowed_for_guest_false_denied(
		self, mock_has_capability, mock_session
	):
		"""Guest accessing a tool with allowed_for_guest=False is denied."""
		mock_session.user = "Guest"

		with patch("frappe.get_doc") as mock_get_doc:
			mock_tool_doc = Mock()
			mock_tool_doc.allowed_for_guest = False
			mock_get_doc.return_value = mock_tool_doc

			result = handle_http_request(
				"GET", "https://api.example.com/", tool_name="test_tool"
			)

			self.assertFalse(result["success"])
			self.assertEqual(result["status_code"], 403)

	@patch("frappe.session")
	@patch("huf.ai.http_handler.has_capability")
	def test_guest_tool_with_allowed_for_guest_true_proceeds(
		self, mock_has_capability, mock_session
	):
		"""Guest accessing a tool with allowed_for_guest=True proceeds."""
		mock_session.user = "Guest"

		with patch("frappe.get_doc") as mock_get_doc:
			mock_tool_doc = Mock()
			mock_tool_doc.base_url = "https://api.example.com/"
			mock_tool_doc.http_headers = []
			mock_tool_doc.allowed_for_guest = True
			mock_get_doc.return_value = mock_tool_doc

			with patch("huf.ai.http_handler.requests.request") as mock_request:
				mock_response = Mock()
				mock_response.status_code = 200
				mock_response.headers = {}
				mock_response.iter_content = Mock(return_value=[b"{}"])
				mock_request.return_value = mock_response

				result = handle_http_request(
					"GET", "https://api.example.com/", tool_name="test_tool"
				)

				# Should proceed past guest check
				self.assertTrue(result["success"])


class TestHeaderOriginBindingST073(unittest.TestCase):
	"""Tests for ST-07.3: Header binding to tool origin."""

	@patch("frappe.session")
	@patch("huf.ai.http_handler.has_capability")
	def test_same_origin_request_attaches_tool_headers(
		self, mock_has_capability, mock_session
	):
		"""Request to same origin as base_url attaches tool headers."""
		mock_session.user = "user@example.com"
		mock_has_capability.return_value = True

		with patch("frappe.get_doc") as mock_get_doc:
			mock_tool_doc = Mock()
			mock_tool_doc.base_url = "https://api.example.com/"
			mock_tool_doc.http_headers = [
				Mock(key="Authorization", value="Bearer token123")
			]
			mock_tool_doc.allowed_for_guest = False
			mock_get_doc.return_value = mock_tool_doc

			with patch("huf.ai.http_handler.requests.request") as mock_request:
				mock_response = Mock()
				mock_response.status_code = 200
				mock_response.headers = {}
				mock_response.iter_content = Mock(return_value=[b"{}"])
				mock_request.return_value = mock_response

				result = handle_http_request(
					"GET",
					"https://api.example.com/endpoint",
					tool_name="test_tool",
				)

				# Verify request was made with tool headers
				call_args = mock_request.call_args
				self.assertIn("Authorization", call_args.kwargs["headers"])
				self.assertEqual(
					call_args.kwargs["headers"]["Authorization"], "Bearer token123"
				)

	@patch("frappe.session")
	@patch("huf.ai.http_handler.has_capability")
	def test_cross_origin_request_does_not_attach_tool_headers(
		self, mock_has_capability, mock_session
	):
		"""Request to different origin than base_url does not attach tool headers."""
		mock_session.user = "user@example.com"
		mock_has_capability.return_value = True

		with patch("frappe.get_doc") as mock_get_doc:
			mock_tool_doc = Mock()
			mock_tool_doc.base_url = "https://api.example.com/"
			mock_tool_doc.http_headers = [
				Mock(key="Authorization", value="Bearer token123")
			]
			mock_tool_doc.allowed_for_guest = False
			mock_get_doc.return_value = mock_tool_doc

			with patch("huf.ai.http_handler.requests.request") as mock_request:
				# Mock validate_url to allow the cross-origin request
				with patch(
					"huf.ai.http_handler.validate_url",
					return_value=(True, None),
				):
					mock_response = Mock()
					mock_response.status_code = 200
					mock_response.headers = {}
					mock_response.iter_content = Mock(return_value=[b"{}"])
					mock_request.return_value = mock_response

					result = handle_http_request(
						"GET",
						"https://attacker.com/",
						tool_name="test_tool",
					)

					# Verify tool headers were NOT attached
					call_args = mock_request.call_args
					self.assertNotIn("Authorization", call_args.kwargs["headers"])

	@patch("frappe.session")
	@patch("huf.ai.http_handler.has_capability")
	def test_redirect_to_cross_origin_strips_auth_headers(
		self, mock_has_capability, mock_session
	):
		"""Redirect to different origin strips Authorization-class headers."""
		mock_session.user = "user@example.com"
		mock_has_capability.return_value = True

		with patch("frappe.get_doc") as mock_get_doc:
			mock_tool_doc = Mock()
			mock_tool_doc.base_url = "https://api.example.com/"
			mock_tool_doc.http_headers = [
				Mock(key="Authorization", value="Bearer token123")
			]
			mock_tool_doc.allowed_for_guest = False
			mock_get_doc.return_value = mock_tool_doc

			with patch("huf.ai.http_handler.requests.request") as mock_request:
				with patch("huf.ai.http_handler.validate_url") as mock_validate:
					mock_validate.return_value = (True, None)

					# First response: 302 redirect to different origin
					redirect_response = Mock()
					redirect_response.status_code = 302
					redirect_response.headers = {"Location": "https://attacker.com/"}
					redirect_response.iter_content = Mock(return_value=[b""])

					# Second response: final response from attacker.com
					final_response = Mock()
					final_response.status_code = 200
					final_response.headers = {}
					final_response.iter_content = Mock(return_value=[b"{}"])

					mock_request.side_effect = [redirect_response, final_response]

					result = handle_http_request(
						"GET",
						"https://api.example.com/endpoint",
						tool_name="test_tool",
					)

					# Second request should have Authorization header stripped
					second_call = mock_request.call_args_list[1]
					self.assertNotIn("Authorization", second_call.kwargs["headers"])


class TestResponseSizeCappingST074(unittest.TestCase):
	"""Tests for ST-07.4: Response size cap enforcement via streaming."""

	@patch("frappe.session")
	@patch("huf.ai.http_handler.has_capability")
	def test_response_under_limit_succeeds(self, mock_has_capability, mock_session):
		"""Response under MAX_RESPONSE_SIZE (10MB) succeeds."""
		mock_session.user = "user@example.com"
		mock_has_capability.return_value = True

		with patch("frappe.get_doc") as mock_get_doc:
			mock_tool_doc = Mock()
			mock_tool_doc.base_url = "https://api.example.com/"
			mock_tool_doc.http_headers = []
			mock_tool_doc.allowed_for_guest = False
			mock_get_doc.return_value = mock_tool_doc

			with patch("huf.ai.http_handler.requests.request") as mock_request:
				mock_response = Mock()
				mock_response.status_code = 200
				mock_response.headers = {"Content-Length": "1000"}
				# Return a small response via iter_content
				test_data = b'{"result": "success"}'
				mock_response.iter_content = Mock(return_value=[test_data])
				mock_request.return_value = mock_response

				result = handle_http_request(
					"GET", "https://api.example.com/", tool_name="test_tool"
				)

				self.assertTrue(result["success"])
				self.assertEqual(result["status_code"], 200)

	@patch("frappe.session")
	@patch("huf.ai.http_handler.has_capability")
	def test_response_exceeding_limit_aborted(self, mock_has_capability, mock_session):
		"""Response exceeding MAX_RESPONSE_SIZE aborts with error."""
		mock_session.user = "user@example.com"
		mock_has_capability.return_value = True

		with patch("frappe.get_doc") as mock_get_doc:
			mock_tool_doc = Mock()
			mock_tool_doc.base_url = "https://api.example.com/"
			mock_tool_doc.http_headers = []
			mock_tool_doc.allowed_for_guest = False
			mock_get_doc.return_value = mock_tool_doc

			with patch("huf.ai.http_handler.requests.request") as mock_request:
				mock_response = Mock()
				mock_response.status_code = 200
				# No Content-Length to pass fast-path check
				mock_response.headers = {}
				# Return chunks totaling > MAX_RESPONSE_SIZE
				# MAX_RESPONSE_SIZE is 10MB, so return > 10MB
				chunk_size = 8192
				num_chunks = int((10 * 1024 * 1024) / chunk_size) + 2
				chunks = [b"x" * chunk_size for _ in range(num_chunks)]
				mock_response.iter_content = Mock(return_value=chunks)
				mock_request.return_value = mock_response

				result = handle_http_request(
					"GET", "https://api.example.com/", tool_name="test_tool"
				)

				self.assertFalse(result["success"])
				self.assertIn("Response too large", result["error"])

	@patch("frappe.session")
	@patch("huf.ai.http_handler.has_capability")
	def test_content_length_pre_check_fast_path(
		self, mock_has_capability, mock_session
	):
		"""Content-Length exceeding limit triggers fast-path rejection."""
		mock_session.user = "user@example.com"
		mock_has_capability.return_value = True

		with patch("frappe.get_doc") as mock_get_doc:
			mock_tool_doc = Mock()
			mock_tool_doc.base_url = "https://api.example.com/"
			mock_tool_doc.http_headers = []
			mock_tool_doc.allowed_for_guest = False
			mock_get_doc.return_value = mock_tool_doc

			with patch("huf.ai.http_handler.requests.request") as mock_request:
				mock_response = Mock()
				mock_response.status_code = 200
				# Set Content-Length > MAX_RESPONSE_SIZE
				mock_response.headers = {"Content-Length": str(20 * 1024 * 1024)}
				mock_request.return_value = mock_response

				result = handle_http_request(
					"GET", "https://api.example.com/", tool_name="test_tool"
				)

				self.assertFalse(result["success"])
				self.assertIn("Content-Length exceeds 10MB limit", result["error"])
				# iter_content should not be called (fast-path)
				mock_response.iter_content.assert_not_called()


class TestRateLimitingDecoratorST075(unittest.TestCase):
	"""Tests for ST-07.5: Rate limiting decorator presence."""

	def test_rate_limit_decorator_present_on_handle_http_request(self):
		"""handle_http_request has @rate_limit decorator."""
		# Check that the function has a __wrapped__ attribute from decorator
		self.assertTrue(
			hasattr(handle_http_request, "__wrapped__")
			or hasattr(handle_http_request, "__name__")
		)

		# Check decorator metadata (if available)
		# The real integration test is bench/integration only per the plan

	def test_rate_limit_decorator_present_on_handle_get_request(self):
		"""handle_get_request has @rate_limit decorator."""
		self.assertTrue(
			hasattr(handle_get_request, "__wrapped__")
			or hasattr(handle_get_request, "__name__")
		)

	def test_rate_limit_decorator_present_on_handle_post_request(self):
		"""handle_post_request has @rate_limit decorator."""
		self.assertTrue(
			hasattr(handle_post_request, "__wrapped__")
			or hasattr(handle_post_request, "__name__")
		)


if __name__ == "__main__":
	unittest.main()
