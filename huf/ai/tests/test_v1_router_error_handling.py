"""
Unit tests for huf.api.v1.router exception handling and error responses.

Tests that:
1. ApiError subclasses return their specific messages to the client
2. Non-ApiError exceptions return a generic message without exception details
3. Full exception details are logged server-side via frappe.log_error
4. All error responses include a request_id for correlation

Run with:
  bench --site <site> run-tests --app huf --module huf.ai.tests.test_v1_router_error_handling
"""

import json
import unittest
from unittest.mock import MagicMock, patch, call

import frappe

from huf.api.v1.router import ApiV1Router
from huf.api.v1.errors import ApiError, ValidationError
from huf.api.v1.context import RequestContext, AuthMode


class TestV1RouterExceptionHandling(unittest.TestCase):
	"""Test that the router properly handles ApiError vs generic exceptions."""

	def setUp(self):
		"""Set up test fixtures."""
		self.router = ApiV1Router()
		self.router.path = "huf/api/v1/ping"

	@patch("frappe.session")
	@patch("frappe.form_dict", {"endpoint": "ping"})
	@patch("huf.api.v1.router._match_route")
	@patch("frappe.log_error")
	def test_non_api_error_exception_returns_generic_message(
		self, mock_log_error, mock_match_route, mock_form_dict, mock_session
	):
		"""Non-ApiError exceptions return generic message without exception details."""
		mock_session.user = "test_user"

		# Handler that raises a generic exception (KeyError)
		def failing_handler(context):
			raise KeyError("sensitive_key_name")

		mock_match_route.return_value = (failing_handler, False)

		# Patch render method to capture the response
		response_body = None
		status_code = None

		def mock_build_response(body, headers=None, http_status_code=200):
			nonlocal response_body, status_code
			response_body = body
			status_code = http_status_code
			return f"HTTP {http_status_code}: {body}"

		self.router.build_response = mock_build_response

		# Execute
		result = self.router.render()

		# Verify response
		self.assertIsNotNone(response_body)
		response_data = json.loads(response_body)

		# Assert: response should be an error envelope
		self.assertIn("error", response_data)
		error = response_data["error"]

		# Assert: generic message (does NOT leak the KeyError or "sensitive_key_name")
		self.assertIn("Internal error. Request ID:", error["message"])
		self.assertNotIn("KeyError", error["message"])
		self.assertNotIn("sensitive_key_name", error["message"])

		# Assert: request_id is present and matches the message
		self.assertIn("request_id", error)
		request_id = error["request_id"]
		self.assertIsNotNone(request_id)
		self.assertIn(request_id, error["message"])

		# Assert: status code is 500
		self.assertEqual(status_code, 500)

		# Verify frappe.log_error was called with full traceback
		mock_log_error.assert_called_once()
		call_args = mock_log_error.call_args
		# First arg should be the traceback
		logged_message = call_args[0][0]
		self.assertIn("KeyError", logged_message)
		# Second arg should be the title
		self.assertEqual(call_args[0][1], "Huf API v1 Router Error")

	@patch("frappe.session")
	@patch("frappe.form_dict", {"endpoint": "ping"})
	@patch("huf.api.v1.router._match_route")
	@patch("frappe.log_error")
	def test_sql_error_does_not_leak_to_client(
		self, mock_log_error, mock_match_route, mock_form_dict, mock_session
	):
		"""SQL errors do not leak to the client."""
		mock_session.user = "test_user"

		# Handler that raises a SQL-like exception
		def failing_handler(context):
			raise Exception("SELECT * FROM frappe.user WHERE password = 'secret'")

		mock_match_route.return_value = (failing_handler, False)

		response_body = None

		def mock_build_response(body, headers=None, http_status_code=200):
			nonlocal response_body
			response_body = body
			return f"HTTP {http_status_code}: {body}"

		self.router.build_response = mock_build_response

		# Execute
		result = self.router.render()

		# Verify response
		response_data = json.loads(response_body)
		error_message = response_data["error"]["message"]

		# Assert: SQL query is NOT in the response
		self.assertNotIn("SELECT", error_message)
		self.assertNotIn("frappe.user", error_message)
		self.assertNotIn("password", error_message)

		# Assert: only generic message
		self.assertIn("Internal error. Request ID:", error_message)

	@patch("frappe.session")
	@patch("frappe.form_dict", {"endpoint": "ping"})
	@patch("huf.api.v1.router._match_route")
	def test_api_error_subclass_returns_specific_message(
		self, mock_match_route, mock_form_dict, mock_session
	):
		"""ApiError subclasses return their specific messages (not generic)."""
		mock_session.user = "test_user"

		# Handler that raises a ValidationError (an ApiError subclass)
		def failing_handler(context):
			raise ValidationError("agent_id is required")

		mock_match_route.return_value = (failing_handler, False)

		response_body = None
		status_code = None

		def mock_build_response(body, headers=None, http_status_code=200):
			nonlocal response_body, status_code
			response_body = body
			status_code = http_status_code
			return f"HTTP {http_status_code}: {body}"

		self.router.build_response = mock_build_response

		# Execute
		result = self.router.render()

		# Verify response
		response_data = json.loads(response_body)
		error = response_data["error"]

		# Assert: specific message is returned (not generic)
		self.assertEqual(error["message"], "agent_id is required")
		self.assertNotIn("Internal error", error["message"])

		# Assert: correct status code (400 for ValidationError)
		self.assertEqual(status_code, 400)

		# Assert: error code matches
		self.assertEqual(error["code"], "validation_error")

	@patch("frappe.session")
	@patch("frappe.form_dict", {"endpoint": "ping"})
	@patch("huf.api.v1.router._match_route")
	def test_error_response_always_includes_request_id(
		self, mock_match_route, mock_form_dict, mock_session
	):
		"""All error responses include a request_id."""
		mock_session.user = "test_user"

		# Handler that raises an exception
		def failing_handler(context):
			raise RuntimeError("something went wrong")

		mock_match_route.return_value = (failing_handler, False)

		response_body = None

		def mock_build_response(body, headers=None, http_status_code=200):
			nonlocal response_body
			response_body = body
			return f"HTTP {http_status_code}: {body}"

		self.router.build_response = mock_build_response

		# Execute
		result = self.router.render()

		# Verify request_id is present in response
		response_data = json.loads(response_body)
		request_id = response_data["error"]["request_id"]

		self.assertIsNotNone(request_id)
		# UUID format check (rough)
		self.assertRegex(request_id, r"^[a-f0-9\-]{36}$")

	@patch("frappe.session")
	@patch("frappe.form_dict", {"endpoint": "agents"})
	@patch("huf.api.v1.router._match_route")
	@patch("frappe.log_error")
	def test_exception_logged_with_full_traceback(
		self, mock_log_error, mock_match_route, mock_form_dict, mock_session
	):
		"""Full exception + traceback is logged server-side."""
		mock_session.user = "test_user"

		def failing_handler(context):
			# Create a multi-level traceback
			def inner():
				return 1 / 0  # ZeroDivisionError

			inner()

		mock_match_route.return_value = (failing_handler, False)

		response_body = None

		def mock_build_response(body, headers=None, http_status_code=200):
			nonlocal response_body
			response_body = body
			return f"HTTP {http_status_code}: {body}"

		self.router.build_response = mock_build_response

		# Execute
		result = self.router.render()

		# Verify frappe.log_error was called
		mock_log_error.assert_called_once()
		call_args = mock_log_error.call_args

		# The logged traceback should contain "ZeroDivisionError"
		logged_traceback = call_args[0][0]
		self.assertIn("ZeroDivisionError", logged_traceback)

		# The log title should be the standard message
		self.assertEqual(call_args[0][1], "Huf API v1 Router Error")

	@patch("frappe.session")
	@patch("frappe.form_dict", {"endpoint": "ping"})
	@patch("huf.api.v1.router._match_route")
	def test_file_path_not_leaked_in_error_response(
		self, mock_match_route, mock_form_dict, mock_session
	):
		"""File paths are not leaked in error responses."""
		mock_session.user = "test_user"

		def failing_handler(context):
			# Simulate a file not found error
			raise FileNotFoundError(
				"/Users/admin/huf/api/v1/router.py: No such file or directory"
			)

		mock_match_route.return_value = (failing_handler, False)

		response_body = None

		def mock_build_response(body, headers=None, http_status_code=200):
			nonlocal response_body
			response_body = body
			return f"HTTP {http_status_code}: {body}"

		self.router.build_response = mock_build_response

		# Execute
		result = self.router.render()

		# Verify response
		response_data = json.loads(response_body)
		error_message = response_data["error"]["message"]

		# Assert: file path is NOT in the response
		self.assertNotIn("/Users/", error_message)
		self.assertNotIn("/huf/api/", error_message)
		self.assertNotIn(".py", error_message)

		# Assert: only generic message
		self.assertIn("Internal error. Request ID:", error_message)
