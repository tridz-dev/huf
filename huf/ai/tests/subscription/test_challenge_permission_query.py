# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (no bench / no live Frappe site) unit tests for
`get_permission_query_conditions()` in
`huf/huf/doctype/subscription_auth_challenge/subscription_auth_challenge.py`.

Context (security fix, Track-Item: fix-h6-challenge-permission-leak):
`SubscriptionAuthChallenge.has_permission()` only gates opening a *specific*
document by name - it is never consulted when Frappe builds the SQL for list
views, report views, or `frappe.client.get_list`. Without a
`permission_query_conditions` hook, any Huf User could list every challenge
row - including `user_code` / `verification_url`, which are live, short-lived
credentials - regardless of who created it or which runtime it belongs to.

`get_permission_query_conditions()` must mirror the exact three-way check
already in `has_permission()`:
  - System Manager -> unrestricted (no condition / None)
  - `subscription_runtime.manage` capability -> unrestricted (no condition / None)
  - otherwise -> restricted to rows where `created_by` is the current user,
    OR the row's `runtime` is one whose `Subscription Runtime.owner_user`
    is the current user.

These tests exercise the real, unmodified module-level function against a
stubbed `frappe` (roles, capability check, and `db.escape`), so no live
Frappe site/DB is required. They verify the condition-building LOGIC (which
branch is taken, and that both allowed clauses are present / properly
escaped) rather than executing the resulting SQL against a real table.
"""

import sys
import types
import unittest
from unittest import mock

import frappe

# Match the frappe-less bootstrap used by test_runtime_doctype_tenancy.py:
# `subscription_auth_challenge.py` does `from frappe.model.document import
# Document`, matching every other HUF DocType controller. `huf/ai/tests/conftest.py`
# only stubs a bare `frappe` module for standalone (frappe-less) runs, which
# is enough for `import frappe` but not for `from frappe.model.document
# import Document` (Python's import machinery needs `frappe.model` and
# `frappe.model.document` present in `sys.modules` as real submodules, not
# just attributes of a MagicMock). Register a minimal, real `Document` base
# class for exactly that import, only when the real `frappe` package isn't
# installed - this must never touch a live bench run.
if not hasattr(frappe, "__file__"):
	_frappe_model = sys.modules.setdefault("frappe.model", types.ModuleType("frappe.model"))
	_frappe_model_document = sys.modules.setdefault(
		"frappe.model.document", types.ModuleType("frappe.model.document")
	)
	if not hasattr(_frappe_model_document, "Document"):
		class Document:  # noqa: D401 - minimal stand-in, real class lives in frappe
			pass

		_frappe_model_document.Document = Document

from huf.huf.doctype.subscription_auth_challenge.subscription_auth_challenge import (
	get_permission_query_conditions,
)


def _escape(value):
	# Minimal stand-in for frappe.db.escape: wrap in single quotes, doubling
	# any embedded quote - good enough to prove the value round-trips into
	# the returned condition string without needing a real DB connection.
	return "'" + str(value).replace("'", "''") + "'"


class TestChallengePermissionQueryConditions(unittest.TestCase):
	def setUp(self):
		# frappe.db is a MagicMock by default (from the conftest stub / real
		# frappe); pin `.escape` to our deterministic stand-in either way.
		frappe.db = mock.MagicMock()
		frappe.db.escape.side_effect = _escape

	def test_system_manager_gets_no_condition(self):
		with mock.patch.object(frappe, "get_roles", return_value=["System Manager"]):
			with mock.patch(
				"huf.permissions.has_capability", return_value=False, create=True
			):
				condition = get_permission_query_conditions("alice@example.com")
		self.assertIsNone(condition)

	def test_capability_holder_gets_no_condition(self):
		with mock.patch.object(frappe, "get_roles", return_value=["Huf User"]):
			with mock.patch(
				"huf.permissions.has_capability", return_value=True, create=True
			) as has_capability:
				condition = get_permission_query_conditions("alice@example.com")
		self.assertIsNone(condition)
		has_capability.assert_called_once_with("alice@example.com", "subscription_runtime.manage")

	def test_plain_user_gets_scoped_condition(self):
		with mock.patch.object(frappe, "get_roles", return_value=["Huf User"]):
			with mock.patch(
				"huf.permissions.has_capability", return_value=False, create=True
			):
				condition = get_permission_query_conditions("bob@example.com")

		self.assertIsNotNone(condition)
		# Own-created-by clause.
		self.assertIn("`tabSubscription Auth Challenge`.`created_by` = 'bob@example.com'", condition)
		# Runtime-owner clause (subquery against Subscription Runtime.owner_user).
		self.assertIn("`tabSubscription Runtime`", condition)
		self.assertIn("`owner_user` = 'bob@example.com'", condition)
		self.assertIn("`tabSubscription Auth Challenge`.`runtime` IN", condition)

	def test_defaults_to_session_user_when_user_not_passed(self):
		frappe.session = types.SimpleNamespace(user="carol@example.com")
		with mock.patch.object(frappe, "get_roles", return_value=["Huf User"]):
			with mock.patch(
				"huf.permissions.has_capability", return_value=False, create=True
			):
				condition = get_permission_query_conditions(None)

		self.assertIsNotNone(condition)
		self.assertIn("'carol@example.com'", condition)

	def test_excludes_other_users_challenge(self):
		"""
		The condition returned for `bob` must NOT admit a row belonging to
		`alice` (different creator, different runtime owner) - i.e. the
		condition is a positive allow-list, not a tautology. We can't run
		the SQL here, but we can assert the generated fragment only ever
		references the *requesting* user's identity, never a hardcoded
		wildcard/true clause, and that a different user's escaped literal
		does not appear in it.
		"""
		with mock.patch.object(frappe, "get_roles", return_value=["Huf User"]):
			with mock.patch(
				"huf.permissions.has_capability", return_value=False, create=True
			):
				condition = get_permission_query_conditions("bob@example.com")

		self.assertNotIn("alice@example.com", condition)
		self.assertNotIn(" 1=1", condition)
		self.assertNotIn("OR 1", condition)


if __name__ == "__main__":
	unittest.main()
