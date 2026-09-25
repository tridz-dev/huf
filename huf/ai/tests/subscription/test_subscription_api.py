# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (no bench / no live Frappe site) unit tests for T-10-api:
`huf.ai.subscription_api`.

Covers:
  - permission gating (unauthorized user rejected before any adapter call)
  - the poll-to-resume wiring (`poll_subscription_auth` calling
    `resume.resume_after_auth_success` on a ready-state transition -- the
    exact call site the T-06-D `# TODO(T-10-api)` in
    `huf/ai/subscription/resume.py` was waiting for)
  - no endpoint ever accepts/logs a password field

Relies on the repo-root ``conftest.py`` to stub ``frappe``/``litellm``/``agents``
before anything under the ``huf`` package is imported, exactly as
``test_resume_and_ordering.py`` / ``test_executor_passthrough.py`` already do.
"""

from __future__ import annotations

import types
import unittest
from unittest import mock

import frappe

from huf.ai import subscription_api
from huf.ai.subscription.errors import SubscriptionAuthError, SubscriptionErrorCode
from huf.ai.subscription.types import AuthStatus


def _fake_runtime(**overrides):
	defaults = dict(
		name="RUNTIME-1",
		provider_family="Claude",
		transport_type="Local",
		executable="claude",
		working_directory=None,
		docker_container=None,
		ssh_connection=None,
		timeout_seconds=None,
		auth_status="required",
	)
	defaults.update(overrides)
	runtime = types.SimpleNamespace(**defaults)
	runtime.check_tenancy = mock.MagicMock(return_value=True)
	runtime.get = lambda field, _r=runtime: getattr(_r, field, None)
	return runtime


def _fake_challenge_doc(**overrides):
	defaults = dict(
		name="SAC-0001",
		runtime="RUNTIME-1",
		provider="Claude",
		status="Waiting User",
		mode="device_code",
		verification_url="https://example.com/device",
		user_code="ABCD-1234",
		safe_instructions="Enter this code",
		expires_at=None,
	)
	defaults.update(overrides)
	doc = types.SimpleNamespace(**defaults)
	doc.get = lambda field, _doc=doc: getattr(_doc, field, None)
	doc.as_dict = lambda _doc=doc: {f: getattr(_doc, f, None) for f in defaults}
	return doc


class _PermissionTestBase(unittest.TestCase):
	def setUp(self):
		self._patches = [
			mock.patch("huf.permissions.has_capability", return_value=False),
			mock.patch.object(frappe, "get_roles", return_value=["Agent User"]),
			mock.patch.object(frappe, "session", types.SimpleNamespace(user="mallory@example.com")),
		]
		for p in self._patches:
			p.start()
			self.addCleanup(p.stop)


class TestPermissionGating(_PermissionTestBase):
	"""Every endpoint must reject an unauthorized user before touching the
	adapter/CLI -- verified by asserting `_build_adapter`/`frappe.get_doc`
	for the runtime are never reached."""

	def test_test_subscription_runtime_connection_rejects_unauthorized_user(self):
		with mock.patch.object(subscription_api, "_build_adapter") as mock_build_adapter:
			with self.assertRaises(frappe.ValidationError):
				subscription_api.test_subscription_runtime_connection("RUNTIME-1")
		mock_build_adapter.assert_not_called()

	def test_refresh_probe_rejects_unauthorized_user(self):
		with mock.patch.object(subscription_api, "_build_adapter") as mock_build_adapter:
			with self.assertRaises(frappe.ValidationError):
				subscription_api.refresh_subscription_runtime_probe("RUNTIME-1")
		mock_build_adapter.assert_not_called()

	def test_begin_subscription_auth_rejects_unauthorized_user(self):
		with mock.patch.object(subscription_api.auth_service, "get_or_create_active_challenge") as mock_challenge:
			with self.assertRaises(frappe.ValidationError):
				subscription_api.begin_subscription_auth("RUNTIME-1")
		mock_challenge.assert_not_called()

	def test_poll_subscription_auth_rejects_unauthorized_user(self):
		with mock.patch.object(frappe, "get_doc", return_value=_fake_challenge_doc()), \
			mock.patch.object(subscription_api, "_build_adapter") as mock_build_adapter:
			with self.assertRaises(frappe.ValidationError):
				subscription_api.poll_subscription_auth("SAC-0001")
		mock_build_adapter.assert_not_called()

	def test_submit_subscription_auth_input_rejects_unauthorized_user(self):
		with mock.patch.object(frappe, "get_doc", return_value=_fake_challenge_doc()), \
			mock.patch.object(subscription_api, "_build_adapter") as mock_build_adapter:
			with self.assertRaises(frappe.ValidationError):
				subscription_api.submit_subscription_auth_input("SAC-0001", "123456")
		mock_build_adapter.assert_not_called()

	def test_cancel_subscription_auth_rejects_unauthorized_user(self):
		with mock.patch.object(frappe, "get_doc", return_value=_fake_challenge_doc()), \
			mock.patch.object(subscription_api, "_build_adapter") as mock_build_adapter:
			with self.assertRaises(frappe.ValidationError):
				subscription_api.cancel_subscription_auth("SAC-0001")
		mock_build_adapter.assert_not_called()

	def test_reauthenticate_rejects_unauthorized_user(self):
		with mock.patch.object(subscription_api.auth_service, "get_or_create_active_challenge") as mock_challenge:
			with self.assertRaises(frappe.ValidationError):
				subscription_api.reauthenticate_subscription_runtime("RUNTIME-1")
		mock_challenge.assert_not_called()

	def test_logout_rejects_use_only_user(self):
		"""Logout requires `.manage` specifically -- a user with only `.use`
		must still be rejected."""

		def fake_has_capability(user, capability):
			return capability == "subscription_runtime.use"

		with mock.patch("huf.permissions.has_capability", side_effect=fake_has_capability), \
			mock.patch.object(subscription_api, "_build_adapter") as mock_build_adapter:
			with self.assertRaises(frappe.ValidationError):
				subscription_api.logout_subscription_runtime("RUNTIME-1")
		mock_build_adapter.assert_not_called()

	def test_tenancy_check_rejects_user_not_authorized_for_this_runtime(self):
		"""A user WITH the use-or-manage capability but who fails this
		specific runtime's `check_tenancy` must still be rejected."""
		runtime = _fake_runtime()
		runtime.check_tenancy = mock.MagicMock(return_value=False)

		with mock.patch("huf.permissions.has_capability", return_value=True), \
			mock.patch.object(frappe, "get_doc", return_value=runtime), \
			mock.patch.object(subscription_api, "_build_adapter") as mock_build_adapter:
			with self.assertRaises(frappe.ValidationError):
				subscription_api.test_subscription_runtime_connection("RUNTIME-1")
		mock_build_adapter.assert_not_called()


