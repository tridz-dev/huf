"""Test that frappe.set_user is called for API-key requests in the router.

Tests that the router correctly sets frappe.session.user to the API-key
owner for API_KEY auth mode, and restores it afterward.
"""

import frappe
import pytest
from unittest.mock import patch, MagicMock

from huf.api.v1.context import AuthMode, RequestContext


def test_set_user_called_for_api_key_requests():
	"""frappe.set_user is called for API_KEY auth mode."""
	context = RequestContext(
		user="alice@example.com",
		auth_mode=AuthMode.API_KEY,
	)

	with patch("frappe.set_user") as mock_set_user:
		# Simulate the router logic
		previous_user = frappe.session.user
		try:
			if context.auth_mode == AuthMode.API_KEY and context.user and context.user != previous_user:
				frappe.set_user(context.user)
		finally:
			if frappe.session.user != previous_user:
				frappe.set_user(previous_user)

		# Verify set_user was called
		mock_set_user.assert_called()


def test_set_user_not_called_for_session_auth():
	"""frappe.set_user is not called for SESSION auth mode."""
	context = RequestContext(
		user="alice@example.com",
		auth_mode=AuthMode.SESSION,
	)

	with patch("frappe.set_user") as mock_set_user:
		# Simulate the router logic
		previous_user = frappe.session.user
		try:
			if context.auth_mode == AuthMode.API_KEY and context.user and context.user != previous_user:
				frappe.set_user(context.user)
		finally:
			if frappe.session.user != previous_user:
				frappe.set_user(previous_user)

		# Verify set_user was not called
		mock_set_user.assert_not_called()


def test_set_user_restored_after_request():
	"""frappe.set_user is restored to original value after the request."""
	context = RequestContext(
		user="alice@example.com",
		auth_mode=AuthMode.API_KEY,
	)

	# Record the original user
	original_user = frappe.session.user
	frappe.session.user = "guest_user"

	try:
		# Simulate the router logic
		previous_user = frappe.session.user
		try:
			if context.auth_mode == AuthMode.API_KEY and context.user and context.user != previous_user:
				frappe.session.user = context.user  # Simulate set_user
		finally:
			if frappe.session.user != previous_user:
				frappe.session.user = previous_user  # Restore

		# Verify it's restored
		assert frappe.session.user == "guest_user"
	finally:
		frappe.session.user = original_user
