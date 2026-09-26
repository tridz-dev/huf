# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (no bench / no live Frappe site) unit tests for T-06-E:
`huf.ai.subscription.auth_service.sweep_expired_auth_challenges` and the
rate-limit guard inside `get_or_create_active_challenge`.

Every Frappe call is mocked/monkeypatched, mirroring the pattern in
`test_auth_service.py`.
"""

import types
import unittest
from datetime import datetime, timedelta
from unittest import mock

import frappe

from huf.ai.subscription import auth_service
from huf.ai.subscription.errors import SubscriptionAuthError, SubscriptionErrorCode


def _fake_challenge_doc(**overrides):
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
	return doc


class TestSweepExpiredAuthChallenges(unittest.TestCase):
	"""
	NOTE: the repo-root `conftest.py` always runs `_stub_bootstrap.py` (needed
	by `test_executor_passthrough.py` et al.) which replaces
	`frappe.utils.now_datetime` with a MagicMock returning a fixed STRING
	("2026-09-26T00:00:00Z"), not a real `datetime`. `check_challenge_expiry`
	imports `now_datetime` by name at module load, so every test here that
	depends on a real expiry comparison patches `auth_service.now_datetime`
	directly rather than relying on `frappe.utils.now_datetime` - this
	pre-existing stub/string mismatch also breaks the unrelated
	`test_auth_service.py::TestCheckChallengeExpiry` tests standalone; it is
	out of scope for T-06-E to fix the shared bootstrap.
	"""

	def test_expired_challenge_marked_expired_and_run_failed_with_timeout(self):
		expired_challenge = _fake_challenge_doc(
			name="SAC-EXPIRED",
			runtime="rt-1",
			status="Waiting User",
			expires_at=datetime.now() - timedelta(minutes=5),
			parked_agent_run="AR-1",
		)

		def fake_get_all(doctype, filters=None, pluck=None, **kwargs):
			if doctype == "Subscription Auth Challenge":
				return ["SAC-EXPIRED"]
			if doctype == "Agent Run":
				self.assertEqual(filters["auth_challenge"], "SAC-EXPIRED")
				return ["AR-1"]
			raise AssertionError(f"unexpected doctype {doctype}")

		set_value_calls = []

		def fake_set_value(doctype, name, value_or_dict, field=None, val=None, **kwargs):
			set_value_calls.append((doctype, name, value_or_dict))

		with mock.patch.object(frappe, "get_all", side_effect=fake_get_all), \
			mock.patch.object(frappe, "get_doc", return_value=expired_challenge), \
			mock.patch.object(auth_service, "now_datetime", return_value=datetime.now()), \
			mock.patch.object(frappe, "db", create=True) as mock_db:
			mock_db.set_value.side_effect = fake_set_value
			mock_db.commit = mock.MagicMock()
			auth_service.sweep_expired_auth_challenges()

		challenge_updates = [c for c in set_value_calls if c[0] == "Subscription Auth Challenge"]
		self.assertEqual(len(challenge_updates), 1)
		self.assertEqual(challenge_updates[0][1], "SAC-EXPIRED")
		self.assertEqual(challenge_updates[0][2], "status")

		run_updates = [c for c in set_value_calls if c[0] == "Agent Run"]
		self.assertEqual(len(run_updates), 1)
		self.assertEqual(run_updates[0][1], "AR-1")
		values = run_updates[0][2]
		self.assertEqual(values["status"], "Failed")
		self.assertEqual(values["error_code"], SubscriptionErrorCode.AUTH_REQUIRED_TIMEOUT.value)

		runtime_updates = [c for c in set_value_calls if c[0] == "Subscription Runtime"]
		self.assertEqual(len(runtime_updates), 1)
		self.assertEqual(runtime_updates[0][1], "rt-1")
		runtime_values = runtime_updates[0][2]
		self.assertEqual(runtime_values["auth_status"], "failed")
		self.assertEqual(runtime_values["auth_error_code"], SubscriptionErrorCode.AUTH_REQUIRED_TIMEOUT.value)

	def test_non_expired_challenge_left_alone(self):
		active_challenge = _fake_challenge_doc(
			name="SAC-ACTIVE",
			runtime="rt-2",
			status="Pending",
			expires_at=datetime.now() + timedelta(minutes=30),
		)

		def fake_get_all(doctype, filters=None, pluck=None, **kwargs):
			if doctype == "Subscription Auth Challenge":
				return ["SAC-ACTIVE"]
			raise AssertionError(f"unexpected doctype {doctype}")

		with mock.patch.object(frappe, "get_all", side_effect=fake_get_all), \
			mock.patch.object(frappe, "get_doc", return_value=active_challenge), \
			mock.patch.object(auth_service, "now_datetime", return_value=datetime.now()), \
			mock.patch.object(frappe, "db", create=True) as mock_db:
			auth_service.sweep_expired_auth_challenges()

		mock_db.set_value.assert_not_called()
		mock_db.commit.assert_not_called()

	def test_no_candidate_challenges_is_a_noop(self):
		with mock.patch.object(frappe, "get_all", return_value=[]), \
			mock.patch.object(frappe, "get_doc") as mock_get_doc, \
			mock.patch.object(frappe, "db", create=True) as mock_db:
			auth_service.sweep_expired_auth_challenges()

		mock_get_doc.assert_not_called()
		mock_db.set_value.assert_not_called()


class TestRateLimiting(unittest.TestCase):
	def test_blocks_new_challenge_after_threshold_recent_failures(self):
		frappe.session = types.SimpleNamespace(user="bob@example.com")

		def fake_get_all(doctype, filters=None, pluck=None, **kwargs):
			if doctype == "Subscription Auth Challenge":
				if filters.get("status") == ["in", list(auth_service.ACTIVE_CHALLENGE_STATUSES)]:
					return []  # no active challenge -> would try to create one
				# rate-limit lookup
				return ["SAC-F1", "SAC-F2", "SAC-F3"]
			raise AssertionError(f"unexpected doctype {doctype}")

		with mock.patch.object(frappe, "get_all", side_effect=fake_get_all), \
			mock.patch.object(frappe.utils, "add_to_date", return_value=datetime.now() - timedelta(hours=1)):
			with self.assertRaises(SubscriptionAuthError) as ctx:
				auth_service.get_or_create_active_challenge("my-runtime")

		self.assertEqual(ctx.exception.code, SubscriptionErrorCode.AUTH_REQUIRED_TIMEOUT)

	def test_allows_new_challenge_when_under_threshold(self):
		frappe.session = types.SimpleNamespace(user="bob@example.com")
		new_doc = _fake_challenge_doc(name="SAC-NEW", status="Pending")
		new_doc.insert = mock.MagicMock()

		def fake_get_all(doctype, filters=None, pluck=None, **kwargs):
			if filters.get("status") == ["in", list(auth_service.ACTIVE_CHALLENGE_STATUSES)]:
				return []
			# under the rate-limit threshold
			return ["SAC-F1"]

		with mock.patch.object(frappe, "get_all", side_effect=fake_get_all), \
			mock.patch.object(frappe.utils, "add_to_date", return_value=datetime.now() - timedelta(hours=1)), \
			mock.patch.object(frappe, "get_doc", return_value=new_doc):
			result = auth_service.get_or_create_active_challenge("my-runtime")

		self.assertEqual(result["name"], "SAC-NEW")
		new_doc.insert.assert_called_once_with(ignore_permissions=True)


if __name__ == "__main__":
	unittest.main()