class TestPollToResumeWiring(unittest.TestCase):
	"""`poll_subscription_auth`, on a ready-state transition, must call
	`resume.resume_after_auth_success` -- the T-10-api call site the
	`resume.py` TODO was waiting for."""

	def setUp(self):
		self._patches = [
			mock.patch("huf.permissions.has_capability", return_value=True),
			mock.patch.object(frappe, "get_roles", return_value=["Agent User"]),
			mock.patch.object(frappe, "session", types.SimpleNamespace(user="alice@example.com")),
			mock.patch.object(frappe, "db", mock.MagicMock()),
		]
		for p in self._patches:
			p.start()
			self.addCleanup(p.stop)

	def test_ready_state_marks_runtime_ready_and_resumes_parked_runs(self):
		runtime = _fake_runtime(auth_status="required")
		challenge = _fake_challenge_doc()
		ready_status = AuthStatus(
			state="ready",
			account_hint="alice@work.com",
			method="oauth",
			message=None,
			checked_at="2026-09-26T00:00:00Z",
		)

		adapter = mock.MagicMock()

		async def fake_poll_auth(_runtime, _challenge_id):
			return ready_status

		adapter.poll_auth = fake_poll_auth

		def fake_get_doc(doctype, name):
			if doctype == "Subscription Auth Challenge":
				return challenge
			if doctype == "Subscription Runtime":
				return runtime
			raise AssertionError(f"unexpected get_doc({doctype!r})")

		with mock.patch.object(frappe, "get_doc", side_effect=fake_get_doc), \
			mock.patch.object(subscription_api, "_build_adapter", return_value=adapter), \
			mock.patch.object(subscription_api.auth_service, "mark_runtime_auth_state") as mock_mark, \
			mock.patch.object(subscription_api.resume, "resume_after_auth_success") as mock_resume:

			result = subscription_api.poll_subscription_auth("SAC-0001")

		mock_mark.assert_called_once_with(runtime, "ready", account_hint="alice@work.com")
		mock_resume.assert_called_once_with("RUNTIME-1")
		self.assertEqual(result["state"], "ready")

	def test_non_ready_state_does_not_resume(self):
		runtime = _fake_runtime(auth_status="waiting_user")
		challenge = _fake_challenge_doc()
		waiting_status = AuthStatus(
			state="waiting_user",
			account_hint=None,
			method=None,
			message=None,
			checked_at="2026-09-26T00:00:00Z",
		)

		adapter = mock.MagicMock()

		async def fake_poll_auth(_runtime, _challenge_id):
			return waiting_status

		adapter.poll_auth = fake_poll_auth

		def fake_get_doc(doctype, name):
			if doctype == "Subscription Auth Challenge":
				return challenge
			if doctype == "Subscription Runtime":
				return runtime
			raise AssertionError(f"unexpected get_doc({doctype!r})")

		with mock.patch.object(frappe, "get_doc", side_effect=fake_get_doc), \
			mock.patch.object(subscription_api, "_build_adapter", return_value=adapter), \
			mock.patch.object(subscription_api.auth_service, "mark_runtime_auth_state"), \
			mock.patch.object(subscription_api.resume, "resume_after_auth_success") as mock_resume:

			subscription_api.poll_subscription_auth("SAC-0001")

		mock_resume.assert_not_called()

	def test_submit_auth_input_ready_state_also_resumes(self):
		runtime = _fake_runtime(auth_status="required")
		challenge = _fake_challenge_doc()
		ready_status = AuthStatus(
			state="ready", account_hint=None, method=None, message=None, checked_at="2026-09-26T00:00:00Z"
		)

		adapter = mock.MagicMock()

		async def fake_submit(_runtime, _challenge_id, _value):
			return ready_status

		adapter.submit_auth_input = fake_submit

		def fake_get_doc(doctype, name):
			if doctype == "Subscription Auth Challenge":
				return challenge
			if doctype == "Subscription Runtime":
				return runtime
			raise AssertionError(f"unexpected get_doc({doctype!r})")

		with mock.patch.object(frappe, "get_doc", side_effect=fake_get_doc), \
			mock.patch.object(subscription_api, "_build_adapter", return_value=adapter), \
			mock.patch.object(subscription_api.auth_service, "mark_runtime_auth_state"), \
			mock.patch.object(subscription_api.resume, "resume_after_auth_success") as mock_resume:

			subscription_api.submit_subscription_auth_input("SAC-0001", "123456")

		mock_resume.assert_called_once_with("RUNTIME-1")


