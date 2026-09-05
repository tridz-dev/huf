"""Test for Gmail token persistence (CL-03)."""

import json
import time
from unittest.mock import patch, MagicMock
import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.tools.gmail import _get_gmail_access_token
from huf.ai.tools.credentials import set_credential, get_credential


class TestGmailTokenPersistence(IntegrationTestCase):
	"""Test Gmail token persistence to avoid unnecessary OAuth refresh calls."""

	def setUp(self):
		"""Set up test fixtures."""
		self.service_name = "gmail"

		# Create an Integration Service for Gmail if it doesn't exist
		if not frappe.db.exists("Integration Service", self.service_name):
			frappe.get_doc({
				"doctype": "Integration Service",
				"name": self.service_name,
				"display_name": "Gmail",
				"category": "Communication"
			}).insert(ignore_if_duplicate=True)

		# Create Integration Settings for Gmail with test credentials
		self.integration_doc_name = frappe.get_all(
			"Integration Settings",
			filters={"service": self.service_name},
			fields=["name"],
			limit=1
		)

		if self.integration_doc_name:
			# Delete existing one to start fresh
			frappe.delete_doc("Integration Settings", self.integration_doc_name[0].name)

		self.integration_doc = frappe.get_doc({
			"doctype": "Integration Settings",
			"service": self.service_name,
			"is_active": 1,
			"is_default": 1,
			"credentials": [
				{"key": "client_id", "value": "test-client-id"},
				{"key": "client_secret", "value": "test-client-secret"},
				{"key": "refresh_token", "value": "test-refresh-token"},
			]
		}).insert()

	def tearDown(self):
		"""Clean up test data."""
		try:
			frappe.delete_doc("Integration Settings", self.integration_doc.name)
		except Exception:
			pass

	@patch("huf.ai.tools.gmail.httpx.post")
	def test_second_call_within_validity_window_no_refresh(self, mock_post):
		"""Test that a second call within token validity does not trigger a new OAuth refresh."""
		# Mock the OAuth refresh endpoint
		mock_response = MagicMock()
		mock_response.json.return_value = {
			"access_token": "new-access-token-123",
			"expires_in": 3600,  # Token valid for 1 hour
			"token_type": "Bearer"
		}
		mock_response.raise_for_status.return_value = None
		mock_post.return_value = mock_response

		# First call: should trigger OAuth refresh
		token1 = _get_gmail_access_token()
		self.assertEqual(token1, "new-access-token-123")
		self.assertEqual(mock_post.call_count, 1, "First call should trigger OAuth refresh")

		# Verify token was persisted
		stored_token = get_credential(self.service_name, "access_token")
		self.assertEqual(stored_token, "new-access-token-123")

		# Verify expiry was persisted
		stored_expiry = get_credential(self.service_name, "access_token_expiry")
		self.assertIsNotNone(stored_expiry)

		# Second call: should NOT trigger OAuth refresh (token still valid)
		token2 = _get_gmail_access_token()
		self.assertEqual(token2, "new-access-token-123")
		self.assertEqual(mock_post.call_count, 1, "Second call should NOT trigger a new OAuth refresh")

	@patch("huf.ai.tools.gmail.httpx.post")
	def test_expired_token_triggers_refresh(self, mock_post):
		"""Test that an expired token triggers a new OAuth refresh."""
		# Mock the OAuth refresh endpoint
		mock_response = MagicMock()
		mock_response.json.side_effect = [
			{
				"access_token": "first-token",
				"expires_in": 3600,
				"token_type": "Bearer"
			},
			{
				"access_token": "second-token",
				"expires_in": 3600,
				"token_type": "Bearer"
			}
		]
		mock_response.raise_for_status.return_value = None
		mock_post.return_value = mock_response

		# First call: should trigger OAuth refresh
		token1 = _get_gmail_access_token()
		self.assertEqual(token1, "first-token")
		self.assertEqual(mock_post.call_count, 1)

		# Manually set token expiry to the past to simulate expiration
		expiry_time = time.time() - 100  # Expired 100 seconds ago
		set_credential(self.service_name, "access_token_expiry", str(expiry_time))

		# Second call: should trigger new OAuth refresh because token is expired
		token2 = _get_gmail_access_token()
		self.assertEqual(token2, "second-token")
		self.assertEqual(mock_post.call_count, 2, "Expired token should trigger a new OAuth refresh")

	@patch("huf.ai.tools.gmail.httpx.post")
	def test_missing_credentials_returns_none(self, mock_post):
		"""Test that missing credentials don't cause exceptions."""
		# Remove the integration settings to test fallback behavior
		frappe.delete_doc("Integration Settings", self.integration_doc.name)

		# This should not raise an exception
		try:
			token = _get_gmail_access_token()
			# Should return None due to missing credentials
			self.assertIsNone(token)
		except Exception as e:
			self.fail(f"_get_gmail_access_token() should not raise: {e}")

	@patch("huf.ai.tools.gmail.httpx.post")
	def test_malformed_expiry_triggers_refresh(self, mock_post):
		"""Test that malformed expiry time triggers a new OAuth refresh."""
		# Mock the OAuth refresh endpoint
		mock_response = MagicMock()
		mock_response.json.return_value = {
			"access_token": "valid-token",
			"expires_in": 3600,
			"token_type": "Bearer"
		}
		mock_response.raise_for_status.return_value = None
		mock_post.return_value = mock_response

		# Set a valid token but with malformed expiry
		set_credential(self.service_name, "access_token", "some-token")
		set_credential(self.service_name, "access_token_expiry", "not-a-number")

		# Call should trigger refresh due to malformed expiry
		token = _get_gmail_access_token()
		self.assertEqual(token, "valid-token")
		self.assertEqual(mock_post.call_count, 1, "Malformed expiry should trigger refresh")

	@patch("huf.ai.tools.gmail.httpx.post")
	def test_token_persistence_survives_restart(self, mock_post):
		"""Test that persisted token is retrieved correctly after a 'restart'."""
		# Mock the OAuth refresh endpoint
		mock_response = MagicMock()
		mock_response.json.return_value = {
			"access_token": "persisted-token",
			"expires_in": 3600,
			"token_type": "Bearer"
		}
		mock_response.raise_for_status.return_value = None
		mock_post.return_value = mock_response

		# First call: persists token
		token1 = _get_gmail_access_token()
		self.assertEqual(token1, "persisted-token")
		self.assertEqual(mock_post.call_count, 1)

		# Simulate reading from credentials (like after a restart)
		stored_token = get_credential(self.service_name, "access_token")
		stored_expiry = get_credential(self.service_name, "access_token_expiry")

		self.assertEqual(stored_token, "persisted-token")
		self.assertIsNotNone(stored_expiry)

		# Second call should use persisted token without refresh
		token2 = _get_gmail_access_token()
		self.assertEqual(token2, "persisted-token")
		self.assertEqual(mock_post.call_count, 1, "Should use persisted token without new refresh")
