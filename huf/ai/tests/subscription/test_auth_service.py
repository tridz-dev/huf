# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (no bench / no live Frappe site) unit tests for
`huf.ai.subscription.auth_service`.

Every Frappe call (`frappe.get_all`, `frappe.get_doc`, `frappe.db.set_value`,
`frappe.session`) is mocked/monkeypatched - this mirrors the pattern used in
`huf/ai/tests/subscription/test_runtime_doctype_tenancy.py` for
Frappe-dependent code that must be testable without a live site/DB.
"""

import types
import unittest
from datetime import datetime, timedelta
from unittest import mock

import frappe

from huf.ai.subscription import auth_service


def _fake_challenge_doc(**overrides):
	"""A minimal stand-in for a `Subscription Auth Challenge` Document with
	just enough surface (`.get`, `.insert`, attribute access) for the
	functions under test."""
	defaults = dict(
		name="SAC-0001",
		runtime="my-runtime",
		provider="Claude",
		status="Pending",
		mode=None,
		verification_url=None,
		user_code=None,
		safe_instructions=None,
		created_by="alice@example.com",
		expires_at=None,
		completed_at=None,
		error_code=None,
		error_message=None,
		parked_agent_run=None,
		parked_conversation=None,
		metadata=None,
	)
	defaults.update(overrides)
	doc = types.SimpleNamespace(**defaults)
	doc.get = lambda field, _doc=doc: getattr(_doc, field, None)
	doc.insert = mock.MagicMock()
	return doc


class TestGetOrCreateActiveChallengeDedup(unittest.TestCase):
	"""Dedup logic: a second call for the same runtime must reuse the
	existing active challenge instead of creating a new one."""

	def test_returns_existing_active_challenge_without_creating_new_one(self):
		existing = _fake_challenge_doc(name="SAC-EXISTING", status="Waiting User")

		with mock.patch.object(frappe, "get_all", return_value=["SAC-EXISTING"]) as mock_get_all, \
			mock.patch.object(frappe, "get_doc", return_value=existing) as mock_get_doc:
			result = auth_service.get_or_create_active_challenge("my-runtime")

		mock_get_all.assert_called_once()
		# get_doc must be called to fetch the *existing* challenge, and only once
		# (i.e. no doc.insert() path was taken for a new challenge).
		mock_get_doc.assert_called_once_with("Subscription Auth Challenge", "SAC-EXISTING")
		self.assertEqual(result["name"], "SAC-EXISTING")
		self.assertEqual(result["status"], "Waiting User")

	def test_second_call_reuses_first_challenge_same_name(self):
		existing = _fake_challenge_doc(name="SAC-DEDUP", status="Pending")

		with mock.patch.object(frappe, "get_all", return_value=["SAC-DEDUP"]), \
			mock.patch.object(frappe, "get_doc", return_value=existing):
			first = auth_service.get_or_create_active_challenge("my-runtime")
			second = auth_service.get_or_create_active_challenge("my-runtime")

		self.assertEqual(first["name"], second["name"])

	def test_creates_new_challenge_when_none_active(self):
		new_doc = _fake_challenge_doc(name="SAC-NEW", status="Pending")
		frappe.session = types.SimpleNamespace(user="bob@example.com")

		with mock.patch.object(frappe, "get_all", return_value=[]), \
			mock.patch.object(frappe, "get_doc", return_value=new_doc) as mock_get_doc:
			result = auth_service.get_or_create_active_challenge("my-runtime")

		# get_doc was used to construct the new document (dict payload), not to
		# fetch an existing one by name.
		(args, _kwargs) = mock_get_doc.call_args
		self.assertIsInstance(args[0], dict)
		self.assertEqual(args[0]["doctype"], "Subscription Auth Challenge")
		self.assertEqual(args[0]["runtime"], "my-runtime")
		self.assertEqual(args[0]["status"], "Pending")
		new_doc.insert.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(result["name"], "SAC-NEW")


class TestCheckChallengeExpiry(unittest.TestCase):
	def test_true_when_expired(self):
		challenge = _fake_challenge_doc(expires_at=datetime.now() - timedelta(minutes=5))
		self.assertTrue(auth_service.check_challenge_expiry(challenge))

	def test_false_when_not_expired(self):
		challenge = _fake_challenge_doc(expires_at=datetime.now() + timedelta(minutes=5))
		self.assertFalse(auth_service.check_challenge_expiry(challenge))

	def test_false_when_no_expiry_set(self):
		challenge = _fake_challenge_doc(expires_at=None)
		self.assertFalse(auth_service.check_challenge_expiry(challenge))

	def test_accepts_plain_dict(self):
		expired = {"expires_at": datetime.now() - timedelta(minutes=1)}
		not_expired = {"expires_at": datetime.now() + timedelta(minutes=1)}
		self.assertTrue(auth_service.check_challenge_expiry(expired))
		self.assertFalse(auth_service.check_challenge_expiry(not_expired))

	def test_does_not_write_to_db(self):
		challenge = _fake_challenge_doc(expires_at=datetime.now() - timedelta(minutes=5))
		with mock.patch.object(frappe, "db", create=True) as mock_db:
			auth_service.check_challenge_expiry(challenge)
			mock_db.set_value.assert_not_called()


class TestParkRun(unittest.TestCase):
	def test_sets_status_and_auth_challenge(self):
		with mock.patch.object(frappe, "db", create=True) as mock_db:
			auth_service.park_run("AR-0001", "SAC-0001")

		mock_db.set_value.assert_called_once_with(
			"Agent Run",
			"AR-0001",
			{
				"status": "Waiting Authentication",
				"auth_challenge": "SAC-0001",
			},
			update_modified=True,
		)


class TestMarkRuntimeAuthState(unittest.TestCase):
	def test_ready_sets_success_timestamp(self):
		with mock.patch.object(frappe, "db", create=True) as mock_db:
			auth_service.mark_runtime_auth_state("my-runtime", "ready")

		(args, kwargs) = mock_db.set_value.call_args
		self.assertEqual(args[0], "Subscription Runtime")
		self.assertEqual(args[1], "my-runtime")
		values = args[2]
		self.assertEqual(values["auth_status"], "ready")
		self.assertIn("last_auth_checked_at", values)
		self.assertIn("last_auth_success_at", values)
		self.assertNotIn("last_auth_failure_at", values)
		self.assertTrue(kwargs.get("update_modified"))

	def test_required_sets_failure_timestamp(self):
		with mock.patch.object(frappe, "db", create=True) as mock_db:
			auth_service.mark_runtime_auth_state("my-runtime", "required")

		values = mock_db.set_value.call_args.args[2]
		self.assertEqual(values["auth_status"], "required")
		self.assertIn("last_auth_failure_at", values)
		self.assertNotIn("last_auth_success_at", values)

	def test_failed_sets_failure_timestamp(self):
		with mock.patch.object(frappe, "db", create=True) as mock_db:
			auth_service.mark_runtime_auth_state("my-runtime", "failed")

		values = mock_db.set_value.call_args.args[2]
		self.assertEqual(values["auth_status"], "failed")
		self.assertIn("last_auth_failure_at", values)

	def test_waiting_user_sets_neither_success_nor_failure(self):
		with mock.patch.object(frappe, "db", create=True) as mock_db:
			auth_service.mark_runtime_auth_state("my-runtime", "waiting_user")

		values = mock_db.set_value.call_args.args[2]
		self.assertNotIn("last_auth_success_at", values)
		self.assertNotIn("last_auth_failure_at", values)

	def test_optional_kwargs_are_forwarded(self):
		with mock.patch.object(frappe, "db", create=True) as mock_db:
			auth_service.mark_runtime_auth_state(
				"my-runtime",
				"failed",
				error_code="AUTH_TIMEOUT",
				error_message="Device code expired",
				account_hint="a***@example.com",
			)

		values = mock_db.set_value.call_args.args[2]
		self.assertEqual(values["auth_error_code"], "AUTH_TIMEOUT")
		self.assertEqual(values["auth_error_message"], "Device code expired")
		self.assertEqual(values["auth_account_hint"], "a***@example.com")

	def test_accepts_runtime_doc_with_name_attribute(self):
		runtime_doc = types.SimpleNamespace(name="my-runtime")
		with mock.patch.object(frappe, "db", create=True) as mock_db:
			auth_service.mark_runtime_auth_state(runtime_doc, "ready")

		self.assertEqual(mock_db.set_value.call_args.args[1], "my-runtime")


class TestResolveParkedRunsForRuntime(unittest.TestCase):
	def test_returns_matching_parked_runs(self):
		def fake_get_all(doctype, filters=None, pluck=None, **kwargs):
			if doctype == "Subscription Auth Challenge":
				return ["SAC-1", "SAC-2"]
			if doctype == "Agent Run":
				self.assertEqual(filters["status"], "Waiting Authentication")
				self.assertEqual(filters["auth_challenge"], ["in", ["SAC-1", "SAC-2"]])
				return ["AR-1", "AR-2"]
			raise AssertionError(f"unexpected doctype {doctype}")

		with mock.patch.object(frappe, "get_all", side_effect=fake_get_all):
			result = auth_service.resolve_parked_runs_for_runtime("my-runtime")

		self.assertEqual(result, ["AR-1", "AR-2"])

	def test_returns_empty_list_when_no_challenges_for_runtime(self):
		with mock.patch.object(frappe, "get_all", return_value=[]) as mock_get_all:
			result = auth_service.resolve_parked_runs_for_runtime("my-runtime")

		self.assertEqual(result, [])
		# Only the challenge lookup should run - no Agent Run query needed.
		mock_get_all.assert_called_once()

	def test_does_not_mutate_state(self):
		with mock.patch.object(frappe, "get_all", return_value=[]), \
			mock.patch.object(frappe, "db", create=True) as mock_db:
			auth_service.resolve_parked_runs_for_runtime("my-runtime")
			mock_db.set_value.assert_not_called()


if __name__ == "__main__":
	unittest.main()
