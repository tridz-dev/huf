"""Test that frappe.set_user is called for API-key requests in the router.

These tests exercise the real router code (`_resolve_switch_user` and
`ApiV1Router.render`) rather than re-implementing its logic inline, so a
regression in `huf/api/v1/router.py` actually fails these tests.
"""

from unittest.mock import MagicMock, patch

import frappe

from huf.api.v1.context import AuthMode, RequestContext
from huf.api.v1.router import ApiV1Router, _resolve_switch_user


def test_resolve_switch_user_for_api_key():
	"""API_KEY context whose user differs from the current user switches."""
	context = RequestContext(user="alice@example.com", auth_mode=AuthMode.API_KEY)
	assert _resolve_switch_user(context, "Guest") == "alice@example.com"


def test_resolve_switch_user_not_called_for_session_auth():
	"""SESSION auth mode never triggers a switch, even if user differs."""
	context = RequestContext(user="alice@example.com", auth_mode=AuthMode.SESSION)
	assert _resolve_switch_user(context, "bob@example.com") is None


def test_resolve_switch_user_not_called_for_guest_fallback():
	"""An unauthenticated Guest context on an allow_guest endpoint never switches."""
	context = RequestContext(user="Guest", auth_mode=AuthMode.SESSION)
	assert _resolve_switch_user(context, "Guest") is None


def test_resolve_switch_user_noop_when_already_matching():
	"""No switch needed if the API-key user is already the current user."""
	context = RequestContext(user="alice@example.com", auth_mode=AuthMode.API_KEY)
	assert _resolve_switch_user(context, "alice@example.com") is None


def _make_router(context, handler_return=None, endpoint="agents"):
	router = ApiV1Router.__new__(ApiV1Router)
	router.path = f"huf/api/v1/{endpoint}"
	frappe.form_dict = frappe._dict({"endpoint": endpoint})
	router._build_context = MagicMock(return_value=context)
	router.build_response = MagicMock(side_effect=lambda body, headers=None, http_status_code=200: body)
	return router


def test_set_user_active_during_handler_for_api_key_request():
	"""frappe.session.user is the API-key owner while the handler runs, and
	is restored to the pre-request value once render() returns."""
	original_user = frappe.session.user
	frappe.session.user = "Guest"
	try:
		context = RequestContext(user="alice@example.com", auth_mode=AuthMode.API_KEY)
		router = _make_router(context)

		seen_user_during_handler = {}

		def fake_handler(ctx):
			seen_user_during_handler["user"] = frappe.session.user
			return {"ok": True}

		with patch("huf.api.v1.router._match_route", return_value=(fake_handler, True)):
			router.render()

		assert seen_user_during_handler["user"] == "alice@example.com"
		assert frappe.session.user == "Guest"
	finally:
		frappe.session.user = original_user


def test_set_user_not_switched_for_session_auth_request():
	"""A session-authenticated request never has its user swapped."""
	original_user = frappe.session.user
	frappe.session.user = "bob@example.com"
	try:
		context = RequestContext(user="bob@example.com", auth_mode=AuthMode.SESSION)
		router = _make_router(context)

		seen_user_during_handler = {}

		def fake_handler(ctx):
			seen_user_during_handler["user"] = frappe.session.user
			return {"ok": True}

		with patch("huf.api.v1.router._match_route", return_value=(fake_handler, True)):
			router.render()

		assert seen_user_during_handler["user"] == "bob@example.com"
		assert frappe.session.user == "bob@example.com"
	finally:
		frappe.session.user = original_user


def test_set_user_not_switched_for_guest_fallback_request():
	"""An unauthenticated request to an allow_guest endpoint keeps Guest."""
	original_user = frappe.session.user
	frappe.session.user = "Guest"
	try:
		context = RequestContext(user="Guest", auth_mode=AuthMode.SESSION)
		router = _make_router(context, endpoint="ping")

		seen_user_during_handler = {}

		def fake_handler(ctx):
			seen_user_during_handler["user"] = frappe.session.user
			return {"ok": True}

		with patch("huf.api.v1.router._match_route", return_value=(fake_handler, False)):
			router.render()

		assert seen_user_during_handler["user"] == "Guest"
		assert frappe.session.user == "Guest"
	finally:
		frappe.session.user = original_user


def test_set_user_restored_after_api_key_request_even_on_handler_error():
	"""frappe.session.user is restored even if the handler raises."""
	original_user = frappe.session.user
	frappe.session.user = "Guest"
	try:
		context = RequestContext(user="alice@example.com", auth_mode=AuthMode.API_KEY)
		router = _make_router(context)

		def failing_handler(ctx):
			raise ValueError("boom")

		with patch("huf.api.v1.router._match_route", return_value=(failing_handler, True)):
			router.render()

		assert frappe.session.user == "Guest"
	finally:
		frappe.session.user = original_user