class TestNoPasswordFields(unittest.TestCase):
	"""No endpoint's signature/body accepts or logs a `password` field."""

	def test_no_endpoint_accepts_a_password_kwarg(self):
		import inspect

		for name in (
			"test_subscription_runtime_connection",
			"refresh_subscription_runtime_probe",
			"begin_subscription_auth",
			"poll_subscription_auth",
			"submit_subscription_auth_input",
			"cancel_subscription_auth",
			"reauthenticate_subscription_runtime",
			"logout_subscription_runtime",
		):
			func = getattr(subscription_api, name)
			params = inspect.signature(func).parameters
			for pname in params:
				self.assertNotIn("password", pname.lower())
				self.assertNotIn("secret", pname.lower())

	def test_submit_auth_input_rejects_oversized_value_without_logging_it(self):
		"""A too-long `value` (implausible for a device-code/paste-back token,
		plausible for an accidentally pasted secret/password blob) is rejected
		up front -- before any adapter call -- and never appears in the thrown
		message (which would otherwise land in Frappe's error log)."""
		runtime = _fake_runtime()
		challenge = _fake_challenge_doc()
		oversized_value = "x" * (subscription_api._MAX_AUTH_INPUT_LENGTH + 1)

		def fake_get_doc(doctype, name):
			if doctype == "Subscription Auth Challenge":
				return challenge
			if doctype == "Subscription Runtime":
				return runtime
			raise AssertionError(f"unexpected get_doc({doctype!r})")

		with mock.patch("huf.permissions.has_capability", return_value=True), \
			mock.patch.object(frappe, "get_roles", return_value=["Agent User"]), \
			mock.patch.object(frappe, "session", types.SimpleNamespace(user="alice@example.com")), \
			mock.patch.object(frappe, "get_doc", side_effect=fake_get_doc), \
			mock.patch.object(subscription_api, "_build_adapter") as mock_build_adapter:

			with self.assertRaises(frappe.ValidationError) as ctx:
				subscription_api.submit_subscription_auth_input("SAC-0001", oversized_value)

		mock_build_adapter.assert_not_called()
		self.assertNotIn(oversized_value, str(ctx.exception))

	def test_submit_auth_input_rejects_blank_value(self):
		runtime = _fake_runtime()
		challenge = _fake_challenge_doc()

		def fake_get_doc(doctype, name):
			if doctype == "Subscription Auth Challenge":
				return challenge
			if doctype == "Subscription Runtime":
				return runtime
			raise AssertionError(f"unexpected get_doc({doctype!r})")

		with mock.patch("huf.permissions.has_capability", return_value=True), \
			mock.patch.object(frappe, "get_roles", return_value=["Agent User"]), \
			mock.patch.object(frappe, "session", types.SimpleNamespace(user="alice@example.com")), \
			mock.patch.object(frappe, "get_doc", side_effect=fake_get_doc), \
			mock.patch.object(subscription_api, "_build_adapter") as mock_build_adapter:

			with self.assertRaises(frappe.ValidationError):
				subscription_api.submit_subscription_auth_input("SAC-0001", "   ")

		mock_build_adapter.assert_not_called()


if __name__ == "__main__":
	unittest.main()
